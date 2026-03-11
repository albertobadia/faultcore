use crate::{
    Config, Layer, record_fault_observability_decision,
    layers::{
        Direction, L1Chaos, L2QoS, L3Routing, L4Transport, L5Session, L6Presentation, L7Resolver,
        LayerDecision, LayerStage, Operation, PacketContext,
    },
};
use std::sync::atomic::{AtomicU64, Ordering};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct DecisionCounters {
    pub continue_count: u64,
    pub delay_count: u64,
    pub drop_count: u64,
    pub timeout_count: u64,
    pub error_count: u64,
    pub connection_error_count: u64,
    pub reorder_count: u64,
    pub duplicate_count: u64,
    pub nxdomain_count: u64,
    pub skipped_count: u64,
}

struct LayerMetrics {
    continue_count: AtomicU64,
    delay_count: AtomicU64,
    drop_count: AtomicU64,
    timeout_count: AtomicU64,
    error_count: AtomicU64,
    connection_error_count: AtomicU64,
    reorder_count: AtomicU64,
    duplicate_count: AtomicU64,
    nxdomain_count: AtomicU64,
    skipped_count: AtomicU64,
}

impl LayerMetrics {
    fn new() -> Self {
        Self {
            continue_count: AtomicU64::new(0),
            delay_count: AtomicU64::new(0),
            drop_count: AtomicU64::new(0),
            timeout_count: AtomicU64::new(0),
            error_count: AtomicU64::new(0),
            connection_error_count: AtomicU64::new(0),
            reorder_count: AtomicU64::new(0),
            duplicate_count: AtomicU64::new(0),
            nxdomain_count: AtomicU64::new(0),
            skipped_count: AtomicU64::new(0),
        }
    }

    fn record_decision(&self, decision: &LayerDecision) {
        let counter = match decision {
            LayerDecision::Continue => &self.continue_count,
            LayerDecision::DelayNs(_) => &self.delay_count,
            LayerDecision::Drop => &self.drop_count,
            LayerDecision::TimeoutMs(_) => &self.timeout_count,
            LayerDecision::Error(_) => &self.error_count,
            LayerDecision::ConnectionErrorKind(_) => &self.connection_error_count,
            LayerDecision::StageReorder => &self.reorder_count,
            LayerDecision::Duplicate(_) => &self.duplicate_count,
            LayerDecision::NxDomain => &self.nxdomain_count,
        };
        counter.fetch_add(1, Ordering::Relaxed);
    }

    fn record_skipped(&self) {
        self.skipped_count.fetch_add(1, Ordering::Relaxed);
    }

    fn snapshot(&self) -> DecisionCounters {
        DecisionCounters {
            continue_count: self.continue_count.load(Ordering::Relaxed),
            delay_count: self.delay_count.load(Ordering::Relaxed),
            drop_count: self.drop_count.load(Ordering::Relaxed),
            timeout_count: self.timeout_count.load(Ordering::Relaxed),
            error_count: self.error_count.load(Ordering::Relaxed),
            connection_error_count: self.connection_error_count.load(Ordering::Relaxed),
            reorder_count: self.reorder_count.load(Ordering::Relaxed),
            duplicate_count: self.duplicate_count.load(Ordering::Relaxed),
            nxdomain_count: self.nxdomain_count.load(Ordering::Relaxed),
            skipped_count: self.skipped_count.load(Ordering::Relaxed),
        }
    }

