use faultcore_network::{
    Config, Direction, FaultOsiAdvancedMetricsSnapshot, FaultOsiMetricsSnapshot, LayerDecision,
    PendingDatagram,
    SetpriorityCompatOutcome, apply_connect_directive, apply_stream_directive,
    bind_fd_to_current_thread, clear_fd_binding, clone_fd_binding, global_fault_osi_engine,
    global_interceptor_runtime, handle_setpriority_compat, init_runtime_shm,
    observe_hostname_for_current_thread_addr, observe_sni_for_fd,
    record_replay_evaluate_or_replay,
    reset_global_fault_osi_metrics, runtime_config_for_addr_or_fd, runtime_config_for_fd,
    runtime_dns_config_for_current_thread, runtime_dns_config_for_query, set_errno_value,
    snapshot_recv_datagram,
    snapshot_recvfrom_datagram, stage_reorder_send, stage_reorder_sendto,
    uplink_duplicate_count_for_addr_or_fd, uplink_duplicate_count_for_fd,
    write_pending_recv_result, write_pending_recvfrom_result,
};
use libc::{addrinfo, c_char, c_int, c_void, size_t, sockaddr, socklen_t, ssize_t};
use std::collections::{HashMap, VecDeque};
use std::ffi::CStr;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};

static INITIALIZED: AtomicBool = AtomicBool::new(false);

type SendFn = unsafe extern "C" fn(c_int, *const c_void, size_t, c_int) -> ssize_t;
type RecvFn = unsafe extern "C" fn(c_int, *mut c_void, size_t, c_int) -> ssize_t;
type WriteFn = unsafe extern "C" fn(c_int, *const c_void, size_t) -> ssize_t;
type ReadFn = unsafe extern "C" fn(c_int, *mut c_void, size_t) -> ssize_t;
type ConnectFn = unsafe extern "C" fn(c_int, *const sockaddr, socklen_t) -> c_int;
type SocketFn = unsafe extern "C" fn(c_int, c_int, c_int) -> c_int;
type CloseFn = unsafe extern "C" fn(c_int) -> c_int;
type DupFn = unsafe extern "C" fn(c_int) -> c_int;
type Dup2Fn = unsafe extern "C" fn(c_int, c_int) -> c_int;
type Dup3Fn = unsafe extern "C" fn(c_int, c_int, c_int) -> c_int;
type AcceptFn = unsafe extern "C" fn(c_int, *mut sockaddr, *mut socklen_t) -> c_int;
type Accept4Fn = unsafe extern "C" fn(c_int, *mut sockaddr, *mut socklen_t, c_int) -> c_int;
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
type SslCtrlFn = unsafe extern "C" fn(*mut c_void, c_int, libc::c_long, *mut c_void) -> libc::c_long;
type SslSetFdFn = unsafe extern "C" fn(*mut c_void, c_int) -> c_int;
type SslGetFdFn = unsafe extern "C" fn(*const c_void) -> c_int;
type SslFreeFn = unsafe extern "C" fn(*mut c_void);

const SSL_CTRL_SET_TLSEXT_HOSTNAME: c_int = 55;
const TLSEXT_NAMETYPE_HOST_NAME: libc::c_long = 0;

lazy_static::lazy_static! {
    pub static ref ORIG_SOCKET: SocketFn = unsafe { get_original_fn("socket") };
    pub static ref ORIG_CLOSE: CloseFn = unsafe { get_original_fn("close") };
    pub static ref ORIG_DUP: DupFn = unsafe { get_original_fn("dup") };
    pub static ref ORIG_DUP2: Dup2Fn = unsafe { get_original_fn("dup2") };
    pub static ref ORIG_DUP3: Dup3Fn = unsafe { get_original_fn("dup3") };
    pub static ref ORIG_ACCEPT: AcceptFn = unsafe { get_original_fn("accept") };
    pub static ref ORIG_ACCEPT4: Accept4Fn = unsafe { get_original_fn("accept4") };
    pub static ref ORIG_CONNECT: ConnectFn = unsafe { get_original_fn("connect") };
    pub static ref ORIG_SEND: SendFn = unsafe { get_original_fn("send") };
    pub static ref ORIG_RECV: RecvFn = unsafe { get_original_fn("recv") };
    pub static ref ORIG_WRITE: WriteFn = unsafe { get_original_fn("write") };
    pub static ref ORIG_READ: ReadFn = unsafe { get_original_fn("read") };
    pub static ref ORIG_SENDTO: SendToFn = unsafe { get_original_fn("sendto") };
    pub static ref ORIG_RECVFROM: RecvFromFn = unsafe { get_original_fn("recvfrom") };
    pub static ref ORIG_GETADDRINFO: GetAddrInfoFn = unsafe { get_original_fn("getaddrinfo") };
    pub static ref ORIG_SSL_CTRL: Option<SslCtrlFn> = unsafe {
        get_optional_ssl_original_fn("SSL_ctrl", Some(SSL_ctrl as *const () as *const c_void))
    };
    pub static ref ORIG_SSL_SET_FD: Option<SslSetFdFn> = unsafe {
        get_optional_ssl_original_fn("SSL_set_fd", Some(SSL_set_fd as *const () as *const c_void))
    };
    pub static ref ORIG_SSL_GET_FD: Option<SslGetFdFn> = unsafe {
        get_optional_ssl_original_fn("SSL_get_fd", None)
    };
    pub static ref ORIG_SSL_FREE: Option<SslFreeFn> = unsafe {
        get_optional_ssl_original_fn("SSL_free", Some(SSL_free as *const () as *const c_void))
    };
    static ref SNI_BY_SSL: Mutex<HashMap<usize, String>> = Mutex::new(HashMap::new());
    static ref FD_BY_SSL: Mutex<HashMap<usize, c_int>> = Mutex::new(HashMap::new());
}

