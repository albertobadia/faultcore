pub mod l1_chaos;
pub mod l2_qos;
pub mod l3_routing;
pub mod l4_transport;

pub use l1_chaos::L1Chaos;
pub use l2_qos::L2QoS;
pub use l3_routing::L3Routing;
pub use l4_transport::L4Transport;

use std::sync::Arc;

#[derive(Debug, Clone)]
pub enum LayerResult {
    Continue,
    Drop,
    Delay(u64),
    Timeout(u64),
    Error(String),
}

pub trait Layer: Send + Sync {
    fn process(&self, config: &super::Config) -> LayerResult;
    fn name(&self) -> &str;
}

pub type SharedLayer = Arc<dyn Layer>;
