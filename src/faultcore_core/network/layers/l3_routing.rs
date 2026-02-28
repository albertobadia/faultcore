use super::{Layer, LayerResult};
use crate::network::context::PacketContext;

pub struct RoutingLayer;

impl Layer for RoutingLayer {
    fn process(&self, _ctx: &mut PacketContext) -> LayerResult {
        // L3 placeholder. In the future, this reads Python ContextVars handles Mangle/Marking.
        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L3_Routing"
    }
}
