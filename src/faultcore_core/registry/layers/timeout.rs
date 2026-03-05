use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{Next, TransportLayer};
use crate::system::shm;

pub struct TimeoutLayer {
    pub timeout_ms: u64,
}

impl TransportLayer for TimeoutLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::write_timeouts(tid, self.timeout_ms, self.timeout_ms);
        }

        let start = std::time::Instant::now();
        let result = next.call();

        if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::clear_config(tid);
        }

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
