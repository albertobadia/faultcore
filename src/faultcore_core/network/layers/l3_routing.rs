use super::{Layer, LayerResult};
use crate::network::context::PacketContext;

pub struct RoutingLayer;

impl Layer for RoutingLayer {
    fn process(&self, _ctx: &mut PacketContext) -> LayerResult {
        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L3_Routing"
    }
}
