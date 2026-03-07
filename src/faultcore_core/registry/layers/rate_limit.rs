use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{Next, QosLayer};
use crate::system::shm;

pub struct RateLimitQosLayer {
    pub rate_bps: u64,
}

impl RateLimitQosLayer {
    pub fn new(rate_bps: u64) -> Self {
        Self { rate_bps }
    }
}

impl QosLayer for RateLimitQosLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        let tid = if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::write_bandwidth(tid, self.rate_bps);
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
        "RateLimitQos"
    }
}
