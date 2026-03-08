use crate::layers::{Layer, LayerDecision, LayerStage, PacketContext};

pub struct L6Presentation;

impl L6Presentation {
    pub fn new() -> Self {
        Self
    }
}

impl Default for L6Presentation {
    fn default() -> Self {
        Self::new()
    }
}

impl Layer for L6Presentation {
    fn stage(&self) -> LayerStage {
        LayerStage::L6
    }

    fn process(&self, _ctx: &PacketContext<'_>) -> LayerDecision {
        LayerDecision::Continue
    }

    fn name(&self) -> &str {
        "L6_Presentation"
    }
}
