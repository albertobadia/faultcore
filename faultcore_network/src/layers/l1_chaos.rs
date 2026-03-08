use crate::{Config, Layer, LayerResult};
use parking_lot::Mutex;
use rand::{Rng, SeedableRng, random, rngs::StdRng};
use std::sync::atomic::{AtomicU64, Ordering};

pub struct L1Chaos {
    seeded_rng: Option<Mutex<StdRng>>,
    burst_remaining: AtomicU64,
}

impl L1Chaos {
    pub fn new() -> Self {
        let seeded_rng = std::env::var("FAULTCORE_SEED")
            .ok()
            .and_then(|raw| raw.parse::<u64>().ok())
            .map(|seed| Mutex::new(StdRng::seed_from_u64(seed)));
        Self {
            seeded_rng,
            burst_remaining: AtomicU64::new(0),
        }
    }

    pub fn with_seed(seed: u64) -> Self {
        Self {
            seeded_rng: Some(Mutex::new(StdRng::seed_from_u64(seed))),
            burst_remaining: AtomicU64::new(0),
        }
    }

    pub fn with_latency(_latency_ms: u64) -> Self {
        Self::new()
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
        if self
            .burst_remaining
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |current| {
                if current > 0 {
                    Some(current - 1)
                } else {
                    None
                }
            })
            .is_ok()
        {
            return LayerResult::Drop;
        }

        if self.should_drop(config.packet_loss_ppm) {
            if config.burst_loss_len > 0 {
                self.burst_remaining
                    .store(config.burst_loss_len.saturating_sub(1), Ordering::Release);
            }
            return LayerResult::Drop;
        }

        if config.latency_ns > 0 || config.jitter_ns > 0 {
            let jitter = self.random_u64_bounded(config.jitter_ns);
            return LayerResult::Delay(config.latency_ns.saturating_add(jitter));
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

    #[test]
    fn jitter_is_bounded_by_config() {
        let layer = L1Chaos::with_seed(7);
        let cfg = Config {
            latency_ns: 1_000,
            jitter_ns: 5_000,
            ..Default::default()
        };

        for _ in 0..256 {
            match layer.process(&cfg) {
                LayerResult::Delay(ns) => {
                    assert!(ns >= 1_000);
                    assert!(ns <= 6_000);
                }
                other => panic!("expected Delay, got {other:?}"),
            }
        }
    }

    #[test]
    fn burst_loss_drops_remaining_packets() {
        let layer = L1Chaos::with_seed(1);
        layer.burst_remaining.store(2, Ordering::Release);
        let cfg = Config::default();

        assert!(matches!(layer.process(&cfg), LayerResult::Drop));
        assert!(matches!(layer.process(&cfg), LayerResult::Drop));
        assert!(matches!(layer.process(&cfg), LayerResult::Continue));
    }

    #[test]
    fn packet_loss_starts_burst_sequence() {
        let layer = L1Chaos::with_seed(1);
        let cfg = Config {
            packet_loss_ppm: 1_000_000,
            burst_loss_len: 4,
            ..Default::default()
        };

        assert!(matches!(layer.process(&cfg), LayerResult::Drop));
        assert_eq!(layer.burst_remaining.load(Ordering::Acquire), 3);
    }
}
