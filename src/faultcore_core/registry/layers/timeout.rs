use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{Next, TransportLayer};
use crate::system::shm;

pub struct TimeoutLayer {
    pub timeout_ms: u64,
}

impl TransportLayer for TimeoutLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        let tid = if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::write_timeouts(tid, self.timeout_ms, self.timeout_ms);
            Some(tid)
        } else {
            None
        };

        let result = next.call();

        if let Some(tid) = tid {
            let _ = shm::clear_config(tid);
        }

        result
    }

    fn name(&self) -> &str {
        "TimeoutTransport"
    }
}
