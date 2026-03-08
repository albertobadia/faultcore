use crate::Config;
use parking_lot::Mutex;
use rand::{Rng, SeedableRng, random, rngs::StdRng};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DnsAction {
    Continue,
    Delay(u64),
    Timeout(u64),
    NxDomain,
}

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

    pub fn process_dns(&self, config: &Config) -> DnsAction {
        if config.dns_timeout_ms > 0 {
            return DnsAction::Timeout(config.dns_timeout_ms);
        }
        if self.event_happens(config.dns_nxdomain_ppm) {
            return DnsAction::NxDomain;
        }
        if config.dns_delay_ns > 0 {
            return DnsAction::Delay(config.dns_delay_ns);
        }
        DnsAction::Continue
    }
}

impl Default for L7Resolver {
    fn default() -> Self {
        Self::new()
    }
}
