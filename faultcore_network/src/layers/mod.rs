pub mod l1_chaos;
pub mod l2_qos;
pub mod l3_routing;
pub mod l4_transport;
pub mod l5_session;
pub mod l6_presentation;
pub mod l7_resolver;

pub use l1_chaos::L1Chaos;
pub use l2_qos::L2QoS;
pub use l3_routing::L3Routing;
pub use l4_transport::L4Transport;
pub use l5_session::L5Session;
pub use l6_presentation::L6Presentation;
pub use l7_resolver::{DnsAction, L7Resolver};

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