    fn reset(&self) {
        self.continue_count.store(0, Ordering::Relaxed);
        self.delay_count.store(0, Ordering::Relaxed);
        self.drop_count.store(0, Ordering::Relaxed);
        self.timeout_count.store(0, Ordering::Relaxed);
        self.error_count.store(0, Ordering::Relaxed);
        self.connection_error_count.store(0, Ordering::Relaxed);
        self.reorder_count.store(0, Ordering::Relaxed);
        self.duplicate_count.store(0, Ordering::Relaxed);
        self.nxdomain_count.store(0, Ordering::Relaxed);
        self.skipped_count.store(0, Ordering::Relaxed);
    }
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
    metrics: [LayerMetrics; 7],
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
            metrics: std::array::from_fn(|_| LayerMetrics::new()),
        }
    }

    pub fn builder() -> ChaosEngineBuilder {
        ChaosEngineBuilder::new()
    }

    pub fn from_env() -> Self {
        Self::builder().build()
    }

    fn stage_index(stage: LayerStage) -> usize {
        match stage {
            LayerStage::L1 => 0,
            LayerStage::L2 => 1,
            LayerStage::L3 => 2,
            LayerStage::L4 => 3,
            LayerStage::L5 => 4,
            LayerStage::L6 => 5,
            LayerStage::L7 => 6,
        }
    }

    pub fn stage_order(&self) -> [LayerStage; 7] {
        [
            self.l1.stage(),
            self.l2.stage(),
            self.l3.stage(),
            self.l4.stage(),
            self.l5.stage(),
            self.l6.stage(),
            self.l7.stage(),
        ]
    }

    pub fn metrics_snapshot(&self) -> [(LayerStage, DecisionCounters); 7] {
        let order = self.stage_order();
        std::array::from_fn(|i| {
            let stage = order[i];
            (stage, self.metrics[i].snapshot())
        })
    }

    pub fn reset_metrics(&self) {
        for metric in &self.metrics {
            metric.reset();
        }
    }

    fn process_pipeline(&self, ctx: &PacketContext<'_>) -> LayerDecision {
        let mut delay_ns: u64 = 0;
        let stages: [&dyn Layer; 7] = [
            &self.l1, &self.l2, &self.l3, &self.l4, &self.l5, &self.l6, &self.l7,
        ];

        for layer in stages {
            let stage_idx = Self::stage_index(layer.stage());
            if !layer.applies_to(ctx) {
                self.metrics[stage_idx].record_skipped();
                continue;
            }

            let decision = layer.process(ctx);
            self.metrics[stage_idx].record_decision(&decision);
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
        let decision = self.process_pipeline(&ctx);
        record_fault_observability_decision(&decision);
        decision
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
        let session_precheck = self
            .l5
            .precheck(fd, bytes, direction, &effective, crate::monotonic_now_ns());
        if !matches!(session_precheck, LayerDecision::Continue) {
            self.metrics[Self::stage_index(LayerStage::L5)].record_decision(&session_precheck);
            record_fault_observability_decision(&session_precheck);
            return session_precheck;
        }
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
            record_fault_observability_decision(&decision);
            return decision;
        }

        let decision = self.l1.reorder_decision(&effective);
        self.metrics[Self::stage_index(LayerStage::L1)].record_decision(&decision);
        record_fault_observability_decision(&decision);
        decision
    }

    pub fn evaluate_stream_post(&self, config: &Config, direction: Direction) -> LayerDecision {
        let effective = match direction {
            Direction::Uplink => config.effective_for_send(),
            Direction::Downlink => config.effective_for_recv(),
        };
        if matches!(direction, Direction::Uplink) {
            let decision = self.l1.duplicate_decision(&effective);
            self.metrics[Self::stage_index(LayerStage::L1)].record_decision(&decision);
            record_fault_observability_decision(&decision);
            decision
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
        let decision = self.process_pipeline(&ctx);
        record_fault_observability_decision(&decision);
        decision
    }

    pub fn record_stream_bytes(&self, fd: i32, bytes: u64) {
        self.l4.record_stream_bytes(fd, bytes);
    }

    pub fn clear_fd_state(&self, fd: i32) {
        self.l4.clear_fd_state(fd);
        self.l5.clear_fd_state(fd);
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

    #[test]
    fn stage_order_is_strict_osi_l1_to_l7() {
        let engine = ChaosEngine::new();
        assert_eq!(
            engine.stage_order(),
            [
                LayerStage::L1,
                LayerStage::L2,
                LayerStage::L3,
                LayerStage::L4,
                LayerStage::L5,
                LayerStage::L6,
                LayerStage::L7,
            ]
        );
    }

    #[test]
    fn dns_lookup_skips_non_dns_layers() {
        let engine = ChaosEngine::new();
        engine.reset_metrics();
        let cfg = Config {
            packet_loss_ppm: 1_000_000,
            ..Default::default()
        };

        assert!(matches!(
            engine.evaluate_dns_lookup(&cfg),
            LayerDecision::Continue
        ));

        let metrics = engine.metrics_snapshot();
        assert!(metrics[0].1.skipped_count > 0);
        assert!(metrics[1].1.skipped_count > 0);
        assert!(metrics[2].1.skipped_count > 0);
        assert!(metrics[3].1.skipped_count > 0);
        assert!(metrics[6].1.continue_count > 0);
    }

    #[test]
    fn stream_path_skips_l7_dns_layer() {
        let engine = ChaosEngine::new();
        engine.reset_metrics();
        let cfg = Config {
            dns_timeout_ms: 123,
            ..Default::default()
        };

        assert!(matches!(
            engine.evaluate_stream_pre(1, &cfg, 0, Direction::Downlink),
            LayerDecision::Continue
        ));

        let metrics = engine.metrics_snapshot();
        assert!(metrics[6].1.skipped_count > 0);
    }

    #[test]
    fn session_budget_precheck_runs_before_fault_pipeline() {
        let engine = ChaosEngine::new();
        let cfg = Config {
            session_budget_enabled: 1,
            session_max_ops: 1,
            session_action: 2,
            session_budget_timeout_ms: 7,
            packet_loss_ppm: 1_000_000,
            ..Default::default()
        };

        assert!(matches!(
            engine.evaluate_stream_pre(55, &cfg, 1, Direction::Uplink),
            LayerDecision::Drop
        ));
        assert!(matches!(
            engine.evaluate_stream_pre(55, &cfg, 1, Direction::Uplink),
            LayerDecision::TimeoutMs(7)
        ));
    }
}
