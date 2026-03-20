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

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MutationKind {
    None = 0,
    Truncate = 1,
    CorruptBytes = 2,
    InjectBytes = 3,
    ReplacePattern = 4,
    CorruptEncoding = 5,
    SwapBytes = 6,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MutationTarget {
    Both = 0,
    UplinkOnly = 1,
    DownlinkOnly = 2,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Mutation {
    Truncate {
        size: u64,
    },
    CorruptBytes {
        count: u64,
        seed: u64,
    },
    InjectBytes {
        position: u64,
        data: [u8; 64],
        len: u64,
    },
    ReplacePattern {
        find: [u8; 32],
        find_len: u64,
        replace: [u8; 32],
        replace_len: u64,
    },
    CorruptEncoding,
    SwapBytes {
        pos1: u64,
        pos2: u64,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MutationOutcome {
    pub applied: bool,
    pub input_len: usize,
    pub output_len: usize,
    pub skipped_rules: u64,
    pub error_count: u64,
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
    Mutate(Vec<Mutation>),
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

    fn process_with_buffer(
        &self,
        ctx: &PacketContext<'_>,
        _buffer: &[u8],
    ) -> (LayerDecision, Option<Vec<u8>>) {
        (self.process(ctx), None)
    }
}

pub type SharedLayer = Arc<dyn Layer>;
