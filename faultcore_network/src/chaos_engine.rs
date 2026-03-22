use crate::{
    Config, Layer,
    layers::{
        Direction, L1Chaos, L2QoS, L3Routing, L4Transport, L5Session, L6Presentation, L7Resolver,
        LayerDecision, LayerStage, Operation, PacketContext,
    },
    record_fault_observability_decision,
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
    pub mutate_count: u64,
    pub skipped_count: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CounterType {
    Continue = 0,
    Delay = 1,
    Drop = 2,
    Timeout = 3,
    Error = 4,
    ConnectionError = 5,
    Reorder = 6,
    Duplicate = 7,
    NxDomain = 8,
    Mutate = 9,
    Skipped = 10,
}

struct LayerMetrics {
    counters: [AtomicU64; 11],
}

impl LayerMetrics {
    fn new() -> Self {
        Self {
            counters: std::array::from_fn(|_| AtomicU64::new(0)),
        }
    }

    fn record_decision(&self, decision: &LayerDecision) {
        let ty = match decision {
            LayerDecision::Continue => CounterType::Continue,
            LayerDecision::DelayNs(_) => CounterType::Delay,
            LayerDecision::Drop => CounterType::Drop,
            LayerDecision::TimeoutMs(_) => CounterType::Timeout,
            LayerDecision::Error(_) => CounterType::Error,
            LayerDecision::ConnectionErrorKind(_) => CounterType::ConnectionError,
            LayerDecision::StageReorder => CounterType::Reorder,
            LayerDecision::Duplicate(_) => CounterType::Duplicate,
            LayerDecision::NxDomain => CounterType::NxDomain,
            LayerDecision::Mutate(_) => CounterType::Mutate,
        };
        self.counters[ty as usize].fetch_add(1, Ordering::Relaxed);
    }

    fn record_skipped(&self) {
        self.counters[CounterType::Skipped as usize].fetch_add(1, Ordering::Relaxed);
    }

    fn snapshot(&self) -> DecisionCounters {
        let load = |ty: CounterType| self.counters[ty as usize].load(Ordering::Relaxed);
        DecisionCounters {
            continue_count: load(CounterType::Continue),
            delay_count: load(CounterType::Delay),
            drop_count: load(CounterType::Drop),
            timeout_count: load(CounterType::Timeout),
            error_count: load(CounterType::Error),
            connection_error_count: load(CounterType::ConnectionError),
            reorder_count: load(CounterType::Reorder),
            duplicate_count: load(CounterType::Duplicate),
            nxdomain_count: load(CounterType::NxDomain),
            mutate_count: load(CounterType::Mutate),
            skipped_count: load(CounterType::Skipped),
        }
    }

    fn reset(&self) {
        for counter in &self.counters {
            counter.store(0, Ordering::Relaxed);
        }
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
        let stage_order = self.stage_order();
        std::array::from_fn(|idx| (stage_order[idx], self.metrics[idx].snapshot()))
    }

    pub fn reset_metrics(&self) {
        for metric in &self.metrics {
            metric.reset();
        }
    }

    fn process_pipeline(&self, ctx: &PacketContext<'_>) -> LayerDecision {
        let mut delay_ns: u64 = 0;
        let stages: [&dyn Layer; 6] = [&self.l1, &self.l2, &self.l3, &self.l4, &self.l6, &self.l7];

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
                LayerDecision::Mutate(_) => {
                    return LayerDecision::Error(format!(
                        "{} returned a payload decision in main pipeline",
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
        let now_ns = crate::monotonic_now_ns();
        let ctx = PacketContext {
            fd,
            bytes: 0,
            operation: Operation::Connect,
            direction: Some(Direction::Uplink),
            config: &effective,
            now_ns,
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
        let operation = match direction {
            Direction::Uplink => Operation::Send,
            Direction::Downlink => Operation::Recv,
        };
        let now_ns = crate::monotonic_now_ns();
        let ctx = PacketContext {
            fd,
            bytes,
            operation,
            direction: Some(direction),
            config: &effective,
            now_ns,
        };

        let session_decision = self.l5.process(&ctx);
        if !matches!(session_decision, LayerDecision::Continue) {
            self.metrics[Self::stage_index(LayerStage::L5)].record_decision(&session_decision);
            record_fault_observability_decision(&session_decision);
            return session_decision;
        }

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
        match direction {
            Direction::Uplink => {
                let decision = self.l1.duplicate_decision(&effective);
                self.metrics[Self::stage_index(LayerStage::L1)].record_decision(&decision);
                record_fault_observability_decision(&decision);
                decision
            }
            Direction::Downlink => LayerDecision::Continue,
        }
    }

    pub fn evaluate_dns_lookup(&self, config: &Config) -> LayerDecision {
        let now_ns = crate::monotonic_now_ns();
        let ctx = PacketContext {
            fd: -1,
            bytes: 0,
            operation: Operation::DnsLookup,
            direction: None,
            config,
            now_ns,
        };
        let decision = self.process_pipeline(&ctx);
        record_fault_observability_decision(&decision);
        decision
    }

    pub fn evaluate_l6_with_buffer(
        &self,
        fd: i32,
        config: &Config,
        direction: Direction,
        bytes: u64,
        buffer: &[u8],
    ) -> (LayerDecision, Option<Vec<u8>>) {
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
            now_ns: crate::monotonic_now_ns(),
        };
        let stage_idx = Self::stage_index(LayerStage::L6);
        if !self.l6.applies_to(&ctx) {
            self.metrics[stage_idx].record_skipped();
            return (LayerDecision::Continue, None);
        }
        let (decision, maybe_buffer) = self.l6.process_with_buffer(&ctx, buffer);
        self.metrics[stage_idx].record_decision(&decision);
        if !matches!(decision, LayerDecision::Continue) {
            record_fault_observability_decision(&decision);
        }
        (decision, maybe_buffer)
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
