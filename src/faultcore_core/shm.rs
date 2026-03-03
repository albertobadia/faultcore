use libc::{MAP_SHARED, O_CREAT, O_RDWR, PROT_READ, PROT_WRITE, ftruncate, mmap, shm_open};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};

pub fn get_thread_id() -> u64 {
    unsafe { libc::syscall(libc::SYS_gettid) as u64 }
}

pub const FAULTCORE_MAGIC: u32 = 0xFACC0DE;
// To support FDs up to 65536 and 1024 TIDs.
// Size needed: (65536 + 1024) * sizeof(FaultcoreConfig) = ~3MB
pub const MAX_FDS: usize = 65536;
pub const MAX_TIDS: usize = 1024;
pub const FAULTCORE_SHM_SIZE: usize = (MAX_FDS + MAX_TIDS) * std::mem::size_of::<FaultcoreConfig>();

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

static SHM_POINTER: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
static SHM_VERSION: AtomicU64 = AtomicU64::new(1);
static SHM_OPEN: AtomicBool = AtomicBool::new(false);

fn get_shm_prefix() -> &'static str {
    ""
}

fn get_shm_name(pid: u32) -> String {
    format!("{}/faultcore_{}_config", get_shm_prefix(), pid)
}

#[allow(clippy::collapsible_if)]
pub fn get_shm_name_env() -> String {
    if let Ok(name) = std::env::var("FAULTCORE_CONFIG_SHM") {
        if !name.is_empty() {
            return name;
        }
    }
    get_shm_name(unsafe { libc::getpid() } as u32)
}

pub fn create_shm(_pid: u32) -> Result<(), String> {
    let shm_name = get_shm_name_env();
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

        // Initialize the memory
        std::ptr::write_bytes(addr as *mut u8, 0, FAULTCORE_SHM_SIZE);

        SHM_POINTER.store(addr as usize, Ordering::SeqCst);
        SHM_OPEN.store(true, Ordering::SeqCst);

        Ok(())
    }
}

pub fn is_shm_open() -> bool {
    SHM_OPEN.load(Ordering::SeqCst)
}

// Memory layout:
// [0 .. MAX_FDS]: FD array
// [MAX_FDS .. MAX_FDS + MAX_TIDS]: TID array
unsafe fn get_config_ptr(tid_or_fd: usize, is_tid: bool) -> Option<*mut FaultcoreConfig> {
    let base_ptr = SHM_POINTER.load(Ordering::SeqCst);
    if base_ptr == 0 {
        return None;
    }
    let array = base_ptr as *mut FaultcoreConfig;
    let idx = if is_tid {
        MAX_FDS + (tid_or_fd % MAX_TIDS)
    } else {
        if tid_or_fd >= MAX_FDS {
            return None; // Exceeds array size
        }
        tid_or_fd
    };
    unsafe { Some(array.add(idx)) }
}

pub fn write_latency(tid: u64, latency_ms: u64) -> Result<(), String> {
    unsafe {
        if let Some(config_ptr) = get_config_ptr(tid as usize, true) {
            let mut cfg = config_ptr.read();
            cfg.magic = FAULTCORE_MAGIC;
            cfg.latency_ns = latency_ms * 1_000_000;
            cfg.version = SHM_VERSION.fetch_add(1, Ordering::SeqCst) + 1;
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
            let mut cfg = config_ptr.read();
            cfg.magic = FAULTCORE_MAGIC;
            cfg.packet_loss_ppm = ppm;
            cfg.version = SHM_VERSION.fetch_add(1, Ordering::SeqCst) + 1;
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
            let mut cfg = config_ptr.read();
            cfg.magic = FAULTCORE_MAGIC;
            cfg.bandwidth_bps = bps;
            cfg.version = SHM_VERSION.fetch_add(1, Ordering::SeqCst) + 1;
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
            let mut cfg = config_ptr.read();
            cfg.magic = FAULTCORE_MAGIC;
            cfg.connect_timeout_ms = connect_ms;
            cfg.recv_timeout_ms = recv_ms;
            cfg.version = SHM_VERSION.fetch_add(1, Ordering::SeqCst) + 1;
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
            let mut cfg = config_ptr.read();
            cfg.magic = 0; // Invalidate magic to mark as empty
            cfg.latency_ns = 0;
            cfg.packet_loss_ppm = 0;
            cfg.bandwidth_bps = 0;
            cfg.connect_timeout_ms = 0;
            cfg.recv_timeout_ms = 0;
            cfg.version = SHM_VERSION.fetch_add(1, Ordering::SeqCst) + 1;
            config_ptr.write(cfg);
            Ok(())
        } else {
            // Already 0 or not open
            Ok(())
        }
    }
}
