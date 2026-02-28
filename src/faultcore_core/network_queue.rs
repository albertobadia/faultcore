use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::network::context::PacketContext;
use crate::network::layers::LayerResult;
use crate::network::layers::l1_chaos::{ChaosConfig, ChaosLayer};
use crate::network::pipeline::Pipeline;

#[derive(Clone, Debug)]
pub struct NetworkQueueConfig {
    pub rate: f64,
    pub capacity: u64,
    pub max_queue_size: u64,
    pub latency_min_ms: u64,
    pub latency_max_ms: u64,
    pub packet_loss_rate: f64,
    pub strategy: QueueStrategy,
}

#[derive(Clone, Debug, PartialEq)]
pub enum QueueStrategy {
    Reject,
    Wait,
}

impl NetworkQueueConfig {
    pub fn new(
        rate: f64,
        capacity: u64,
        max_queue_size: u64,
        latency_min_ms: u64,
        latency_max_ms: u64,
        packet_loss_rate: f64,
        strategy: QueueStrategy,
    ) -> Option<Self> {
        if rate <= 0.0 || capacity == 0 || max_queue_size == 0 {
            return None;
        }
        if latency_min_ms > latency_max_ms {
            return None;
        }
        if !(0.0..=1.0).contains(&packet_loss_rate) {
            return None;
        }
        Some(Self {
            rate,
            capacity,
            max_queue_size,
            latency_min_ms,
            latency_max_ms,
            packet_loss_rate,
            strategy,
        })
    }
}

#[derive(Clone)]
pub struct NetworkQueueCore {
    pub config: NetworkQueueConfig,
    tokens: Arc<Mutex<(f64, Instant)>>,
    queue: Arc<Mutex<Vec<QueueEntry>>>,
    stats: Arc<Mutex<QueueStats>>,
    fd_count: Arc<Mutex<u64>>,
    fd_limit: u64,
}

#[derive(Clone, Debug)]
#[allow(dead_code)]
struct QueueEntry {
    enqueued_at: Instant,
    data: Option<Vec<u8>>,
}

#[derive(Clone, Debug, Default)]
pub struct QueueStats {
    pub enqueued: u64,
    pub dequeued: u64,
    pub rejected: u64,
    pub dropped: u64,
    pub current_queue_size: u64,
}

impl NetworkQueueCore {
    pub fn new(config: NetworkQueueConfig, fd_limit: u64) -> Option<Self> {
        Some(Self {
            tokens: Arc::new(Mutex::new((config.capacity as f64, Instant::now()))),
            queue: Arc::new(Mutex::new(Vec::new())),
            stats: Arc::new(Mutex::new(QueueStats::default())),
            fd_count: Arc::new(Mutex::new(0)),
            fd_limit,
            config,
        })
    }

    fn refill_tokens(tokens: &mut (f64, Instant), rate: f64, capacity: f64) {
        let elapsed = tokens.1.elapsed().as_secs_f64();
        let new_tokens = elapsed * rate;
        tokens.0 = (tokens.0 + new_tokens).min(capacity);
        tokens.1 = Instant::now();
    }

    pub fn try_acquire(&self) -> bool {
        let mut tokens = self.tokens.lock().unwrap();
        Self::refill_tokens(&mut tokens, self.config.rate, self.config.capacity as f64);

        if tokens.0 >= 1.0 {
            tokens.0 -= 1.0;
            true
        } else {
            false
        }
    }

