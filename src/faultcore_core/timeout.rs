use std::time::{Duration, Instant};

#[derive(Clone)]
pub struct TimeoutPolicy {
    pub timeout: Duration,
}

impl TimeoutPolicy {
    pub fn new(timeout_ms: u64) -> Option<Self> {
        if timeout_ms == 0 {
            return None;
        }
        Some(Self {
            timeout: Duration::from_millis(timeout_ms),
        })
    }

    pub fn is_expired(&self, start: Instant) -> bool {
        start.elapsed() > self.timeout
    }

    pub fn timeout_ms(&self) -> u64 {
        self.timeout.as_millis() as u64
    }
}
