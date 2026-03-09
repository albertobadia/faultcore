use faultcore_network::{
    Direction, FaultOsiEngine, InterceptorRuntime, LayerDecision, PendingDatagram,
    apply_connect_directive, apply_stream_directive, bind_fd_to_current_thread, clear_fd_binding,
    init_runtime_shm, runtime_config_for_addr_or_fd, runtime_config_for_fd,
    runtime_dns_config_for_current_thread, try_handle_setpriority,
};
use libc::{addrinfo, c_char, c_int, c_void, size_t, sockaddr, socklen_t, ssize_t};
use std::sync::atomic::{AtomicBool, Ordering};

static INITIALIZED: AtomicBool = AtomicBool::new(false);

type SendFn = unsafe extern "C" fn(c_int, *const c_void, size_t, c_int) -> ssize_t;
type RecvFn = unsafe extern "C" fn(c_int, *mut c_void, size_t, c_int) -> ssize_t;
type ConnectFn = unsafe extern "C" fn(c_int, *const sockaddr, socklen_t) -> c_int;
type SocketFn = unsafe extern "C" fn(c_int, c_int, c_int) -> c_int;
type CloseFn = unsafe extern "C" fn(c_int) -> c_int;
type SendToFn = unsafe extern "C" fn(
    c_int,
    *const c_void,
    size_t,
    c_int,
    *const sockaddr,
    socklen_t,
) -> ssize_t;
type RecvFromFn = unsafe extern "C" fn(
    c_int,
    *mut c_void,
    size_t,
    c_int,
    *mut sockaddr,
    *mut socklen_t,
) -> ssize_t;
type GetAddrInfoFn = unsafe extern "C" fn(
    *const c_char,
    *const c_char,
    *const addrinfo,
    *mut *mut addrinfo,
) -> c_int;

lazy_static::lazy_static! {
    pub static ref ORIG_SOCKET: SocketFn = unsafe { get_original_fn("socket") };
    pub static ref ORIG_CLOSE: CloseFn = unsafe { get_original_fn("close") };
    pub static ref ORIG_CONNECT: ConnectFn = unsafe { get_original_fn("connect") };
    pub static ref ORIG_SEND: SendFn = unsafe { get_original_fn("send") };
    pub static ref ORIG_RECV: RecvFn = unsafe { get_original_fn("recv") };
    pub static ref ORIG_SENDTO: SendToFn = unsafe { get_original_fn("sendto") };
    pub static ref ORIG_RECVFROM: RecvFromFn = unsafe { get_original_fn("recvfrom") };
    pub static ref ORIG_GETADDRINFO: GetAddrInfoFn = unsafe { get_original_fn("getaddrinfo") };

    pub static ref CHAOS_ENGINE: FaultOsiEngine = FaultOsiEngine::new();
    pub static ref INTERCEPTOR_RUNTIME: InterceptorRuntime = InterceptorRuntime::new();
}

unsafe fn get_original_fn<T>(name: &str) -> T {
    let symbol_name = std::ffi::CString::new(name).unwrap();
    let fn_ptr = unsafe { libc::dlsym(libc::RTLD_NEXT, symbol_name.as_ptr()) };
    if fn_ptr.is_null() {
        unsafe { libc::abort() };
    }
    unsafe { std::mem::transmute_copy(&fn_ptr) }
}

fn record_stream_bytes(fd: c_int, bytes: u64) {
    CHAOS_ENGINE.record_stream_bytes(fd, bytes);
}

fn maybe_duplicate_send(fd: c_int, b: *const c_void, sent: ssize_t, f: c_int) {
    if sent <= 0 {
        return;
    }
    let Some(network_cfg) = runtime_config_for_fd(fd) else {
        return;
    };
    let count = match CHAOS_ENGINE.evaluate_stream_post(&network_cfg, Direction::Uplink) {
        LayerDecision::Duplicate(n) => n,
        _ => 0,
    };
    for _ in 0..count {
        unsafe {
            let _ = (ORIG_SEND)(fd, b, sent as size_t, f);
        }
    }
}

