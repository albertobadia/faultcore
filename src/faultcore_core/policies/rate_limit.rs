use std::time::Instant;

#[derive(Clone, Debug)]
pub struct RateLimitPolicy {
    pub rate: f64,
    pub capacity: f64,
    tokens: f64,
    last_refill: Instant,
}

impl RateLimitPolicy {
    pub fn new(rate: f64, capacity: u64) -> Option<Self> {
        if rate <= 0.0 || capacity == 0 {
            return None;
        }
        let capacity = capacity as f64;
        Some(Self {
            rate,
            capacity,
            tokens: capacity,
            last_refill: Instant::now(),
        })
    }

    pub fn try_acquire(&mut self) -> bool {
        self.refill_tokens();
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }

    fn refill_tokens(&mut self) {
        let elapsed = self.last_refill.elapsed().as_secs_f64();
        let new_tokens = elapsed * self.rate;
        self.tokens = (self.tokens + new_tokens).min(self.capacity);
        self.last_refill = Instant::now();
    }

    pub fn available_tokens(&self) -> f64 {
        self.tokens
    }

    pub fn rate(&self) -> f64 {
        self.rate
    }

    pub fn capacity(&self) -> u64 {
        self.capacity as u64
    }
}
