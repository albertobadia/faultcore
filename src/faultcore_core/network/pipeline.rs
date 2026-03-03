use super::context::PacketContext;
use super::layers::{LayerResult, SharedLayer};

pub struct Pipeline {
    layers: Vec<SharedLayer>,
}

impl Pipeline {
    pub fn new() -> Self {
        Self { layers: Vec::new() }
    }

    pub fn add_layer(&mut self, layer: SharedLayer) {
        self.layers.push(layer);
    }

    pub fn process(&self, ctx: &mut PacketContext) -> LayerResult {
        for layer in &self.layers {
            match layer.process(ctx) {
                LayerResult::Continue => continue,
                LayerResult::Drop => {
                    ctx.dropped = true;
                    return LayerResult::Drop;
                }
                LayerResult::Error(e) => return LayerResult::Error(e),
            }
        }
        LayerResult::Continue
    }
}

impl Default for Pipeline {
    fn default() -> Self {
        Self::new()
    }
}