fn maybe_duplicate_sendto(
    fd: c_int,
    b: *const c_void,
    sent: ssize_t,
    f: c_int,
    addr: *const sockaddr,
    addr_len: socklen_t,
) {
    if sent <= 0 {
        return;
    }
    let Some(network_cfg) = (unsafe { runtime_config_for_addr_or_fd(fd, addr, addr_len) }) else {
        return;
    };
    let count = match CHAOS_ENGINE.evaluate_stream_post(&network_cfg, Direction::Uplink) {
        LayerDecision::Duplicate(n) => n,
        _ => 0,
    };
    for _ in 0..count {
        unsafe {
            let _ = (ORIG_SENDTO)(fd, b, sent as size_t, f, addr, addr_len);
        }
    }
}

fn maybe_stage_reorder_sendto(
    b: *const c_void,
    l: size_t,
    f: c_int,
    addr: *const sockaddr,
    addr_len: socklen_t,
    pending: &mut std::collections::VecDeque<PendingDatagram>,
) -> Option<ssize_t> {
    if l == 0 || b.is_null() {
        return None;
    }
    let data = unsafe { std::slice::from_raw_parts(b.cast::<u8>(), l).to_vec() };
    let addr_bytes = if !addr.is_null() && addr_len > 0 {
        unsafe { std::slice::from_raw_parts(addr.cast::<u8>(), addr_len as usize).to_vec() }
    } else {
        Vec::new()
    };
    INTERCEPTOR_RUNTIME.stage_reorder_datagram(pending, data, f, addr_bytes, addr_len);
    Some(l as ssize_t)
}

fn maybe_stage_reorder_send(
    b: *const c_void,
    l: size_t,
    f: c_int,
    pending: &mut std::collections::VecDeque<PendingDatagram>,
) -> Option<ssize_t> {
    if l == 0 || b.is_null() {
        return None;
    }
    let data = unsafe { std::slice::from_raw_parts(b.cast::<u8>(), l).to_vec() };
    INTERCEPTOR_RUNTIME.stage_reorder_datagram(pending, data, f, Vec::new(), 0);
    Some(l as ssize_t)
}

fn send_pending_datagram(fd: c_int, pkt: &PendingDatagram) {
    let addr_ptr = if pkt.addr.is_empty() {
        std::ptr::null()
    } else {
        pkt.addr.as_ptr().cast::<sockaddr>()
    };
    unsafe {
        let _ = (ORIG_SENDTO)(
            fd,
            pkt.data.as_ptr().cast::<c_void>(),
            pkt.data.len(),
            pkt.flags,
            addr_ptr,
            pkt.addr_len as socklen_t,
        );
    }
}

fn set_errno(val: i32) {
    unsafe {
        *libc::__errno_location() = val;
    }
}

/// # Safety
/// `b` must point to a writable buffer of `l` bytes.
/// `addr`/`addr_len` must be null together or a valid writable socket address pair.
unsafe fn write_pending_recvfrom_result(
    pkt: &PendingDatagram,
    b: *mut c_void,
    l: size_t,
    addr: *mut sockaddr,
    addr_len: *mut socklen_t,
) -> ssize_t {
    if b.is_null() || l == 0 {
        return 0;
    }
    let to_copy = usize::min(l, pkt.data.len());
    unsafe {
        std::ptr::copy_nonoverlapping(pkt.data.as_ptr(), b.cast::<u8>(), to_copy);
    }
    if !addr.is_null() && !addr_len.is_null() {
        let capacity = unsafe { *addr_len as usize };
        let available = usize::min(pkt.addr.len(), pkt.addr_len as usize);
        let copy_addr = usize::min(capacity, available);
        if copy_addr > 0 {
            unsafe {
                std::ptr::copy_nonoverlapping(pkt.addr.as_ptr(), addr.cast::<u8>(), copy_addr);
            }
        }
        unsafe {
            *addr_len = pkt.addr_len as socklen_t;
        }
    }
    to_copy as ssize_t
}

/// # Safety
/// `b` must point to a writable buffer of `l` bytes.
unsafe fn write_pending_recv_result(pkt: &PendingDatagram, b: *mut c_void, l: size_t) -> ssize_t {
    if b.is_null() || l == 0 {
        return 0;
    }
    let to_copy = usize::min(l, pkt.data.len());
    unsafe {
        std::ptr::copy_nonoverlapping(pkt.data.as_ptr(), b.cast::<u8>(), to_copy);
    }
    to_copy as ssize_t
}

