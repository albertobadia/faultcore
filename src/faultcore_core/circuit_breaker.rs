use std::time::{Duration, Instant};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CircuitState {
    Closed,
    Open,
    HalfOpen,
}

#[derive(Clone)]
pub struct CircuitBreakerPolicy {
    pub failure_threshold: u32,
    pub success_threshold: u32,
    pub timeout: Duration,
    pub state: CircuitState,
    pub failure_count: u32,
    success_count: u32,
    last_failure_time: Option<Instant>,
}

impl CircuitBreakerPolicy {
    pub fn new(failure_threshold: u32, success_threshold: u32, timeout_ms: u64) -> Self {
        Self {
            failure_threshold,
            success_threshold,
            timeout: Duration::from_millis(timeout_ms),
            state: CircuitState::Closed,
            failure_count: 0,
            success_count: 0,
            last_failure_time: None,
        }
    }

    pub fn is_open(&self) -> bool {
        self.state == CircuitState::Open
    }

    pub fn can_attempt(&mut self) -> bool {
        match self.state {
            CircuitState::Closed => true,
            CircuitState::Open => {
                if let Some(last_time) = self.last_failure_time {
                    if last_time.elapsed() > self.timeout {
                        self.state = CircuitState::HalfOpen;
                        self.failure_count = 0;
                        self.success_count = 0;
                        true
                    } else {
                        false
                    }
                } else {
                    false
                }
            }
            CircuitState::HalfOpen => true,
        }
    }

    pub fn record_success(&mut self) {
        self.success_count += 1;
        if self.state == CircuitState::HalfOpen && self.success_count >= self.success_threshold {
            self.state = CircuitState::Closed;
            self.failure_count = 0;
            self.success_count = 0;
        }
    }

    pub fn record_failure(&mut self) {
        self.failure_count += 1;
        self.last_failure_time = Some(Instant::now());

        match self.state {
            CircuitState::HalfOpen => {
                self.state = CircuitState::Open;
            }
            _ => {
                if self.failure_count >= self.failure_threshold {
                    self.state = CircuitState::Open;
                }
            }
        }
    }

    pub fn state(&self) -> &CircuitState {
        &self.state
    }
}
