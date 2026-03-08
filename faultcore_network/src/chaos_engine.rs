use crate::{
    Config, Layer, LayerResult,
    layers::{L1Chaos, L2QoS, L3Routing},
};

pub struct ChaosEngine {
    l1: L1Chaos,
    l2: L2QoS,
    l3: L3Routing,
}

impl ChaosEngine {
    pub fn new() -> Self {
        Self {
            l1: L1Chaos::new(),
            l2: L2QoS::with_rate(0),
            l3: L3Routing::new(),
        }
    }

    pub fn process_send(&self, config: &Config, bytes: u64) -> LayerResult {
        let mut delay_ns: u64 = 0;
        for layer_result in [
            self.l1.process(config),
            self.l2.process_with_bytes(bytes, config),
            self.l3.process(config),
        ] {
            match layer_result {
                LayerResult::Continue => {}
                LayerResult::Delay(ns) => delay_ns = delay_ns.saturating_add(ns),
                LayerResult::Drop => return LayerResult::Drop,
                LayerResult::Timeout(ms) => return LayerResult::Timeout(ms),
                LayerResult::Error(err) => return LayerResult::Error(err),
            }
        }
        if delay_ns > 0 {
            LayerResult::Delay(delay_ns)
        } else {
            LayerResult::Continue
        }
    }

    pub fn process_recv(&self, config: &Config, bytes: u64) -> LayerResult {
        let mut delay_ns: u64 = 0;
        for layer_result in [
            self.l1.process(config),
            self.l2.process_with_bytes(bytes, config),
            self.l3.process(config),
        ] {
            match layer_result {
                LayerResult::Continue => {}
                LayerResult::Delay(ns) => delay_ns = delay_ns.saturating_add(ns),
                LayerResult::Drop => return LayerResult::Drop,
                LayerResult::Timeout(ms) => return LayerResult::Timeout(ms),
                LayerResult::Error(err) => return LayerResult::Error(err),
            }
        }
        if delay_ns > 0 {
            LayerResult::Delay(delay_ns)
        } else {
            LayerResult::Continue
        }
    }
}

impl Default for ChaosEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn combines_l1_latency_and_l3_jitter_delay() {
        let engine = ChaosEngine::new();
        let cfg = Config {
            latency_ns: 1_000,
            jitter_ns: 2_000,
            ..Default::default()
        };

        match engine.process_recv(&cfg, 0) {
            LayerResult::Delay(ns) => {
                assert!(ns >= 1_000);
                assert!(ns <= 3_000);
            }
            other => panic!("expected Delay, got {other:?}"),
        }
    }

    #[test]
    fn drop_short_circuits_other_layers() {
        let engine = ChaosEngine::new();
        let cfg = Config {
            packet_loss_ppm: 1_000_000,
            jitter_ns: 5_000,
            ..Default::default()
        };

        assert!(matches!(engine.process_recv(&cfg, 0), LayerResult::Drop));
    }

    #[test]
    fn recv_applies_bandwidth_qos_delay() {
        let engine = ChaosEngine::new();
        let cfg = Config {
            bandwidth_bps: 8,
            ..Default::default()
        };

        match engine.process_recv(&cfg, 1) {
            LayerResult::Delay(ns) => {
                assert!(ns >= 900_000_000, "ns={ns}");
                assert!(ns <= 1_100_000_000, "ns={ns}");
            }
            other => panic!("expected Delay, got {other:?}"),
        }
    }
}