/// # Safety
/// `b` must point to a readable buffer with at least `recv_len` bytes.
/// `addr`/`addr_len` must be null together or a valid readable socket address pair.
unsafe fn snapshot_recvfrom_datagram(
    b: *mut c_void,
    recv_len: ssize_t,
    flags: c_int,
    addr: *mut sockaddr,
    addr_len: *mut socklen_t,
) -> Option<PendingDatagram> {
    if recv_len <= 0 || b.is_null() {
        return None;
    }
    let data = unsafe { std::slice::from_raw_parts(b.cast::<u8>(), recv_len as usize).to_vec() };
    let (addr_bytes, len_u32) = if !addr.is_null() && !addr_len.is_null() {
        let len = unsafe { *addr_len as usize };
        if len == 0 {
            (Vec::new(), 0)
        } else {
            let bytes = unsafe { std::slice::from_raw_parts(addr.cast::<u8>(), len).to_vec() };
            (bytes, len as u32)
        }
    } else {
        (Vec::new(), 0)
    };
    Some(PendingDatagram::new(data, flags, addr_bytes, len_u32))
}

/// # Safety
/// `b` must point to a readable buffer with at least `recv_len` bytes.
unsafe fn snapshot_recv_datagram(
    b: *mut c_void,
    recv_len: ssize_t,
    flags: c_int,
) -> Option<PendingDatagram> {
    if recv_len <= 0 || b.is_null() {
        return None;
    }
    let data = unsafe { std::slice::from_raw_parts(b.cast::<u8>(), recv_len as usize).to_vec() };
    Some(PendingDatagram::new(data, flags, Vec::new(), 0))
}

lazy_static::lazy_static! {
    static ref RECURSION_GUARD_KEY: libc::pthread_key_t = unsafe {
        let mut key = 0;
        libc::pthread_key_create(&mut key, None);
        key
    };
}

fn enter_hook() -> bool {
    unsafe {
        let val = libc::pthread_getspecific(*RECURSION_GUARD_KEY);
        if !val.is_null() {
            return false;
        }
        if libc::pthread_setspecific(*RECURSION_GUARD_KEY, std::ptr::dangling::<c_void>()) != 0 {
            return false;
        }
        true
    }
}

fn exit_hook() {
    unsafe {
        libc::pthread_setspecific(*RECURSION_GUARD_KEY, std::ptr::null());
    }
}

fn initialize() {
    if !INITIALIZED.swap(true, Ordering::SeqCst) {
        lazy_static::initialize(&ORIG_SOCKET);
        lazy_static::initialize(&ORIG_CLOSE);
        lazy_static::initialize(&ORIG_CONNECT);
        lazy_static::initialize(&ORIG_SEND);
        lazy_static::initialize(&ORIG_RECV);
        lazy_static::initialize(&ORIG_SENDTO);
        lazy_static::initialize(&ORIG_RECVFROM);
        lazy_static::initialize(&ORIG_GETADDRINFO);
        let _ = init_runtime_shm();
    }
}

fn is_non_blocking(fd: c_int) -> bool {
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL, 0) };
    if flags < 0 {
        return false;
    }
    (flags & libc::O_NONBLOCK) != 0
}


#[unsafe(no_mangle)]
pub extern "C" fn socket(domain: c_int, ty: c_int, protocol: c_int) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_SOCKET)(domain, ty, protocol) };
    }

    initialize();
    let fd = unsafe { (ORIG_SOCKET)(domain, ty, protocol) };

    if fd >= 0 {
        bind_fd_to_current_thread(fd);
    }

    exit_hook();
    fd
}

#[unsafe(no_mangle)]
pub extern "C" fn close(fd: c_int) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_CLOSE)(fd) };
    }

    initialize();
    CHAOS_ENGINE.clear_fd_state(fd);
    INTERCEPTOR_RUNTIME.clear_fd_state(fd);
    clear_fd_binding(fd);

    let result = unsafe { (ORIG_CLOSE)(fd) };
    exit_hook();
    result
}

