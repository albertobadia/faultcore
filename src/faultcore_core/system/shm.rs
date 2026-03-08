use libc::{MAP_SHARED, O_CREAT, O_RDWR, PROT_READ, PROT_WRITE, ftruncate, mmap, shm_open};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};

pub fn get_thread_id() -> u64 {
    unsafe { libc::syscall(libc::SYS_gettid) as u64 }
}

pub const FAULTCORE_MAGIC: u32 = 0xFACC0DE;
pub const MAX_FDS: usize = 131072;
pub const MAX_TIDS: usize = 8192;
pub const MAX_POLICIES: usize = 1024;
pub const FAULTCORE_SHM_SIZE: usize = ((MAX_FDS + MAX_TIDS)
    * std::mem::size_of::<FaultcoreConfig>())
    + (MAX_POLICIES * std::mem::size_of::<PolicyState>());

#[repr(C)]
#[derive(Debug, Clone, Copy, Default)]
pub struct FaultcoreConfig {
    pub magic: u32,
    pub version: u64,
    pub latency_ns: u64,
    pub packet_loss_ppm: u64,
    pub bandwidth_bps: u64,
    pub connect_timeout_ms: u64,
    pub recv_timeout_ms: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Default)]
pub struct PolicyState {
    pub magic: u32,
    pub name: [u8; 32],
    pub enabled: bool,
    pub total_calls: u64,
    pub total_failures: u64,
}

struct ShmState {
    pointer: usize,
    version: AtomicU64,
}

static SHM_STATE: OnceLock<ShmState> = OnceLock::new();
static SHM_INIT_MUTEX: Mutex<()> = Mutex::new(());

fn get_shm_prefix() -> &'static str {
    ""
}

fn get_shm_name(pid: u32) -> String {
    format!("{}/faultcore_{}_config", get_shm_prefix(), pid)
}

pub fn create_shm() -> Result<(), String> {
    if SHM_STATE.get().is_some() {
        return Ok(());
    }
    let _lock = SHM_INIT_MUTEX.lock().map_err(|e| e.to_string())?;
    if SHM_STATE.get().is_some() {
        return Ok(());
    }
    let shm_name = {
        if let Ok(name) = std::env::var("FAULTCORE_CONFIG_SHM")
            && !name.is_empty()
        {
            name
        } else {
            get_shm_name(unsafe { libc::getpid() } as u32)
        }
    };
    unsafe {
        std::env::set_var("FAULTCORE_CONFIG_SHM", &shm_name);
    }

    let name_cstr = std::ffi::CString::new(shm_name.as_bytes()).map_err(|e| e.to_string())?;

    unsafe {
        let fd = shm_open(name_cstr.as_ptr(), O_CREAT | O_RDWR, 0o600);
        if fd < 0 {
            let err = std::io::Error::last_os_error();
            return Err(format!("Failed to create shm: {}", err));
        }

        if ftruncate(fd, FAULTCORE_SHM_SIZE as i64) < 0 {
            libc::close(fd);
            return Err(format!(
                "Failed to truncate shm: {}",
                std::io::Error::last_os_error()
            ));
        }

        let addr = mmap(
            std::ptr::null_mut(),
            FAULTCORE_SHM_SIZE,
            PROT_READ | PROT_WRITE,
            MAP_SHARED,
            fd,
            0,
        );
        libc::close(fd);

        if addr as isize == -1isize {
            return Err(format!(
                "Failed to mmap shm: {}",
                std::io::Error::last_os_error()
            ));
        }

        std::ptr::write_bytes(addr as *mut u8, 0, FAULTCORE_SHM_SIZE);

        let state = ShmState {
            pointer: addr as usize,
            version: AtomicU64::new(1),
        };
        SHM_STATE
            .set(state)
            .map_err(|_| "SHM already initialized".to_string())?;
    }
    Ok(())
}

pub fn is_shm_open() -> bool {
    SHM_STATE.get().is_some()
}

unsafe fn get_config_ptr(tid_or_fd: usize, is_tid: bool) -> Option<*mut FaultcoreConfig> {
    let state = SHM_STATE.get()?;
    let base_ptr = state.pointer;
    if base_ptr == 0 {
        return None;
    }
    let array = base_ptr as *mut FaultcoreConfig;
    let idx = if is_tid {
        MAX_FDS + (tid_or_fd % MAX_TIDS)
    } else {
        if tid_or_fd >= MAX_FDS {
            return None;
        }
        tid_or_fd
    };
    unsafe { Some(array.add(idx)) }
}

pub fn write_latency(tid: u64, latency_ms: u64) -> Result<(), String> {
    unsafe {
        if let Some(config_ptr) = get_config_ptr(tid as usize, true) {
            let state = SHM_STATE.get().ok_or("SHM not initialized")?;
            let mut cfg = config_ptr.read();
            cfg.magic = FAULTCORE_MAGIC;
            cfg.latency_ns = latency_ms * 1_000_000;
            cfg.version = state.version.fetch_add(1, Ordering::SeqCst) + 1;
            config_ptr.write(cfg);
            Ok(())
        } else {
            Err("SHM not initialized".to_string())
        }
    }
}

