pub mod chaos_engine;
pub mod interceptor_bridge;
pub mod observability;
pub mod layers;
pub mod runtime;
pub mod record_replay;
pub mod setpriority_compat;
pub mod shm_contract;
pub mod shm_runtime;
pub mod socket_runtime;
use std::sync::OnceLock;

pub use chaos_engine::{ChaosEngine, DecisionCounters};
pub use observability::{
    FaultOsiAdvancedMetricsSnapshot, FaultTypeCountersSnapshot, TargetRuleCounterSnapshot,
    advanced_metrics_snapshot as global_fault_osi_advanced_metrics_snapshot,
    record_fault_decision as record_fault_observability_decision,
    record_target_rule_hit as record_target_rule_observability_hit, reset_advanced_metrics,
};
pub type FaultOsiEngine = ChaosEngine;
pub type FaultOsiDecisionCounters = DecisionCounters;
pub use interceptor_bridge::{
    bind_fd_to_current_thread, clear_fd_binding, clone_fd_binding, init_runtime_shm,
    observe_hostname_for_current_thread_addr, observe_sni_for_fd, reset_runtime_reload_metrics,
    runtime_reload_metrics_snapshot, runtime_config_for_addr_or_fd, runtime_config_for_fd,
    runtime_dns_config_for_current_thread, runtime_dns_config_for_query, uplink_duplicate_count_for_addr_or_fd,
    uplink_duplicate_count_for_fd,
};
pub use layers::{
    Direction, L1Chaos, L2QoS, L3Routing, L4Transport, L5Session, L6Presentation, L7Resolver,
    Layer, LayerDecision, LayerStage, Operation, PacketContext,
};
pub use runtime::{
    ConnectDirective, InterceptorRuntime, PendingDatagram, StreamDirective,
    apply_connect_directive, apply_stream_directive, set_errno_value, snapshot_recv_datagram,
    snapshot_recvfrom_datagram, stage_reorder_send, stage_reorder_sendto,
    write_pending_recv_result, write_pending_recvfrom_result,
};
pub use record_replay::{
    RecordReplayCore, RecordReplayEvent, RecordReplayMode, record_replay_evaluate_or_replay,
};
pub use setpriority_compat::{
    FAULTCORE_SETPRIORITY_BANDWIDTH, FAULTCORE_SETPRIORITY_LATENCY, FAULTCORE_SETPRIORITY_TIMEOUT,
    SetpriorityCompatOutcome, handle_setpriority_compat, try_handle_setpriority,
};
pub use shm_contract::{
    FAULTCORE_MAGIC, FAULTCORE_SHM_SIZE, FaultcoreConfig, MAX_BANDWIDTH_BPS, MAX_FDS,
    MAX_LATENCY_NS, MAX_POLICIES, MAX_TARGET_RULES_PER_TID, MAX_TIDS, PolicyState, TargetRule,
};
pub use shm_runtime::{
    assign_rule_to_fd, clear_rule_for_fd, clone_rule_for_fd, get_config_for_fd, get_config_for_tid,
    get_config_for_tid_slot, get_current_policy_name, get_target_rules_for_tid_slot, get_thread_id,
    get_tid_slot_for_fd, get_tid_slot_for_tid, is_shm_open, try_open_shm, update_config_for_tid,
};
pub use socket_runtime::{endpoint_for_addr_or_fd, endpoint_for_fd, monotonic_now_ns};

static GLOBAL_ENGINE: OnceLock<ChaosEngine> = OnceLock::new();
static GLOBAL_RUNTIME: OnceLock<InterceptorRuntime> = OnceLock::new();
const FAULT_OSI_LAYER_COUNT: usize = 7;

pub fn global_fault_osi_engine() -> &'static FaultOsiEngine {
    GLOBAL_ENGINE.get_or_init(ChaosEngine::new)
}