#[unsafe(no_mangle)]
pub extern "C" fn send(s: c_int, b: *const c_void, l: size_t, f: c_int) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_SEND)(s, b, l, f) };
    }

    initialize();
    let mut pending = INTERCEPTOR_RUNTIME.take_reorder_pending(s);
    let mut staged_reorder = false;
    let mut faults_applied = false;
    let result = if let Some(network_cfg) = runtime_config_for_fd(s) {
        faults_applied = true;
        for pkt in INTERCEPTOR_RUNTIME.flush_expired_reorder(&mut pending, network_cfg.reorder_max_delay_ns) {
            send_pending_datagram(s, &pkt);
        }
        let decision = CHAOS_ENGINE.evaluate_stream_pre(s, &network_cfg, l as u64, Direction::Uplink);
        let directive = INTERCEPTOR_RUNTIME.map_stream_decision(s, decision.clone(), is_non_blocking(s));
        if let Some(error) = apply_stream_directive(directive) {
            error as ssize_t
        } else if matches!(decision, LayerDecision::StageReorder) {
            staged_reorder = true;
            let staged = maybe_stage_reorder_send(b, l, f, &mut pending).unwrap_or(l as ssize_t);
            for pkt in INTERCEPTOR_RUNTIME.enforce_reorder_window(
                &mut pending,
                network_cfg.reorder_window as usize,
            ) {
                send_pending_datagram(s, &pkt);
            }
            staged
        } else {
            unsafe { (ORIG_SEND)(s, b, l, f) }
        }
    } else {
        unsafe { (ORIG_SEND)(s, b, l, f) }
    };

    if result > 0 {
        record_stream_bytes(s, result as u64);
        if faults_applied && !staged_reorder {
            maybe_duplicate_send(s, b, result, f);
        }
        if faults_applied
            && let Some(pkt) = INTERCEPTOR_RUNTIME.pop_reorder_after_success(&mut pending, staged_reorder)
        {
            send_pending_datagram(s, &pkt);
        }
    }
    INTERCEPTOR_RUNTIME.put_reorder_pending(s, pending);

    exit_hook();
    result
}

#[unsafe(no_mangle)]
/// # Safety
/// `b` must point to a writable buffer of `l` bytes.
pub unsafe extern "C" fn recv(s: c_int, b: *mut c_void, l: size_t, f: c_int) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_RECV)(s, b, l, f) };
    }

    initialize();
    let non_blocking = is_non_blocking(s);
    let mut pending = INTERCEPTOR_RUNTIME.take_reorder_pending_recv(s);
    let result = if let Some(network_cfg) = runtime_config_for_fd(s) {
        if non_blocking
            && let Some(pkt) = pending.pop_front()
        {
            let out = unsafe { write_pending_recv_result(&pkt, b, l) };
            INTERCEPTOR_RUNTIME.put_reorder_pending_recv(s, pending);
            exit_hook();
            return out;
        }

        let decision =
            CHAOS_ENGINE.evaluate_stream_pre(s, &network_cfg, l as u64, Direction::Downlink);
        let directive = INTERCEPTOR_RUNTIME.map_stream_decision(s, decision.clone(), non_blocking);
        if let Some(error) = apply_stream_directive(directive) {
            error as ssize_t
        } else {
            let recv_result = unsafe { (ORIG_RECV)(s, b, l, f) };
            if non_blocking
                && matches!(decision, LayerDecision::StageReorder)
                && recv_result > 0
                && let Some(pkt) = unsafe { snapshot_recv_datagram(b, recv_result, f) }
            {
                pending.push_back(pkt);
                set_errno(libc::EAGAIN);
                -1
            } else {
                recv_result
            }
        }
    } else {
        unsafe { (ORIG_RECV)(s, b, l, f) }
    };

    if result > 0 {
        record_stream_bytes(s, result as u64);
    }
    INTERCEPTOR_RUNTIME.put_reorder_pending_recv(s, pending);

    exit_hook();
    result
}

#[unsafe(no_mangle)]
/// # Safety
/// `a` must be either null or point to a valid socket address buffer of length `l`.
pub unsafe extern "C" fn connect(s: c_int, a: *const sockaddr, l: socklen_t) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_CONNECT)(s, a, l) };
    }

    initialize();
    bind_fd_to_current_thread(s);

    let result = if let Some(network_cfg) = unsafe { runtime_config_for_addr_or_fd(s, a, l) } {
        let decision = CHAOS_ENGINE.evaluate_connect(s, &network_cfg);
        let directive = INTERCEPTOR_RUNTIME.map_connect_decision(decision);
        if let Some(error) = apply_connect_directive(directive) {
            error
        } else {
            unsafe { (ORIG_CONNECT)(s, a, l) }
        }
    } else {
        unsafe { (ORIG_CONNECT)(s, a, l) }
    };

    exit_hook();
    result
}

