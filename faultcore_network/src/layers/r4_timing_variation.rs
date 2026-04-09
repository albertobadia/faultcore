use crate::layers::{Layer, LayerDecision, LayerStage, PacketContext};
use parking_lot::Mutex;
use rand::{Rng, SeedableRng, random, rngs::StdRng};
use std::sync::atomic::{AtomicU64, Ordering};

pub struct R4TimingVariation {
    seeded_rng: Option<Mutex<StdRng>>,
    policy_counter: AtomicU64,
}

impl R4TimingVariation {
    pub fn new() -> Self {
        let seeded_rng = std::env::var("FAULTCORE_SEED")
            .ok()
            .and_then(|raw| raw.parse::<u64>().ok())
            .map(|seed| Mutex::new(StdRng::seed_from_u64(seed)));
        Self {
            seeded_rng,
            policy_counter: AtomicU64::new(0),
        }
    }

    pub fn with_seed(seed: u64) -> Self {
        Self {
            seeded_rng: Some(Mutex::new(StdRng::seed_from_u64(seed))),
            policy_counter: AtomicU64::new(0),
        }
    }

    fn splitmix64(mut x: u64) -> u64 {
        x = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = x;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    fn random_u32(&self, policy_seed: u64) -> u32 {
        if policy_seed > 0 {
            let step = self.policy_counter.fetch_add(1, Ordering::Relaxed);
            let mixed = Self::splitmix64(policy_seed ^ 0x4C33_0A05 ^ step);
            return (mixed & 0xFFFF_FFFF) as u32;
        }
        if let Some(rng) = &self.seeded_rng {
            rng.lock().next_u32()
        } else {
            random::<u32>()
        }
    }

    fn random_u64_bounded(&self, upper_inclusive: u64, policy_seed: u64) -> u64 {
        if upper_inclusive == 0 {
            return 0;
        }
        let v = self.random_u32(policy_seed) as u64;
        v % (upper_inclusive + 1)
    }
}

impl Default for R4TimingVariation {
    fn default() -> Self {
        Self::new()
    }
}

impl Layer for R4TimingVariation {
    fn stage(&self) -> LayerStage {
        LayerStage::R4
    }

    fn applies_to(&self, ctx: &PacketContext<'_>) -> bool {
        !ctx.is_dns()
    }

    fn process(&self, ctx: &PacketContext<'_>) -> LayerDecision {
        if ctx.config.jitter_ns > 0 {
            return LayerDecision::DelayNs(
                self.random_u64_bounded(ctx.config.jitter_ns, ctx.config.policy_seed),
            );
        }
        LayerDecision::Continue
    }

    fn name(&self) -> &str {
        "R4_TimingVariation"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn jitter_is_bounded_by_config() {
        let layer = R4TimingVariation::with_seed(7);
        let cfg = crate::Config {
            jitter_ns: 5_000,
            ..Default::default()
        };
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: crate::layers::Operation::Recv,
            direction: None,
            config: &cfg,
            now_ns: 0,
        };

        for _ in 0..256 {
            match layer.process(&ctx) {
                LayerDecision::DelayNs(ns) => {
                    assert!(ns <= 5_000);
                }
                other => panic!("expected Delay, got {other:?}"),
            }
        }
    }

    #[test]
    fn same_seed_produces_same_jitter_sequence() {
        let cfg = crate::Config {
            jitter_ns: 10_000,
            ..Default::default()
        };
        let a = R4TimingVariation::with_seed(123);
        let b = R4TimingVariation::with_seed(123);
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: crate::layers::Operation::Recv,
            direction: None,
            config: &cfg,
            now_ns: 0,
        };

        let s1: Vec<u64> = (0..128)
            .map(|_| match a.process(&ctx) {
                LayerDecision::DelayNs(ns) => ns,
                _ => 0,
            })
            .collect();
        let s2: Vec<u64> = (0..128)
            .map(|_| match b.process(&ctx) {
                LayerDecision::DelayNs(ns) => ns,
                _ => 0,
            })
            .collect();
        assert_eq!(s1, s2);
    }

    #[test]
    fn policy_seed_produces_same_jitter_sequence_across_instances() {
        let cfg = crate::Config {
            jitter_ns: 10_000,
            policy_seed: 777,
            ..Default::default()
        };
        let a = R4TimingVariation::new();
        let b = R4TimingVariation::new();
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: crate::layers::Operation::Recv,
            direction: None,
            config: &cfg,
            now_ns: 0,
        };

        let s1: Vec<u64> = (0..128)
            .map(|_| match a.process(&ctx) {
                LayerDecision::DelayNs(ns) => ns,
                _ => 0,
            })
            .collect();
        let s2: Vec<u64> = (0..128)
            .map(|_| match b.process(&ctx) {
                LayerDecision::DelayNs(ns) => ns,
                _ => 0,
            })
            .collect();
        assert_eq!(s1, s2);
    }
}