pub fn global_interceptor_runtime() -> &'static InterceptorRuntime {
    GLOBAL_RUNTIME.get_or_init(InterceptorRuntime::new)
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Default)]
pub struct FaultOsiLayerMetricsSnapshot {
    pub stage: u8,
    pub reserved: [u8; 7],
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

#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct FaultOsiMetricsSnapshot {
    pub len: u64,
    pub layers: [FaultOsiLayerMetricsSnapshot; FAULT_OSI_LAYER_COUNT],
    pub reload_applied_count: u64,
    pub reload_retry_count: u64,
}

impl Default for FaultOsiMetricsSnapshot {
    fn default() -> Self {
        Self {
            len: 0,
            layers: [FaultOsiLayerMetricsSnapshot::default(); FAULT_OSI_LAYER_COUNT],
            reload_applied_count: 0,
            reload_retry_count: 0,
        }
    }
}

fn stage_code(stage: LayerStage) -> u8 {
    match stage {
        LayerStage::L1 => 1,
        LayerStage::L2 => 2,
        LayerStage::L3 => 3,
        LayerStage::L4 => 4,
        LayerStage::L5 => 5,
        LayerStage::L6 => 6,
        LayerStage::L7 => 7,
    }
}

pub fn global_fault_osi_metrics_snapshot() -> FaultOsiMetricsSnapshot {
    let raw = global_fault_osi_engine().metrics_snapshot();
    let mut out = FaultOsiMetricsSnapshot {
        len: raw.len() as u64,
        ..Default::default()
    };
    for (idx, (stage, counters)) in raw.iter().enumerate() {
        out.layers[idx] = FaultOsiLayerMetricsSnapshot {
            stage: stage_code(*stage),
            reserved: [0; 7],
            continue_count: counters.continue_count,
            delay_count: counters.delay_count,
            drop_count: counters.drop_count,
            timeout_count: counters.timeout_count,
            error_count: counters.error_count,
            connection_error_count: counters.connection_error_count,
            reorder_count: counters.reorder_count,
            duplicate_count: counters.duplicate_count,
            nxdomain_count: counters.nxdomain_count,
            skipped_count: counters.skipped_count,
        };
    }
    let (reload_applied, reload_retry) = runtime_reload_metrics_snapshot();
    out.reload_applied_count = reload_applied;
    out.reload_retry_count = reload_retry;
    out
}

