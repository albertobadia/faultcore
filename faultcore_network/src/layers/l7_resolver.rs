use crate::layers::{Layer, LayerDecision, LayerStage, PacketContext};
use parking_lot::Mutex;
use rand::{Rng, SeedableRng, random, rngs::StdRng};

pub struct L7Resolver {
    seeded_rng: Option<Mutex<StdRng>>,
}

impl L7Resolver {
    pub fn new() -> Self {
        let seeded_rng = std::env::var("FAULTCORE_SEED")
            .ok()
            .and_then(|raw| raw.parse::<u64>().ok())
            .map(|seed| Mutex::new(StdRng::seed_from_u64(seed)));
        Self { seeded_rng }
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
        if self.event_happens(ctx.config.dns_nxdomain_ppm) {
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
