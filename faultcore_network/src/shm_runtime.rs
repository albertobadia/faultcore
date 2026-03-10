use crate::{
    FAULTCORE_MAGIC, FAULTCORE_SHM_SIZE, FaultcoreConfig, MAX_FDS, MAX_POLICIES,
    MAX_TARGET_RULES_PER_TID, MAX_TIDS, PolicyState, TargetRule,
};
use libc::{
    MAP_SHARED, O_RDWR, PROT_READ, PROT_WRITE, c_int, fstat, ftruncate, mmap, shm_open, stat,
};
use parking_lot::{Mutex, RwLock};
use std::ptr;
use std::sync::atomic::{AtomicU64, Ordering, fence};

pub fn get_thread_id() -> u64 {
    unsafe { libc::syscall(libc::SYS_gettid) as u64 }
}

static SHM_POINTER: RwLock<usize> = RwLock::new(0);
static SHM_OPEN: AtomicU64 = AtomicU64::new(0);
static SHM_INIT_LOCK: Mutex<()> = Mutex::new(());
const INVALID_TID_SLOT: u64 = u64::MAX;

const CONFIG_REGION_SIZE: usize = (MAX_FDS + MAX_TIDS) * core::mem::size_of::<FaultcoreConfig>();
const POLICY_REGION_OFFSET: usize = CONFIG_REGION_SIZE;
const POLICY_REGION_SIZE: usize = MAX_POLICIES * core::mem::size_of::<PolicyState>();
const TARGET_RULES_REGION_OFFSET: usize = POLICY_REGION_OFFSET + POLICY_REGION_SIZE;
const TARGET_RULES_REGION_SIZE: usize =
    MAX_TIDS * MAX_TARGET_RULES_PER_TID * core::mem::size_of::<TargetRule>();
const FD_OWNER_REGION_OFFSET: usize = TARGET_RULES_REGION_OFFSET + TARGET_RULES_REGION_SIZE;
const OFFSET_RULESET_GENERATION: usize = 376;

#[inline]
fn tid_slot(tid: usize) -> usize {
    let hash = (tid ^ (tid >> 16)).wrapping_mul(0x45d9f3b) ^ (tid >> 16);
    hash % MAX_TIDS
}

fn check_enabled() -> bool {
    !matches!(
        std::env::var("FAULTCORE_ENABLED").as_deref(),
        Ok("0" | "false" | "no" | "off")
    )
}

