use libc::{c_int, sockaddr, socklen_t};

use crate::{
    Config, Endpoint, TargetRule, assign_rule_to_fd, clear_rule_for_fd, endpoint_for_addr_or_fd, endpoint_for_fd,
    get_config_for_fd, get_config_for_tid, get_target_rules_for_tid_slot, get_thread_id,
    get_tid_slot_for_fd, monotonic_now_ns, try_open_shm,
};

fn endpoint_matches_rule(endpoint: Endpoint, rule: &TargetRule) -> bool {
    if rule.enabled == 0 || rule.kind == 0 {
        return false;
    }
    if rule.protocol > 0 && rule.protocol != endpoint.protocol {
        return false;
    }
    if rule.port > 0 && rule.port != u64::from(endpoint.port) {
        return false;
    }
    match rule.kind {
        1 => endpoint.ipv4 == rule.ipv4 as u32,
        2 => {
            if rule.prefix_len == 0 {
                true
            } else if rule.prefix_len >= 32 {
                endpoint.ipv4 == rule.ipv4 as u32
            } else {
                let mask = u32::MAX << (32 - rule.prefix_len as u32);
                (endpoint.ipv4 & mask) == ((rule.ipv4 as u32) & mask)
            }
        }
        _ => false,
    }
}

fn select_best_target_rule(
    endpoint: Endpoint,
    rules: &[TargetRule],
    count: usize,
) -> Option<TargetRule> {
    let mut selected_idx: Option<usize> = None;
    let mut selected_priority: u64 = 0;
    let limit = usize::min(count, rules.len());

    for (idx, rule) in rules.iter().take(limit).enumerate() {
        if !endpoint_matches_rule(endpoint, rule) {
            continue;
        }
        if selected_idx.is_none() || rule.priority > selected_priority {
            selected_idx = Some(idx);
            selected_priority = rule.priority;
        }
    }
    selected_idx.map(|idx| rules[idx])
}

fn apply_multi_target_for_fd(mut cfg: Config, fd: c_int, endpoint: Option<Endpoint>) -> Option<Config> {
    if cfg.target_enabled <= 1 {
        return cfg.runtime_filtered(endpoint, monotonic_now_ns());
    }
    let endpoint = endpoint?;
    let slot = get_tid_slot_for_fd(fd)?;
    let rules = get_target_rules_for_tid_slot(slot)?;
    let count = usize::min(cfg.target_enabled as usize, rules.len());
    let rule = select_best_target_rule(endpoint, &rules, count)?;
    cfg.target_enabled = 1;
    cfg.target_kind = rule.kind;
    cfg.target_ipv4 = rule.ipv4;
    cfg.target_prefix_len = rule.prefix_len;
    cfg.target_port = rule.port;
    cfg.target_protocol = rule.protocol;
    cfg.runtime_filtered(Some(endpoint), monotonic_now_ns())
}

pub fn init_runtime_shm() -> bool {
    try_open_shm()
}

pub fn bind_fd_to_current_thread(fd: c_int) {
    if fd < 0 {
        return;
    }
    let tid = get_thread_id() as usize;
    assign_rule_to_fd(fd, tid);
}

pub fn clear_fd_binding(fd: c_int) {
    clear_rule_for_fd(fd);
}

pub fn runtime_config_for_fd(fd: c_int) -> Option<Config> {
    let cfg = get_config_for_fd(fd)?.into_network_config();
    apply_multi_target_for_fd(cfg, fd, endpoint_for_fd(fd))
}

/// # Safety
/// `addr` must point to a valid socket address buffer of at least `addr_len` bytes.
pub unsafe fn runtime_config_for_addr_or_fd(
    fd: c_int,
    addr: *const sockaddr,
    addr_len: socklen_t,
) -> Option<Config> {
    let cfg = get_config_for_fd(fd)?.into_network_config();
    apply_multi_target_for_fd(cfg, fd, unsafe { endpoint_for_addr_or_fd(fd, addr, addr_len) })
}

pub fn runtime_dns_config_for_current_thread() -> Option<Config> {
    let tid = get_thread_id();
    let cfg = get_config_for_tid(tid)?.into_network_config();
    cfg.runtime_filtered(None, monotonic_now_ns())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn select_rule_prefers_higher_priority() {
        let endpoint = Endpoint {
            ipv4: 0x0A010203,
            port: 443,
            protocol: 1,
        };
        let rules = [
            TargetRule {
                enabled: 1,
                priority: 10,
                kind: 1,
                ipv4: endpoint.ipv4 as u64,
                prefix_len: 32,
                port: endpoint.port as u64,
                protocol: endpoint.protocol,
                reserved: 0,
            },
            TargetRule {
                enabled: 1,
                priority: 200,
                kind: 1,
                ipv4: endpoint.ipv4 as u64,
                prefix_len: 32,
                port: endpoint.port as u64,
                protocol: endpoint.protocol,
                reserved: 0,
            },
        ];
        let selected = select_best_target_rule(endpoint, &rules, rules.len()).expect("must select");
        assert_eq!(selected.priority, 200);
    }

    #[test]
    fn select_rule_keeps_first_on_priority_tie() {
        let endpoint = Endpoint {
            ipv4: 0x0A010203,
            port: 53,
            protocol: 2,
        };
        let rules = [
            TargetRule {
                enabled: 1,
                priority: 100,
                kind: 2,
                ipv4: 0x0A000000,
                prefix_len: 8,
                port: endpoint.port as u64,
                protocol: endpoint.protocol,
                reserved: 0,
            },
            TargetRule {
                enabled: 1,
                priority: 100,
                kind: 2,
                ipv4: 0x0A010000,
                prefix_len: 16,
                port: endpoint.port as u64,
                protocol: endpoint.protocol,
                reserved: 0,
            },
        ];
        let selected = select_best_target_rule(endpoint, &rules, rules.len()).expect("must select");
        assert_eq!(selected.ipv4, 0x0A000000);
        assert_eq!(selected.prefix_len, 8);
    }

    #[test]
    fn select_rule_returns_none_when_no_match() {
        let endpoint = Endpoint {
            ipv4: 0xC0A80101,
            port: 80,
            protocol: 1,
        };
        let rules = [TargetRule {
            enabled: 1,
            priority: 100,
            kind: 1,
            ipv4: 0x0A000001,
            prefix_len: 32,
            port: endpoint.port as u64,
            protocol: endpoint.protocol,
            reserved: 0,
        }];
        assert!(select_best_target_rule(endpoint, &rules, rules.len()).is_none());
    }
}
