use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

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

        if self.should_drop_packet() {
            stats.dropped += 1;
            return Err(QueueError::PacketDropped);
        }

        *fd_count += 1;
        let enqueued_at = Instant::now();
        let latency = self.calculate_latency();

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
            latency_ms: latency,
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

    fn should_drop_packet(&self) -> bool {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .subsec_nanos();
        let random: f64 = (nanos as f64) / (u32::MAX as f64);
        random < self.config.packet_loss_rate
    }

    fn calculate_latency(&self) -> u64 {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .subsec_nanos();
        let range = self.config.latency_max_ms - self.config.latency_min_ms;
        if range == 0 {
            return self.config.latency_min_ms;
        }
        self.config.latency_min_ms + ((nanos as u64) % range)
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
