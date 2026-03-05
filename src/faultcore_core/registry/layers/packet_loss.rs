use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{ChaosLayer, Next};
use crate::system::shm;

pub struct PacketLossChaosLayer {
    pub ppm: u64,
}

impl ChaosLayer for PacketLossChaosLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::write_packet_loss(tid, self.ppm);
        }

        let result = next.call();

        if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::clear_config(tid);
        }

        result
    }

    fn name(&self) -> &str {
        "PacketLossChaos"
    }
}
