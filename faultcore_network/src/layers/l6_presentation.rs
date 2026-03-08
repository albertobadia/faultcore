use crate::{Config, Layer, LayerResult};

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
    fn process(&self, _config: &Config) -> LayerResult {
        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L6_Presentation"
    }
}
