use libc::{c_int, sockaddr, socklen_t};

use crate::{
    Config, Direction, Endpoint, FaultOsiEngine, LayerDecision, TargetRule, assign_rule_to_fd,
    clear_rule_for_fd, clone_rule_for_fd, endpoint_for_addr_or_fd, endpoint_for_fd,
    get_config_for_tid, get_config_for_tid_slot, get_target_rules_for_tid_slot, get_thread_id,
    get_tid_slot_for_fd, get_tid_slot_for_tid, monotonic_now_ns, try_open_shm,
};

const RULESET_READ_RETRY_LIMIT: usize = 3;

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
    let family = rule.address_family;
    match rule.kind {
        1 => {
            if family == 0 {
                endpoint.ipv4 == rule.ipv4 as u32
            } else {
                endpoint.address_family == family && endpoint.addr == rule.addr
            }
        }
        2 => {
            if family == 0 {
                if rule.prefix_len == 0 {
                    true
                } else if rule.prefix_len >= 32 {
                    endpoint.ipv4 == rule.ipv4 as u32
                } else {
                    let mask = u32::MAX << (32 - rule.prefix_len as u32);
                    (endpoint.ipv4 & mask) == ((rule.ipv4 as u32) & mask)
                }
            } else {
                let max_prefix = if family == 1 { 32 } else { 128 };
                let bounded_prefix = usize::min(rule.prefix_len as usize, max_prefix);
                endpoint.address_family == family
                    && prefix_match(&endpoint.addr, &rule.addr, bounded_prefix)
            }
        }
        _ => false,
    }
}

