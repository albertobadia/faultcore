pub mod chaos_engine;
pub mod layers;

pub use chaos_engine::ChaosEngine;
pub use layers::{L1Chaos, L2QoS, L3Routing, L4Transport, Layer, LayerResult};

#[derive(Default)]
pub struct Config {
    pub latency_ns: u64,
    pub packet_loss_ppm: u64,
    pub bandwidth_bps: u64,
    pub connect_timeout_ms: u64,
    pub recv_timeout_ms: u64,
}

impl Config {
    pub fn is_enabled(&self) -> bool {
        self.latency_ns > 0
            || self.packet_loss_ppm > 0
            || self.bandwidth_bps > 0
            || self.connect_timeout_ms > 0
            || self.recv_timeout_ms > 0
    }
}
