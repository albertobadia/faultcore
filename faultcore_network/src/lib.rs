pub mod chaos_engine;
pub mod layers;

pub use chaos_engine::{ChaosEngine, DecisionCounters};
pub type FaultOsiEngine = ChaosEngine;
pub type FaultOsiDecisionCounters = DecisionCounters;
pub use layers::{
    Direction, L1Chaos, L2QoS, L3Routing, L4Transport, L5Session, L6Presentation, L7Resolver, Layer,
    LayerDecision, LayerStage, Operation, PacketContext,
};

#[derive(Default)]
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
    }

    pub fn effective_for_send(&self) -> Self {
        let mut out = self.clone_for_effective();
        if self.uplink_latency_ns > 0 {
            out.latency_ns = self.uplink_latency_ns;
        }
        if self.uplink_jitter_ns > 0 {
            out.jitter_ns = self.uplink_jitter_ns;
        }
        if self.uplink_packet_loss_ppm > 0 {
            out.packet_loss_ppm = self.uplink_packet_loss_ppm;
        }
        if self.uplink_burst_loss_len > 0 {
            out.burst_loss_len = self.uplink_burst_loss_len;
        }
        if self.uplink_bandwidth_bps > 0 {
            out.bandwidth_bps = self.uplink_bandwidth_bps;
        }
        out
    }

    pub fn effective_for_recv(&self) -> Self {
        let mut out = self.clone_for_effective();
        if self.downlink_latency_ns > 0 {
            out.latency_ns = self.downlink_latency_ns;
        }
        if self.downlink_jitter_ns > 0 {
            out.jitter_ns = self.downlink_jitter_ns;
        }
        if self.downlink_packet_loss_ppm > 0 {
            out.packet_loss_ppm = self.downlink_packet_loss_ppm;
        }
        if self.downlink_burst_loss_len > 0 {
            out.burst_loss_len = self.downlink_burst_loss_len;
        }
        if self.downlink_bandwidth_bps > 0 {
            out.bandwidth_bps = self.downlink_bandwidth_bps;
        }
        out
    }

    fn clone_for_effective(&self) -> Self {
        Self {
            latency_ns: self.latency_ns,
            jitter_ns: self.jitter_ns,
            packet_loss_ppm: self.packet_loss_ppm,
            burst_loss_len: self.burst_loss_len,
            bandwidth_bps: self.bandwidth_bps,
            connect_timeout_ms: self.connect_timeout_ms,
            recv_timeout_ms: self.recv_timeout_ms,
            uplink_latency_ns: self.uplink_latency_ns,
            uplink_jitter_ns: self.uplink_jitter_ns,
            uplink_packet_loss_ppm: self.uplink_packet_loss_ppm,
            uplink_burst_loss_len: self.uplink_burst_loss_len,
            uplink_bandwidth_bps: self.uplink_bandwidth_bps,
            downlink_latency_ns: self.downlink_latency_ns,
            downlink_jitter_ns: self.downlink_jitter_ns,
            downlink_packet_loss_ppm: self.downlink_packet_loss_ppm,
            downlink_burst_loss_len: self.downlink_burst_loss_len,
            downlink_bandwidth_bps: self.downlink_bandwidth_bps,
            ge_enabled: self.ge_enabled,
            ge_p_good_to_bad_ppm: self.ge_p_good_to_bad_ppm,
            ge_p_bad_to_good_ppm: self.ge_p_bad_to_good_ppm,
            ge_loss_good_ppm: self.ge_loss_good_ppm,
            ge_loss_bad_ppm: self.ge_loss_bad_ppm,
            conn_err_kind: self.conn_err_kind,
            conn_err_prob_ppm: self.conn_err_prob_ppm,
            half_open_after_bytes: self.half_open_after_bytes,
            half_open_err_kind: self.half_open_err_kind,
            dup_prob_ppm: self.dup_prob_ppm,
            dup_max_extra: self.dup_max_extra,
            reorder_prob_ppm: self.reorder_prob_ppm,
            reorder_max_delay_ns: self.reorder_max_delay_ns,
            reorder_window: self.reorder_window,
            dns_delay_ns: self.dns_delay_ns,
            dns_timeout_ms: self.dns_timeout_ms,
            dns_nxdomain_ppm: self.dns_nxdomain_ppm,
            target_enabled: self.target_enabled,
            target_kind: self.target_kind,
            target_ipv4: self.target_ipv4,
            target_prefix_len: self.target_prefix_len,
            target_port: self.target_port,
            target_protocol: self.target_protocol,
        }
    }
}