unsafe fn get_original_fn<T>(name: &str) -> T {
    let symbol_name = std::ffi::CString::new(name).unwrap();
    let fn_ptr = unsafe { libc::dlsym(libc::RTLD_NEXT, symbol_name.as_ptr()) };
    if fn_ptr.is_null() {
        unsafe { libc::abort() };
    }
    unsafe { std::mem::transmute_copy(&fn_ptr) }
}

fn is_excluded_symbol(symbol: *mut c_void, exclude: Option<*const c_void>) -> bool {
    match exclude {
        Some(excluded) => std::ptr::eq(symbol.cast_const(), excluded),
        None => false,
    }
}

unsafe fn get_optional_ssl_original_fn<T>(
    name: &str,
    exclude_symbol: Option<*const c_void>,
) -> Option<T> {
    let symbol_name = std::ffi::CString::new(name).unwrap();

    let next_ptr = unsafe { libc::dlsym(libc::RTLD_NEXT, symbol_name.as_ptr()) };
    if !next_ptr.is_null() && !is_excluded_symbol(next_ptr, exclude_symbol) {
        return Some(unsafe { std::mem::transmute_copy(&next_ptr) });
    }

    // Some Python/OpenSSL builds under LD_PRELOAD expose SSL_* symbols only
    // through explicit libssl handles, not RTLD_NEXT.
    for lib_name in [c"libssl.so.3", c"libssl.so.1.1", c"libssl.so"] {
        let handle = unsafe { libc::dlopen(lib_name.as_ptr(), libc::RTLD_NOW | libc::RTLD_LOCAL) };
        if handle.is_null() {
            continue;
        }
        // Keep libssl handles open because function pointers are cached globally.
        let ptr = unsafe { libc::dlsym(handle, symbol_name.as_ptr()) };
        if !ptr.is_null() && !is_excluded_symbol(ptr, exclude_symbol) {
            return Some(unsafe { std::mem::transmute_copy(&ptr) });
        }
    }

    None
}

fn record_stream_bytes(fd: c_int, bytes: u64) {
    global_fault_osi_engine().record_stream_bytes(fd, bytes);
}

fn maybe_duplicate_send(fd: c_int, b: *const c_void, sent: ssize_t, f: c_int) {
    if sent <= 0 {
        return;
    }
    let decision = record_replay_evaluate_or_replay("stream_uplink_post_send", || {
        let count = uplink_duplicate_count_for_fd(global_fault_osi_engine(), fd);
        if count > 0 {
            LayerDecision::Duplicate(count)
        } else {
            LayerDecision::Continue
        }
    });
    let count = match decision {
        LayerDecision::Duplicate(n) => n,
        _ => 0,
    };
    for _ in 0..count {
        unsafe {
            let _ = (ORIG_SEND)(fd, b, sent as size_t, f);
        }
    }
}