pub fn reset_global_fault_osi_metrics() {
    global_fault_osi_engine().reset_metrics();
    reset_runtime_reload_metrics();
    reset_advanced_metrics();
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Endpoint {
    pub address_family: u64,
    pub addr: [u8; 16],
    pub ipv4: u32,
    pub port: u16,
    pub protocol: u64,
}

#[derive(Clone, Copy, Default)]
pub struct Config {
    pub latency_ns: u64,
    pub jitter_ns: u64,
    pub packet_loss_ppm: u64,
    pub burst_loss_len: u64,
    pub bandwidth_bps: u64,
    pub connect_timeout_ms: u64,
    pub recv_timeout_ms: u64,
    pub uplink_latency_ns: u64,
    pub uplink_jitter_ns: u64,
    pub uplink_packet_loss_ppm: u64,
    pub uplink_burst_loss_len: u64,
    pub uplink_bandwidth_bps: u64,
    pub downlink_latency_ns: u64,
    pub downlink_jitter_ns: u64,
    pub downlink_packet_loss_ppm: u64,
    pub downlink_burst_loss_len: u64,
    pub downlink_bandwidth_bps: u64,
    pub ge_enabled: u64,
    pub ge_p_good_to_bad_ppm: u64,
    pub ge_p_bad_to_good_ppm: u64,
    pub ge_loss_good_ppm: u64,
    pub ge_loss_bad_ppm: u64,
    pub conn_err_kind: u64,
    pub conn_err_prob_ppm: u64,
    pub half_open_after_bytes: u64,
    pub half_open_err_kind: u64,
    pub dup_prob_ppm: u64,
    pub dup_max_extra: u64,
    pub reorder_prob_ppm: u64,
    pub reorder_max_delay_ns: u64,
    pub reorder_window: u64,
    pub dns_delay_ns: u64,
    pub dns_timeout_ms: u64,
    pub dns_nxdomain_ppm: u64,
    pub target_enabled: u64,
    pub target_kind: u64,
    pub target_ipv4: u64,
    pub target_prefix_len: u64,
    pub target_port: u64,
    pub target_protocol: u64,
    pub target_address_family: u64,
    pub target_addr: [u8; 16],
    pub target_hostname: [u8; 32],
    pub target_sni: [u8; 32],
    pub session_budget_enabled: u64,
    pub session_max_bytes_tx: u64,
    pub session_max_bytes_rx: u64,
    pub session_max_ops: u64,
    pub session_max_duration_ms: u64,
    pub session_action: u64,
    pub session_budget_timeout_ms: u64,
    pub session_error_kind: u64,
    pub policy_seed: u64,
    pub ruleset_generation: u64,
    pub schedule_type: u64,
    pub schedule_param_a_ns: u64,
    pub schedule_param_b_ns: u64,
    pub schedule_param_c_ns: u64,
    pub schedule_started_monotonic_ns: u64,
}

impl Config {
    pub fn is_enabled(&self) -> bool {
        self.latency_ns > 0
            || self.jitter_ns > 0
            || self.packet_loss_ppm > 0
            || self.burst_loss_len > 0
            || self.bandwidth_bps > 0
            || self.connect_timeout_ms > 0
            || self.recv_timeout_ms > 0
            || self.uplink_latency_ns > 0
            || self.uplink_jitter_ns > 0
            || self.uplink_packet_loss_ppm > 0
            || self.uplink_burst_loss_len > 0
            || self.uplink_bandwidth_bps > 0
            || self.downlink_latency_ns > 0
            || self.downlink_jitter_ns > 0
            || self.downlink_packet_loss_ppm > 0
            || self.downlink_burst_loss_len > 0
            || self.downlink_bandwidth_bps > 0
            || self.ge_enabled > 0
            || self.conn_err_kind > 0
            || self.half_open_after_bytes > 0
            || self.dup_prob_ppm > 0
            || self.reorder_prob_ppm > 0
            || self.reorder_max_delay_ns > 0
            || self.dns_delay_ns > 0
            || self.dns_timeout_ms > 0
            || self.dns_nxdomain_ppm > 0
            || self.target_enabled > 0
            || self.session_budget_enabled > 0
            || self.policy_seed > 0
            || self.schedule_type > 0
    }

    pub fn effective_for_send(&self) -> Self {
        let mut out = *self;
        apply_direction_overrides(
            &mut out,
            self.uplink_latency_ns,
            self.uplink_jitter_ns,
            self.uplink_packet_loss_ppm,
            self.uplink_burst_loss_len,
            self.uplink_bandwidth_bps,
        );
        out
    }

    pub fn effective_for_recv(&self) -> Self {
        let mut out = *self;
        apply_direction_overrides(
            &mut out,
            self.downlink_latency_ns,
            self.downlink_jitter_ns,
            self.downlink_packet_loss_ppm,
            self.downlink_burst_loss_len,
            self.downlink_bandwidth_bps,
        );
        out
    }

    pub fn runtime_filtered(
        &self,
        endpoint: Option<Endpoint>,
        now_monotonic_ns: u64,
    ) -> Option<Self> {
        let mut out = *self;
        if !out.matches_target(endpoint) {
            return None;
        }
        out.apply_schedule(now_monotonic_ns);
        Some(out)
    }

    fn matches_target(&self, endpoint: Option<Endpoint>) -> bool {
        if self.target_enabled == 0 || self.target_kind == 0 {
            return true;
        }
        let Some(endpoint) = endpoint else {
            return false;
        };
        if self.target_protocol > 0 && self.target_protocol != endpoint.protocol {
            return false;
        }
        if self.target_port > 0 && self.target_port != u64::from(endpoint.port) {
            return false;
        }
        let family = self.target_address_family;
        if family == 0 {
            return false;
        }
        match self.target_kind {
            1 => endpoint.address_family == family && endpoint.addr == self.target_addr,
            2 => {
                let prefix_len = self.target_prefix_len;
                let max_prefix = if family == 1 { 32 } else { 128 };
                let bounded_prefix = usize::min(prefix_len as usize, max_prefix);
                endpoint.address_family == family
                    && prefix_match(&endpoint.addr, &self.target_addr, bounded_prefix)
            }
            _ => false,
        }
    }

    fn apply_schedule(&mut self, now_monotonic_ns: u64) {
        if self.schedule_type == 0 {
            return;
        }
        let started = self.schedule_started_monotonic_ns;
        if started == 0 || now_monotonic_ns <= started {
            return;
        }
        let elapsed = now_monotonic_ns - started;
        match self.schedule_type {
            1 => {
                let ramp_ns = self.schedule_param_a_ns;
                if ramp_ns == 0 || elapsed >= ramp_ns {
                    return;
                }
                let factor = elapsed as f64 / ramp_ns as f64;
                self.scale_faults(factor);
            }
            2 => {
                let cycle_ns = self.schedule_param_a_ns;
                let active_ns = self.schedule_param_b_ns;
                if cycle_ns == 0 || active_ns == 0 || active_ns > cycle_ns {
                    self.zero_faults();
                    return;
                }
                if (elapsed % cycle_ns) >= active_ns {
                    self.zero_faults();
                }
            }
            3 => {
                let on_ns = self.schedule_param_a_ns;
                let off_ns = self.schedule_param_b_ns;
                let cycle_ns = on_ns.saturating_add(off_ns);
                if on_ns == 0 || off_ns == 0 || cycle_ns == 0 {
                    self.zero_faults();
                    return;
                }
                if (elapsed % cycle_ns) >= on_ns {
                    self.zero_faults();
                }
            }
            _ => {}
        }
    }

    fn scale_faults(&mut self, factor: f64) {
        macro_rules! scale {
            ($($field:ident),*) => {
                $(self.$field = scale_u64(self.$field, factor);)*
            };
        }
        scale!(
            latency_ns,
            jitter_ns,
            packet_loss_ppm,
            burst_loss_len,
            bandwidth_bps,
            connect_timeout_ms,
            recv_timeout_ms,
            uplink_latency_ns,
            uplink_jitter_ns,
            uplink_packet_loss_ppm,
            uplink_burst_loss_len,
            uplink_bandwidth_bps,
            downlink_latency_ns,
            downlink_jitter_ns,
            downlink_packet_loss_ppm,
            downlink_burst_loss_len,
            downlink_bandwidth_bps,
            conn_err_prob_ppm,
            dup_prob_ppm,
            reorder_prob_ppm,
            dns_delay_ns,
            dns_timeout_ms,
            dns_nxdomain_ppm
        );
    }

    fn zero_faults(&mut self) {
        macro_rules! zero {
            ($($field:ident),*) => {
                $(self.$field = 0;)*
            };
        }
        zero!(
            latency_ns,
            jitter_ns,
            packet_loss_ppm,
            burst_loss_len,
            bandwidth_bps,
            connect_timeout_ms,
            recv_timeout_ms,
            uplink_latency_ns,
            uplink_jitter_ns,
            uplink_packet_loss_ppm,
            uplink_burst_loss_len,
            uplink_bandwidth_bps,
            downlink_latency_ns,
            downlink_jitter_ns,
            downlink_packet_loss_ppm,
            downlink_burst_loss_len,
            downlink_bandwidth_bps,
            ge_enabled,
            ge_p_good_to_bad_ppm,
            ge_p_bad_to_good_ppm,
            ge_loss_good_ppm,
            ge_loss_bad_ppm,
            conn_err_kind,
            conn_err_prob_ppm,
            half_open_after_bytes,
            half_open_err_kind,
            dup_prob_ppm,
            dup_max_extra,
            reorder_prob_ppm,
            reorder_max_delay_ns,
            reorder_window,
            dns_delay_ns,
            dns_timeout_ms,
            dns_nxdomain_ppm
        );
    }
}

fn scale_u64(value: u64, factor: f64) -> u64 {
    ((value as f64) * factor).round() as u64
}

fn apply_direction_overrides(
    out: &mut Config,
    latency_ns: u64,
    jitter_ns: u64,
    packet_loss_ppm: u64,
    burst_loss_len: u64,
    bandwidth_bps: u64,
) {
    macro_rules! override_if_pos {
        ($($val:ident -> $field:ident),*) => {
            $(if $val > 0 { out.$field = $val; })*
        };
    }
    override_if_pos!(
        latency_ns -> latency_ns,
        jitter_ns -> jitter_ns,
        packet_loss_ppm -> packet_loss_ppm,
        burst_loss_len -> burst_loss_len,
        bandwidth_bps -> bandwidth_bps
    );
}

fn prefix_match(candidate: &[u8; 16], network: &[u8; 16], prefix_len: usize) -> bool {
    if prefix_len == 0 {
        return true;
    }
    let full_bytes = prefix_len / 8;
    let partial_bits = prefix_len % 8;
    if full_bytes > 0 && candidate[..full_bytes] != network[..full_bytes] {
        return false;
    }
    if partial_bits == 0 {
        return true;
    }
    let mask = (!0u8) << (8 - partial_bits);
    (candidate[full_bytes] & mask) == (network[full_bytes] & mask)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn metrics_snapshot_contract_is_stable() {
        let snapshot = global_fault_osi_metrics_snapshot();
        assert_eq!(snapshot.len, 7);
        assert_eq!(snapshot.layers[0].stage, 1);
        assert_eq!(snapshot.layers[6].stage, 7);
    }

    #[test]
    fn advanced_metrics_snapshot_contract_is_stable() {
        let _guard = observability::advanced_metrics_test_guard();
        let snapshot = global_fault_osi_advanced_metrics_snapshot();
        assert_eq!(snapshot.latency_bucket_len as usize, observability::LATENCY_BUCKET_COUNT);
        assert_eq!(
            snapshot.latency_bucket_upper_bounds_ns,
            observability::LATENCY_BUCKET_UPPER_BOUNDS_NS
        );
    }

    #[test]
    fn reset_global_metrics_clears_advanced_observability() {
        let _guard = observability::advanced_metrics_test_guard();
        reset_advanced_metrics();
        record_fault_observability_decision(&LayerDecision::Drop);
        record_target_rule_observability_hit(1234);
        let before = global_fault_osi_advanced_metrics_snapshot();
        assert_eq!(before.fault_counters.drop_count, 1);
        assert_eq!(before.target_rule_top_len, 1);

        reset_global_fault_osi_metrics();
        let after = global_fault_osi_advanced_metrics_snapshot();
        assert_eq!(after.fault_counters.drop_count, 0);
        assert_eq!(after.target_rule_top_len, 0);
        assert_eq!(after.target_rule_other_count, 0);
    }

    #[test]
    fn ramp_schedule_scales_bandwidth_fields() {
        let mut cfg = Config {
            bandwidth_bps: 1_000,
            uplink_bandwidth_bps: 2_000,
            downlink_bandwidth_bps: 3_000,
            schedule_type: 1,
            schedule_param_a_ns: 100,
            schedule_started_monotonic_ns: 1_000,
            ..Default::default()
        };

        cfg.apply_schedule(1_050);

        assert_eq!(cfg.bandwidth_bps, 500);
        assert_eq!(cfg.uplink_bandwidth_bps, 1_000);
        assert_eq!(cfg.downlink_bandwidth_bps, 1_500);
    }
}
