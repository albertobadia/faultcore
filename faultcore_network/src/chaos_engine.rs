use crate::{
    Config, Layer, LayerResult,
    layers::{DnsAction, L1Chaos, L2QoS, L3Routing, L4Transport, L5Session, L6Presentation, L7Resolver},
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StreamDirection {
    Send,
    Recv,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StreamAction {
    Continue,
    Drop,
    Delay(u64),
    Timeout(u64),
    Error(String),
    ConnectionErrorKind(u64),
    StageReorder,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConnectAction {
    Continue,
    Drop,
    Delay(u64),
    Timeout(u64),
    Error(String),
    ConnectionErrorKind(u64),
}

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
            l4: L4Transport::new(0, 0),
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

    pub fn process_send(&self, config: &Config, bytes: u64) -> LayerResult {
        let effective = config.effective_for_send();
        let l4_result = self.l4.timeout_for_stream(&effective, false);
        self.process_pipeline(&effective, bytes, l4_result)
    }

    pub fn process_recv(&self, config: &Config, bytes: u64) -> LayerResult {
        let effective = config.effective_for_recv();
        let l4_result = self.l4.timeout_for_stream(&effective, true);
        self.process_pipeline(&effective, bytes, l4_result)
    }

    fn process_pipeline(&self, effective: &Config, bytes: u64, l4_result: LayerResult) -> LayerResult {
        let mut delay_ns: u64 = 0;
        for layer_result in [
            self.l1.process(effective),
            self.l2.process_with_bytes(bytes, effective),
            self.l3.process(effective),
            l4_result,
            self.l5.process(effective),
            self.l6.process(effective),
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

    pub fn process_connect(&self, fd: i32, config: &Config) -> ConnectAction {
        let effective = config.effective_for_send();
        if let Some(kind) = self.l4.connection_error_kind(fd, &effective, true) {
            return ConnectAction::ConnectionErrorKind(kind);
        }
        let l4_result = self.l4.timeout_for_connect(&effective);
        match self.process_pipeline(&effective, 0, l4_result) {
            LayerResult::Continue => ConnectAction::Continue,
            LayerResult::Drop => ConnectAction::Drop,
            LayerResult::Delay(ns) => ConnectAction::Delay(ns),
            LayerResult::Timeout(ms) => ConnectAction::Timeout(ms),
            LayerResult::Error(err) => ConnectAction::Error(err),
        }
    }

    pub fn process_stream_pre(
        &self,
        fd: i32,
        config: &Config,
        bytes: u64,
        direction: StreamDirection,
    ) -> StreamAction {
        let effective = match direction {
            StreamDirection::Send => config.effective_for_send(),
            StreamDirection::Recv => config.effective_for_recv(),
        };
        if let Some(kind) = self.l4.connection_error_kind(fd, &effective, false) {
            return StreamAction::ConnectionErrorKind(kind);
        }
        let l4_result = self
            .l4
            .timeout_for_stream(&effective, matches!(direction, StreamDirection::Recv));
        match self.process_pipeline(&effective, bytes, l4_result) {
            LayerResult::Continue => {
                if matches!(direction, StreamDirection::Send) && self.l1.should_reorder(&effective) {
                    StreamAction::StageReorder
                } else {
                    StreamAction::Continue
                }
            }
            LayerResult::Drop => StreamAction::Drop,
            LayerResult::Delay(ns) => StreamAction::Delay(ns),
            LayerResult::Timeout(ms) => StreamAction::Timeout(ms),
            LayerResult::Error(err) => StreamAction::Error(err),
        }
    }

    pub fn duplicate_extra_count(&self, config: &Config, direction: StreamDirection) -> u64 {
        let effective = match direction {
            StreamDirection::Send => config.effective_for_send(),
            StreamDirection::Recv => config.effective_for_recv(),
        };
        self.l1.duplicate_extra(&effective)
    }

    pub fn record_stream_bytes(&self, fd: i32, bytes: u64) {
        self.l4.record_stream_bytes(fd, bytes);
    }

    pub fn clear_fd_state(&self, fd: i32) {
        self.l4.clear_fd_state(fd);
    }

    pub fn process_dns_lookup(&self, config: &Config) -> DnsAction {
        self.l7.process_dns(config)
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