fn maybe_duplicate_write(fd: c_int, b: *const c_void, sent: ssize_t) {
    if sent <= 0 {
        return;
    }
    let decision = record_replay_evaluate_or_replay("stream_uplink_post_write", || {
        let count = uplink_duplicate_count_for_fd(global_fault_osi_engine(), fd);
        if count > 0 {
            LayerDecision::Duplicate(count)
        } else {
            LayerDecision::Continue
        }
    });
    let count = match decision {
        LayerDecision::Duplicate(n) => n,
        _ => 0,
    };
    for _ in 0..count {
        unsafe {
            let _ = (ORIG_WRITE)(fd, b, sent as size_t);
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
    let decision = record_replay_evaluate_or_replay("stream_uplink_post_sendto", || {
        let count = unsafe {
            uplink_duplicate_count_for_addr_or_fd(global_fault_osi_engine(), fd, addr, addr_len)
        };
        if count > 0 {
            LayerDecision::Duplicate(count)
        } else {
            LayerDecision::Continue
        }
    });
    let count = match decision {
        LayerDecision::Duplicate(n) => n,
        _ => 0,
    };
    for _ in 0..count {
        unsafe {
            let _ = (ORIG_SENDTO)(fd, b, sent as size_t, f, addr, addr_len);
        }
    }
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
        lazy_static::initialize(&ORIG_DUP);
        lazy_static::initialize(&ORIG_DUP2);
        lazy_static::initialize(&ORIG_DUP3);
        lazy_static::initialize(&ORIG_ACCEPT);
        lazy_static::initialize(&ORIG_ACCEPT4);
        lazy_static::initialize(&ORIG_CONNECT);
        lazy_static::initialize(&ORIG_SEND);
        lazy_static::initialize(&ORIG_RECV);
        lazy_static::initialize(&ORIG_WRITE);
        lazy_static::initialize(&ORIG_READ);
        lazy_static::initialize(&ORIG_SENDTO);
        lazy_static::initialize(&ORIG_RECVFROM);
        lazy_static::initialize(&ORIG_GETADDRINFO);
        lazy_static::initialize(&ORIG_SSL_CTRL);
        lazy_static::initialize(&ORIG_SSL_SET_FD);
        lazy_static::initialize(&ORIG_SSL_GET_FD);
        lazy_static::initialize(&ORIG_SSL_FREE);
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

/// # Safety
/// `raw` must be null or point to a valid NUL-terminated C string.
unsafe fn normalized_name_from_cstr(raw: *const c_char) -> Option<String> {
    if raw.is_null() {
        return None;
    }
    let observed = unsafe { CStr::from_ptr(raw) }.to_str().ok()?;
    let normalized = observed.trim().trim_end_matches('.').to_ascii_lowercase();
    if normalized.is_empty() {
        return None;
    }
    Some(normalized)
}

fn lock_map<T>(mutex: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|err| err.into_inner())
}

fn ssl_key(ssl: *mut c_void) -> Option<usize> {
    (!ssl.is_null()).then_some(ssl as usize)
}

fn remember_ssl_sni(ssl: *mut c_void, sni: String) {
    let Some(key) = ssl_key(ssl) else {
        return;
    };
    lock_map(&SNI_BY_SSL).insert(key, sni);
}

fn forget_ssl_state(ssl: *mut c_void) {
    let Some(key) = ssl_key(ssl) else {
        return;
    };
    lock_map(&SNI_BY_SSL).remove(&key);
    lock_map(&FD_BY_SSL).remove(&key);
}

fn forget_ssl_bindings_for_fd(fd: c_int) {
    if fd < 0 {
        return;
    }
    let keys: Vec<usize> = {
        let map = lock_map(&FD_BY_SSL);
        map.iter()
            .filter_map(|(key, mapped_fd)| (*mapped_fd == fd).then_some(*key))
            .collect()
    };
    if keys.is_empty() {
        return;
    }
    {
        let mut fd_map = lock_map(&FD_BY_SSL);
        for key in &keys {
            fd_map.remove(key);
        }
    }
    let mut sni_map = lock_map(&SNI_BY_SSL);
    for key in keys {
        sni_map.remove(&key);
    }
}

fn remember_ssl_fd(ssl: *mut c_void, fd: c_int) {
    if fd < 0 {
        return;
    }
    let Some(key) = ssl_key(ssl) else {
        return;
    };
    lock_map(&FD_BY_SSL).insert(key, fd);
    let sni = lock_map(&SNI_BY_SSL).get(&key).cloned();
    if let Some(sni) = sni {
        observe_sni_for_fd(fd, &sni);
    }
}

fn bind_ssl_sni_if_possible(ssl: *mut c_void, sni: &str) {
    let Some(key) = ssl_key(ssl) else {
        return;
    };
    if let Some(get_fd) = *ORIG_SSL_GET_FD {
        let fd = unsafe { get_fd(ssl.cast_const()) };
        if fd >= 0 {
            remember_ssl_fd(ssl, fd);
            observe_sni_for_fd(fd, sni);
            return;
        }
    }
    if let Some(fd) = lock_map(&FD_BY_SSL).get(&key).copied() {
        observe_sni_for_fd(fd, sni);
    }
}

fn tls_client_hello_sni(payload: &[u8]) -> Option<String> {
    if payload.len() < 5 || payload[0] != 22 {
        return None;
    }
    let record_len = u16::from_be_bytes([payload[3], payload[4]]) as usize;
    let record_end = 5usize.checked_add(record_len)?;
    if record_end > payload.len() {
        return None;
    }
    if payload.get(5).copied()? != 1 {
        return None;
    }
    let hs_len = ((payload.get(6).copied()? as usize) << 16)
        | ((payload.get(7).copied()? as usize) << 8)
        | (payload.get(8).copied()? as usize);
    let hs_start = 9usize;
    let hs_end = hs_start.checked_add(hs_len)?;
    if hs_end > record_end {
        return None;
    }
    let mut p = hs_start;
    if p + 34 > hs_end {
        return None;
    }
    p += 34;

    let session_len = payload.get(p).copied()? as usize;
    p = p.checked_add(1 + session_len)?;
    if p > hs_end {
        return None;
    }

    if p + 2 > hs_end {
        return None;
    }
    let suites_len = u16::from_be_bytes([payload[p], payload[p + 1]]) as usize;
    p = p.checked_add(2 + suites_len)?;
    if p > hs_end {
        return None;
    }

    let compression_len = payload.get(p).copied()? as usize;
    p = p.checked_add(1 + compression_len)?;
    if p > hs_end {
        return None;
    }

    if p + 2 > hs_end {
        return None;
    }
    let extensions_len = u16::from_be_bytes([payload[p], payload[p + 1]]) as usize;
    p += 2;
    let ext_end = p.checked_add(extensions_len)?;
    if ext_end > hs_end {
        return None;
    }

    while p + 4 <= ext_end {
        let ext_type = u16::from_be_bytes([payload[p], payload[p + 1]]);
        let ext_len = u16::from_be_bytes([payload[p + 2], payload[p + 3]]) as usize;
        p += 4;
        let data_end = p.checked_add(ext_len)?;
        if data_end > ext_end {
            return None;
        }
        if ext_type == 0 {
            if p + 2 > data_end {
                return None;
            }
            let list_len = u16::from_be_bytes([payload[p], payload[p + 1]]) as usize;
            let mut q = p + 2;
            let list_end = q.checked_add(list_len)?;
            if list_end > data_end {
                return None;
            }
            while q + 3 <= list_end {
                let name_type = payload[q];
                let name_len = u16::from_be_bytes([payload[q + 1], payload[q + 2]]) as usize;
                q += 3;
                let name_end = q.checked_add(name_len)?;
                if name_end > list_end {
                    return None;
                }
                if name_type == 0 {
                    let host = std::str::from_utf8(&payload[q..name_end]).ok()?;
                    let normalized = host.trim().trim_end_matches('.').to_ascii_lowercase();
                    return (!normalized.is_empty()).then_some(normalized);
                }
                q = name_end;
            }
            return None;
        }
        p = data_end;
    }
    None
}

/// # Safety
/// `b` must be null or point to a readable buffer of `l` bytes.
unsafe fn observe_tls_sni_from_send_buffer(fd: c_int, b: *const c_void, l: size_t) {
    if fd < 0 || b.is_null() || l < 5 {
        return;
    }
    let payload = unsafe { std::slice::from_raw_parts(b.cast::<u8>(), l) };
    if let Some(sni) = tls_client_hello_sni(payload) {
        observe_sni_for_fd(fd, &sni);
    }
}

#[allow(clippy::too_many_arguments)]
fn handle_uplink_send<FConfig, FOrig, FStage, FDuplicate>(
    site: &str,
    s: c_int,
    l: size_t,
    non_blocking: bool,
    pending: &mut VecDeque<PendingDatagram>,
    config_lookup: FConfig,
    mut call_orig: FOrig,
    mut stage_reorder: FStage,
    duplicate_after_success: FDuplicate,
) -> ssize_t
where
    FConfig: FnOnce() -> Option<Config>,
    FOrig: FnMut() -> ssize_t,
    FStage: FnMut(&mut VecDeque<PendingDatagram>) -> ssize_t,
    FDuplicate: FnOnce(ssize_t),
{
    let mut staged_reorder = false;
    let mut faults_applied = false;
    let result = if let Some(network_cfg) = config_lookup() {
        faults_applied = true;
        for pkt in global_interceptor_runtime()
            .flush_expired_reorder(pending, network_cfg.reorder_max_delay_ns)
        {
            send_pending_datagram(s, &pkt);
        }
        let decision = record_replay_evaluate_or_replay(site, || {
            global_fault_osi_engine().evaluate_stream_pre(
                s,
                &network_cfg,
                l as u64,
                Direction::Uplink,
            )
        });
        let directive =
            global_interceptor_runtime().map_stream_decision(s, decision.clone(), non_blocking);
        if let Some(error) = apply_stream_directive(directive) {
            error as ssize_t
        } else if matches!(decision, LayerDecision::StageReorder) {
            staged_reorder = true;
            let staged = stage_reorder(pending);
            for pkt in global_interceptor_runtime()
                .enforce_reorder_window(pending, network_cfg.reorder_window as usize)
            {
                send_pending_datagram(s, &pkt);
            }
            staged
        } else {
            call_orig()
        }
    } else {
        call_orig()
    };

    if result > 0 {
        record_stream_bytes(s, result as u64);
        if faults_applied && !staged_reorder {
            duplicate_after_success(result);
        }
        if faults_applied
            && let Some(pkt) =
                global_interceptor_runtime().pop_reorder_after_success(pending, staged_reorder)
        {
            send_pending_datagram(s, &pkt);
        }
    }

    result
}

#[allow(clippy::too_many_arguments)]
fn handle_downlink_recv<FOrig, FSnapshot, FWriteStaged>(
    site: &str,
    s: c_int,
    l: size_t,
    non_blocking: bool,
    pending: &mut VecDeque<PendingDatagram>,
    mut call_orig: FOrig,
    mut snapshot: FSnapshot,
    mut write_staged: FWriteStaged,
) -> (ssize_t, bool)
where
    FOrig: FnMut() -> ssize_t,
    FSnapshot: FnMut(ssize_t) -> Option<PendingDatagram>,
    FWriteStaged: FnMut(&PendingDatagram) -> ssize_t,
{
    if let Some(network_cfg) = runtime_config_for_fd(s) {
        if let Some(pkt) = pending.pop_front() {
            return (write_staged(&pkt), false);
        }

        let decision = record_replay_evaluate_or_replay(site, || {
            global_fault_osi_engine().evaluate_stream_pre(
                s,
                &network_cfg,
                l as u64,
                Direction::Downlink,
            )
        });
        let directive =
            global_interceptor_runtime().map_stream_decision(s, decision.clone(), non_blocking);
        let out = if let Some(error) = apply_stream_directive(directive) {
            error as ssize_t
        } else if !non_blocking && matches!(decision, LayerDecision::StageReorder) {
            let first_recv = call_orig();
            if first_recv <= 0 {
                first_recv
            } else if let Some(pkt) = snapshot(first_recv) {
                pending.push_back(pkt);
                let second_recv = call_orig();
                if second_recv > 0 {
                    second_recv
                } else if let Some(staged) = pending.pop_front() {
                    write_staged(&staged)
                } else {
                    second_recv
                }
            } else {
                first_recv
            }
        } else {
            let recv_result = call_orig();
            if non_blocking && matches!(decision, LayerDecision::StageReorder) && recv_result > 0 {
                if let Some(pkt) = snapshot(recv_result) {
                    pending.push_back(pkt);
                    set_errno_value(libc::EAGAIN);
                    -1
                } else {
                    recv_result
                }
            } else {
                recv_result
            }
        };
        (out, true)
    } else {
        (call_orig(), true)
    }
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
    global_fault_osi_engine().clear_fd_state(fd);
    global_interceptor_runtime().clear_fd_state(fd);
    forget_ssl_bindings_for_fd(fd);
    clear_fd_binding(fd);

    let result = unsafe { (ORIG_CLOSE)(fd) };
    exit_hook();
    result
}

#[unsafe(no_mangle)]
pub extern "C" fn dup(oldfd: c_int) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_DUP)(oldfd) };
    }

    initialize();
    let newfd = unsafe { (ORIG_DUP)(oldfd) };
    if newfd >= 0 {
        clone_fd_binding(oldfd, newfd);
    }

    exit_hook();
    newfd
}

