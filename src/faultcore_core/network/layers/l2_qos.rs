use super::{Layer, LayerResult};
use crate::network::context::PacketContext;
use std::sync::{Arc, Mutex};
use std::time::Instant;

/// Configuration for shaping traffic.
#[derive(Clone, Debug)]
pub struct QoSConfig {
    pub rate: f64,     // tokens per second
    pub capacity: f64, // max tokens
}

/// L2 Layer implementing a simple Token Bucket for QoS.
pub struct QoSLayer {
    config: QoSConfig,
    tokens: Arc<Mutex<(f64, Instant)>>,
}

impl QoSLayer {
    pub fn new(config: QoSConfig) -> Self {
        Self {
            tokens: Arc::new(Mutex::new((config.capacity, Instant::now()))),
            config,
        }
    }

    fn refill_tokens(tokens: &mut (f64, Instant), rate: f64, capacity: f64) {
        let elapsed = tokens.1.elapsed().as_secs_f64();
        let new_tokens = elapsed * rate;
        tokens.0 = (tokens.0 + new_tokens).min(capacity);
        tokens.1 = Instant::now();
    }
}

impl Layer for QoSLayer {
    fn process(&self, _ctx: &mut PacketContext) -> LayerResult {
        let mut tokens = self.tokens.lock().unwrap();
        Self::refill_tokens(&mut tokens, self.config.rate, self.config.capacity);

        if tokens.0 >= 1.0 {
            tokens.0 -= 1.0;
            LayerResult::Continue
        } else {
            LayerResult::Drop
        }
    }

    fn name(&self) -> &str {
        "L2_QoS"
    }
}
