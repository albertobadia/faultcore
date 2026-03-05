use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{Next, TransportLayer};

pub struct TimeoutLayer {
    pub timeout_ms: u64,
}

impl TransportLayer for TimeoutLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        let start = std::time::Instant::now();
        let result = next.call();

        if start.elapsed().as_millis() > self.timeout_ms as u128 {
            return PolicyResult::Error {
                message: "Timeout exceeded".to_string(),
                exception: None,
            };
        }
        result
    }

    fn name(&self) -> &str {
        "TimeoutTransport"
    }
}
