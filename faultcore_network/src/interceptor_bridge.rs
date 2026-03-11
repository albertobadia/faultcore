use libc::{c_int, sockaddr, socklen_t};
use parking_lot::Mutex;
use std::collections::HashMap;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicU64, Ordering};

use crate::{
    Config, Direction, Endpoint, FaultOsiEngine, LayerDecision, TargetRule, assign_rule_to_fd,
    clear_rule_for_fd, clone_rule_for_fd, endpoint_for_addr_or_fd, endpoint_for_fd,
    get_config_for_tid, get_config_for_tid_slot, get_target_rules_for_tid_slot, get_thread_id,
    get_tid_slot_for_fd, get_tid_slot_for_tid, monotonic_now_ns, try_open_shm,
};

const RULESET_READ_RETRY_LIMIT: usize = 3;
const HOSTNAME_OBSERVATION_TTL_NS: u64 = 30_000_000_000;
const HOSTNAME_OBSERVATION_MAX_ENTRIES: usize = 4096;
static RELOAD_APPLIED_TOTAL: AtomicU64 = AtomicU64::new(0);
static RELOAD_RETRY_TOTAL: AtomicU64 = AtomicU64::new(0);
static OBSERVED_SNI_BY_FD: OnceLock<Mutex<HashMap<c_int, String>>> = OnceLock::new();
static OBSERVED_HOSTNAME_BY_ENDPOINT: OnceLock<Mutex<HashMap<HostnameObservationKey, ObservedName>>> =
    OnceLock::new();

fn observed_sni_by_fd() -> &'static Mutex<HashMap<c_int, String>> {
    OBSERVED_SNI_BY_FD.get_or_init(|| Mutex::new(HashMap::new()))
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
struct HostnameObservationKey {
    tid_slot: usize,
    address_family: u64,
    addr: [u8; 16],
}

#[derive(Clone)]
struct ObservedName {
    hostname: String,
    observed_at_ns: u64,
}

fn observed_hostname_by_endpoint() -> &'static Mutex<HashMap<HostnameObservationKey, ObservedName>> {
    OBSERVED_HOSTNAME_BY_ENDPOINT.get_or_init(|| Mutex::new(HashMap::new()))
}

fn normalize_semantic_name(value: &str) -> Option<String> {
    let normalized = value.trim().trim_end_matches('.').to_ascii_lowercase();
    if normalized.is_empty() {
        return None;
    }
    Some(normalized)
}

fn observed_sni_for_fd(fd: c_int) -> Option<String> {
    if fd < 0 {
        return None;
    }
    observed_sni_by_fd().lock().get(&fd).cloned()
}

fn hostname_observation_key(tid_slot: usize, endpoint: Endpoint) -> Option<HostnameObservationKey> {
    if endpoint.address_family != 1 && endpoint.address_family != 2 {
        return None;
    }
    Some(HostnameObservationKey {
        tid_slot,
        address_family: endpoint.address_family,
        addr: endpoint.addr,
    })
}

fn prune_hostname_observations(map: &mut HashMap<HostnameObservationKey, ObservedName>, now_ns: u64) {
    map.retain(|_, item| now_ns.saturating_sub(item.observed_at_ns) <= HOSTNAME_OBSERVATION_TTL_NS);
    if map.len() <= HOSTNAME_OBSERVATION_MAX_ENTRIES {
        return;
    }
    let mut items: Vec<(HostnameObservationKey, u64)> = map
        .iter()
        .map(|(key, item)| (*key, item.observed_at_ns))
        .collect();
    items.sort_unstable_by_key(|(_, observed_at)| *observed_at);
    let remove_count = map.len().saturating_sub(HOSTNAME_OBSERVATION_MAX_ENTRIES);
    for (key, _) in items.into_iter().take(remove_count) {
        map.remove(&key);
    }
}