#[unsafe(no_mangle)]
/// # Safety
/// `b` must point to a readable buffer of `l` bytes.
/// `addr` must be null or point to a valid socket address buffer of length `addr_len`.
pub unsafe extern "C" fn sendto(
    s: c_int,
    b: *const c_void,
    l: size_t,
    f: c_int,
    addr: *const sockaddr,
    addr_len: socklen_t,
) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_SENDTO)(s, b, l, f, addr, addr_len) };
    }

    initialize();
    let mut pending = INTERCEPTOR_RUNTIME.take_reorder_pending(s);
    let mut staged_reorder = false;
    let mut faults_applied = false;
    let result = if let Some(network_cfg) = unsafe { runtime_config_for_addr_or_fd(s, addr, addr_len) } {
        faults_applied = true;
        for pkt in INTERCEPTOR_RUNTIME.flush_expired_reorder(&mut pending, network_cfg.reorder_max_delay_ns) {
            send_pending_datagram(s, &pkt);
        }
        let decision = CHAOS_ENGINE.evaluate_stream_pre(s, &network_cfg, l as u64, Direction::Uplink);
        let directive = INTERCEPTOR_RUNTIME.map_stream_decision(s, decision.clone(), is_non_blocking(s));
        if let Some(error) = apply_stream_directive(directive) {
            error as ssize_t
        } else if matches!(decision, LayerDecision::StageReorder) {
            staged_reorder = true;
            let staged =
                maybe_stage_reorder_sendto(b, l, f, addr, addr_len, &mut pending).unwrap_or(l as ssize_t);
            for pkt in INTERCEPTOR_RUNTIME.enforce_reorder_window(
                &mut pending,
                network_cfg.reorder_window as usize,
            ) {
                send_pending_datagram(s, &pkt);
            }
            staged
        } else {
            unsafe { (ORIG_SENDTO)(s, b, l, f, addr, addr_len) }
        }
    } else {
        unsafe { (ORIG_SENDTO)(s, b, l, f, addr, addr_len) }
    };

    if result > 0 {
        record_stream_bytes(s, result as u64);
        if faults_applied && !staged_reorder {
            maybe_duplicate_sendto(s, b, result, f, addr, addr_len);
        }
        if faults_applied
            && let Some(pkt) = INTERCEPTOR_RUNTIME.pop_reorder_after_success(&mut pending, staged_reorder)
        {
            send_pending_datagram(s, &pkt);
        }
    }
    INTERCEPTOR_RUNTIME.put_reorder_pending(s, pending);

    exit_hook();
    result
}

#[unsafe(no_mangle)]
/// # Safety
/// `b` must point to a writable buffer of `l` bytes.
/// `addr`/`addr_len` must be null together or point to valid writable memory.
pub unsafe extern "C" fn recvfrom(
    s: c_int,
    b: *mut c_void,
    l: size_t,
    f: c_int,
    addr: *mut sockaddr,
    addr_len: *mut socklen_t,
) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_RECVFROM)(s, b, l, f, addr, addr_len) };
    }

    initialize();
    let non_blocking = is_non_blocking(s);
    let mut pending = INTERCEPTOR_RUNTIME.take_reorder_pending_recv(s);
    let result = if let Some(network_cfg) = runtime_config_for_fd(s) {
        if non_blocking
            && let Some(pkt) = pending.pop_front()
        {
            let out = unsafe { write_pending_recvfrom_result(&pkt, b, l, addr, addr_len) };
            INTERCEPTOR_RUNTIME.put_reorder_pending_recv(s, pending);
            exit_hook();
            return out;
        }

        let decision = CHAOS_ENGINE.evaluate_stream_pre(s, &network_cfg, l as u64, Direction::Downlink);
        let directive = INTERCEPTOR_RUNTIME.map_stream_decision(s, decision.clone(), non_blocking);
        if let Some(error) = apply_stream_directive(directive) {
            error as ssize_t
        } else {
            let recv_result = unsafe { (ORIG_RECVFROM)(s, b, l, f, addr, addr_len) };
            if non_blocking
                && matches!(decision, LayerDecision::StageReorder)
                && recv_result > 0
                && let Some(pkt) = unsafe { snapshot_recvfrom_datagram(b, recv_result, f, addr, addr_len) }
            {
                pending.push_back(pkt);
                set_errno(libc::EAGAIN);
                -1
            } else {
                recv_result
            }
        }
    } else {
        unsafe { (ORIG_RECVFROM)(s, b, l, f, addr, addr_len) }
    };

    if result > 0 {
        record_stream_bytes(s, result as u64);
    }
    INTERCEPTOR_RUNTIME.put_reorder_pending_recv(s, pending);

    exit_hook();
    result
}