    pub fn enqueue(&self) -> Result<NetworkTicket, QueueError> {
        let mut queue = self.queue.lock().unwrap();
        let mut stats = self.stats.lock().unwrap();

        if queue.len() as u64 >= self.config.max_queue_size {
            stats.rejected += 1;
            return Err(QueueError::QueueFull);
        }

        let mut fd_count = self.fd_count.lock().unwrap();
        if *fd_count >= self.fd_limit {
            stats.dropped += 1;
            return Err(QueueError::FdLimitExceeded);
        }

        // Build dynamically the pipeline for this context
        let mut pipeline = Pipeline::new();

        // Add Chaos Layer (L1)
        // (L2 QoS Token Bucket is currently handled before enqueue via try_acquire)
        let chaos_config = ChaosConfig {
            packet_loss_rate: self.config.packet_loss_rate,
            latency_min_ms: self.config.latency_min_ms,
            latency_max_ms: self.config.latency_max_ms,
        };
        pipeline.add_layer(Arc::new(ChaosLayer::new(chaos_config)));

        // Process Packet Context
        let mut pkt_ctx = PacketContext::new(vec![]);

        match pipeline.process(&mut pkt_ctx) {
            LayerResult::Drop => {
                stats.dropped += 1;
                return Err(QueueError::PacketDropped);
            }
            LayerResult::Error(_) => {
                stats.dropped += 1;
                return Err(QueueError::PacketDropped);
            }
            LayerResult::Continue => {}
        }

        *fd_count += 1;
        let enqueued_at = Instant::now();

        queue.push(QueueEntry {
            enqueued_at,
            data: None,
        });

        stats.enqueued += 1;
        stats.current_queue_size = queue.len() as u64;

        Ok(NetworkTicket {
            queue: self.queue.clone(),
            fd_count: self.fd_count.clone(),
            stats: self.stats.clone(),
            enqueued_at,
            latency_ms: pkt_ctx.accumulated_delay_ms,
            strategy: self.config.strategy.clone(),
        })
    }

    pub fn stats(&self) -> QueueStats {
        self.stats.lock().unwrap().clone()
    }

    pub fn available_tokens(&self) -> f64 {
        let mut tokens = self.tokens.lock().unwrap();
        Self::refill_tokens(&mut tokens, self.config.rate, self.config.capacity as f64);
        tokens.0
    }

    pub fn queue_size(&self) -> u64 {
        self.queue.lock().unwrap().len() as u64
    }

    pub fn rate(&self) -> f64 {
        self.config.rate
    }

    pub fn capacity(&self) -> u64 {
        self.config.capacity
    }

    pub fn max_queue_size(&self) -> u64 {
        self.config.max_queue_size
    }

    pub fn strategy(&self) -> &QueueStrategy {
        &self.config.strategy
    }
}

#[allow(dead_code)]
pub struct NetworkTicket {
    queue: Arc<Mutex<Vec<QueueEntry>>>,
    fd_count: Arc<Mutex<u64>>,
    stats: Arc<Mutex<QueueStats>>,
    enqueued_at: Instant,
    latency_ms: u64,
    strategy: QueueStrategy,
}

impl NetworkTicket {
    pub fn wait_and_release(self) {
        let elapsed = self.enqueued_at.elapsed();
        if elapsed < Duration::from_millis(self.latency_ms) {
            std::thread::sleep(Duration::from_millis(self.latency_ms) - elapsed);
        }

        let queue_size = {
            let mut queue = self.queue.lock().unwrap();
            if !queue.is_empty() {
                queue.remove(0);
            }
            queue.len() as u64
        };

        {
            let mut fd_count = self.fd_count.lock().unwrap();
            if *fd_count > 0 {
                *fd_count -= 1;
            }
        }

        let mut stats = self.stats.lock().unwrap();
        stats.dequeued += 1;
        stats.current_queue_size = queue_size;
    }
}

#[derive(Clone, Debug)]
pub enum QueueError {
    QueueFull,
    FdLimitExceeded,
    PacketDropped,
    Timeout,
}

impl std::fmt::Display for QueueError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            QueueError::QueueFull => write!(f, "Network queue is full"),
            QueueError::FdLimitExceeded => write!(f, "File descriptor limit exceeded"),
            QueueError::PacketDropped => write!(f, "Packet dropped due to network simulation"),
            QueueError::Timeout => write!(f, "Queue operation timed out"),
        }
    }
}

impl std::error::Error for QueueError {}

#[allow(dead_code)]
pub type NetworkQueueMap = HashMap<String, Arc<Mutex<Option<NetworkQueueCore>>>>;