fn prefix_match(candidate: &[u8; 16], network: &[u8; 16], prefix_len: usize) -> bool {
    if prefix_len == 0 {
        return true;
    }
    let full_bytes = prefix_len / 8;
    let partial_bits = prefix_len % 8;
    if full_bytes > 0 && candidate[..full_bytes] != network[..full_bytes] {
        return false;
    }
    if partial_bits == 0 {
        return true;
    }
    let mask = (!0u8) << (8 - partial_bits);
    (candidate[full_bytes] & mask) == (network[full_bytes] & mask)
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

fn apply_multi_target_for_tid(
    cfg: Config,
    tid_slot: usize,
    endpoint: Option<Endpoint>,
) -> Option<Config> {
    if cfg.target_enabled <= 1 {
        return cfg.runtime_filtered(endpoint, monotonic_now_ns());
    }
    let endpoint = endpoint?;
    apply_multi_target_for_tid_with_reader(
        cfg,
        endpoint,
        || get_target_rules_for_tid_slot(tid_slot),
        || get_config_for_tid_slot(tid_slot).map(|item| item.into_network_config()),
    )
}

fn apply_multi_target_for_tid_with_reader<FRules, FCfg>(
    mut cfg: Config,
    endpoint: Endpoint,
    mut read_rules: FRules,
    mut read_cfg: FCfg,
) -> Option<Config>
where
    FRules: FnMut() -> Option<[TargetRule; crate::MAX_TARGET_RULES_PER_TID]>,
    FCfg: FnMut() -> Option<Config>,
{
    for _ in 0..RULESET_READ_RETRY_LIMIT {
        if cfg.target_enabled <= 1 {
            return cfg.runtime_filtered(Some(endpoint), monotonic_now_ns());
        }

        let generation_before = cfg.ruleset_generation;
        let rules = read_rules()?;
        let refreshed_cfg = read_cfg()?;
        if refreshed_cfg.ruleset_generation != generation_before {
            cfg = refreshed_cfg;
            continue;
        }

        let count = usize::min(cfg.target_enabled as usize, rules.len());
        let rule = select_best_target_rule(endpoint, &rules, count)?;
        cfg.target_enabled = 1;
        cfg.target_kind = rule.kind;
        cfg.target_ipv4 = rule.ipv4;
        cfg.target_prefix_len = rule.prefix_len;
        cfg.target_port = rule.port;
        cfg.target_protocol = rule.protocol;
        cfg.target_address_family = rule.address_family;
        cfg.target_addr = rule.addr;
        return cfg.runtime_filtered(Some(endpoint), monotonic_now_ns());
    }

    None
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

pub fn clone_fd_binding(src_fd: c_int, dst_fd: c_int) {
    clone_rule_for_fd(src_fd, dst_fd);
}

fn resolve_runtime_config_for_endpoint(fd: c_int, endpoint: Option<Endpoint>) -> Option<Config> {
    let tid = get_thread_id();
    let owner_slot = get_tid_slot_for_fd(fd);
    let owner_cfg = owner_slot
        .and_then(get_config_for_tid_slot)
        .map(|cfg| cfg.into_network_config());

    let (base_cfg, slot) = if let (Some(slot), Some(cfg)) = (owner_slot, owner_cfg) {
        (cfg, slot)
    } else {
        let cfg = get_config_for_tid(tid)?.into_network_config();
        (cfg, get_tid_slot_for_tid(tid))
    };

    apply_multi_target_for_tid(base_cfg, slot, endpoint)
}

pub fn runtime_config_for_fd(fd: c_int) -> Option<Config> {
    resolve_runtime_config_for_endpoint(fd, endpoint_for_fd(fd))
}

/// # Safety
/// `addr` must point to a valid socket address buffer of at least `addr_len` bytes.
pub unsafe fn runtime_config_for_addr_or_fd(
    fd: c_int,
    addr: *const sockaddr,
    addr_len: socklen_t,
) -> Option<Config> {
    resolve_runtime_config_for_endpoint(fd, unsafe { endpoint_for_addr_or_fd(fd, addr, addr_len) })
}

pub fn runtime_dns_config_for_current_thread() -> Option<Config> {
    let tid = get_thread_id();
    let cfg = get_config_for_tid(tid)?.into_network_config();
    cfg.runtime_filtered(None, monotonic_now_ns())
}

pub fn uplink_duplicate_count_for_fd(engine: &FaultOsiEngine, fd: c_int) -> u64 {
    let Some(network_cfg) = runtime_config_for_fd(fd) else {
        return 0;
    };
    match engine.evaluate_stream_post(&network_cfg, Direction::Uplink) {
        LayerDecision::Duplicate(n) => n,
        _ => 0,
    }
}

/// # Safety
/// `addr` must be null or point to a valid socket address buffer of at least `addr_len` bytes.
pub unsafe fn uplink_duplicate_count_for_addr_or_fd(
    engine: &FaultOsiEngine,
    fd: c_int,
    addr: *const sockaddr,
    addr_len: socklen_t,
) -> u64 {
    let Some(network_cfg) = (unsafe { runtime_config_for_addr_or_fd(fd, addr, addr_len) }) else {
        return 0;
    };
    match engine.evaluate_stream_post(&network_cfg, Direction::Uplink) {
        LayerDecision::Duplicate(n) => n,
        _ => 0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    fn endpoint_v4(ipv4: u32, port: u16, protocol: u64) -> Endpoint {
        let mut addr = [0u8; 16];
        addr[..4].copy_from_slice(&ipv4.to_be_bytes());
        Endpoint {
            address_family: 1,
            addr,
            ipv4,
            port,
            protocol,
        }
    }

    fn endpoint_v6(addr: [u8; 16], port: u16, protocol: u64) -> Endpoint {
        Endpoint {
            address_family: 2,
            addr,
            ipv4: 0,
            port,
            protocol,
        }
    }

    fn cfg_with_latency(latency_ns: u64) -> Config {
        Config {
            latency_ns,
            ..Default::default()
        }
    }

    fn select_base_config_for_test(
        fd: c_int,
        endpoint: Option<Endpoint>,
        tid: u64,
        current_cfg: Option<Config>,
        owner_slot: Option<usize>,
        owner_cfg: Option<Config>,
    ) -> Option<Config> {
        let (base_cfg, slot) = if let (Some(slot), Some(cfg)) = (owner_slot, owner_cfg) {
            (cfg, slot)
        } else {
            (current_cfg?, get_tid_slot_for_tid(tid))
        };
        let _ = fd;
        apply_multi_target_for_tid(base_cfg, slot, endpoint)
    }

    #[test]
    fn select_rule_prefers_higher_priority() {
        let endpoint = endpoint_v4(0x0A010203, 443, 1);
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
                address_family: 0,
                addr: [0; 16],
                hostname: [0; 32],
                sni: [0; 32],
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
                address_family: 0,
                addr: [0; 16],
                hostname: [0; 32],
                sni: [0; 32],
            },
        ];
        let selected = select_best_target_rule(endpoint, &rules, rules.len()).expect("must select");
        assert_eq!(selected.priority, 200);
    }

    #[test]
    fn select_rule_keeps_first_on_priority_tie() {
        let endpoint = endpoint_v4(0x0A010203, 53, 2);
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
                address_family: 0,
                addr: [0; 16],
                hostname: [0; 32],
                sni: [0; 32],
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
                address_family: 0,
                addr: [0; 16],
                hostname: [0; 32],
                sni: [0; 32],
            },
        ];
        let selected = select_best_target_rule(endpoint, &rules, rules.len()).expect("must select");
        assert_eq!(selected.ipv4, 0x0A000000);
        assert_eq!(selected.prefix_len, 8);
    }

    #[test]
    fn select_rule_returns_none_when_no_match() {
        let endpoint = endpoint_v4(0xC0A80101, 80, 1);
        let rules = [TargetRule {
            enabled: 1,
            priority: 100,
            kind: 1,
            ipv4: 0x0A000001,
            prefix_len: 32,
            port: endpoint.port as u64,
            protocol: endpoint.protocol,
            reserved: 0,
            address_family: 0,
            addr: [0; 16],
            hostname: [0; 32],
            sni: [0; 32],
        }];
        assert!(select_best_target_rule(endpoint, &rules, rules.len()).is_none());
    }

    #[test]
    fn select_rule_skips_disabled_entries() {
        let endpoint = endpoint_v4(0x0A010203, 443, 1);
        let rules = [
            TargetRule {
                enabled: 0,
                priority: 1_000,
                kind: 1,
                ipv4: endpoint.ipv4 as u64,
                prefix_len: 32,
                port: endpoint.port as u64,
                protocol: endpoint.protocol,
                reserved: 0,
                address_family: 0,
                addr: [0; 16],
                hostname: [0; 32],
                sni: [0; 32],
            },
            TargetRule {
                enabled: 1,
                priority: 100,
                kind: 1,
                ipv4: endpoint.ipv4 as u64,
                prefix_len: 32,
                port: endpoint.port as u64,
                protocol: endpoint.protocol,
                reserved: 0,
                address_family: 0,
                addr: [0; 16],
                hostname: [0; 32],
                sni: [0; 32],
            },
        ];
        let selected = select_best_target_rule(endpoint, &rules, rules.len()).expect("must select");
        assert_eq!(selected.priority, 100);
    }

    #[test]
    fn select_rule_respects_protocol_and_port_filters() {
        let endpoint = endpoint_v4(0x0A010203, 53, 2);
        let rules = [
            TargetRule {
                enabled: 1,
                priority: 50,
                kind: 1,
                ipv4: endpoint.ipv4 as u64,
                prefix_len: 32,
                port: 443,
                protocol: endpoint.protocol,
                reserved: 0,
                address_family: 0,
                addr: [0; 16],
                hostname: [0; 32],
                sni: [0; 32],
            },
            TargetRule {
                enabled: 1,
                priority: 60,
                kind: 1,
                ipv4: endpoint.ipv4 as u64,
                prefix_len: 32,
                port: endpoint.port as u64,
                protocol: 1,
                reserved: 0,
                address_family: 0,
                addr: [0; 16],
                hostname: [0; 32],
                sni: [0; 32],
            },
            TargetRule {
                enabled: 1,
                priority: 70,
                kind: 1,
                ipv4: endpoint.ipv4 as u64,
                prefix_len: 32,
                port: endpoint.port as u64,
                protocol: endpoint.protocol,
                reserved: 0,
                address_family: 0,
                addr: [0; 16],
                hostname: [0; 32],
                sni: [0; 32],
            },
        ];
        let selected = select_best_target_rule(endpoint, &rules, rules.len()).expect("must select");
        assert_eq!(selected.priority, 70);
    }

    #[test]
    fn select_rule_cidr_zero_prefix_matches_any_ipv4() {
        let endpoint = endpoint_v4(0xC0A8010A, 8080, 1);
        let rules = [TargetRule {
            enabled: 1,
            priority: 10,
            kind: 2,
            ipv4: 0,
            prefix_len: 0,
            port: 0,
            protocol: 0,
            reserved: 0,
            address_family: 0,
            addr: [0; 16],
            hostname: [0; 32],
            sni: [0; 32],
        }];
        let selected = select_best_target_rule(endpoint, &rules, rules.len()).expect("must select");
        assert_eq!(selected.kind, 2);
        assert_eq!(selected.prefix_len, 0);
    }

    #[test]
    fn fd_owner_slot_config_takes_precedence_over_current_tid_config() {
        let current_tid = 42_u64;
        let owner_slot = Some(7_usize);
        let selected = select_base_config_for_test(
            10,
            None,
            current_tid,
            Some(cfg_with_latency(111)),
            owner_slot,
            Some(cfg_with_latency(777)),
        )
        .expect("config should resolve");
        assert_eq!(selected.latency_ns, 777);
    }

    #[test]
    fn falls_back_to_current_tid_config_when_fd_owner_slot_is_missing() {
        let current_tid = 42_u64;
        let selected = select_base_config_for_test(
            10,
            None,
            current_tid,
            Some(cfg_with_latency(111)),
            Some(7_usize),
            None,
        )
        .expect("config should resolve from current tid");
        assert_eq!(selected.latency_ns, 111);
    }

    #[test]
    fn lockstep_retries_on_generation_change_and_then_applies_rule() {
        let endpoint = endpoint_v4(0x0A010203, 443, 1);
        let mut base_cfg = cfg_with_latency(500);
        base_cfg.target_enabled = 2;
        base_cfg.ruleset_generation = 10;

        let rules = [TargetRule {
            enabled: 1,
            priority: 100,
            kind: 1,
            ipv4: endpoint.ipv4 as u64,
            prefix_len: 32,
            port: endpoint.port as u64,
            protocol: endpoint.protocol,
            reserved: 0,
            address_family: 0,
            addr: [0; 16],
            hostname: [0; 32],
            sni: [0; 32],
        }; crate::MAX_TARGET_RULES_PER_TID];

        let cfg_reads = Cell::new(0usize);
        let result = apply_multi_target_for_tid_with_reader(
            base_cfg,
            endpoint,
            || Some(rules),
            || {
                let n = cfg_reads.get();
                cfg_reads.set(n + 1);
                let mut refreshed = cfg_with_latency(500);
                refreshed.target_enabled = 2;
                refreshed.ruleset_generation = 11;
                Some(refreshed)
            },
        )
        .expect("rule should apply after generation stabilizes");

        assert_eq!(cfg_reads.get(), 2);
        assert_eq!(result.target_enabled, 1);
        assert_eq!(result.target_kind, 1);
        assert_eq!(result.target_ipv4, endpoint.ipv4 as u64);
    }

    #[test]
    fn lockstep_returns_none_when_generation_never_stabilizes() {
        let endpoint = endpoint_v4(0x0A010203, 443, 1);
        let mut base_cfg = cfg_with_latency(500);
        base_cfg.target_enabled = 2;
        base_cfg.ruleset_generation = 20;

        let rules = [TargetRule {
            enabled: 1,
            priority: 100,
            kind: 1,
            ipv4: endpoint.ipv4 as u64,
            prefix_len: 32,
            port: endpoint.port as u64,
            protocol: endpoint.protocol,
            reserved: 0,
            address_family: 0,
            addr: [0; 16],
            hostname: [0; 32],
            sni: [0; 32],
        }; crate::MAX_TARGET_RULES_PER_TID];

        let cfg_reads = Cell::new(0usize);
        let result = apply_multi_target_for_tid_with_reader(
            base_cfg,
            endpoint,
            || Some(rules),
            || {
                let n = cfg_reads.get();
                cfg_reads.set(n + 1);
                let mut refreshed = cfg_with_latency(500);
                refreshed.target_enabled = 2;
                refreshed.ruleset_generation = 21 + (n as u64);
                Some(refreshed)
            },
        );

        assert!(result.is_none());
        assert_eq!(cfg_reads.get(), RULESET_READ_RETRY_LIMIT);
    }

    #[test]
    fn select_rule_ipv6_host_exact_match() {
        let endpoint = endpoint_v6(
            [
                0x20, 0x01, 0x0D, 0xB8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10,
            ],
            443,
            1,
        );
        let rules = [TargetRule {
            enabled: 1,
            priority: 300,
            kind: 1,
            ipv4: 0,
            prefix_len: 128,
            port: 443,
            protocol: 1,
            reserved: 0,
            address_family: 2,
            addr: [
                0x20, 0x01, 0x0D, 0xB8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10,
            ],
            hostname: [0; 32],
            sni: [0; 32],
        }];
        let selected = select_best_target_rule(endpoint, &rules, rules.len()).expect("must select");
        assert_eq!(selected.priority, 300);
    }

    #[test]
    fn select_rule_ipv6_cidr_match() {
        let endpoint = endpoint_v6(
            [
                0x20, 0x01, 0x0D, 0xB8, 0xAB, 0xCD, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10,
            ],
            443,
            1,
        );
        let rules = [TargetRule {
            enabled: 1,
            priority: 300,
            kind: 2,
            ipv4: 0,
            prefix_len: 48,
            port: 443,
            protocol: 1,
            reserved: 0,
            address_family: 2,
            addr: [
                0x20, 0x01, 0x0D, 0xB8, 0xAB, 0xCD, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            ],
            hostname: [0; 32],
            sni: [0; 32],
        }];
        let selected = select_best_target_rule(endpoint, &rules, rules.len()).expect("must select");
        assert_eq!(selected.kind, 2);
        assert_eq!(selected.prefix_len, 48);
    }
}
