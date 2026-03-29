pub mod r1_session_guard;
pub mod r2_chaos_base;
pub mod r3_flow_control;
pub mod r4_timing_variation;
pub mod r5_transport_faults;
pub mod r6_resolver_faults;
pub mod r7_payload_transform;

pub use r1_session_guard::R1SessionGuard;
pub use r2_chaos_base::R2ChaosBase;
pub use r3_flow_control::R3FlowControl;
pub use r4_timing_variation::R4TimingVariation;
pub use r5_transport_faults::R5TransportFaults;
pub use r6_resolver_faults::R6ResolverFaults;
pub use r7_payload_transform::R7PayloadTransform;

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
    R0,
    R1,
    R2,
    R3,
    R4,
    R5,
    R6,
    R7,
    R8,
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