pub fn write_packet_loss(tid: u64, ppm: u64) -> Result<(), String> {
    unsafe {
        if let Some(config_ptr) = get_config_ptr(tid as usize, true) {
            let state = SHM_STATE.get().ok_or("SHM not initialized")?;
            let mut cfg = config_ptr.read();
            cfg.magic = FAULTCORE_MAGIC;
            cfg.packet_loss_ppm = ppm;
            cfg.version = state.version.fetch_add(1, Ordering::SeqCst) + 1;
            config_ptr.write(cfg);
            Ok(())
        } else {
            Err("SHM not initialized".to_string())
        }
    }
}

pub fn write_bandwidth(tid: u64, bps: u64) -> Result<(), String> {
    unsafe {
        if let Some(config_ptr) = get_config_ptr(tid as usize, true) {
            let state = SHM_STATE.get().ok_or("SHM not initialized")?;
            let mut cfg = config_ptr.read();
            cfg.magic = FAULTCORE_MAGIC;
            cfg.bandwidth_bps = bps;
            cfg.version = state.version.fetch_add(1, Ordering::SeqCst) + 1;
            config_ptr.write(cfg);
            Ok(())
        } else {
            Err("SHM not initialized".to_string())
        }
    }
}

pub fn write_timeouts(tid: u64, connect_ms: u64, recv_ms: u64) -> Result<(), String> {
    unsafe {
        if let Some(config_ptr) = get_config_ptr(tid as usize, true) {
            let state = SHM_STATE.get().ok_or("SHM not initialized")?;
            let mut cfg = config_ptr.read();
            cfg.magic = FAULTCORE_MAGIC;
            cfg.connect_timeout_ms = connect_ms;
            cfg.recv_timeout_ms = recv_ms;
            cfg.version = state.version.fetch_add(1, Ordering::SeqCst) + 1;
            config_ptr.write(cfg);
            Ok(())
        } else {
            Err("SHM not initialized".to_string())
        }
    }
}

pub fn clear_config(tid: u64) -> Result<(), String> {
    unsafe {
        if let Some(config_ptr) = get_config_ptr(tid as usize, true) {
            let state = SHM_STATE.get().ok_or("SHM not initialized")?;
            let mut cfg = config_ptr.read();
            cfg.magic = 0;
            cfg.latency_ns = 0;
            cfg.packet_loss_ppm = 0;
            cfg.bandwidth_bps = 0;
            cfg.connect_timeout_ms = 0;
            cfg.recv_timeout_ms = 0;
            cfg.version = state.version.fetch_add(1, Ordering::SeqCst) + 1;
            config_ptr.write(cfg);
            Ok(())
        } else {
            Ok(())
        }
    }
}

/// Returns a pointer to the policy state at the given index in SHM.
///
/// # Safety
/// The caller must ensure that SHM is open and the index is within bounds.
pub unsafe fn get_policy_ptr(idx: usize) -> Option<*mut PolicyState> {
    let state = SHM_STATE.get()?;
    let base_ptr = state.pointer;
    if base_ptr == 0 || idx >= MAX_POLICIES {
        return None;
    }
    unsafe {
        let array_start = (base_ptr as *mut FaultcoreConfig).add(MAX_FDS + MAX_TIDS);
        let policy_array = array_start as *mut PolicyState;
        Some(policy_array.add(idx))
    }
}

pub fn write_policy_state(
    idx: usize,
    name: &str,
    enabled: bool,
    calls: u64,
    failures: u64,
) -> Result<(), String> {
    unsafe {
        if let Some(ptr) = get_policy_ptr(idx) {
            let mut state = ptr.read();
            state.magic = FAULTCORE_MAGIC;
            let name_bytes = name.as_bytes();
            let len = name_bytes.len().min(31);
            state.name = [0; 32];
            state.name[..len].copy_from_slice(&name_bytes[..len]);
            state.enabled = enabled;
            state.total_calls = calls;
            state.total_failures = failures;
            ptr.write(state);
            Ok(())
        } else {
            Err("SHM not initialized or index out of bounds".to_string())
        }
    }
}

pub fn update_policy_metrics(idx: usize, success: bool) -> Result<(), String> {
    unsafe {
        if let Some(ptr) = get_policy_ptr(idx) {
            let mut state = ptr.read();
            if state.magic == FAULTCORE_MAGIC {
                state.total_calls += 1;
                if !success {
                    state.total_failures += 1;
                }
                ptr.write(state);
            }
            Ok(())
        } else {
            Err("SHM not initialized or index out of bounds".to_string())
        }
    }
}