fn observe_hostname_for_slot_endpoint(tid_slot: usize, endpoint: Endpoint, hostname: &str) {
    let Some(normalized) = normalize_semantic_name(hostname) else {
        return;
    };
    let Some(key) = hostname_observation_key(tid_slot, endpoint) else {
        return;
    };
    let now_ns = monotonic_now_ns();
    let mut map = observed_hostname_by_endpoint().lock();
    map.insert(
        key,
        ObservedName {
            hostname: normalized,
            observed_at_ns: now_ns,
        },
    );
    prune_hostname_observations(&mut map, now_ns);
}

fn observed_hostname_for_slot_endpoint(tid_slot: usize, endpoint: Endpoint) -> Option<String> {
    let key = hostname_observation_key(tid_slot, endpoint)?;
    let now_ns = monotonic_now_ns();
    let mut map = observed_hostname_by_endpoint().lock();
    let observed = map.get(&key).cloned()?;
    if now_ns.saturating_sub(observed.observed_at_ns) > HOSTNAME_OBSERVATION_TTL_NS {
        map.remove(&key);
        return None;
    }
    Some(observed.hostname)
}

pub fn observe_sni_for_fd(fd: c_int, sni: &str) {
    if fd < 0 {
        return;
    }
    let Some(normalized) = normalize_semantic_name(sni) else {
        return;
    };
    observed_sni_by_fd().lock().insert(fd, normalized);
}

pub fn clear_observed_semantic_for_fd(fd: c_int) {
    if fd < 0 {
        return;
    }
    observed_sni_by_fd().lock().remove(&fd);
}

pub fn clone_observed_semantic_for_fd(src_fd: c_int, dst_fd: c_int) {
    if src_fd < 0 || dst_fd < 0 {
        return;
    }
    let cloned = observed_sni_by_fd().lock().get(&src_fd).cloned();
    let mut map = observed_sni_by_fd().lock();
    if let Some(sni) = cloned {
        map.insert(dst_fd, sni);
    } else {
        map.remove(&dst_fd);
    }
}

/// # Safety
/// `addr` must point to a valid socket address buffer of at least `addr_len` bytes.
pub unsafe fn observe_hostname_for_current_thread_addr(
    addr: *const sockaddr,
    addr_len: socklen_t,
    hostname: &str,
) {
    let tid_slot = get_tid_slot_for_tid(get_thread_id());
    let Some(endpoint) = (unsafe { endpoint_for_addr_or_fd(-1, addr, addr_len) }) else {
        return;
    };
    observe_hostname_for_slot_endpoint(tid_slot, endpoint, hostname);
}

pub fn runtime_reload_metrics_snapshot() -> (u64, u64) {
    (
        RELOAD_APPLIED_TOTAL.load(Ordering::Relaxed),
        RELOAD_RETRY_TOTAL.load(Ordering::Relaxed),
    )
}

pub fn reset_runtime_reload_metrics() {
    RELOAD_APPLIED_TOTAL.store(0, Ordering::Relaxed);
    RELOAD_RETRY_TOTAL.store(0, Ordering::Relaxed);
}

#[derive(Clone, Copy, Default)]
struct SemanticContext<'a> {
    hostname: Option<&'a str>,
    sni: Option<&'a str>,
}

fn rule_name(raw: &[u8; 32]) -> Option<&str> {
    let len = raw.iter().position(|b| *b == 0).unwrap_or(raw.len());
    if len == 0 {
        return None;
    }
    std::str::from_utf8(&raw[..len]).ok()
}

fn wildcard_suffix(name: &str) -> Option<&str> {
    name.strip_prefix("*.")
}

fn wildcard_matches(suffix: &str, candidate: &str) -> bool {
    if candidate == suffix {
        return false;
    }
    candidate
        .strip_suffix(suffix)
        .is_some_and(|prefix| prefix.ends_with('.'))
}

fn match_name_score(rule_name: &str, candidate: Option<&str>) -> Option<u8> {
    let candidate = candidate?;
    if let Some(suffix) = wildcard_suffix(rule_name) {
        return wildcard_matches(suffix, candidate).then_some(1);
    }
    (rule_name == candidate).then_some(2)
}

fn rule_port_end(rule: &TargetRule) -> u64 {
    if rule.reserved > 0 {
        rule.reserved
    } else {
        rule.port
    }
}