#[unsafe(no_mangle)]
pub extern "C" fn dup2(oldfd: c_int, newfd: c_int) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_DUP2)(oldfd, newfd) };
    }

    initialize();
    let out = unsafe { (ORIG_DUP2)(oldfd, newfd) };
    if out >= 0 {
        if oldfd != out {
            global_fault_osi_engine().clear_fd_state(out);
            global_interceptor_runtime().clear_fd_state(out);
        }
        clone_fd_binding(oldfd, out);
    }

    exit_hook();
    out
}

#[unsafe(no_mangle)]
pub extern "C" fn dup3(oldfd: c_int, newfd: c_int, flags: c_int) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_DUP3)(oldfd, newfd, flags) };
    }

    initialize();
    let out = unsafe { (ORIG_DUP3)(oldfd, newfd, flags) };
    if out >= 0 {
        if oldfd != out {
            global_fault_osi_engine().clear_fd_state(out);
            global_interceptor_runtime().clear_fd_state(out);
        }
        clone_fd_binding(oldfd, out);
    }

    exit_hook();
    out
}

#[unsafe(no_mangle)]
/// # Safety
/// `addr`/`addr_len` must be null together or point to valid writable memory.
pub unsafe extern "C" fn accept(s: c_int, addr: *mut sockaddr, addr_len: *mut socklen_t) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_ACCEPT)(s, addr, addr_len) };
    }

    initialize();
    let newfd = unsafe { (ORIG_ACCEPT)(s, addr, addr_len) };
    if newfd >= 0 {
        clone_fd_binding(s, newfd);
    }

    exit_hook();
    newfd
}

