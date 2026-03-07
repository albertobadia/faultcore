use crate::{Config, Layer, LayerResult};

pub struct L4Transport {
    _connect_timeout_ms: u64,
    _recv_timeout_ms: u64,
}

impl L4Transport {
    pub fn new(connect_timeout_ms: u64, recv_timeout_ms: u64) -> Self {
        Self {
            _connect_timeout_ms: connect_timeout_ms,
            _recv_timeout_ms: recv_timeout_ms,
        }
    }

    pub fn with_config(config: &Config) -> Self {
        Self {
            _connect_timeout_ms: config.connect_timeout_ms,
            _recv_timeout_ms: config.recv_timeout_ms,
        }
    }
}

impl Layer for L4Transport {
    fn process(&self, config: &Config) -> LayerResult {
        let timeout_ms = if config.connect_timeout_ms > 0 {
            config.connect_timeout_ms
        } else if config.recv_timeout_ms > 0 {
            config.recv_timeout_ms
        } else {
            return LayerResult::Continue;
        };

        LayerResult::Timeout(timeout_ms)
    }

    fn name(&self) -> &str {
        "L4_Transport"
    }
}
