use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{Next, TransportLayer};
use crate::system::shm;

pub struct TimeoutLayer {
    pub timeout_ms: u64,
}

struct ShmGuard {
    tid: Option<u64>,
}

impl Drop for ShmGuard {
    fn drop(&mut self) {
        if let Some(tid) = self.tid {
            let _ = shm::clear_config(tid);
        }
    }
}

impl TransportLayer for TimeoutLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        let guard = if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::write_timeouts(tid, self.timeout_ms, self.timeout_ms);
            ShmGuard { tid: Some(tid) }
        } else {
            ShmGuard { tid: None }
        };

        let result = next.call();
        drop(guard);
        result
    }

    fn name(&self) -> &str {
        "TimeoutTransport"
    }
}
