use crate::{Config, Layer, LayerResult};
use parking_lot::Mutex;
use rand::{Rng, SeedableRng, random, rngs::StdRng};

pub struct L1Chaos {
    seeded_rng: Option<Mutex<StdRng>>,
}

impl L1Chaos {
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

    pub fn with_latency(_latency_ms: u64) -> Self {
        Self::new()
    }

    fn random_u32(&self) -> u32 {
        if let Some(rng) = &self.seeded_rng {
            rng.lock().r#gen::<u32>()
        } else {
            random::<u32>()
        }
    }

    fn should_drop(&self, packet_loss_ppm: u64) -> bool {
        if packet_loss_ppm == 0 {
            return false;
        }
        let drop_threshold = 1_000_000.0 / packet_loss_ppm as f64;
        let random = self.random_u32();
        (random as f64) % drop_threshold < 1.0
    }
}

impl Default for L1Chaos {
    fn default() -> Self {
        Self::new()
    }
}

impl Layer for L1Chaos {
    fn process(&self, config: &Config) -> LayerResult {
        if self.should_drop(config.packet_loss_ppm) {
            return LayerResult::Drop;
        }

        if config.latency_ns > 0 {
            return LayerResult::Delay(config.latency_ns);
        }

        LayerResult::Continue
    }

    fn name(&self) -> &str {
        "L1_Chaos"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn drop_sequence(seed: u64, packet_loss_ppm: u64, n: usize) -> Vec<bool> {
        let layer = L1Chaos::with_seed(seed);
        let cfg = Config {
            packet_loss_ppm,
            ..Default::default()
        };
        (0..n)
            .map(|_| matches!(layer.process(&cfg), LayerResult::Drop))
            .collect()
    }

    #[test]
    fn same_seed_produces_same_drop_sequence() {
        let seq1 = drop_sequence(42, 250_000, 512);
        let seq2 = drop_sequence(42, 250_000, 512);
        assert_eq!(seq1, seq2);
    }

    #[test]
    fn different_seed_produces_different_drop_sequence() {
        let seq1 = drop_sequence(42, 250_000, 512);
        let seq2 = drop_sequence(43, 250_000, 512);
        assert_ne!(seq1, seq2);
    }

    #[test]
    fn env_seed_produces_deterministic_sequence_across_instances() {
        unsafe {
            std::env::set_var("FAULTCORE_SEED", "1337");
        }

        let cfg = Config {
            packet_loss_ppm: 250_000,
            ..Default::default()
        };
        let first = L1Chaos::new();
        let second = L1Chaos::new();

        let seq1: Vec<bool> = (0..256)
            .map(|_| matches!(first.process(&cfg), LayerResult::Drop))
            .collect();
        let seq2: Vec<bool> = (0..256)
            .map(|_| matches!(second.process(&cfg), LayerResult::Drop))
            .collect();

        assert_eq!(seq1, seq2);

        unsafe {
            std::env::remove_var("FAULTCORE_SEED");
        }
    }
}
