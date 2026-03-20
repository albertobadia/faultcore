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
pub use l7_resolver::L7Resolver;

use std::sync::Arc;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction {
    Uplink,
    Downlink,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Operation {
    Connect,
    Send,
    Recv,
    DnsLookup,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LayerStage {
    L1,
    L2,
    L3,
    L4,
    L5,
    L6,
    L7,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LayerDecision {
    Continue,
    DelayNs(u64),
    Drop,
    TimeoutMs(u64),
    Error(String),
    ConnectionErrorKind(u64),
    StageReorder,
    Duplicate(u64),
    NxDomain,
}

pub struct PacketContext<'a> {
    pub fd: i32,
    pub bytes: u64,
    pub operation: Operation,
    pub direction: Option<Direction>,
    pub config: &'a super::Config,
    pub now_ns: u64,
}

impl PacketContext<'_> {
    pub fn is_stream(&self) -> bool {
        matches!(self.operation, Operation::Send | Operation::Recv)
    }

    pub fn is_dns(&self) -> bool {
        matches!(self.operation, Operation::DnsLookup)
    }

    pub fn is_connect(&self) -> bool {
        matches!(self.operation, Operation::Connect)
    }

    pub fn is_send(&self) -> bool {
        matches!(self.operation, Operation::Send)
    }

    pub fn is_recv(&self) -> bool {
        matches!(self.operation, Operation::Recv)
    }
}

pub trait Layer: Send + Sync {
    fn stage(&self) -> LayerStage;
    fn applies_to(&self, _ctx: &PacketContext<'_>) -> bool {
        true
    }
    fn process(&self, ctx: &PacketContext<'_>) -> LayerDecision;
    fn name(&self) -> &str;
}

pub type SharedLayer = Arc<dyn Layer>;
