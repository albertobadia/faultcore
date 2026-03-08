use crate::{
    Config, Layer,
    layers::{
        Direction, L1Chaos, L2QoS, L3Routing, L4Transport, L5Session, L6Presentation, L7Resolver,
        LayerDecision, Operation, PacketContext,
    },
};

pub struct ChaosEngineBuilder;

impl ChaosEngineBuilder {
    pub fn new() -> Self {
        Self
    }

    pub fn build(self) -> ChaosEngine {
        ChaosEngine::new()
    }
}

impl Default for ChaosEngineBuilder {
    fn default() -> Self {
        Self::new()
    }
}

pub struct ChaosEngine {
    l1: L1Chaos,
    l2: L2QoS,
    l3: L3Routing,
    l4: L4Transport,
    l5: L5Session,
    l6: L6Presentation,
    l7: L7Resolver,
}

impl ChaosEngine {
    pub fn new() -> Self {
        Self {
            l1: L1Chaos::new(),
            l2: L2QoS::with_rate(0),
            l3: L3Routing::new(),
            l4: L4Transport::new(),
            l5: L5Session::new(),
            l6: L6Presentation::new(),
            l7: L7Resolver::new(),
        }
    }

    pub fn builder() -> ChaosEngineBuilder {
        ChaosEngineBuilder::new()
    }

    pub fn from_env() -> Self {
        Self::builder().build()
    }

    fn process_pipeline(&self, ctx: &PacketContext<'_>) -> LayerDecision {
        let mut delay_ns: u64 = 0;
        let stages: [&dyn Layer; 7] = [
            &self.l1, &self.l2, &self.l3, &self.l4, &self.l5, &self.l6, &self.l7,
        ];

        for layer in stages {
            if !layer.applies_to(ctx) {
                continue;
            }

            let decision = layer.process(ctx);
            match decision {
                LayerDecision::Continue => {}
                LayerDecision::DelayNs(ns) => delay_ns = delay_ns.saturating_add(ns),
                LayerDecision::Drop
                | LayerDecision::TimeoutMs(_)
                | LayerDecision::Error(_)
                | LayerDecision::ConnectionErrorKind(_)
                | LayerDecision::NxDomain => return decision,
                LayerDecision::StageReorder | LayerDecision::Duplicate(_) => {
                    return LayerDecision::Error(format!(
                        "{} returned a post-routing decision in main pipeline",
                        layer.name()
                    ));
                }
            }
        }

        if delay_ns > 0 {
            LayerDecision::DelayNs(delay_ns)
        } else {
            LayerDecision::Continue
        }
    }

    pub fn evaluate_connect(&self, fd: i32, config: &Config) -> LayerDecision {
        let effective = config.effective_for_send();
        let ctx = PacketContext {
            fd,
            bytes: 0,
            operation: Operation::Connect,
            direction: Some(Direction::Uplink),
            config: &effective,
        };
        self.process_pipeline(&ctx)
    }

    pub fn evaluate_stream_pre(
        &self,
        fd: i32,
        config: &Config,
        bytes: u64,
        direction: Direction,
    ) -> LayerDecision {
        let effective = match direction {
            Direction::Uplink => config.effective_for_send(),
            Direction::Downlink => config.effective_for_recv(),
        };
        let operation = match direction {
            Direction::Uplink => Operation::Send,
            Direction::Downlink => Operation::Recv,
        };
        let ctx = PacketContext {
            fd,
            bytes,
            operation,
            direction: Some(direction),
            config: &effective,
        };

        let decision = self.process_pipeline(&ctx);
        if !matches!(decision, LayerDecision::Continue) {
            return decision;
        }

        if matches!(direction, Direction::Uplink) {
            self.l1.reorder_decision(&effective)
        } else {
            LayerDecision::Continue
        }
    }

    pub fn evaluate_stream_post(&self, config: &Config, direction: Direction) -> LayerDecision {
        let effective = match direction {
            Direction::Uplink => config.effective_for_send(),
            Direction::Downlink => config.effective_for_recv(),
        };
        if matches!(direction, Direction::Uplink) {
            self.l1.duplicate_decision(&effective)
        } else {
            LayerDecision::Continue
        }
    }

    pub fn evaluate_dns_lookup(&self, config: &Config) -> LayerDecision {
        let ctx = PacketContext {
            fd: -1,
            bytes: 0,
            operation: Operation::DnsLookup,
            direction: None,
            config,
        };
        self.process_pipeline(&ctx)
    }

    pub fn record_stream_bytes(&self, fd: i32, bytes: u64) {
        self.l4.record_stream_bytes(fd, bytes);
    }

    pub fn clear_fd_state(&self, fd: i32) {
        self.l4.clear_fd_state(fd);
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

        match engine.evaluate_stream_pre(1, &cfg, 0, Direction::Downlink) {
            LayerDecision::DelayNs(ns) => {
                assert!(ns >= 1_000);
                assert!(ns <= 3_000);
            }
            other => panic!("expected DelayNs, got {other:?}"),
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

        assert!(matches!(
            engine.evaluate_stream_pre(1, &cfg, 0, Direction::Downlink),
            LayerDecision::Drop
        ));
    }

    #[test]
    fn recv_applies_bandwidth_qos_delay() {
        let engine = ChaosEngine::new();
        let cfg = Config {
            bandwidth_bps: 8,
            ..Default::default()
        };

        match engine.evaluate_stream_pre(1, &cfg, 1, Direction::Downlink) {
            LayerDecision::DelayNs(ns) => {
                assert!(ns >= 900_000_000, "ns={ns}");
                assert!(ns <= 1_100_000_000, "ns={ns}");
            }
            other => panic!("expected DelayNs, got {other:?}"),
        }
    }
}
