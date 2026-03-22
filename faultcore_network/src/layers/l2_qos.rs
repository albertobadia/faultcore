use crate::{
    layers::{Layer, LayerDecision, LayerStage, PacketContext},
    Config,
};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

use parking_lot::Mutex;

pub struct L2QoS {
    rate_bps: u64,
    capacity_tokens: f64,
    tokens: AtomicU64,
    last_refill: Mutex<Instant>,
}

impl L2QoS {
    pub fn new(rate_bps: u64, capacity_tokens: f64) -> Self {
        Self {
            rate_bps,
            capacity_tokens,
            tokens: AtomicU64::new(capacity_tokens as u64),
            last_refill: Mutex::new(Instant::now()),
        }
    }

    pub fn with_rate(rate_bps: u64) -> Self {
        Self::new(rate_bps, rate_bps as f64 * 2.0)
    }

    fn refill(&self, rate_bps: u64, capacity_tokens: f64) {
        if rate_bps == 0 {
            return;
        }

        let mut last = self.last_refill.lock();
        let elapsed = last.elapsed().as_secs_f64();
        if elapsed <= 0.0 {
            return;
        }

        let new_tokens = elapsed * rate_bps as f64;
        *last = Instant::now();

        let current = self.tokens.load(Ordering::Acquire);
        let new_value = (current as f64 + new_tokens).min(capacity_tokens) as u64;
        self.tokens.store(new_value, Ordering::Release);
    }

    fn try_acquire(&self, tokens_needed: u64, rate_bps: u64, capacity_tokens: f64) -> bool {
        self.refill(rate_bps, capacity_tokens);

        loop {
            let current = self.tokens.load(Ordering::Acquire);
            if current >= tokens_needed {
                let new_value = current - tokens_needed;
                if self
                    .tokens
                    .compare_exchange_weak(current, new_value, Ordering::Release, Ordering::Acquire)
                    .is_ok()
                {
                    return true;
                }
            } else {
                return false;
            }
        }
    }
    fn process_with_bytes(&self, bytes: u64, config: &Config) -> LayerDecision {
        let has_override_rate = config.bandwidth_bps > 0;
        let rate = if has_override_rate {
            config.bandwidth_bps
        } else {
            self.rate_bps
        };

        if rate == 0 {
            return LayerDecision::Continue;
        }

        let bits_needed = bytes.saturating_mul(8);
        let capacity_tokens = if has_override_rate {
            (rate as f64) * 2.0
        } else {
            self.capacity_tokens
        };

        if self.try_acquire(bits_needed, rate, capacity_tokens) {
            LayerDecision::Continue
        } else {
            let current = self.tokens.load(Ordering::Acquire);
            let deficit = bits_needed.saturating_sub(current);
            let delay_secs = deficit as f64 / rate as f64;
            let delay_ns = (delay_secs * 1_000_000_000.0) as u64;

            if delay_ns > 0 {
                LayerDecision::DelayNs(delay_ns)
            } else {
                LayerDecision::Continue
            }
        }
    }
}

impl Layer for L2QoS {
    fn stage(&self) -> LayerStage {
        LayerStage::L2
    }

    fn applies_to(&self, ctx: &PacketContext<'_>) -> bool {
        ctx.is_stream()
    }

    fn process(&self, ctx: &PacketContext<'_>) -> LayerDecision {
        self.process_with_bytes(ctx.bytes, ctx.config)
    }

    fn name(&self) -> &str {
        "L2_QoS"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn test_qos_refill_concurrency() {
        let qos = Arc::new(L2QoS::new(1000, 2000.0));
        let handles: Vec<_> = (0..10)
            .map(|_| {
                let qos_clone = Arc::clone(&qos);
                thread::spawn(move || {
                    for _ in 0..100 {
                        qos_clone.try_acquire(10, 1000, 2000.0);
                        thread::sleep(std::time::Duration::from_millis(1));
                    }
                })
            })
            .collect();

        for handle in handles {
            handle.join().unwrap();
        }
    }

    #[test]
    fn test_process_with_dynamic_rate_refills_tokens() {
        let qos = L2QoS::new(0, 0.0);
        let config = Config {
            bandwidth_bps: 80,
            ..Default::default()
        };
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: crate::layers::Operation::Recv,
            direction: None,
            config: &config,
            now_ns: 0,
        };

        assert!(matches!(qos.process(&ctx), LayerDecision::DelayNs(_)));

        thread::sleep(Duration::from_millis(120));

        assert!(matches!(qos.process(&ctx), LayerDecision::Continue));
    }

    #[test]
    fn test_bandwidth_bps_uses_bit_units_for_delay() {
        let qos = L2QoS::new(0, 0.0);
        let config = Config {
            bandwidth_bps: 8,
            ..Default::default()
        };
        let ctx = PacketContext {
            fd: 1,
            bytes: 1,
            operation: crate::layers::Operation::Recv,
            direction: None,
            config: &config,
            now_ns: 0,
        };

        match qos.process(&ctx) {
            LayerDecision::DelayNs(delay_ns) => {
                assert!(delay_ns >= 900_000_000, "delay_ns={delay_ns}");
                assert!(delay_ns <= 1_100_000_000, "delay_ns={delay_ns}");
            }
            other => panic!("expected Delay, got {other:?}"),
        }
    }
}
