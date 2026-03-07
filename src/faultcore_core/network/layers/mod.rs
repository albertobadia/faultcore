use super::context::PacketContext;
use std::sync::Arc;

pub mod l1_chaos;
pub mod l2_qos;
pub mod l3_routing;
pub mod l4_transport;

#[derive(Debug)]
pub enum LayerResult {
    Continue,
    Drop,
    Error(String),
}

pub trait Layer: Send + Sync {
    fn process(&self, ctx: &mut PacketContext) -> LayerResult;

    fn name(&self) -> &str {
        "UnknownLayer"
    }
}

pub type SharedLayer = Arc<dyn Layer>;
