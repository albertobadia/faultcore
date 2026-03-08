use crate::{Config, Layer, LayerResult};

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
    fn process(&self, _config: &Config) -> LayerResult {
        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L5_Session"
    }
}
