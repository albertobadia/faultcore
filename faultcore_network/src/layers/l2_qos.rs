use crate::{Config, Layer, LayerResult};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

use parking_lot::Mutex;

pub struct L2QoS {
    rate_bps: u64,
    capacity_tokens: f64,
    tokens: AtomicU64,
    last_refill: Mutex<Instant>,
}

impl L2QoS {
    pub fn new(rate_bps: u64, capacity_tokens: f64) -> Self {
        Self {
            rate_bps,
            capacity_tokens,
            tokens: AtomicU64::new(capacity_tokens as u64),
            last_refill: Mutex::new(Instant::now()),
        }
    }

    pub fn with_rate(rate_bps: u64) -> Self {
        Self::new(rate_bps, rate_bps as f64 * 2.0)
    }

    fn refill(&self) {
        let mut last = self.last_refill.lock();
        let elapsed = last.elapsed().as_secs_f64();
        if elapsed <= 0.0 {
            return;
        }

        let new_tokens = elapsed * self.rate_bps as f64;
        *last = Instant::now();

        let current = self.tokens.load(Ordering::Acquire);
        let new_value = (current as f64 + new_tokens).min(self.capacity_tokens) as u64;
        self.tokens.store(new_value, Ordering::Release);
    }

    fn try_acquire(&self, tokens_needed: u64) -> bool {
        self.refill();

        loop {
            let current = self.tokens.load(Ordering::Acquire);
            if current >= tokens_needed {
                let new_value = current - tokens_needed;
                if self
                    .tokens
                    .compare_exchange_weak(current, new_value, Ordering::Release, Ordering::Acquire)
                    .is_ok()
                {
                    return true;
                }
            } else {
                return false;
            }
        }
    }
    pub fn process_with_bytes(&self, bytes: u64, config: &Config) -> LayerResult {
        let rate = if config.bandwidth_bps > 0 {
            config.bandwidth_bps
        } else {
            self.rate_bps
        };

        if rate == 0 {
            return LayerResult::Continue;
        }

        // We use bits for calculation if we want precision, or just bytes.
        // Interceptor used bytes * 8.0.
        let bytes_needed = bytes;
        if self.try_acquire(bytes_needed) {
            LayerResult::Continue
        } else {
            // Calculate delay based on deficit
            let current = self.tokens.load(Ordering::Acquire);
            let deficit = bytes_needed.saturating_sub(current);
            let delay_secs = deficit as f64 / rate as f64;
            let delay_ns = (delay_secs * 1_000_000_000.0) as u64;

            if delay_ns > 0 {
                LayerResult::Delay(delay_ns)
            } else {
                LayerResult::Continue
            }
        }
    }
}

impl Layer for L2QoS {
    fn process(&self, config: &Config) -> LayerResult {
        self.process_with_bytes(0, config)
    }

    fn name(&self) -> &str {
        "L2_QoS"
    }
}