fn get_shm_name() -> Option<String> {
    std::env::var("FAULTCORE_CONFIG_SHM")
        .ok()
        .filter(|s| !s.is_empty())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ShmOpenMode {
    Creator,
    Consumer,
}

fn shm_open_mode() -> ShmOpenMode {
    match std::env::var("FAULTCORE_SHM_OPEN_MODE") {
        Ok(raw) if raw.eq_ignore_ascii_case("creator") => ShmOpenMode::Creator,
        _ => ShmOpenMode::Consumer,
    }
}

pub fn try_open_shm() -> bool {
    if !check_enabled() || is_shm_open() {
        return is_shm_open();
    }
    let _init_guard = SHM_INIT_LOCK.lock();
    if is_shm_open() {
        return true;
    }

    let shm_name = get_shm_name()
        .unwrap_or_else(|| format!("/faultcore_{}_config", unsafe { libc::getpid() }));

    let name_cstr = std::ffi::CString::new(shm_name.as_bytes()).unwrap();
    let open_mode = shm_open_mode();

    unsafe {
        let fd = shm_open(name_cstr.as_ptr(), O_RDWR, 0);
        if fd < 0 {
            return false;
        }

        match open_mode {
            ShmOpenMode::Creator => {
                if ftruncate(fd, FAULTCORE_SHM_SIZE as i64) < 0 {
                    libc::close(fd);
                    return false;
                }
            }
            ShmOpenMode::Consumer => {
                let mut st: stat = std::mem::zeroed();
                if fstat(fd, &mut st) < 0 || st.st_size < FAULTCORE_SHM_SIZE as i64 {
                    libc::close(fd);
                    return false;
                }
            }
        }

        let addr = mmap(
            ptr::null_mut(),
            FAULTCORE_SHM_SIZE,
            PROT_READ | PROT_WRITE,
            MAP_SHARED,
            fd,
            0,
        );

        libc::close(fd);

        if addr as isize == -1isize {
            return false;
        }

        *SHM_POINTER.write() = addr as usize;
        SHM_OPEN.store(1, Ordering::SeqCst);

        true
    }
}

pub fn is_shm_open() -> bool {
    SHM_OPEN.load(Ordering::SeqCst) == 1
}

pub(crate) unsafe fn get_config_ptr(
    tid_or_fd: usize,
    is_tid: bool,
) -> Option<*mut FaultcoreConfig> {
    let ptr_val = *SHM_POINTER.read();
    if ptr_val == 0 {
        return None;
    }
    unsafe {
        let array = ptr_val as *mut FaultcoreConfig;
        let idx = if is_tid {
            MAX_FDS + tid_slot(tid_or_fd)
        } else {
            if tid_or_fd >= MAX_FDS {
                return None;
            }
            tid_or_fd
        };
        let ptr = array.add(idx);
        Some(ptr)
    }
}

unsafe fn get_target_rules_base_ptr() -> Option<*mut TargetRule> {
    let ptr_val = *SHM_POINTER.read();
    if ptr_val == 0 {
        return None;
    }
    Some((ptr_val + TARGET_RULES_REGION_OFFSET) as *mut TargetRule)
}

unsafe fn get_fd_owner_base_ptr() -> Option<*mut u64> {
    let ptr_val = *SHM_POINTER.read();
    if ptr_val == 0 {
        return None;
    }
    Some((ptr_val + FD_OWNER_REGION_OFFSET) as *mut u64)
}

pub fn get_tid_slot_for_fd(fd: c_int) -> Option<usize> {
    if !is_shm_open() || fd < 0 {
        try_open_shm();
    }
    if fd < 0 || (fd as usize) >= MAX_FDS {
        return None;
    }
    unsafe {
        let owners = get_fd_owner_base_ptr()?;
        let slot = ptr::read_unaligned(owners.add(fd as usize));
        if slot == INVALID_TID_SLOT || slot >= MAX_TIDS as u64 {
            return None;
        }
        Some(slot as usize)
    }
}

pub fn get_tid_slot_for_tid(tid: u64) -> usize {
    tid_slot(tid as usize)
}

pub fn get_target_rules_for_tid_slot(
    slot: usize,
) -> Option<[TargetRule; MAX_TARGET_RULES_PER_TID]> {
    if !is_shm_open() {
        try_open_shm();
    }
    if slot >= MAX_TIDS {
        return None;
    }
    unsafe {
        let base = get_target_rules_base_ptr()?;
        let start = slot * MAX_TARGET_RULES_PER_TID;
        let mut out = [TargetRule::default(); MAX_TARGET_RULES_PER_TID];
        for (i, item) in out.iter_mut().enumerate().take(MAX_TARGET_RULES_PER_TID) {
            *item = ptr::read_unaligned(base.add(start + i));
        }
        Some(out)
    }
}

pub fn get_config_for_fd(fd: c_int) -> Option<FaultcoreConfig> {
    if !is_shm_open() || fd < 0 {
        try_open_shm();
    }
    if fd < 0 {
        return None;
    }

    unsafe {
        if let Some(config_ptr) = get_config_ptr(fd as usize, false) {
            return read_stable_config(config_ptr);
        }
    }
    None
}

pub fn get_config_for_tid(tid: u64) -> Option<FaultcoreConfig> {
    if !is_shm_open() {
        try_open_shm();
    }

    unsafe {
        if let Some(config_ptr) = get_config_ptr(tid as usize, true) {
            return read_stable_config(config_ptr);
        }
    }
    None
}

pub fn get_config_for_tid_slot(slot: usize) -> Option<FaultcoreConfig> {
    if !is_shm_open() {
        try_open_shm();
    }
    if slot >= MAX_TIDS {
        return None;
    }

    unsafe {
        let ptr_val = *SHM_POINTER.read();
        if ptr_val == 0 {
            return None;
        }
        let config_ptr = (ptr_val as *mut FaultcoreConfig).add(MAX_FDS + slot);
        read_stable_config(config_ptr)
    }
}

pub fn assign_rule_to_fd(fd: c_int, tid: usize) {
    if fd < 0 || (fd as usize) >= MAX_FDS {
        return;
    }
    unsafe {
        if let Some(owners) = get_fd_owner_base_ptr() {
            ptr::write_unaligned(owners.add(fd as usize), tid_slot(tid) as u64);
        }
    }
}

pub fn clear_rule_for_fd(fd: c_int) {
    if fd < 0 || (fd as usize) >= MAX_FDS {
        return;
    }
    unsafe {
        if let Some(owners) = get_fd_owner_base_ptr() {
            ptr::write_unaligned(owners.add(fd as usize), INVALID_TID_SLOT);
        }
        if let Some(fd_ptr) = get_config_ptr(fd as usize, false) {
            write_config_with_generation_publish(fd_ptr, |config| {
                *config = FaultcoreConfig::default();
            });
        }
    }
}

pub fn clone_rule_for_fd(src_fd: c_int, dst_fd: c_int) {
    if src_fd < 0 || dst_fd < 0 || (src_fd as usize) >= MAX_FDS || (dst_fd as usize) >= MAX_FDS {
        return;
    }
    unsafe {
        if let Some(owners) = get_fd_owner_base_ptr() {
            let src_slot = ptr::read_unaligned(owners.add(src_fd as usize));
            ptr::write_unaligned(owners.add(dst_fd as usize), src_slot);
        }
    }
}

unsafe fn read_stable_config(config_ptr: *mut FaultcoreConfig) -> Option<FaultcoreConfig> {
    for _ in 0..10 {
        let generation_ptr = unsafe {
            config_ptr
                .cast::<u8>()
                .add(OFFSET_RULESET_GENERATION) as *const u64
        };
        let g1 = unsafe { ptr::read_unaligned(generation_ptr) };
        if !g1.is_multiple_of(2) {
            continue;
        }
        fence(Ordering::SeqCst);
        let config = unsafe { ptr::read_unaligned(config_ptr) };
        fence(Ordering::SeqCst);
        let g2 = unsafe { ptr::read_unaligned(generation_ptr) };
        if g1 != g2 {
            continue;
        }
        if config.is_valid() {
            return Some(config);
        }
        break;
    }
    None
}

unsafe fn write_config_with_generation_publish<F>(config_ptr: *mut FaultcoreConfig, mutate: F)
where
    F: FnOnce(&mut FaultcoreConfig),
{
    let generation_ptr =
        unsafe { config_ptr.cast::<u8>().add(OFFSET_RULESET_GENERATION) as *mut u64 };
    let start_generation = unsafe { ptr::read_unaligned(generation_ptr as *const u64) } | 1;

    unsafe { ptr::write_unaligned(generation_ptr, start_generation) };
    fence(Ordering::SeqCst);

    let mut config = unsafe { ptr::read_unaligned(config_ptr) };
    mutate(&mut config);
    config.ruleset_generation = start_generation;

    unsafe { ptr::write_unaligned(config_ptr, config) };
    fence(Ordering::SeqCst);

    let published_generation = (start_generation.wrapping_add(1)) & !1;
    unsafe { ptr::write_unaligned(generation_ptr, published_generation) };
}

pub fn update_config_for_tid<F>(tid: usize, mutate: F) -> bool
where
    F: FnOnce(&mut FaultcoreConfig),
{
    if let Some(config_ptr) = unsafe { get_config_ptr(tid, true) } {
        unsafe {
            write_config_with_generation_publish(config_ptr, |config| {
                mutate(config);
                config.magic = FAULTCORE_MAGIC;
            });
        }
        return true;
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{
        Arc, Barrier, Mutex,
        atomic::{AtomicBool, Ordering as AtomicOrdering},
    };
    use std::thread;

    static TEST_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn test_faultcore_config_is_valid() {
        let config = FaultcoreConfig {
            magic: FAULTCORE_MAGIC,
            version: 1,
            latency_ns: 100_000_000,
            jitter_ns: 0,
            packet_loss_ppm: 0,
            burst_loss_len: 0,
            bandwidth_bps: 0,
            connect_timeout_ms: 5000,
            recv_timeout_ms: 3000,
            uplink_latency_ns: 0,
            uplink_jitter_ns: 0,
            uplink_packet_loss_ppm: 0,
            uplink_burst_loss_len: 0,
            uplink_bandwidth_bps: 0,
            downlink_latency_ns: 0,
            downlink_jitter_ns: 0,
            downlink_packet_loss_ppm: 0,
            downlink_burst_loss_len: 0,
            downlink_bandwidth_bps: 0,
            ge_enabled: 0,
            ge_p_good_to_bad_ppm: 0,
            ge_p_bad_to_good_ppm: 0,
            ge_loss_good_ppm: 0,
            ge_loss_bad_ppm: 0,
            conn_err_kind: 0,
            conn_err_prob_ppm: 0,
            half_open_after_bytes: 0,
            half_open_err_kind: 0,
            dup_prob_ppm: 0,
            dup_max_extra: 0,
            reorder_prob_ppm: 0,
            reorder_max_delay_ns: 0,
            reorder_window: 0,
            dns_delay_ns: 0,
            dns_timeout_ms: 0,
            dns_nxdomain_ppm: 0,
            target_enabled: 0,
            target_kind: 0,
            target_ipv4: 0,
            target_prefix_len: 0,
            target_port: 0,
            target_protocol: 0,
            schedule_type: 0,
            schedule_param_a_ns: 0,
            schedule_param_b_ns: 0,
            schedule_param_c_ns: 0,
            schedule_started_monotonic_ns: 0,
            reserved: 0,
            ruleset_generation: 0,
            target_address_family: 0,
            target_addr: [0; 16],
            target_hostname: [0; 32],
            target_sni: [0; 32],
            session_budget_enabled: 0,
            session_max_bytes_tx: 0,
            session_max_bytes_rx: 0,
            session_max_ops: 0,
            session_max_duration_ms: 0,
            session_action: 0,
            session_budget_timeout_ms: 0,
            session_error_kind: 0,
        };
        assert!(config.is_valid());
    }

    #[test]
    fn test_faultcore_config_invalid_magic() {
        let config = FaultcoreConfig {
            magic: 0xDEADBEEF,
            version: 1,
            latency_ns: 100_000_000,
            jitter_ns: 0,
            packet_loss_ppm: 0,
            burst_loss_len: 0,
            bandwidth_bps: 0,
            connect_timeout_ms: 5000,
            recv_timeout_ms: 3000,
            uplink_latency_ns: 0,
            uplink_jitter_ns: 0,
            uplink_packet_loss_ppm: 0,
            uplink_burst_loss_len: 0,
            uplink_bandwidth_bps: 0,
            downlink_latency_ns: 0,
            downlink_jitter_ns: 0,
            downlink_packet_loss_ppm: 0,
            downlink_burst_loss_len: 0,
            downlink_bandwidth_bps: 0,
            ge_enabled: 0,
            ge_p_good_to_bad_ppm: 0,
            ge_p_bad_to_good_ppm: 0,
            ge_loss_good_ppm: 0,
            ge_loss_bad_ppm: 0,
            conn_err_kind: 0,
            conn_err_prob_ppm: 0,
            half_open_after_bytes: 0,
            half_open_err_kind: 0,
            dup_prob_ppm: 0,
            dup_max_extra: 0,
            reorder_prob_ppm: 0,
            reorder_max_delay_ns: 0,
            reorder_window: 0,
            dns_delay_ns: 0,
            dns_timeout_ms: 0,
            dns_nxdomain_ppm: 0,
            target_enabled: 0,
            target_kind: 0,
            target_ipv4: 0,
            target_prefix_len: 0,
            target_port: 0,
            target_protocol: 0,
            schedule_type: 0,
            schedule_param_a_ns: 0,
            schedule_param_b_ns: 0,
            schedule_param_c_ns: 0,
            schedule_started_monotonic_ns: 0,
            reserved: 0,
            ruleset_generation: 0,
            target_address_family: 0,
            target_addr: [0; 16],
            target_hostname: [0; 32],
            target_sni: [0; 32],
            session_budget_enabled: 0,
            session_max_bytes_tx: 0,
            session_max_bytes_rx: 0,
            session_max_ops: 0,
            session_max_duration_ms: 0,
            session_action: 0,
            session_budget_timeout_ms: 0,
            session_error_kind: 0,
        };
        assert!(!config.is_valid());
    }

    #[test]
    fn test_tid_collision() {
        let _guard = TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut table = vec![0u64; FAULTCORE_SHM_SIZE.div_ceil(core::mem::size_of::<u64>())];

        let prev_ptr = *SHM_POINTER.read();
        let prev_open = SHM_OPEN.load(Ordering::SeqCst);

        *SHM_POINTER.write() = table.as_mut_ptr().cast::<u8>() as usize;
        SHM_OPEN.store(1, Ordering::SeqCst);

        let tid1 = 0;
        let tid2 = MAX_TIDS;

        unsafe {
            let ptr1 = get_config_ptr(tid1, true);
            let ptr2 = get_config_ptr(tid2, true);

            assert_ne!(
                ptr1, ptr2,
                "TIDs {} and {} incorrectly collide in SHM mapping",
                tid1, tid2
            );
        }

        *SHM_POINTER.write() = prev_ptr;
        SHM_OPEN.store(prev_open, Ordering::SeqCst);
    }

    #[test]
    fn test_clear_rule_for_fd_resets_fd_slot() {
        let _guard = TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut table = vec![0u64; FAULTCORE_SHM_SIZE.div_ceil(core::mem::size_of::<u64>())];

        let prev_ptr = *SHM_POINTER.read();
        let prev_open = SHM_OPEN.load(Ordering::SeqCst);

        *SHM_POINTER.write() = table.as_mut_ptr().cast::<u8>() as usize;
        SHM_OPEN.store(1, Ordering::SeqCst);

        let fd = 7usize;
        unsafe {
            let ptr = get_config_ptr(fd, false).expect("fd pointer should exist");
            ptr.write(FaultcoreConfig {
                magic: FAULTCORE_MAGIC,
                version: 2,
                latency_ns: 123,
                jitter_ns: 234,
                packet_loss_ppm: 456,
                burst_loss_len: 567,
                bandwidth_bps: 789,
                connect_timeout_ms: 111,
                recv_timeout_ms: 222,
                uplink_latency_ns: 0,
                uplink_jitter_ns: 0,
                uplink_packet_loss_ppm: 0,
                uplink_burst_loss_len: 0,
                uplink_bandwidth_bps: 0,
                downlink_latency_ns: 0,
                downlink_jitter_ns: 0,
                downlink_packet_loss_ppm: 0,
                downlink_burst_loss_len: 0,
                downlink_bandwidth_bps: 0,
                ge_enabled: 0,
                ge_p_good_to_bad_ppm: 0,
                ge_p_bad_to_good_ppm: 0,
                ge_loss_good_ppm: 0,
                ge_loss_bad_ppm: 0,
                conn_err_kind: 0,
                conn_err_prob_ppm: 0,
                half_open_after_bytes: 0,
                half_open_err_kind: 0,
                dup_prob_ppm: 0,
                dup_max_extra: 0,
                reorder_prob_ppm: 0,
                reorder_max_delay_ns: 0,
                reorder_window: 0,
                dns_delay_ns: 0,
                dns_timeout_ms: 0,
                dns_nxdomain_ppm: 0,
                target_enabled: 0,
                target_kind: 0,
                target_ipv4: 0,
                target_prefix_len: 0,
                target_port: 0,
                target_protocol: 0,
                schedule_type: 0,
                schedule_param_a_ns: 0,
                schedule_param_b_ns: 0,
                schedule_param_c_ns: 0,
                schedule_started_monotonic_ns: 0,
                reserved: 0,
                ruleset_generation: 0,
                target_address_family: 0,
                target_addr: [0; 16],
                target_hostname: [0; 32],
                target_sni: [0; 32],
                session_budget_enabled: 0,
                session_max_bytes_tx: 0,
                session_max_bytes_rx: 0,
                session_max_ops: 0,
                session_max_duration_ms: 0,
                session_action: 0,
                session_budget_timeout_ms: 0,
                session_error_kind: 0,
            });
        }

        clear_rule_for_fd(fd as c_int);

        unsafe {
            let ptr = get_config_ptr(fd, false).expect("fd pointer should exist");
            let base = ptr as *const u8;
            let magic = ptr::read_unaligned(base as *const u32);
            let ruleset_generation = ptr::read_unaligned(base.add(376) as *const u64);
            let latency_ns = ptr::read_unaligned(base.add(12) as *const u64);
            let jitter_ns = ptr::read_unaligned(base.add(20) as *const u64);
            let packet_loss_ppm = ptr::read_unaligned(base.add(28) as *const u64);
            let burst_loss_len = ptr::read_unaligned(base.add(36) as *const u64);
            let bandwidth_bps = ptr::read_unaligned(base.add(44) as *const u64);
            let connect_timeout_ms = ptr::read_unaligned(base.add(52) as *const u64);
            let recv_timeout_ms = ptr::read_unaligned(base.add(60) as *const u64);
            let uplink_latency_ns = ptr::read_unaligned(base.add(68) as *const u64);
            let uplink_jitter_ns = ptr::read_unaligned(base.add(76) as *const u64);
            let uplink_packet_loss_ppm = ptr::read_unaligned(base.add(84) as *const u64);
            let uplink_burst_loss_len = ptr::read_unaligned(base.add(92) as *const u64);
            let uplink_bandwidth_bps = ptr::read_unaligned(base.add(100) as *const u64);
            let downlink_latency_ns = ptr::read_unaligned(base.add(108) as *const u64);
            let downlink_jitter_ns = ptr::read_unaligned(base.add(116) as *const u64);
            let downlink_packet_loss_ppm = ptr::read_unaligned(base.add(124) as *const u64);
            let downlink_burst_loss_len = ptr::read_unaligned(base.add(132) as *const u64);
            let downlink_bandwidth_bps = ptr::read_unaligned(base.add(140) as *const u64);
            let ge_enabled = ptr::read_unaligned(base.add(148) as *const u64);
            let ge_p_good_to_bad_ppm = ptr::read_unaligned(base.add(156) as *const u64);
            let ge_p_bad_to_good_ppm = ptr::read_unaligned(base.add(164) as *const u64);
            let ge_loss_good_ppm = ptr::read_unaligned(base.add(172) as *const u64);
            let ge_loss_bad_ppm = ptr::read_unaligned(base.add(180) as *const u64);
            let conn_err_kind = ptr::read_unaligned(base.add(188) as *const u64);
            let conn_err_prob_ppm = ptr::read_unaligned(base.add(196) as *const u64);
            let half_open_after_bytes = ptr::read_unaligned(base.add(204) as *const u64);
            let half_open_err_kind = ptr::read_unaligned(base.add(212) as *const u64);
            let dup_prob_ppm = ptr::read_unaligned(base.add(220) as *const u64);
            let dup_max_extra = ptr::read_unaligned(base.add(228) as *const u64);
            let reorder_prob_ppm = ptr::read_unaligned(base.add(236) as *const u64);
            let reorder_max_delay_ns = ptr::read_unaligned(base.add(244) as *const u64);
            let reorder_window = ptr::read_unaligned(base.add(252) as *const u64);
            let dns_delay_ns = ptr::read_unaligned(base.add(260) as *const u64);
            let dns_timeout_ms = ptr::read_unaligned(base.add(268) as *const u64);
            let dns_nxdomain_ppm = ptr::read_unaligned(base.add(276) as *const u64);
            let target_enabled = ptr::read_unaligned(base.add(284) as *const u64);
            let target_kind = ptr::read_unaligned(base.add(292) as *const u64);
            let target_ipv4 = ptr::read_unaligned(base.add(300) as *const u64);
            let target_prefix_len = ptr::read_unaligned(base.add(308) as *const u64);
            let target_port = ptr::read_unaligned(base.add(316) as *const u64);
            let target_protocol = ptr::read_unaligned(base.add(324) as *const u64);
            let schedule_type = ptr::read_unaligned(base.add(332) as *const u64);
            let schedule_param_a_ns = ptr::read_unaligned(base.add(340) as *const u64);
            let schedule_param_b_ns = ptr::read_unaligned(base.add(348) as *const u64);
            let schedule_param_c_ns = ptr::read_unaligned(base.add(356) as *const u64);
            let schedule_started_monotonic_ns = ptr::read_unaligned(base.add(364) as *const u64);
            let reserved = ptr::read_unaligned(base.add(372) as *const u32);
            assert_eq!(magic, 0);
            assert_eq!(ruleset_generation % 2, 0);
            assert_eq!(latency_ns, 0);
            assert_eq!(jitter_ns, 0);
            assert_eq!(packet_loss_ppm, 0);
            assert_eq!(burst_loss_len, 0);
            assert_eq!(bandwidth_bps, 0);
            assert_eq!(connect_timeout_ms, 0);
            assert_eq!(recv_timeout_ms, 0);
            assert_eq!(uplink_latency_ns, 0);
            assert_eq!(uplink_jitter_ns, 0);
            assert_eq!(uplink_packet_loss_ppm, 0);
            assert_eq!(uplink_burst_loss_len, 0);
            assert_eq!(uplink_bandwidth_bps, 0);
            assert_eq!(downlink_latency_ns, 0);
            assert_eq!(downlink_jitter_ns, 0);
            assert_eq!(downlink_packet_loss_ppm, 0);
            assert_eq!(downlink_burst_loss_len, 0);
            assert_eq!(downlink_bandwidth_bps, 0);
            assert_eq!(ge_enabled, 0);
            assert_eq!(ge_p_good_to_bad_ppm, 0);
            assert_eq!(ge_p_bad_to_good_ppm, 0);
            assert_eq!(ge_loss_good_ppm, 0);
            assert_eq!(ge_loss_bad_ppm, 0);
            assert_eq!(conn_err_kind, 0);
            assert_eq!(conn_err_prob_ppm, 0);
            assert_eq!(half_open_after_bytes, 0);
            assert_eq!(half_open_err_kind, 0);
            assert_eq!(dup_prob_ppm, 0);
            assert_eq!(dup_max_extra, 0);
            assert_eq!(reorder_prob_ppm, 0);
            assert_eq!(reorder_max_delay_ns, 0);
            assert_eq!(reorder_window, 0);
            assert_eq!(dns_delay_ns, 0);
            assert_eq!(dns_timeout_ms, 0);
            assert_eq!(dns_nxdomain_ppm, 0);
            assert_eq!(target_enabled, 0);
            assert_eq!(target_kind, 0);
            assert_eq!(target_ipv4, 0);
            assert_eq!(target_prefix_len, 0);
            assert_eq!(target_port, 0);
            assert_eq!(target_protocol, 0);
            assert_eq!(schedule_type, 0);
            assert_eq!(schedule_param_a_ns, 0);
            assert_eq!(schedule_param_b_ns, 0);
            assert_eq!(schedule_param_c_ns, 0);
            assert_eq!(schedule_started_monotonic_ns, 0);
            assert_eq!(reserved, 0);
        }

        *SHM_POINTER.write() = prev_ptr;
        SHM_OPEN.store(prev_open, Ordering::SeqCst);
    }

    #[test]
    fn test_get_config_for_tid_slot_reads_tid_region() {
        let _guard = TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut table = vec![0u64; FAULTCORE_SHM_SIZE.div_ceil(core::mem::size_of::<u64>())];

        let prev_ptr = *SHM_POINTER.read();
        let prev_open = SHM_OPEN.load(Ordering::SeqCst);

        *SHM_POINTER.write() = table.as_mut_ptr().cast::<u8>() as usize;
        SHM_OPEN.store(1, Ordering::SeqCst);

        let slot = 123usize;
        unsafe {
            let base = *SHM_POINTER.read() as *mut FaultcoreConfig;
            let ptr = base.add(MAX_FDS + slot);
            ptr::write_unaligned(
                ptr,
                FaultcoreConfig {
                    magic: FAULTCORE_MAGIC,
                    version: 2,
                    reorder_prob_ppm: 1_000_000,
                    reorder_window: 2,
                    ..Default::default()
                },
            );
        }

        let cfg = get_config_for_tid_slot(slot).expect("tid slot config should be readable");
        let reorder_prob_ppm = cfg.reorder_prob_ppm;
        let reorder_window = cfg.reorder_window;
        assert_eq!(reorder_prob_ppm, 1_000_000);
        assert_eq!(reorder_window, 2);

        *SHM_POINTER.write() = prev_ptr;
        SHM_OPEN.store(prev_open, Ordering::SeqCst);
    }

    #[test]
    fn test_assign_rule_to_fd_ignores_out_of_range_fd() {
        let _guard = TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut table = vec![0u64; FAULTCORE_SHM_SIZE.div_ceil(core::mem::size_of::<u64>()) + 1];

        let prev_ptr = *SHM_POINTER.read();
        let prev_open = SHM_OPEN.load(Ordering::SeqCst);

        *SHM_POINTER.write() = table.as_mut_ptr().cast::<u8>() as usize;
        SHM_OPEN.store(1, Ordering::SeqCst);

        let guard_idx = FAULTCORE_SHM_SIZE / core::mem::size_of::<u64>();
        table[guard_idx] = 0xABCD_EF01;

        assign_rule_to_fd(MAX_FDS as c_int, 1234);

        assert_eq!(table[guard_idx], 0xABCD_EF01);

        *SHM_POINTER.write() = prev_ptr;
        SHM_OPEN.store(prev_open, Ordering::SeqCst);
    }

    #[test]
    fn test_clear_rule_for_fd_ignores_out_of_range_fd() {
        let _guard = TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut table = vec![0u64; FAULTCORE_SHM_SIZE.div_ceil(core::mem::size_of::<u64>()) + 1];

        let prev_ptr = *SHM_POINTER.read();
        let prev_open = SHM_OPEN.load(Ordering::SeqCst);

        *SHM_POINTER.write() = table.as_mut_ptr().cast::<u8>() as usize;
        SHM_OPEN.store(1, Ordering::SeqCst);

        let guard_idx = FAULTCORE_SHM_SIZE / core::mem::size_of::<u64>();
        table[guard_idx] = 0x1234_5678;

        clear_rule_for_fd(MAX_FDS as c_int);

        assert_eq!(table[guard_idx], 0x1234_5678);

        *SHM_POINTER.write() = prev_ptr;
        SHM_OPEN.store(prev_open, Ordering::SeqCst);
    }

    #[test]
    fn test_clone_rule_for_fd_copies_owner_slot() {
        let _guard = TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut table = vec![0u64; FAULTCORE_SHM_SIZE.div_ceil(core::mem::size_of::<u64>())];

        let prev_ptr = *SHM_POINTER.read();
        let prev_open = SHM_OPEN.load(Ordering::SeqCst);
        *SHM_POINTER.write() = table.as_mut_ptr().cast::<u8>() as usize;
        SHM_OPEN.store(1, Ordering::SeqCst);

        let src_fd = 12 as c_int;
        let dst_fd = 34 as c_int;
        assign_rule_to_fd(src_fd, 4242);
        clone_rule_for_fd(src_fd, dst_fd);

        assert_eq!(get_tid_slot_for_fd(src_fd), get_tid_slot_for_fd(dst_fd));

        *SHM_POINTER.write() = prev_ptr;
        SHM_OPEN.store(prev_open, Ordering::SeqCst);
    }

    #[test]
    fn test_get_tid_slot_for_fd_out_of_range_returns_none() {
        let _guard = TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut table = vec![0u64; FAULTCORE_SHM_SIZE.div_ceil(core::mem::size_of::<u64>()) + 1];

        let prev_ptr = *SHM_POINTER.read();
        let prev_open = SHM_OPEN.load(Ordering::SeqCst);

        *SHM_POINTER.write() = table.as_mut_ptr().cast::<u8>() as usize;
        SHM_OPEN.store(1, Ordering::SeqCst);

        let guard_idx = FAULTCORE_SHM_SIZE / core::mem::size_of::<u64>();
        table[guard_idx] = 1;

        let slot = get_tid_slot_for_fd(MAX_FDS as c_int);
        assert!(slot.is_none());

        *SHM_POINTER.write() = prev_ptr;
        SHM_OPEN.store(prev_open, Ordering::SeqCst);
    }

    #[test]
    fn test_shm_open_mode_defaults_to_consumer() {
        unsafe {
            std::env::remove_var("FAULTCORE_SHM_OPEN_MODE");
        }
        assert_eq!(shm_open_mode(), ShmOpenMode::Consumer);
    }

    #[test]
    fn test_shm_open_mode_accepts_creator() {
        unsafe {
            std::env::set_var("FAULTCORE_SHM_OPEN_MODE", "creator");
        }
        assert_eq!(shm_open_mode(), ShmOpenMode::Creator);
        unsafe {
            std::env::remove_var("FAULTCORE_SHM_OPEN_MODE");
        }
    }

    #[test]
    fn test_get_config_for_tid_never_observes_torn_writes_under_concurrency() {
        let _guard = TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut table = vec![0u64; FAULTCORE_SHM_SIZE.div_ceil(core::mem::size_of::<u64>())];

        let prev_ptr = *SHM_POINTER.read();
        let prev_open = SHM_OPEN.load(Ordering::SeqCst);
        *SHM_POINTER.write() = table.as_mut_ptr().cast::<u8>() as usize;
        SHM_OPEN.store(1, Ordering::SeqCst);

        let tid = 4242usize;
        assert!(update_config_for_tid(tid, |cfg| {
            cfg.latency_ns = 111;
            cfg.jitter_ns = 222;
            cfg.packet_loss_ppm = 333;
            cfg.bandwidth_bps = 444;
            cfg.connect_timeout_ms = 555;
            cfg.recv_timeout_ms = 666;
        }));

        let stop = Arc::new(AtomicBool::new(false));
        let start = Arc::new(Barrier::new(6));

        let writer_start = Arc::clone(&start);
        let writer_stop = Arc::clone(&stop);
        let writer = thread::spawn(move || {
            writer_start.wait();
            for i in 0..20_000 {
                let use_a = i % 2 == 0;
                let ok = update_config_for_tid(tid, |cfg| {
                    if use_a {
                        cfg.latency_ns = 111;
                        cfg.jitter_ns = 222;
                        cfg.packet_loss_ppm = 333;
                        cfg.bandwidth_bps = 444;
                        cfg.connect_timeout_ms = 555;
                        cfg.recv_timeout_ms = 666;
                    } else {
                        cfg.latency_ns = 10_111;
                        cfg.jitter_ns = 10_222;
                        cfg.packet_loss_ppm = 10_333;
                        cfg.bandwidth_bps = 10_444;
                        cfg.connect_timeout_ms = 10_555;
                        cfg.recv_timeout_ms = 10_666;
                    }
                });
                assert!(ok, "writer failed to update config");
            }
            writer_stop.store(true, AtomicOrdering::Release);
        });

        let mut readers = Vec::new();
        for _ in 0..4 {
            let reader_start = Arc::clone(&start);
            let reader_stop = Arc::clone(&stop);
            readers.push(thread::spawn(move || {
                reader_start.wait();
                while !reader_stop.load(AtomicOrdering::Acquire) {
                    if let Some(cfg) = get_config_for_tid(tid as u64) {
                        let is_profile_a = cfg.latency_ns == 111
                            && cfg.jitter_ns == 222
                            && cfg.packet_loss_ppm == 333
                            && cfg.bandwidth_bps == 444
                            && cfg.connect_timeout_ms == 555
                            && cfg.recv_timeout_ms == 666;
                        let is_profile_b = cfg.latency_ns == 10_111
                            && cfg.jitter_ns == 10_222
                            && cfg.packet_loss_ppm == 10_333
                            && cfg.bandwidth_bps == 10_444
                            && cfg.connect_timeout_ms == 10_555
                            && cfg.recv_timeout_ms == 10_666;
                        let latency_ns = cfg.latency_ns;
                        let jitter_ns = cfg.jitter_ns;
                        let packet_loss_ppm = cfg.packet_loss_ppm;
                        let bandwidth_bps = cfg.bandwidth_bps;
                        let connect_timeout_ms = cfg.connect_timeout_ms;
                        let recv_timeout_ms = cfg.recv_timeout_ms;
                        assert!(
                            is_profile_a || is_profile_b,
                            "observed torn config snapshot: latency={} jitter={} loss={} bandwidth={} cto={} rto={}",
                            latency_ns,
                            jitter_ns,
                            packet_loss_ppm,
                            bandwidth_bps,
                            connect_timeout_ms,
                            recv_timeout_ms
                        );
                    }
                }
            }));
        }

        start.wait();
        writer.join().expect("writer thread must complete");
        for reader in readers {
            reader.join().expect("reader thread must complete");
        }

        *SHM_POINTER.write() = prev_ptr;
        SHM_OPEN.store(prev_open, Ordering::SeqCst);
    }
}
