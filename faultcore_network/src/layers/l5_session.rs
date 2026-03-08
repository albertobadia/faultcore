use crate::layers::{Layer, LayerDecision, LayerStage, PacketContext};

pub struct L5Session;

impl L5Session {
    pub fn new() -> Self {
        Self
    }
}

impl Default for L5Session {
    fn default() -> Self {
        Self::new()
    }
}

impl Layer for L5Session {
    fn stage(&self) -> LayerStage {
        LayerStage::L5
    }

    fn process(&self, _ctx: &PacketContext<'_>) -> LayerDecision {
        LayerDecision::Continue
    }

    fn name(&self) -> &str {
        "L5_Session"
    }
}
