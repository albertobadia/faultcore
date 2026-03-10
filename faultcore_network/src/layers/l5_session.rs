use crate::{
    Config, Direction,
    layers::{Layer, LayerDecision, LayerStage, PacketContext},
};
use parking_lot::Mutex;
use std::collections::HashMap;

#[derive(Clone, Copy)]
struct SessionState {
    started_monotonic_ns: u64,
    tx_bytes: u64,
    rx_bytes: u64,
    ops: u64,
}

pub struct L5Session {
    state_by_fd: Mutex<HashMap<i32, SessionState>>,
}

impl L5Session {
    pub fn new() -> Self {
        Self {
            state_by_fd: Mutex::new(HashMap::new()),
        }
    }

    fn action_decision(&self, config: &Config) -> LayerDecision {
        match config.session_action {
            1 => LayerDecision::Drop,
            2 => LayerDecision::TimeoutMs(config.session_budget_timeout_ms.max(1)),
            3 => LayerDecision::ConnectionErrorKind(if config.session_error_kind == 0 {
                1
            } else {
                config.session_error_kind
            }),
            _ => LayerDecision::Continue,
        }
    }

    pub fn precheck(
        &self,
        fd: i32,
        bytes: u64,
        direction: Direction,
        config: &Config,
        now_monotonic_ns: u64,
    ) -> LayerDecision {
        if fd < 0 || config.session_budget_enabled == 0 || config.session_action == 0 {
            return LayerDecision::Continue;
        }

        let mut map = self.state_by_fd.lock();
        let state = map.entry(fd).or_insert(SessionState {
            started_monotonic_ns: now_monotonic_ns,
            tx_bytes: 0,
            rx_bytes: 0,
            ops: 0,
        });

        if config.session_max_duration_ms > 0 {
            let duration_ns = config.session_max_duration_ms.saturating_mul(1_000_000);
            if now_monotonic_ns.saturating_sub(state.started_monotonic_ns) >= duration_ns {
                return self.action_decision(config);
            }
        }

        if config.session_max_ops > 0 && state.ops >= config.session_max_ops {
            return self.action_decision(config);
        }

        match direction {
            Direction::Uplink if config.session_max_bytes_tx > 0 => {
                if state.tx_bytes.saturating_add(bytes) > config.session_max_bytes_tx {
                    return self.action_decision(config);
                }
            }
            Direction::Downlink if config.session_max_bytes_rx > 0 => {
                if state.rx_bytes.saturating_add(bytes) > config.session_max_bytes_rx {
                    return self.action_decision(config);
                }
            }
            _ => {}
        }

        state.ops = state.ops.saturating_add(1);
        match direction {
            Direction::Uplink => {
                state.tx_bytes = state.tx_bytes.saturating_add(bytes);
            }
            Direction::Downlink => {
                state.rx_bytes = state.rx_bytes.saturating_add(bytes);
            }
        }
        LayerDecision::Continue
    }

    pub fn clear_fd_state(&self, fd: i32) {
        if fd < 0 {
            return;
        }
        self.state_by_fd.lock().remove(&fd);
    }
}

impl Default for L5Session {
    fn default() -> Self {
        Self::new()
    }
}

impl Layer for L5Session {
    fn stage(&self) -> LayerStage {
        LayerStage::L5
    }

    fn process(&self, _ctx: &PacketContext<'_>) -> LayerDecision {
        LayerDecision::Continue
    }

    fn name(&self) -> &str {
        "L5_Session"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn budget_config(action: u64) -> Config {
        Config {
            session_budget_enabled: 1,
            session_action: action,
            ..Default::default()
        }
    }

    #[test]
    fn precheck_enforces_max_ops_with_drop() {
        let layer = L5Session::new();
        let mut cfg = budget_config(1);
        cfg.session_max_ops = 1;

        assert!(matches!(
            layer.precheck(10, 10, Direction::Uplink, &cfg, 1_000),
            LayerDecision::Continue
        ));
        assert!(matches!(
            layer.precheck(10, 10, Direction::Uplink, &cfg, 1_001),
            LayerDecision::Drop
        ));
    }

    #[test]
    fn precheck_enforces_max_bytes_with_timeout_action() {
        let layer = L5Session::new();
        let mut cfg = budget_config(2);
        cfg.session_max_bytes_tx = 3;
        cfg.session_budget_timeout_ms = 55;

        assert!(matches!(
            layer.precheck(11, 2, Direction::Uplink, &cfg, 1_000),
            LayerDecision::Continue
        ));
        assert!(matches!(
            layer.precheck(11, 2, Direction::Uplink, &cfg, 1_001),
            LayerDecision::TimeoutMs(55)
        ));
    }

    #[test]
    fn precheck_enforces_duration_with_connection_error_action() {
        let layer = L5Session::new();
        let mut cfg = budget_config(3);
        cfg.session_max_duration_ms = 1;
        cfg.session_error_kind = 2;

        assert!(matches!(
            layer.precheck(12, 0, Direction::Downlink, &cfg, 1_000_000),
            LayerDecision::Continue
        ));
        assert!(matches!(
            layer.precheck(12, 0, Direction::Downlink, &cfg, 2_000_000),
            LayerDecision::ConnectionErrorKind(2)
        ));
    }

    #[test]
    fn clear_fd_state_resets_budget_state() {
        let layer = L5Session::new();
        let mut cfg = budget_config(1);
        cfg.session_max_ops = 1;

        assert!(matches!(
            layer.precheck(13, 1, Direction::Uplink, &cfg, 10),
            LayerDecision::Continue
        ));
        assert!(matches!(
            layer.precheck(13, 1, Direction::Uplink, &cfg, 11),
            LayerDecision::Drop
        ));

        layer.clear_fd_state(13);
        assert!(matches!(
            layer.precheck(13, 1, Direction::Uplink, &cfg, 12),
            LayerDecision::Continue
        ));
    }
}
