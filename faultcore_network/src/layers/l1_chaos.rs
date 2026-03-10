use crate::{
    Config,
    layers::{Layer, LayerDecision, LayerStage, PacketContext},
};
use parking_lot::Mutex;
use rand::{Rng, SeedableRng, random, rngs::StdRng};
use std::collections::HashMap;

pub struct L1Chaos {
    seeded_rng: Option<Mutex<StdRng>>,
    burst_remaining_by_fd: Mutex<HashMap<i32, u64>>,
    ge_state_by_fd: Mutex<HashMap<i32, u8>>,
}

impl L1Chaos {
    pub fn new() -> Self {
        let seeded_rng = std::env::var("FAULTCORE_SEED")
            .ok()
            .and_then(|raw| raw.parse::<u64>().ok())
            .map(|seed| Mutex::new(StdRng::seed_from_u64(seed)));
        Self {
            seeded_rng,
            burst_remaining_by_fd: Mutex::new(HashMap::new()),
            ge_state_by_fd: Mutex::new(HashMap::new()),
        }
    }

    pub fn with_seed(seed: u64) -> Self {
        Self {
            seeded_rng: Some(Mutex::new(StdRng::seed_from_u64(seed))),
            burst_remaining_by_fd: Mutex::new(HashMap::new()),
            ge_state_by_fd: Mutex::new(HashMap::new()),
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

    fn correlated_loss_ppm(&self, fd: i32, config: &Config) -> Option<u64> {
        if config.ge_enabled == 0 {
            return None;
        }

        let mut ge_state_by_fd = self.ge_state_by_fd.lock();
        let current_state = ge_state_by_fd.get(&fd).copied().unwrap_or(0);
        let mut next_state = current_state;
        if current_state == 0 {
            if self.event_happens(config.ge_p_good_to_bad_ppm) {
                next_state = 1;
            }
        } else if self.event_happens(config.ge_p_bad_to_good_ppm) {
            next_state = 0;
        }

        if next_state == 0 {
            ge_state_by_fd.remove(&fd);
            Some(config.ge_loss_good_ppm)
        } else {
            ge_state_by_fd.insert(fd, 1);
            Some(config.ge_loss_bad_ppm)
        }
    }

    fn duplicate_extra(&self, config: &Config) -> u64 {
        if config.dup_prob_ppm == 0 {
            return 0;
        }
        let max_extra = if config.dup_max_extra == 0 {
            1
        } else {
            config.dup_max_extra
        };
        let mut count = 0;
        for _ in 0..max_extra {
            if self.event_happens(config.dup_prob_ppm) {
                count += 1;
            }
        }
        count
    }

    pub fn should_reorder(&self, config: &Config) -> bool {
        self.event_happens(config.reorder_prob_ppm)
    }

    pub fn duplicate_decision(&self, config: &Config) -> LayerDecision {
        let count = self.duplicate_extra(config);
        if count > 0 {
            LayerDecision::Duplicate(count)
        } else {
            LayerDecision::Continue
        }
    }

    pub fn reorder_decision(&self, config: &Config) -> LayerDecision {
        if self.should_reorder(config) {
            LayerDecision::StageReorder
        } else {
            LayerDecision::Continue
        }
    }
}

impl Default for L1Chaos {
    fn default() -> Self {
        Self::new()
    }
}

impl Layer for L1Chaos {
    fn stage(&self) -> LayerStage {
        LayerStage::L1
    }

    fn applies_to(&self, ctx: &PacketContext<'_>) -> bool {
        !ctx.is_dns()
    }

    fn process(&self, ctx: &PacketContext<'_>) -> LayerDecision {
        let config = ctx.config;
        {
            let mut map = self.burst_remaining_by_fd.lock();
            if let Some(current) = map.get_mut(&ctx.fd)
                && *current > 0
            {
                *current -= 1;
                if *current == 0 {
                    map.remove(&ctx.fd);
                }
                return LayerDecision::Drop;
            }
        }

        let effective_loss = self
            .correlated_loss_ppm(ctx.fd, config)
            .unwrap_or(config.packet_loss_ppm);
        if self.event_happens(effective_loss) {
            if config.burst_loss_len > 0 {
                self.burst_remaining_by_fd
                    .lock()
                    .insert(ctx.fd, config.burst_loss_len.saturating_sub(1));
            }
            return LayerDecision::Drop;
        }

        if config.latency_ns > 0 {
            return LayerDecision::DelayNs(config.latency_ns);
        }

        LayerDecision::Continue
    }

    fn name(&self) -> &str {
        "L1_Chaos"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::layers::Operation;

    fn drop_sequence(seed: u64, packet_loss_ppm: u64, n: usize) -> Vec<bool> {
        let layer = L1Chaos::with_seed(seed);
        let cfg = Config {
            packet_loss_ppm,
            ..Default::default()
        };
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg,
        };
        (0..n)
            .map(|_| matches!(layer.process(&ctx), LayerDecision::Drop))
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
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg,
        };

        let seq1: Vec<bool> = (0..256)
            .map(|_| matches!(first.process(&ctx), LayerDecision::Drop))
            .collect();
        let seq2: Vec<bool> = (0..256)
            .map(|_| matches!(second.process(&ctx), LayerDecision::Drop))
            .collect();

        assert_eq!(seq1, seq2);

        unsafe {
            std::env::remove_var("FAULTCORE_SEED");
        }
    }

    #[test]
    fn burst_loss_drops_remaining_packets() {
        let layer = L1Chaos::with_seed(1);
        layer.burst_remaining_by_fd.lock().insert(1, 2);
        let cfg = Config::default();
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg,
        };

        assert!(matches!(layer.process(&ctx), LayerDecision::Drop));
        assert!(matches!(layer.process(&ctx), LayerDecision::Drop));
        assert!(matches!(layer.process(&ctx), LayerDecision::Continue));
    }

