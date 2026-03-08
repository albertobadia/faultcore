use libc::{MAP_SHARED, O_RDWR, PROT_READ, PROT_WRITE, c_int, ftruncate, mmap, shm_open};
use parking_lot::RwLock;
use std::ptr;
use std::sync::atomic::{AtomicU64, Ordering};

#[macro_export]
macro_rules! shm_error {
    ($($arg:tt)*) => {};
}

#[macro_export]
macro_rules! shm_info {
    ($($arg:tt)*) => {};
}

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

impl FaultcoreConfig {
    pub fn is_valid(&self) -> bool {
        self.magic == FAULTCORE_MAGIC
            && self.latency_ns <= MAX_LATENCY_NS
            && self.packet_loss_ppm <= 1_000_000
            && self.bandwidth_bps <= MAX_BANDWIDTH_BPS
    }

    pub fn into_network_config(self) -> faultcore_network::Config {
        faultcore_network::Config {
            latency_ns: self.latency_ns,
            packet_loss_ppm: self.packet_loss_ppm,
            bandwidth_bps: self.bandwidth_bps,
            connect_timeout_ms: self.connect_timeout_ms,
            recv_timeout_ms: self.recv_timeout_ms,
        }
    }
}

pub const MAX_LATENCY_NS: u64 = 60_000_000_000;
pub const MAX_BANDWIDTH_BPS: u64 = 100_000_000_000;

static SHM_POINTER: RwLock<usize> = RwLock::new(0);
static SHM_OPEN: AtomicU64 = AtomicU64::new(0);

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

pub fn try_open_shm() -> bool {
    if !check_enabled() || is_shm_open() {
        return is_shm_open();
    }

    let shm_name = get_shm_name()
        .unwrap_or_else(|| format!("/faultcore_{}_config", unsafe { libc::getpid() }));

    let name_cstr = std::ffi::CString::new(shm_name.as_bytes()).unwrap();

    unsafe {
        let fd = shm_open(name_cstr.as_ptr(), O_RDWR, 0);
        if fd < 0 {
            return false;
        }

        if ftruncate(fd, FAULTCORE_SHM_SIZE as i64) < 0 {
            libc::close(fd);
            return false;
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
            MAX_FDS + (tid_or_fd % MAX_TIDS)
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

pub fn get_config_for_fd(fd: c_int) -> Option<FaultcoreConfig> {
    if !is_shm_open() || fd < 0 {
        try_open_shm();
    }
    if fd < 0 {
        return None;
    }

    unsafe {
        if let Some(config_ptr) = get_config_ptr(fd as usize, false) {
            let config = config_ptr.read();
            if config.is_valid() {
                return Some(config);
            }
        }
    }
    None
}

pub fn assign_rule_to_fd(fd: c_int, tid: usize) {
    if fd < 0 {
        return;
    }
    unsafe {
        if let Some(tid_ptr) = get_config_ptr(tid, true) {
            let tid_cfg = tid_ptr.read();
            if tid_cfg.is_valid()
                && let Some(fd_ptr) = get_config_ptr(fd as usize, false)
            {
                fd_ptr.write(tid_cfg);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_faultcore_config_is_valid() {
        let config = FaultcoreConfig {
            magic: FAULTCORE_MAGIC,
            version: 1,
            latency_ns: 100_000_000,
            packet_loss_ppm: 0,
            bandwidth_bps: 0,
            connect_timeout_ms: 5000,
            recv_timeout_ms: 3000,
        };
        assert!(config.is_valid());
    }

    #[test]
    fn test_faultcore_config_invalid_magic() {
        let config = FaultcoreConfig {
            magic: 0xDEADBEEF,
            version: 1,
            latency_ns: 100_000_000,
            packet_loss_ppm: 0,
            bandwidth_bps: 0,
            connect_timeout_ms: 5000,
            recv_timeout_ms: 3000,
        };
        assert!(!config.is_valid());
    }
}
