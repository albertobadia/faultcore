use crate::{
    Config, Layer, LayerResult,
    layers::{L1Chaos, L2QoS},
};

pub struct ChaosEngine {
    l1: L1Chaos,
    l2: L2QoS,
}

impl ChaosEngine {
    pub fn new() -> Self {
        Self {
            l1: L1Chaos::new(),
            l2: L2QoS::with_rate(0),
        }
    }

    pub fn process_send(&self, config: &Config, bytes: u64) -> LayerResult {
        match self.l1.process(config) {
            LayerResult::Continue => self.l2.process_with_bytes(bytes, config),
            res => res,
        }
    }

    pub fn process_recv(&self, config: &Config, _bytes: u64) -> LayerResult {
        self.l1.process(config)
    }
}

impl Default for ChaosEngine {
    fn default() -> Self {
        Self::new()
    }
}
