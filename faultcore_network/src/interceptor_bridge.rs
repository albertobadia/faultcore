use libc::{c_int, sockaddr, socklen_t};

use crate::{
    Config, assign_rule_to_fd, clear_rule_for_fd, endpoint_for_addr_or_fd, endpoint_for_fd,
    get_config_for_fd, get_config_for_tid, get_thread_id, monotonic_now_ns, try_open_shm,
};

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
    cfg.runtime_filtered(endpoint_for_fd(fd), monotonic_now_ns())
}

/// # Safety
/// `addr` must point to a valid socket address buffer of at least `addr_len` bytes.
pub unsafe fn runtime_config_for_addr_or_fd(
    fd: c_int,
    addr: *const sockaddr,
    addr_len: socklen_t,
) -> Option<Config> {
    let cfg = get_config_for_fd(fd)?.into_network_config();
    cfg.runtime_filtered(
        unsafe { endpoint_for_addr_or_fd(fd, addr, addr_len) },
        monotonic_now_ns(),
    )
}

pub fn runtime_dns_config_for_current_thread() -> Option<Config> {
    let tid = get_thread_id();
    let cfg = get_config_for_tid(tid)?.into_network_config();
    cfg.runtime_filtered(None, monotonic_now_ns())
}
