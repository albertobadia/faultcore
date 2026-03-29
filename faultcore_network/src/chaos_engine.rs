use crate::{
    Config, Layer,
    layers::{
        Direction, LayerDecision, LayerStage, Operation, PacketContext, R1SessionGuard,
        R2ChaosBase, R3FlowControl, R4TimingVariation, R5TransportFaults, R6ResolverFaults,
        R7PayloadTransform,
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
    r2: R2ChaosBase,
    r3: R3FlowControl,
    r4: R4TimingVariation,
    r5: R5TransportFaults,
    r1: R1SessionGuard,
    r7: R7PayloadTransform,
    r6: R6ResolverFaults,
    metrics: [LayerMetrics; 9],
}

impl ChaosEngine {
    pub fn new() -> Self {
        Self {
            r2: R2ChaosBase::new(),
            r3: R3FlowControl::with_rate(0),
            r4: R4TimingVariation::new(),
            r5: R5TransportFaults::new(),
            r1: R1SessionGuard::new(),
            r7: R7PayloadTransform::new(),
            r6: R6ResolverFaults::new(),
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
            LayerStage::R0 => 0,
            LayerStage::R1 => 1,
            LayerStage::R2 => 2,
            LayerStage::R3 => 3,
            LayerStage::R4 => 4,
            LayerStage::R5 => 5,
            LayerStage::R6 => 6,
            LayerStage::R7 => 7,
            LayerStage::R8 => 8,
        }
    }

    pub fn stage_order(&self) -> [LayerStage; 9] {
        [
            LayerStage::R0,
            LayerStage::R1,
            LayerStage::R2,
            LayerStage::R3,
            LayerStage::R4,
            LayerStage::R5,
            LayerStage::R6,
            LayerStage::R7,
            LayerStage::R8,
        ]
    }

    pub fn metrics_snapshot(&self) -> [(LayerStage, DecisionCounters); 9] {
        let stage_order = self.stage_order();
        std::array::from_fn(|idx| (stage_order[idx], self.metrics[idx].snapshot()))
    }

    fn record_config_resolve(&self) {
        self.metrics[Self::stage_index(LayerStage::R0)].record_decision(&LayerDecision::Continue);
    }

    pub fn reset_metrics(&self) {
        for metric in &self.metrics {
            metric.reset();
        }
    }

    fn process_pipeline(&self, ctx: &PacketContext<'_>) -> LayerDecision {
        let mut delay_ns: u64 = 0;
        let stages: [&dyn Layer; 5] = [&self.r2, &self.r3, &self.r4, &self.r5, &self.r6];

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
                    return LayerDecision::Error(format!("{} returned an unsupported decision in main pipeline", layer.name()));
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
        self.record_config_resolve();
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
        self.record_config_resolve();
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

        let session_decision = self.r1.process(&ctx);
        if !matches!(session_decision, LayerDecision::Continue) {
            self.metrics[Self::stage_index(LayerStage::R1)].record_decision(&session_decision);
            record_fault_observability_decision(&session_decision);
            return session_decision;
        }
        self.metrics[Self::stage_index(LayerStage::R1)].record_decision(&LayerDecision::Continue);

        let decision = self.process_pipeline(&ctx);
        if !matches!(decision, LayerDecision::Continue) {
            record_fault_observability_decision(&decision);
            return decision;
        }

        let decision = self.r2.reorder_decision(&effective);
        self.metrics[Self::stage_index(LayerStage::R8)].record_decision(&decision);
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
                let decision = self.r2.duplicate_decision(&effective);
                self.metrics[Self::stage_index(LayerStage::R8)].record_decision(&decision);
                record_fault_observability_decision(&decision);
                decision
            }
            Direction::Downlink => LayerDecision::Continue,
        }
    }

    pub fn evaluate_dns_lookup(&self, config: &Config) -> LayerDecision {
        self.record_config_resolve();
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

    pub fn evaluate_r7_with_buffer(
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
        let stage_idx = Self::stage_index(LayerStage::R7);
        if !self.r7.applies_to(&ctx) {
            self.metrics[stage_idx].record_skipped();
            return (LayerDecision::Continue, None);
        }
        let (decision, maybe_buffer) = self.r7.process_with_buffer(&ctx, buffer);
        self.metrics[stage_idx].record_decision(&decision);
        if !matches!(decision, LayerDecision::Continue) {
            record_fault_observability_decision(&decision);
        }
        (decision, maybe_buffer)
    }

    pub fn record_stream_bytes(&self, fd: i32, bytes: u64) {
        self.r5.record_stream_bytes(fd, bytes);
    }

    pub fn clear_fd_state(&self, fd: i32) {
        self.r5.clear_fd_state(fd);
        self.r1.clear_fd_state(fd);
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
    fn combines_r2_latency_and_r4_jitter_delay() {
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
    fn stage_order_follows_runtime_r0_to_r8() {
        let engine = ChaosEngine::new();
        assert_eq!(
            engine.stage_order(),
            [
                LayerStage::R0,
                LayerStage::R1,
                LayerStage::R2,
                LayerStage::R3,
                LayerStage::R4,
                LayerStage::R5,
                LayerStage::R6,
                LayerStage::R7,
                LayerStage::R8,
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
        assert!(metrics[0].1.continue_count > 0);
        assert!(metrics[2].1.skipped_count > 0);
        assert!(metrics[3].1.skipped_count > 0);
        assert!(metrics[4].1.skipped_count > 0);
        assert!(metrics[5].1.skipped_count > 0);
        assert!(metrics[6].1.continue_count > 0);
    }

    #[test]
    fn stream_path_skips_r6_resolver_stage() {
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
