use super::{Layer, LayerResult};
use crate::network::context::PacketContext;

/// Configuration for the Chaos layer.
#[derive(Clone, Debug)]
pub struct ChaosConfig {
    pub packet_loss_rate: f64,
    pub latency_min_ms: u64,
    pub latency_max_ms: u64,
}

/// L1 Layer simulating latency, jitter, and packet loss.
pub struct ChaosLayer {
    config: ChaosConfig,
}

impl ChaosLayer {
    pub fn new(config: ChaosConfig) -> Self {
        Self { config }
    }

    fn calculate_latency(&self) -> u64 {
        let range = self
            .config
            .latency_max_ms
            .saturating_sub(self.config.latency_min_ms);
        if range == 0 {
            return self.config.latency_min_ms;
        }
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .subsec_nanos();
        self.config.latency_min_ms + ((nanos as u64) % range)
    }

    fn should_drop_packet(&self) -> bool {
        if self.config.packet_loss_rate <= 0.0 {
            return false;
        }
        use rand::RngExt;
        let mut rng = rand::rng();
        let random: f64 = rng.random();
        random < self.config.packet_loss_rate
    }
}

impl Layer for ChaosLayer {
    fn process(&self, ctx: &mut PacketContext) -> LayerResult {
        if self.should_drop_packet() {
            return LayerResult::Drop;
        }

        ctx.accumulated_delay_ms += self.calculate_latency();
        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L1_Chaos"
    }
}
