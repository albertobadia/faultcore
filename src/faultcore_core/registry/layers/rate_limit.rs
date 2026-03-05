use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{Next, QosLayer};
use std::sync::{Arc, Mutex};
use std::time::Instant;

pub struct RateLimitQosLayer {
    pub rate: f64,
    pub capacity: f64,
    pub tokens: Arc<Mutex<(f64, Instant)>>,
}

impl QosLayer for RateLimitQosLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        let mut tokens = self.tokens.lock().unwrap();
        let elapsed = tokens.1.elapsed().as_secs_f64();
        let new_tokens = elapsed * self.rate;
        tokens.0 = (tokens.0 + new_tokens).min(self.capacity);
        tokens.1 = Instant::now();

        if tokens.0 >= 1.0 {
            tokens.0 -= 1.0;
            drop(tokens);
            next()
        } else {
            PolicyResult::Drop {
                reason: "Rate limit exceeded",
            }
        }
    }

    fn name(&self) -> &str {
        "RateLimitQos"
    }
}
