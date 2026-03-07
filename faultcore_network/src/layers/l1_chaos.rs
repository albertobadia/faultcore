use crate::{Config, Layer, LayerResult};
use rand::random;

pub struct L1Chaos;

impl L1Chaos {
    pub fn new() -> Self {
        Self
    }

    pub fn with_latency(_latency_ms: u64) -> Self {
        Self
    }

    fn should_drop(&self, packet_loss_ppm: u64) -> bool {
        if packet_loss_ppm == 0 {
            return false;
        }
        let drop_threshold = 1_000_000.0 / packet_loss_ppm as f64;
        let random: u32 = random();
        (random as f64) % drop_threshold < 1.0
    }
}

impl Default for L1Chaos {
    fn default() -> Self {
        Self
    }
}

impl Layer for L1Chaos {
    fn process(&self, config: &Config) -> LayerResult {
        if self.should_drop(config.packet_loss_ppm) {
            return LayerResult::Drop;
        }

        if config.latency_ns > 0 {
            return LayerResult::Delay(config.latency_ns);
        }

        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L1_Chaos"
    }
}