#[unsafe(no_mangle)]
/// # Safety
/// `addr`/`addr_len` must be null together or point to valid writable memory.
pub unsafe extern "C" fn accept4(
    s: c_int,
    addr: *mut sockaddr,
    addr_len: *mut socklen_t,
    flags: c_int,
) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_ACCEPT4)(s, addr, addr_len, flags) };
    }

    initialize();
    let newfd = unsafe { (ORIG_ACCEPT4)(s, addr, addr_len, flags) };
    if newfd >= 0 {
        clone_fd_binding(s, newfd);
    }

    exit_hook();
    newfd
}

#[unsafe(no_mangle)]
/// # Safety
/// `b` must point to a readable buffer of `l` bytes.
pub unsafe extern "C" fn write(s: c_int, b: *const c_void, l: size_t) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_WRITE)(s, b, l) };
    }

    initialize();
    unsafe { observe_tls_sni_from_send_buffer(s, b, l) };
    let result = global_interceptor_runtime().with_reorder_pending(s, |pending| {
        handle_uplink_send(
            "stream_uplink_pre_write",
            s,
            l,
            is_non_blocking(s),
            pending,
            || runtime_config_for_fd(s),
            || unsafe { (ORIG_WRITE)(s, b, l) },
            |pending| unsafe { stage_reorder_send(pending, b, l, 0) }.unwrap_or(l as ssize_t),
            |sent| maybe_duplicate_write(s, b, sent),
        )
    });

    exit_hook();
    result
}

#[unsafe(no_mangle)]
/// # Safety
/// `b` must point to a writable buffer of `l` bytes.
pub unsafe extern "C" fn read(s: c_int, b: *mut c_void, l: size_t) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_READ)(s, b, l) };
    }

    initialize();
    let non_blocking = is_non_blocking(s);
    let (result, should_record) =
        global_interceptor_runtime().with_reorder_pending_recv(s, |pending| {
            handle_downlink_recv(
                "stream_downlink_pre_read",
                s,
                l,
                non_blocking,
                pending,
                || unsafe { (ORIG_READ)(s, b, l) },
                |recv_result| unsafe { snapshot_recv_datagram(b, recv_result, 0) },
                |pkt| unsafe { write_pending_recv_result(pkt, b, l) },
            )
        });

    if should_record && result > 0 {
        record_stream_bytes(s, result as u64);
    }

    exit_hook();
    result
}

