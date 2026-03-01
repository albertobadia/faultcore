use super::context::PacketContext;
use std::sync::Arc;

pub mod l1_chaos;
pub mod l2_qos;
pub mod l3_routing;
pub mod l4_transport;

/// Result of a single layer processing the context.
#[derive(Debug)]
pub enum LayerResult {
    /// The layer successfully processed the context, proceed to the next layer.
    Continue,
    /// The layer decided to drop the packet, halt processing.
    Drop,
    /// The layer had an error, halt processing and return the error.
    Error(String),
}

/// A standard layer in the FaultOSI Pipeline.
pub trait Layer: Send + Sync {
    /// Process the context. Modifications to `ctx` are preserved for next layers.
    fn process(&self, ctx: &mut PacketContext) -> LayerResult;

    /// Optional name for debugging/tracing.
    fn name(&self) -> &str {
        "UnknownLayer"
    }
}

pub type SharedLayer = Arc<dyn Layer>;
