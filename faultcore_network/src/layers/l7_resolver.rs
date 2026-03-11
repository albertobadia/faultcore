use crate::layers::{Layer, LayerDecision, LayerStage, PacketContext};
use parking_lot::Mutex;
use rand::{Rng, SeedableRng, random, rngs::StdRng};
use std::sync::atomic::{AtomicU64, Ordering};

pub struct L7Resolver {
    seeded_rng: Option<Mutex<StdRng>>,
    policy_counter: AtomicU64,
}

impl L7Resolver {
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
            let mixed = Self::splitmix64(policy_seed ^ 0x4C37_0A05 ^ step);
            return (mixed & 0xFFFF_FFFF) as u32;
        }
        if let Some(rng) = &self.seeded_rng {
            rng.lock().next_u32()
        } else {
            random::<u32>()
        }
    }

    fn event_happens(&self, probability_ppm: u64, policy_seed: u64) -> bool {
        if probability_ppm == 0 {
            return false;
        }
        if probability_ppm >= 1_000_000 {
            return true;
        }
        let random = self.random_u32(policy_seed) % 1_000_000;
        random < probability_ppm as u32
    }
}

impl Layer for L7Resolver {
    fn stage(&self) -> LayerStage {
        LayerStage::L7
    }

    fn applies_to(&self, ctx: &PacketContext<'_>) -> bool {
        ctx.is_dns()
    }

    fn process(&self, ctx: &PacketContext<'_>) -> LayerDecision {
        if ctx.config.dns_timeout_ms > 0 {
            return LayerDecision::TimeoutMs(ctx.config.dns_timeout_ms);
        }
        if self.event_happens(ctx.config.dns_nxdomain_ppm, ctx.config.policy_seed) {
            return LayerDecision::NxDomain;
        }
        if ctx.config.dns_delay_ns > 0 {
            return LayerDecision::DelayNs(ctx.config.dns_delay_ns);
        }
        LayerDecision::Continue
    }

    fn name(&self) -> &str {
        "L7_Resolver"
    }
}

impl Default for L7Resolver {
    fn default() -> Self {
        Self::new()
    }
}
