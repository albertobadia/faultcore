use crate::{Config, Layer, LayerResult};
use parking_lot::Mutex;
use rand::{Rng, SeedableRng, random, rngs::StdRng};
use std::collections::HashMap;

pub struct L4Transport {
    _connect_timeout_ms: u64,
    _recv_timeout_ms: u64,
    seeded_rng: Option<Mutex<StdRng>>,
    stream_bytes: Mutex<HashMap<i32, u64>>,
}

impl L4Transport {
    pub fn new(connect_timeout_ms: u64, recv_timeout_ms: u64) -> Self {
        let seeded_rng = std::env::var("FAULTCORE_SEED")
            .ok()
            .and_then(|raw| raw.parse::<u64>().ok())
            .map(|seed| Mutex::new(StdRng::seed_from_u64(seed)));
        Self {
            _connect_timeout_ms: connect_timeout_ms,
            _recv_timeout_ms: recv_timeout_ms,
            seeded_rng,
            stream_bytes: Mutex::new(HashMap::new()),
        }
    }

    pub fn with_config(config: &Config) -> Self {
        Self {
            _connect_timeout_ms: config.connect_timeout_ms,
            _recv_timeout_ms: config.recv_timeout_ms,
            seeded_rng: std::env::var("FAULTCORE_SEED")
                .ok()
                .and_then(|raw| raw.parse::<u64>().ok())
                .map(|seed| Mutex::new(StdRng::seed_from_u64(seed))),
            stream_bytes: Mutex::new(HashMap::new()),
        }
    }

    fn random_u32(&self) -> u32 {
        if let Some(rng) = &self.seeded_rng {
            rng.lock().next_u32()
        } else {
            random::<u32>()
        }
    }

    fn event_happens(&self, probability_ppm: u64) -> bool {
        if probability_ppm == 0 {
            return false;
        }
        if probability_ppm >= 1_000_000 {
            return true;
        }
        let random = self.random_u32() % 1_000_000;
        random < probability_ppm as u32
    }

    pub fn record_stream_bytes(&self, fd: i32, bytes: u64) {
        if bytes == 0 || fd < 0 {
            return;
        }
        let mut map = self.stream_bytes.lock();
        let current = map.get(&fd).copied().unwrap_or(0);
        map.insert(fd, current.saturating_add(bytes));
    }

    pub fn clear_fd_state(&self, fd: i32) {
        if fd < 0 {
            return;
        }
        self.stream_bytes.lock().remove(&fd);
    }

    pub fn connection_error_kind(&self, fd: i32, config: &Config, is_connect: bool) -> Option<u64> {
        if !is_connect && config.half_open_after_bytes > 0 {
            let seen = self.stream_bytes.lock().get(&fd).copied().unwrap_or(0);
            if seen >= config.half_open_after_bytes {
                let kind = if config.half_open_err_kind == 0 {
                    1
                } else {
                    config.half_open_err_kind
                };
                return Some(kind);
            }
        }
        if config.conn_err_kind > 0 && self.event_happens(config.conn_err_prob_ppm) {
            return Some(config.conn_err_kind);
        }
        None
    }

    pub fn timeout_for_connect(&self, config: &Config) -> LayerResult {
        if config.connect_timeout_ms > 0 {
            LayerResult::Timeout(config.connect_timeout_ms)
        } else {
            LayerResult::Continue
        }
    }

    pub fn timeout_for_stream(&self, config: &Config, is_recv: bool) -> LayerResult {
        if is_recv && config.recv_timeout_ms > 0 {
            LayerResult::Timeout(config.recv_timeout_ms)
        } else {
            LayerResult::Continue
        }
    }
}

impl Layer for L4Transport {
    fn process(&self, _config: &Config) -> LayerResult {
        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L4_Transport"
    }
}
