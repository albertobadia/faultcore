use super::{Layer, LayerResult};
use crate::network::context::PacketContext;

pub struct TransportLayer;

impl Layer for TransportLayer {
    fn process(&self, _ctx: &mut PacketContext) -> LayerResult {
        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L4_Transport"
    }
}