#[unsafe(no_mangle)]
/// # Safety
/// `b` must point to a readable buffer of `l` bytes.
pub unsafe extern "C" fn send(s: c_int, b: *const c_void, l: size_t, f: c_int) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_SEND)(s, b, l, f) };
    }

    initialize();
    unsafe { observe_tls_sni_from_send_buffer(s, b, l) };
    let result = global_interceptor_runtime().with_reorder_pending(s, |pending| {
        handle_uplink_send(
            "stream_uplink_pre_send",
            s,
            l,
            is_non_blocking(s),
            pending,
            || runtime_config_for_fd(s),
            || unsafe { (ORIG_SEND)(s, b, l, f) },
            |pending| unsafe { stage_reorder_send(pending, b, l, f) }.unwrap_or(l as ssize_t),
            |result| maybe_duplicate_send(s, b, result, f),
        )
    });

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
    let (result, should_record) =
        global_interceptor_runtime().with_reorder_pending_recv(s, |pending| {
            handle_downlink_recv(
                "stream_downlink_pre_recv",
                s,
                l,
                non_blocking,
                pending,
                || unsafe { (ORIG_RECV)(s, b, l, f) },
                |recv_result| unsafe { snapshot_recv_datagram(b, recv_result, f) },
                |pkt| unsafe { write_pending_recv_result(pkt, b, l) },
            )
        });

    if should_record && result > 0 {
        record_stream_bytes(s, result as u64);
    }

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
        let decision = record_replay_evaluate_or_replay("connect_pre", || {
            global_fault_osi_engine().evaluate_connect(s, &network_cfg)
        });
        let directive = global_interceptor_runtime().map_connect_decision(decision);
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
    unsafe { observe_tls_sni_from_send_buffer(s, b, l) };
    let result = global_interceptor_runtime().with_reorder_pending(s, |pending| {
        handle_uplink_send(
            "stream_uplink_pre_sendto",
            s,
            l,
            is_non_blocking(s),
            pending,
            || unsafe { runtime_config_for_addr_or_fd(s, addr, addr_len) },
            || unsafe { (ORIG_SENDTO)(s, b, l, f, addr, addr_len) },
            |pending| {
                unsafe { stage_reorder_sendto(pending, b, l, f, addr, addr_len) }
                    .unwrap_or(l as ssize_t)
            },
            |result| maybe_duplicate_sendto(s, b, result, f, addr, addr_len),
        )
    });

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
    let (result, should_record) =
        global_interceptor_runtime().with_reorder_pending_recv(s, |pending| {
            handle_downlink_recv(
                "stream_downlink_pre_recvfrom",
                s,
                l,
                non_blocking,
                pending,
                || unsafe { (ORIG_RECVFROM)(s, b, l, f, addr, addr_len) },
                |recv_result| unsafe {
                    snapshot_recvfrom_datagram(b, recv_result, f, addr, addr_len)
                },
                |pkt| unsafe { write_pending_recvfrom_result(pkt, b, l, addr, addr_len) },
            )
        });

    if should_record && result > 0 {
        record_stream_bytes(s, result as u64);
    }

    exit_hook();
    result
}

#[unsafe(no_mangle)]
/// # Safety
/// `node`, `service`, `hints` and `res` follow libc `getaddrinfo` pointer contracts.
pub unsafe extern "C" fn getaddrinfo(
    node: *const c_char,
    service: *const c_char,
    hints: *const addrinfo,
    res: *mut *mut addrinfo,
) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_GETADDRINFO)(node, service, hints, res) };
    }

    initialize();
    let observed_hostname = unsafe { normalized_name_from_cstr(node) };
    let dns_cfg = runtime_dns_config_for_query(observed_hostname.as_deref(), None)
        .or_else(runtime_dns_config_for_current_thread);
    if let Some(network_cfg) = dns_cfg {
        let decision = record_replay_evaluate_or_replay("dns_lookup", || {
            global_fault_osi_engine().evaluate_dns_lookup(&network_cfg)
        });
        if let LayerDecision::DelayNs(ns) = &decision {
            std::thread::sleep(std::time::Duration::from_nanos(*ns));
        } else if let LayerDecision::TimeoutMs(ms) = &decision {
            std::thread::sleep(std::time::Duration::from_millis(*ms));
        }
        if let Some(eai) = global_interceptor_runtime().map_dns_decision_to_eai(&decision) {
            exit_hook();
            return eai;
        }
    }

    let result = unsafe { (ORIG_GETADDRINFO)(node, service, hints, res) };
    if result == 0
        && let (Some(hostname), false) = (observed_hostname.as_deref(), res.is_null())
    {
        let mut item = unsafe { *res };
        while !item.is_null() {
            let addr = unsafe { (*item).ai_addr };
            let addr_len = unsafe { (*item).ai_addrlen };
            if !addr.is_null() && addr_len > 0 {
                unsafe {
                    observe_hostname_for_current_thread_addr(addr.cast_const(), addr_len as socklen_t, hostname)
                };
            }
            item = unsafe { (*item).ai_next };
        }
    }
    exit_hook();
    result
}

#[unsafe(no_mangle)]
/// # Safety
/// `ssl` and `parg` follow OpenSSL contracts for `SSL_ctrl`.
pub unsafe extern "C" fn SSL_ctrl(
    ssl: *mut c_void,
    cmd: c_int,
    larg: libc::c_long,
    parg: *mut c_void,
) -> libc::c_long {
    if !enter_hook() {
        return if let Some(orig) = *ORIG_SSL_CTRL {
            unsafe { orig(ssl, cmd, larg, parg) }
        } else {
            0
        };
    }

    initialize();
    if cmd == SSL_CTRL_SET_TLSEXT_HOSTNAME && larg == TLSEXT_NAMETYPE_HOST_NAME {
        let observed = unsafe { normalized_name_from_cstr(parg.cast::<c_char>().cast_const()) };
        if let Some(sni) = observed {
            remember_ssl_sni(ssl, sni.clone());
            bind_ssl_sni_if_possible(ssl, &sni);
        } else {
            forget_ssl_state(ssl);
        }
    }

    let result = if let Some(orig) = *ORIG_SSL_CTRL {
        unsafe { orig(ssl, cmd, larg, parg) }
    } else {
        0
    };
    exit_hook();
    result
}

#[unsafe(no_mangle)]
/// # Safety
/// `ssl` must be a valid OpenSSL handle when required by the original call.
pub unsafe extern "C" fn SSL_set_fd(ssl: *mut c_void, fd: c_int) -> c_int {
    if !enter_hook() {
        return if let Some(orig) = *ORIG_SSL_SET_FD {
            unsafe { orig(ssl, fd) }
        } else {
            0
        };
    }

    initialize();
    let out = if let Some(orig) = *ORIG_SSL_SET_FD {
        unsafe { orig(ssl, fd) }
    } else {
        0
    };
    if out == 1 {
        remember_ssl_fd(ssl, fd);
    }
    exit_hook();
    out
}