    #[test]
    fn packet_loss_starts_burst_sequence() {
        let layer = L1Chaos::with_seed(1);
        let cfg = Config {
            packet_loss_ppm: 1_000_000,
            burst_loss_len: 4,
            ..Default::default()
        };
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg,
        };

        assert!(matches!(layer.process(&ctx), LayerDecision::Drop));
        let remaining = layer
            .burst_remaining_by_fd
            .lock()
            .get(&1)
            .copied()
            .unwrap_or(0);
        assert_eq!(remaining, 3);
    }

    #[test]
    fn correlated_loss_can_force_bad_state_and_drop() {
        let layer = L1Chaos::with_seed(5);
        let cfg = Config {
            ge_enabled: 1,
            ge_p_good_to_bad_ppm: 1_000_000,
            ge_p_bad_to_good_ppm: 0,
            ge_loss_good_ppm: 0,
            ge_loss_bad_ppm: 1_000_000,
            ..Default::default()
        };
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg,
        };

        assert!(matches!(layer.process(&ctx), LayerDecision::Drop));
    }

    #[test]
    fn correlated_loss_in_good_state_can_avoid_drop() {
        let layer = L1Chaos::with_seed(5);
        let cfg = Config {
            ge_enabled: 1,
            ge_p_good_to_bad_ppm: 0,
            ge_p_bad_to_good_ppm: 1_000_000,
            ge_loss_good_ppm: 0,
            ge_loss_bad_ppm: 1_000_000,
            ..Default::default()
        };
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg,
        };

        assert!(matches!(layer.process(&ctx), LayerDecision::Continue));
    }

    #[test]
    fn burst_state_must_not_leak_between_fds() {
        let layer = L1Chaos::with_seed(1);
        let cfg_trigger = Config {
            packet_loss_ppm: 1_000_000,
            burst_loss_len: 2,
            ..Default::default()
        };
        let cfg_clean = Config::default();

        let ctx_fd1 = PacketContext {
            fd: 10,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg_trigger,
        };
        let ctx_fd2 = PacketContext {
            fd: 11,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg_clean,
        };

        assert!(matches!(layer.process(&ctx_fd1), LayerDecision::Drop));
        assert!(matches!(layer.process(&ctx_fd2), LayerDecision::Continue));
    }

    #[test]
    fn correlated_loss_state_must_not_leak_between_fds() {
        let layer = L1Chaos::with_seed(1);
        let cfg_fd1 = Config {
            ge_enabled: 1,
            ge_p_good_to_bad_ppm: 1_000_000,
            ge_p_bad_to_good_ppm: 0,
            ge_loss_good_ppm: 0,
            ge_loss_bad_ppm: 1_000_000,
            ..Default::default()
        };
        let cfg_fd2 = Config {
            ge_enabled: 1,
            ge_p_good_to_bad_ppm: 0,
            ge_p_bad_to_good_ppm: 0,
            ge_loss_good_ppm: 0,
            ge_loss_bad_ppm: 1_000_000,
            ..Default::default()
        };

        let ctx_fd1 = PacketContext {
            fd: 20,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg_fd1,
        };
        let ctx_fd2 = PacketContext {
            fd: 21,
            bytes: 1,
            operation: Operation::Recv,
            direction: None,
            config: &cfg_fd2,
        };

        assert!(matches!(layer.process(&ctx_fd1), LayerDecision::Drop));
        assert!(matches!(layer.process(&ctx_fd2), LayerDecision::Continue));
    }
}
