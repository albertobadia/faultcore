use crate::Config;

pub const FAULTCORE_MAGIC: u32 = 0xFACC0DE;
pub const MAX_FDS: usize = 131072;
pub const MAX_TIDS: usize = 65536;
pub const MAX_POLICIES: usize = 1024;
pub const MAX_LATENCY_NS: u64 = 60_000_000_000;
pub const MAX_BANDWIDTH_BPS: u64 = 100_000_000_000;
pub const FAULTCORE_SHM_SIZE: usize = ((MAX_FDS + MAX_TIDS) * core::mem::size_of::<FaultcoreConfig>())
    + (MAX_POLICIES * core::mem::size_of::<PolicyState>());

#[repr(C, packed)]
#[derive(Debug, Clone, Copy, Default)]
pub struct FaultcoreConfig {
    pub magic: u32,
    pub version: u64,
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
    pub schedule_type: u64,
    pub schedule_param_a_ns: u64,
    pub schedule_param_b_ns: u64,
    pub schedule_param_c_ns: u64,
    pub schedule_started_monotonic_ns: u64,
    pub reserved: u32,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Default)]
pub struct PolicyState {
    pub magic: u32,
    pub name: [u8; 32],
    pub enabled: bool,
    pub total_calls: u64,
    pub total_failures: u64,
}

impl FaultcoreConfig {
    pub fn is_valid(&self) -> bool {
        self.magic == FAULTCORE_MAGIC
            && self.latency_ns <= MAX_LATENCY_NS
            && self.jitter_ns <= MAX_LATENCY_NS
            && self.packet_loss_ppm <= 1_000_000
            && self.burst_loss_len <= 1_000_000
            && self.bandwidth_bps <= MAX_BANDWIDTH_BPS
            && self.uplink_packet_loss_ppm <= 1_000_000
            && self.downlink_packet_loss_ppm <= 1_000_000
            && self.uplink_burst_loss_len <= 1_000_000
            && self.downlink_burst_loss_len <= 1_000_000
            && self.uplink_bandwidth_bps <= MAX_BANDWIDTH_BPS
            && self.downlink_bandwidth_bps <= MAX_BANDWIDTH_BPS
            && self.uplink_latency_ns <= MAX_LATENCY_NS
            && self.uplink_jitter_ns <= MAX_LATENCY_NS
            && self.downlink_latency_ns <= MAX_LATENCY_NS
            && self.downlink_jitter_ns <= MAX_LATENCY_NS
            && self.ge_p_good_to_bad_ppm <= 1_000_000
            && self.ge_p_bad_to_good_ppm <= 1_000_000
            && self.ge_loss_good_ppm <= 1_000_000
            && self.ge_loss_bad_ppm <= 1_000_000
            && self.conn_err_kind <= 3
            && self.conn_err_prob_ppm <= 1_000_000
            && self.half_open_err_kind <= 3
            && self.dup_prob_ppm <= 1_000_000
            && self.reorder_prob_ppm <= 1_000_000
            && self.reorder_window <= 1_000_000
            && self.dns_delay_ns <= MAX_LATENCY_NS
            && self.dns_nxdomain_ppm <= 1_000_000
            && self.target_enabled <= 1
            && self.target_kind <= 2
            && self.target_prefix_len <= 32
            && self.target_port <= 65_535
            && self.target_protocol <= 2
            && self.schedule_type <= 3
    }

    pub fn into_network_config(self) -> Config {
        Config {
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
            schedule_type: self.schedule_type,
            schedule_param_a_ns: self.schedule_param_a_ns,
            schedule_param_b_ns: self.schedule_param_b_ns,
            schedule_param_c_ns: self.schedule_param_c_ns,
            schedule_started_monotonic_ns: self.schedule_started_monotonic_ns,
        }
    }
}