#[unsafe(no_mangle)]
/// # Safety
/// `ssl` must be a valid OpenSSL handle when required by the original call.
pub unsafe extern "C" fn SSL_free(ssl: *mut c_void) {
    if !enter_hook() {
        if let Some(orig) = *ORIG_SSL_FREE {
            unsafe { orig(ssl) };
        }
        return;
    }

    initialize();
    forget_ssl_state(ssl);
    if let Some(orig) = *ORIG_SSL_FREE {
        unsafe { orig(ssl) };
    }
    exit_hook();
}

#[unsafe(no_mangle)]
pub extern "C" fn setpriority(which: c_int, who: c_int, prio: c_int) -> c_int {
    match handle_setpriority_compat(which, who, prio) {
        SetpriorityCompatOutcome::Handled => return 0,
        SetpriorityCompatOutcome::FaultcoreError { errno } => {
            set_errno_value(errno);
            return -1;
        }
        SetpriorityCompatOutcome::NotHandled => {}
    }

    unsafe {
        let orig = libc::dlsym(libc::RTLD_NEXT, c"setpriority".as_ptr());
        if orig.is_null() {
            set_errno_value(libc::ENOSYS);
            return -1;
        }
        let orig_func: extern "C" fn(c_int, c_int, c_int) -> c_int = std::mem::transmute(orig);
        orig_func(which, who, prio)
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn faultcore_interceptor_is_active() -> bool {
    true
}

#[unsafe(no_mangle)]
/// # Safety
/// `out` must be a valid writable pointer to `FaultOsiMetricsSnapshot`.
pub unsafe extern "C" fn faultcore_metrics_snapshot(out: *mut FaultOsiMetricsSnapshot) -> bool {
    if out.is_null() {
        return false;
    }
    let snapshot = faultcore_network::global_fault_osi_metrics_snapshot();
    unsafe {
        std::ptr::write(out, snapshot);
    }
    true
}

#[unsafe(no_mangle)]
/// # Safety
/// `out` must be a valid writable pointer to `FaultOsiAdvancedMetricsSnapshot`.
pub unsafe extern "C" fn faultcore_advanced_metrics_snapshot(
    out: *mut FaultOsiAdvancedMetricsSnapshot,
) -> bool {
    if out.is_null() {
        return false;
    }
    let snapshot = faultcore_network::global_fault_osi_advanced_metrics_snapshot();
    unsafe {
        std::ptr::write(out, snapshot);
    }
    true
}

#[unsafe(no_mangle)]
pub extern "C" fn faultcore_metrics_reset() {
    reset_global_fault_osi_metrics();
}



#[cfg(test)]
mod tests {
    use super::*;

    fn build_client_hello_record(server_name: &str) -> Vec<u8> {
       let host = server_name.as_bytes();
       let server_name_list_len = 1 + 2 + host.len();
       let sni_ext_data_len = 2 + server_name_list_len;
       let extensions_len = 4 + sni_ext_data_len;
       let handshake_len = 2 + 32 + 1 + 2 + 2 + 1 + 1 + 2 + extensions_len;
       let record_len = 4 + handshake_len;

       let mut out = Vec::with_capacity(5 + record_len);
       out.extend_from_slice(&[22, 0x03, 0x03]);
       out.extend_from_slice(&(record_len as u16).to_be_bytes());
       out.push(1);
       out.push(((handshake_len >> 16) & 0xFF) as u8);
       out.push(((handshake_len >> 8) & 0xFF) as u8);
       out.push((handshake_len & 0xFF) as u8);
       out.extend_from_slice(&[0x03, 0x03]);
       out.extend_from_slice(&[0; 32]);
       out.push(0);
       out.extend_from_slice(&2u16.to_be_bytes());
       out.extend_from_slice(&[0x00, 0x2F]);
       out.push(1);
       out.push(0);
       out.extend_from_slice(&(extensions_len as u16).to_be_bytes());
       out.extend_from_slice(&0u16.to_be_bytes());
       out.extend_from_slice(&(sni_ext_data_len as u16).to_be_bytes());
       out.extend_from_slice(&(server_name_list_len as u16).to_be_bytes());
       out.push(0);
       out.extend_from_slice(&(host.len() as u16).to_be_bytes());
       out.extend_from_slice(host);
       out
    }
    
    #[test]
    fn connect_timeout_maps_to_etimedout() {
       let directive =
           global_interceptor_runtime().map_connect_decision(LayerDecision::TimeoutMs(10));
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
       let directive = global_interceptor_runtime()
           .map_connect_decision(LayerDecision::ConnectionErrorKind(1));
       assert_eq!(
           directive,
           faultcore_network::ConnectDirective::ReturnErrno {
               errno: libc::ECONNRESET,
               ret: -1,
           }
       );
    }
    
    #[test]
    fn stream_drop_maps_to_errno() {
       let directive =
           global_interceptor_runtime().map_stream_decision(1, LayerDecision::Drop, false);
       assert_eq!(
           directive,
           faultcore_network::StreamDirective::ReturnErrno {
               errno: libc::EIO,
               ret: -1,
           }
       );
    }
    
    #[test]
    fn stream_drop_must_not_look_like_successful_zero_byte_io() {
       let directive =
           global_interceptor_runtime().map_stream_decision(1, LayerDecision::Drop, false);
       assert!(
           !matches!(
               directive,
               faultcore_network::StreamDirective::ReturnValue(0)
           ),
           "drop for stream I/O should not be mapped as a successful zero-byte operation"
       );
    }
    
    #[test]
    fn stream_timeout_maps_to_etimedout() {
       let directive = global_interceptor_runtime().map_stream_decision(
           1,
           LayerDecision::TimeoutMs(50),
           false,
       );
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
       let directive =
           global_interceptor_runtime().map_stream_decision(1, LayerDecision::StageReorder, false);
       assert_eq!(directive, faultcore_network::StreamDirective::Continue);
    }
    
    #[test]
    fn dns_mapping_contract_is_stable() {
       assert_eq!(
           global_interceptor_runtime().map_dns_decision_to_eai(&LayerDecision::TimeoutMs(1)),
           Some(libc::EAI_AGAIN)
       );
       assert_eq!(
           global_interceptor_runtime().map_dns_decision_to_eai(&LayerDecision::NxDomain),
           Some(libc::EAI_NONAME)
       );
       assert_eq!(
           global_interceptor_runtime()
               .map_dns_decision_to_eai(&LayerDecision::ConnectionErrorKind(1)),
           Some(libc::EAI_FAIL)
       );
       assert_eq!(
           global_interceptor_runtime().map_dns_decision_to_eai(&LayerDecision::DelayNs(1)),
           None
       );
    }
    
    #[test]
    fn metrics_snapshot_null_pointer_returns_false() {
       let ok = unsafe { faultcore_metrics_snapshot(std::ptr::null_mut()) };
       assert!(!ok);
    }

    #[test]
    fn advanced_metrics_snapshot_null_pointer_returns_false() {
       let ok = unsafe { faultcore_advanced_metrics_snapshot(std::ptr::null_mut()) };
       assert!(!ok);
    }
    
    #[test]
    fn setpriority_hook_must_check_dlsym_pointer_before_transmute() {
       let src = include_str!("lib.rs");
       let setpriority_block = src
           .split("pub extern \"C\" fn setpriority")
           .nth(1)
           .expect("setpriority hook must exist");
       assert!(setpriority_block.contains("is_null"));
    }
    
    #[test]
    fn setpriority_faultcore_failure_must_return_errno_without_libc_fallback() {
       let src = include_str!("lib.rs");
       let setpriority_block = src
           .split("pub extern \"C\" fn setpriority")
           .nth(1)
           .expect("setpriority hook must exist");
       assert!(setpriority_block.contains("SetpriorityCompatOutcome::FaultcoreError"));
       assert!(setpriority_block.contains("set_errno_value(errno)"));
    }
    
    #[test]
    fn send_hooks_share_uplink_helper_flow() {
       let src = include_str!("lib.rs");
       let send_block = src
           .split("pub unsafe extern \"C\" fn send(")
           .nth(1)
           .expect("send hook must exist");
       let sendto_block = src
           .split("pub unsafe extern \"C\" fn sendto(")
           .nth(1)
           .expect("sendto hook must exist");
       assert!(send_block.contains("handle_uplink_send("));
       assert!(sendto_block.contains("handle_uplink_send("));
    }
    
    #[test]
    fn recv_hooks_share_downlink_helper_flow() {
       let src = include_str!("lib.rs");
       let recv_block = src
           .split("pub unsafe extern \"C\" fn recv(")
           .nth(1)
           .expect("recv hook must exist");
       let recvfrom_block = src
           .split("pub unsafe extern \"C\" fn recvfrom(")
           .nth(1)
           .expect("recvfrom hook must exist");
       assert!(recv_block.contains("handle_downlink_recv("));
       assert!(recvfrom_block.contains("handle_downlink_recv("));
    }
    
    #[test]
    fn aliasing_hooks_propagate_fd_binding() {
       let src = include_str!("lib.rs");
       let dup_block = src
           .split("pub extern \"C\" fn dup(")
           .nth(1)
           .expect("dup hook must exist");
       let dup2_block = src
           .split("pub extern \"C\" fn dup2(")
           .nth(1)
           .expect("dup2 hook must exist");
       let dup3_block = src
           .split("pub extern \"C\" fn dup3(")
           .nth(1)
           .expect("dup3 hook must exist");
       let accept_block = src
           .split("pub unsafe extern \"C\" fn accept(")
           .nth(1)
           .expect("accept hook must exist");
       let accept4_block = src
           .split("pub unsafe extern \"C\" fn accept4(")
           .nth(1)
           .expect("accept4 hook must exist");
       assert!(dup_block.contains("clone_fd_binding(oldfd, newfd)"));
       assert!(dup2_block.contains("clone_fd_binding(oldfd, out)"));
       assert!(dup3_block.contains("clone_fd_binding(oldfd, out)"));
       assert!(accept_block.contains("clone_fd_binding(s, newfd)"));
       assert!(accept4_block.contains("clone_fd_binding(s, newfd)"));
    }

    #[test]
    fn tls_client_hello_sni_parser_extracts_normalized_host() {
       let payload = build_client_hello_record("Api.Foo.com.");
       let observed = tls_client_hello_sni(&payload);
       assert_eq!(observed.as_deref(), Some("api.foo.com"));
    }

    #[test]
    fn tls_client_hello_sni_parser_returns_none_for_non_tls_payload() {
       assert!(tls_client_hello_sni(b"plain-text").is_none());
    }
}
