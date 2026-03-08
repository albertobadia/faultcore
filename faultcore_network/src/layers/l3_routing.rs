use crate::{Config, Layer, LayerResult};
use parking_lot::Mutex;
use rand::{Rng, SeedableRng, random, rngs::StdRng};

pub struct L3Routing {
    seeded_rng: Option<Mutex<StdRng>>,
}

impl L3Routing {
    pub fn new() -> Self {
        let seeded_rng = std::env::var("FAULTCORE_SEED")
            .ok()
            .and_then(|raw| raw.parse::<u64>().ok())
            .map(|seed| Mutex::new(StdRng::seed_from_u64(seed)));
        Self { seeded_rng }
    }

    pub fn with_seed(seed: u64) -> Self {
        Self {
            seeded_rng: Some(Mutex::new(StdRng::seed_from_u64(seed))),
        }
    }

    fn random_u32(&self) -> u32 {
        if let Some(rng) = &self.seeded_rng {
            rng.lock().next_u32()
        } else {
            random::<u32>()
        }
    }

    fn random_u64_bounded(&self, upper_inclusive: u64) -> u64 {
        if upper_inclusive == 0 {
            return 0;
        }
        let v = self.random_u32() as u64;
        v % (upper_inclusive + 1)
    }
}

impl Default for L3Routing {
    fn default() -> Self {
        Self::new()
    }
}

impl Layer for L3Routing {
    fn process(&self, config: &Config) -> LayerResult {
        if config.jitter_ns > 0 {
            return LayerResult::Delay(self.random_u64_bounded(config.jitter_ns));
        }
        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L3_Routing"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn jitter_is_bounded_by_config() {
        let layer = L3Routing::with_seed(7);
        let cfg = Config {
            jitter_ns: 5_000,
            ..Default::default()
        };

        for _ in 0..256 {
            match layer.process(&cfg) {
                LayerResult::Delay(ns) => {
                    assert!(ns <= 5_000);
                }
                other => panic!("expected Delay, got {other:?}"),
            }
        }
    }

    #[test]
    fn same_seed_produces_same_jitter_sequence() {
        let cfg = Config {
            jitter_ns: 10_000,
            ..Default::default()
        };
        let a = L3Routing::with_seed(123);
        let b = L3Routing::with_seed(123);

        let s1: Vec<u64> = (0..128)
            .map(|_| match a.process(&cfg) {
                LayerResult::Delay(ns) => ns,
                _ => 0,
            })
            .collect();
        let s2: Vec<u64> = (0..128)
            .map(|_| match b.process(&cfg) {
                LayerResult::Delay(ns) => ns,
                _ => 0,
            })
            .collect();
        assert_eq!(s1, s2);
    }
}