fn endpoint_matches_rule_filters(rule: &TargetRule, endpoint: Endpoint) -> bool {
    if rule.protocol > 0 && rule.protocol != endpoint.protocol {
        return false;
    }

    let endpoint_port = u64::from(endpoint.port);
    let port_start = rule.port;
    let port_end = rule_port_end(rule);
    if (port_start > 0 || port_end > 0) && (endpoint_port < port_start || endpoint_port > port_end) {
        return false;
    }

    true
}

fn rule_match_class(
    rule: &TargetRule,
    endpoint: Option<Endpoint>,
    semantic: SemanticContext<'_>,
) -> Option<u8> {
    if rule.enabled == 0 {
        return None;
    }
    let hostname_rule = rule_name(&rule.hostname);
    let sni_rule = rule_name(&rule.sni);
    if hostname_rule.is_some() && sni_rule.is_some() {
        return None;
    }

    let is_semantic = hostname_rule.is_some() || sni_rule.is_some();
    if is_semantic && rule.kind != 0 {
        return None;
    }

    if let Some(name) = sni_rule {
        if rule.protocol > 0 || rule.port > 0 || rule.reserved > 0 {
            let endpoint = endpoint?;
            if !endpoint_matches_rule_filters(rule, endpoint) {
                return None;
            }
        }
        return match_name_score(name, semantic.sni).map(|score| score + 3);
    }
    if let Some(name) = hostname_rule {
        if rule.protocol > 0 || rule.port > 0 || rule.reserved > 0 {
            let endpoint = endpoint?;
            if !endpoint_matches_rule_filters(rule, endpoint) {
                return None;
            }
        }
        return match_name_score(name, semantic.hostname).map(|score| score + 1);
    }

    let endpoint = endpoint?;
    if !endpoint_matches_rule_filters(rule, endpoint) {
        return None;
    }

    let family = rule.address_family;
    if family == 0 {
        return None;
    }
    match rule.kind {
        1 => (endpoint.address_family == family && endpoint.addr == rule.addr).then_some(1),
        2 => {
            let max_prefix = if family == 1 { 32 } else { 128 };
            let bounded_prefix = usize::min(rule.prefix_len as usize, max_prefix);
            (endpoint.address_family == family && prefix_match(&endpoint.addr, &rule.addr, bounded_prefix))
                .then_some(1)
        }
        _ => None,
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
    endpoint: Option<Endpoint>,
    semantic: SemanticContext<'_>,
    rules: &[TargetRule],
    count: usize,
) -> Option<TargetRule> {
    let mut selected_idx: Option<usize> = None;
    let mut selected_priority: u64 = 0;
    let mut selected_class: u8 = 0;
    let limit = usize::min(count, rules.len());

    for (idx, rule) in rules.iter().take(limit).enumerate() {
        let Some(match_class) = rule_match_class(rule, endpoint, semantic) else {
            continue;
        };
        if selected_idx.is_none()
            || rule.priority > selected_priority
            || (rule.priority == selected_priority && match_class > selected_class)
        {
            selected_idx = Some(idx);
            selected_priority = rule.priority;
            selected_class = match_class;
        }
    }
    selected_idx.map(|idx| rules[idx])
}

fn apply_multi_target_for_tid(
    cfg: Config,
    tid_slot: usize,
    endpoint: Option<Endpoint>,
    semantic: SemanticContext<'_>,
) -> Option<Config> {
    if cfg.target_enabled == 0 {
        return cfg.runtime_filtered(endpoint, monotonic_now_ns());
    }
    let endpoint = endpoint?;
    apply_multi_target_for_tid_with_reader(
        cfg,
        Some(endpoint),
        semantic,
        || get_target_rules_for_tid_slot(tid_slot),
        || get_config_for_tid_slot(tid_slot).map(|item| item.into_network_config()),
    )
}

fn apply_multi_target_for_tid_with_reader<FRules, FCfg>(
    mut cfg: Config,
    endpoint: Option<Endpoint>,
    semantic: SemanticContext<'_>,
    mut read_rules: FRules,
    mut read_cfg: FCfg,
) -> Option<Config>
where
    FRules: FnMut() -> Option<[TargetRule; crate::MAX_TARGET_RULES_PER_TID]>,
    FCfg: FnMut() -> Option<Config>,
{
    for _ in 0..RULESET_READ_RETRY_LIMIT {
        if cfg.target_enabled == 0 {
            return cfg.runtime_filtered(endpoint, monotonic_now_ns());
        }

        let generation_before = cfg.ruleset_generation;
        let rules = read_rules()?;
        let refreshed_cfg = read_cfg()?;
        if refreshed_cfg.ruleset_generation != generation_before {
            RELOAD_RETRY_TOTAL.fetch_add(1, Ordering::Relaxed);
            cfg = refreshed_cfg;
            continue;
        }

        let count = usize::min(cfg.target_enabled as usize, rules.len());
        let rule = select_best_target_rule(endpoint, semantic, &rules, count)?;
        cfg.target_enabled = 0;
        cfg.target_kind = rule.kind;
        cfg.target_prefix_len = rule.prefix_len;
        cfg.target_port = rule.port;
        cfg.target_protocol = rule.protocol;
        cfg.target_address_family = rule.address_family;
        cfg.target_addr = rule.addr;
        cfg.target_hostname = rule.hostname;
        cfg.target_sni = rule.sni;
        RELOAD_APPLIED_TOTAL.fetch_add(1, Ordering::Relaxed);
        return cfg.runtime_filtered(endpoint, monotonic_now_ns());
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
    clear_observed_semantic_for_fd(fd);
}

pub fn clone_fd_binding(src_fd: c_int, dst_fd: c_int) {
    clone_rule_for_fd(src_fd, dst_fd);
    clone_observed_semantic_for_fd(src_fd, dst_fd);
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

    let observed_sni = observed_sni_for_fd(fd);
    let observed_hostname = endpoint.and_then(|resolved| observed_hostname_for_slot_endpoint(slot, resolved));
    let semantic = SemanticContext {
        hostname: observed_hostname.as_deref(),
        sni: observed_sni.as_deref(),
    };
    apply_multi_target_for_tid(base_cfg, slot, endpoint, semantic)
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
    runtime_dns_config_for_query(None, None)
}

pub fn runtime_dns_config_for_query(hostname: Option<&str>, sni: Option<&str>) -> Option<Config> {
    let tid = get_thread_id();
    let cfg = get_config_for_tid(tid)?.into_network_config();
    let slot = get_tid_slot_for_tid(tid);
    if cfg.target_enabled == 0 {
        return cfg.runtime_filtered(None, monotonic_now_ns());
    }
    apply_multi_target_for_tid_with_reader(
        cfg,
        None,
        SemanticContext { hostname, sni },
        || get_target_rules_for_tid_slot(slot),
        || get_config_for_tid_slot(slot).map(|item| item.into_network_config()),
    )
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
    
    fn addr_v4(ipv4: u32) -> [u8; 16] {
       let mut addr = [0u8; 16];
       addr[..4].copy_from_slice(&ipv4.to_be_bytes());
       addr
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

    fn name32(value: &str) -> [u8; 32] {
       let mut out = [0u8; 32];
       let bytes = value.as_bytes();
       out[..bytes.len()].copy_from_slice(bytes);
       out
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
       apply_multi_target_for_tid(base_cfg, slot, endpoint, SemanticContext::default())
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
               address_family: 1,
               addr: endpoint.addr,
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
               address_family: 1,
               addr: endpoint.addr,
               hostname: [0; 32],
               sni: [0; 32],
           },
       ];
       let selected = select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).expect("must select");
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
               address_family: 1,
               addr: addr_v4(0x0A000000),
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
               address_family: 1,
               addr: addr_v4(0x0A010000),
               hostname: [0; 32],
               sni: [0; 32],
           },
       ];
       let selected = select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).expect("must select");
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
           address_family: 1,
           addr: addr_v4(0x0A000001),
           hostname: [0; 32],
           sni: [0; 32],
       }];
       assert!(select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).is_none());
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
               address_family: 1,
               addr: endpoint.addr,
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
               address_family: 1,
               addr: endpoint.addr,
               hostname: [0; 32],
               sni: [0; 32],
           },
       ];
       let selected = select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).expect("must select");
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
               address_family: 1,
               addr: endpoint.addr,
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
               address_family: 1,
               addr: endpoint.addr,
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
               address_family: 1,
               addr: endpoint.addr,
               hostname: [0; 32],
               sni: [0; 32],
           },
       ];
       let selected = select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).expect("must select");
       assert_eq!(selected.priority, 70);
    }
    
    #[test]
    fn select_rule_respects_port_range() {
       let endpoint = endpoint_v4(0x0A010203, 8080, 1);
       let rules = [TargetRule {
           enabled: 1,
           priority: 70,
           kind: 1,
           ipv4: endpoint.ipv4 as u64,
           prefix_len: 32,
           port: 8000,
           protocol: endpoint.protocol,
           reserved: 9000,
           address_family: 1,
           addr: endpoint.addr,
           hostname: [0; 32],
           sni: [0; 32],
       }];
       let selected = select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).expect("must select");
       assert_eq!(selected.priority, 70);
    }
    
    #[test]
    fn select_rule_rejects_port_range_miss() {
       let endpoint = endpoint_v4(0x0A010203, 9100, 1);
       let rules = [TargetRule {
           enabled: 1,
           priority: 70,
           kind: 1,
           ipv4: endpoint.ipv4 as u64,
           prefix_len: 32,
           port: 8000,
           protocol: endpoint.protocol,
           reserved: 9000,
           address_family: 1,
           addr: endpoint.addr,
           hostname: [0; 32],
           sni: [0; 32],
       }];
       assert!(select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).is_none());
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
           address_family: 1,
           addr: addr_v4(0),
           hostname: [0; 32],
           sni: [0; 32],
       }];
       let selected = select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).expect("must select");
       assert_eq!(selected.kind, 2);
       assert_eq!(selected.prefix_len, 0);
    }

    #[test]
    fn select_rule_prioritizes_sni_over_ip_on_tie() {
       let endpoint = endpoint_v4(0x0A010203, 443, 1);
       let rules = [
           TargetRule {
               enabled: 1,
               priority: 100,
               kind: 1,
               ipv4: endpoint.ipv4 as u64,
               prefix_len: 32,
               port: endpoint.port as u64,
               protocol: endpoint.protocol,
               reserved: 0,
               address_family: 1,
               addr: endpoint.addr,
               hostname: [0; 32],
               sni: [0; 32],
           },
           TargetRule {
               enabled: 1,
               priority: 100,
               kind: 0,
               ipv4: 0,
               prefix_len: 0,
               port: endpoint.port as u64,
               protocol: endpoint.protocol,
               reserved: 0,
               address_family: 0,
               addr: [0; 16],
               hostname: [0; 32],
               sni: name32("api.foo.com"),
           },
       ];
       let selected = select_best_target_rule(
           Some(endpoint),
           SemanticContext { hostname: None, sni: Some("api.foo.com") },
           &rules,
           rules.len(),
       )
       .expect("must select");
       assert_eq!(selected.kind, 0);
       assert_eq!(&selected.sni[0..11], b"api.foo.com");
    }

    #[test]
    fn select_rule_matches_hostname_wildcard_for_dns_query() {
       let rules = [TargetRule {
           enabled: 1,
           priority: 100,
           kind: 0,
           ipv4: 0,
           prefix_len: 0,
           port: 0,
           protocol: 0,
           reserved: 0,
           address_family: 0,
           addr: [0; 16],
           hostname: name32("*.foo.com"),
           sni: [0; 32],
       }];
       let selected = select_best_target_rule(
           None,
           SemanticContext { hostname: Some("api.foo.com"), sni: None },
           &rules,
           rules.len(),
       )
       .expect("must select");
       assert_eq!(selected.kind, 0);
    }

    #[test]
    fn select_rule_rejects_semantic_rule_when_hostname_not_observable() {
       let endpoint = endpoint_v4(0x0A010203, 443, 1);
       let rules = [TargetRule {
           enabled: 1,
           priority: 100,
           kind: 0,
           ipv4: 0,
           prefix_len: 0,
           port: endpoint.port as u64,
           protocol: endpoint.protocol,
           reserved: 0,
           address_family: 0,
           addr: [0; 16],
           hostname: name32("api.foo.com"),
           sni: [0; 32],
       }];
       assert!(
           select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len())
               .is_none()
       );
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
    fn observed_sni_state_clones_and_clears_by_fd() {
       observe_sni_for_fd(12, "Api.Foo.com.");
       assert_eq!(observed_sni_for_fd(12).as_deref(), Some("api.foo.com"));

       clone_observed_semantic_for_fd(12, 13);
       assert_eq!(observed_sni_for_fd(13).as_deref(), Some("api.foo.com"));

       clear_observed_semantic_for_fd(12);
       clear_observed_semantic_for_fd(13);
       assert!(observed_sni_for_fd(12).is_none());
       assert!(observed_sni_for_fd(13).is_none());
    }

    #[test]
    fn observed_hostname_state_is_slot_and_endpoint_scoped() {
       let endpoint = endpoint_v4(0x7F000001, 443, 1);
       observed_hostname_by_endpoint().lock().clear();
       observe_hostname_for_slot_endpoint(77, endpoint, "Api.Foo.com.");
       assert_eq!(
           observed_hostname_for_slot_endpoint(77, endpoint).as_deref(),
           Some("api.foo.com")
       );
       assert!(observed_hostname_for_slot_endpoint(78, endpoint).is_none());
       observed_hostname_by_endpoint().lock().clear();
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
           address_family: 1,
           addr: endpoint.addr,
           hostname: [0; 32],
           sni: [0; 32],
       }; crate::MAX_TARGET_RULES_PER_TID];
    
       let cfg_reads = Cell::new(0usize);
       let result = apply_multi_target_for_tid_with_reader(
            base_cfg,
            Some(endpoint),
            SemanticContext::default(),
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
       // Rule-table selection already matched the endpoint, so single-target filtering is disabled.
       assert_eq!(result.target_enabled, 0);
       assert_eq!(result.target_kind, 1);
       assert_eq!(result.target_address_family, 1);
       assert_eq!(result.target_addr, endpoint.addr);
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
           address_family: 1,
           addr: endpoint.addr,
           hostname: [0; 32],
           sni: [0; 32],
       }; crate::MAX_TARGET_RULES_PER_TID];
    
       let cfg_reads = Cell::new(0usize);
       let result = apply_multi_target_for_tid_with_reader(
            base_cfg,
            Some(endpoint),
            SemanticContext::default(),
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
    fn reload_metrics_count_retry_and_apply() {
       reset_runtime_reload_metrics();
       let (applied_before, retry_before) = runtime_reload_metrics_snapshot();
       let endpoint = endpoint_v4(0x0A010203, 443, 1);
       let mut base_cfg = cfg_with_latency(500);
       base_cfg.target_enabled = 1;
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
           address_family: 1,
           addr: endpoint.addr,
           hostname: [0; 32],
           sni: [0; 32],
       }; crate::MAX_TARGET_RULES_PER_TID];

       let cfg_reads = Cell::new(0usize);
       let _ = apply_multi_target_for_tid_with_reader(
           base_cfg,
           Some(endpoint),
           SemanticContext::default(),
           || Some(rules),
           || {
               let n = cfg_reads.get();
               cfg_reads.set(n + 1);
               let mut refreshed = cfg_with_latency(500);
               refreshed.target_enabled = 1;
               refreshed.ruleset_generation = 11;
               Some(refreshed)
           },
       );

       let (applied, retry) = runtime_reload_metrics_snapshot();
       assert!(applied.saturating_sub(applied_before) >= 1);
       assert!(retry.saturating_sub(retry_before) >= 1);
       reset_runtime_reload_metrics();
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
       let selected = select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).expect("must select");
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
       let selected = select_best_target_rule(Some(endpoint), SemanticContext::default(), &rules, rules.len()).expect("must select");
       assert_eq!(selected.kind, 2);
       assert_eq!(selected.prefix_len, 48);
    }
}
