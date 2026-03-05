use crate::circuit_breaker::CircuitBreakerPolicy as CircuitBreakerCore;
use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{Next, TransportLayer};
use std::sync::{Arc, RwLock};

pub struct CircuitBreakerLayer {
    pub core: Arc<RwLock<CircuitBreakerCore>>,
}

impl TransportLayer for CircuitBreakerLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        {
            let mut guard = self.core.write().unwrap();
            if guard.is_open() && !guard.can_attempt() {
                return PolicyResult::Error {
                    message: "Circuit breaker is OPEN".to_string(),
                    exception: None,
                };
            }
        }

        let result = next();

        {
            let mut guard = self.core.write().unwrap();
            if result.is_ok() {
                guard.record_success();
            } else {
                guard.record_failure();
            }
        }
        result
    }

    fn name(&self) -> &str {
        "CircuitBreakerTransport"
    }
}
