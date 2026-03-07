use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{ChaosLayer, Next};
use crate::system::shm;

pub struct LatencyChaosLayer {
    pub latency_ms: u64,
}

impl ChaosLayer for LatencyChaosLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        let tid = if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::write_latency(tid, self.latency_ms);
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
        "LatencyChaos"
    }
}
