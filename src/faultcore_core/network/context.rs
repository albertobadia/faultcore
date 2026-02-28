use std::time::Instant;

/// The context that flows through the FaultOSI Pipeline.
/// Represents a single network operation or packet being intercepted.
#[derive(Debug, Clone)]
pub struct PacketContext {
    /// External identifiers (e.g., from Python `ContextVars`) to route this packet
    pub keys: Vec<String>,
    /// Accumulated simulated delay that L0 will wait for.
    pub accumulated_delay_ms: u64,
    /// Has this packet been explicitly dropped by the simulation?
    pub dropped: bool,
    /// When did this packet enter the pipeline
    pub start_time: Instant,
    // Future additions: payload size, socket type, destination IP/Port, etc.
}

impl PacketContext {
    pub fn new(keys: Vec<String>) -> Self {
        Self {
            keys,
            accumulated_delay_ms: 0,
            dropped: false,
            start_time: Instant::now(),
        }
    }
}