#[unsafe(no_mangle)]
pub extern "C" fn getaddrinfo(
    node: *const c_char,
    service: *const c_char,
    hints: *const addrinfo,
    res: *mut *mut addrinfo,
) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_GETADDRINFO)(node, service, hints, res) };
    }

    initialize();
    if let Some(network_cfg) = runtime_dns_config_for_current_thread() {
        let decision = CHAOS_ENGINE.evaluate_dns_lookup(&network_cfg);
        if let LayerDecision::DelayNs(ns) = &decision {
            std::thread::sleep(std::time::Duration::from_nanos(*ns));
        } else if let LayerDecision::TimeoutMs(ms) = &decision {
            std::thread::sleep(std::time::Duration::from_millis(*ms));
        }
        if let Some(eai) = INTERCEPTOR_RUNTIME.map_dns_decision_to_eai(&decision) {
            exit_hook();
            return eai;
        }
    }

    let result = unsafe { (ORIG_GETADDRINFO)(node, service, hints, res) };
    exit_hook();
    result
}

#[unsafe(no_mangle)]
pub extern "C" fn setpriority(which: c_int, who: c_int, prio: c_int) -> c_int {
    if try_handle_setpriority(which, who, prio) {
        return 0;
    }

    unsafe {
        let orig = libc::dlsym(libc::RTLD_NEXT, c"setpriority".as_ptr());
        let orig_func: extern "C" fn(c_int, c_int, c_int) -> c_int = std::mem::transmute(orig);
        orig_func(which, who, prio)
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn faultcore_interceptor_is_active() -> bool {
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn connect_timeout_maps_to_etimedout() {
        let directive = INTERCEPTOR_RUNTIME.map_connect_decision(LayerDecision::TimeoutMs(10));
        assert_eq!(
            directive,
            faultcore_network::ConnectDirective::ReturnErrno {
                errno: libc::ETIMEDOUT,
                ret: -1,
            }
        );
    }

    #[test]
    fn connect_error_kind_maps_to_errno() {
        let directive = INTERCEPTOR_RUNTIME.map_connect_decision(LayerDecision::ConnectionErrorKind(1));
        assert_eq!(
            directive,
            faultcore_network::ConnectDirective::ReturnErrno {
                errno: libc::ECONNRESET,
                ret: -1,
            }
        );
    }

    #[test]
    fn stream_drop_maps_to_zero() {
        let directive = INTERCEPTOR_RUNTIME.map_stream_decision(1, LayerDecision::Drop, false);
        assert_eq!(directive, faultcore_network::StreamDirective::ReturnValue(0));
    }

    #[test]
    fn stream_timeout_maps_to_etimedout() {
        let directive = INTERCEPTOR_RUNTIME.map_stream_decision(1, LayerDecision::TimeoutMs(50), false);
        assert_eq!(
            directive,
            faultcore_network::StreamDirective::ReturnErrno {
                errno: libc::ETIMEDOUT,
                ret: -1,
            }
        );
    }

    #[test]
    fn stream_stage_reorder_is_non_terminal() {
        let directive = INTERCEPTOR_RUNTIME.map_stream_decision(1, LayerDecision::StageReorder, false);
        assert_eq!(directive, faultcore_network::StreamDirective::Continue);
    }

    #[test]
    fn dns_mapping_contract_is_stable() {
        assert_eq!(
            INTERCEPTOR_RUNTIME.map_dns_decision_to_eai(&LayerDecision::TimeoutMs(1)),
            Some(libc::EAI_AGAIN)
        );
        assert_eq!(
            INTERCEPTOR_RUNTIME.map_dns_decision_to_eai(&LayerDecision::NxDomain),
            Some(libc::EAI_NONAME)
        );
        assert_eq!(
            INTERCEPTOR_RUNTIME.map_dns_decision_to_eai(&LayerDecision::ConnectionErrorKind(1)),
            Some(libc::EAI_FAIL)
        );
        assert_eq!(INTERCEPTOR_RUNTIME.map_dns_decision_to_eai(&LayerDecision::DelayNs(1)), None);
    }
}
