use crate::{Config, Layer, LayerResult};

pub struct L3Routing {
    _enabled: bool,
}

impl L3Routing {
    pub fn new() -> Self {
        Self { _enabled: true }
    }
}

impl Default for L3Routing {
    fn default() -> Self {
        Self::new()
    }
}

impl Layer for L3Routing {
    fn process(&self, _config: &Config) -> LayerResult {
        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L3_Routing"
    }
}
