use faultcore_network::{ChaosEngine, Direction, LayerDecision};
use libc::{addrinfo, c_char, c_int, c_void, size_t, sockaddr, socklen_t, ssize_t};
use std::cell::RefCell;
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

mod shm;

static INITIALIZED: AtomicBool = AtomicBool::new(false);

const FAULTCORE_SETPRIORITY_LATENCY: c_int = 0xFA;
const FAULTCORE_SETPRIORITY_BANDWIDTH: c_int = 0xFB;
const FAULTCORE_SETPRIORITY_TIMEOUT: c_int = 0xFC;


thread_local! {
    static LATENCY_START: RefCell<HashMap<c_int, Instant>> = RefCell::new(HashMap::new());
}

lazy_static::lazy_static! {
    static ref REORDER_PENDING_SENDTO: parking_lot::Mutex<HashMap<c_int, PendingDatagram>> = parking_lot::Mutex::new(HashMap::new());
}

struct PendingDatagram {
    data: Vec<u8>,
    flags: c_int,
    addr: Vec<u8>,
    addr_len: socklen_t,
}

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

    pub static ref CHAOS_ENGINE: ChaosEngine = ChaosEngine::new();
}

unsafe fn get_original_fn<T>(name: &str) -> T {
    let symbol_name = std::ffi::CString::new(name).unwrap();
    let fn_ptr = unsafe { libc::dlsym(libc::RTLD_NEXT, symbol_name.as_ptr()) };
    if fn_ptr.is_null() {
        unsafe { libc::abort() };
    }
    unsafe { std::mem::transmute_copy(&fn_ptr) }
}

fn set_errno(val: i32) {
    unsafe {
        *libc::__errno_location() = val;
    }
}

fn err_kind_to_errno(kind: u64) -> Option<i32> {
    match kind {
        1 => Some(libc::ECONNRESET),
        2 => Some(libc::ECONNREFUSED),
        3 => Some(libc::ENETUNREACH),
        _ => None,
    }
}

fn network_config_for_fd(fd: c_int) -> Option<faultcore_network::Config> {
    Some(shm::get_config_for_fd(fd)?.into_network_config())
}

fn map_connect_decision_to_result(decision: LayerDecision) -> Option<c_int> {
    match decision {
        LayerDecision::Continue => None,
        LayerDecision::Drop => {
            set_errno(libc::ECONNREFUSED);
            Some(-1)
        }
        LayerDecision::DelayNs(latency_ns) => {
            if latency_ns > 0 {
                std::thread::sleep(std::time::Duration::from_nanos(latency_ns));
            }
            None
        }
        LayerDecision::TimeoutMs(_) => {
            set_errno(libc::ETIMEDOUT);
            Some(-1)
        }
        LayerDecision::Error(_) => {
            set_errno(libc::EIO);
            Some(-1)
        }
        LayerDecision::ConnectionErrorKind(kind) => {
            set_errno(err_kind_to_errno(kind).unwrap_or(libc::EIO));
            Some(-1)
        }
        LayerDecision::StageReorder | LayerDecision::Duplicate(_) | LayerDecision::NxDomain => {
            set_errno(libc::EIO);
            Some(-1)
        }
    }
}

fn map_stream_decision_to_result(fd: c_int, decision: LayerDecision) -> Option<ssize_t> {
    match decision {
        LayerDecision::Continue | LayerDecision::StageReorder | LayerDecision::Duplicate(_) => None,
        LayerDecision::Drop => Some(0),
        LayerDecision::DelayNs(latency_ns) => {
            if is_non_blocking(fd) {
                let mut elapsed = false;
                LATENCY_START.with(|cell| {
                    let mut latency_start = cell.borrow_mut();
                    if let Some(start) = latency_start.get(&fd) {
                        if start.elapsed().as_nanos() >= latency_ns as u128 {
                            elapsed = true;
                            latency_start.remove(&fd);
                        }
                    } else {
                        latency_start.insert(fd, Instant::now());
                    }
                });
                if !elapsed {
                    set_errno(libc::EAGAIN);
                    return Some(-1);
                }
            } else if latency_ns > 0 {
                std::thread::sleep(std::time::Duration::from_nanos(latency_ns));
            }
            None
        }
        LayerDecision::TimeoutMs(_) => {
            set_errno(libc::ETIMEDOUT);
            Some(-1)
        }
        LayerDecision::Error(_) => {
            set_errno(libc::EIO);
            Some(-1)
        }
        LayerDecision::ConnectionErrorKind(kind) => {
            set_errno(err_kind_to_errno(kind).unwrap_or(libc::EIO));
            Some(-1)
        }
        LayerDecision::NxDomain => {
            set_errno(libc::EIO);
            Some(-1)
        }
    }
}

fn record_stream_bytes(fd: c_int, bytes: u64) {
    CHAOS_ENGINE.record_stream_bytes(fd, bytes);
}

fn maybe_duplicate_send(fd: c_int, b: *const c_void, sent: ssize_t, f: c_int) {
    if sent <= 0 {
        return;
    }
    let Some(cfg) = shm::get_config_for_fd(fd) else {
        return;
    };
    let network_cfg = cfg.into_network_config();
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
    let Some(cfg) = shm::get_config_for_fd(fd) else {
        return;
    };
    let network_cfg = cfg.into_network_config();
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
    fd: c_int,
    b: *const c_void,
    l: size_t,
    f: c_int,
    addr: *const sockaddr,
    addr_len: socklen_t,
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
    REORDER_PENDING_SENDTO.lock().insert(
        fd,
        PendingDatagram {
            data,
            flags: f,
            addr: addr_bytes,
            addr_len,
        },
    );
    Some(l as ssize_t)
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
        let _ = shm::try_open_shm();
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
        let tid = shm::get_thread_id() as usize;
        shm::assign_rule_to_fd(fd, tid);
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
    LATENCY_START.with(|cell| {
        cell.borrow_mut().remove(&fd);
    });
    CHAOS_ENGINE.clear_fd_state(fd);
    REORDER_PENDING_SENDTO.lock().remove(&fd);
    shm::clear_rule_for_fd(fd);

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
    let result = if let Some(network_cfg) = network_config_for_fd(s) {
        let decision = CHAOS_ENGINE.evaluate_stream_pre(s, &network_cfg, l as u64, Direction::Uplink);
        if let Some(error) = map_stream_decision_to_result(s, decision) {
            error
        } else {
            unsafe { (ORIG_SEND)(s, b, l, f) }
        }
    } else {
        unsafe { (ORIG_SEND)(s, b, l, f) }
    };

    if result > 0 {
        record_stream_bytes(s, result as u64);
        maybe_duplicate_send(s, b, result, f);
    }

    exit_hook();
    result
}

#[unsafe(no_mangle)]
pub extern "C" fn recv(s: c_int, b: *mut c_void, l: size_t, f: c_int) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_RECV)(s, b, l, f) };
    }

    initialize();
    let result = if let Some(network_cfg) = network_config_for_fd(s) {
        let decision =
            CHAOS_ENGINE.evaluate_stream_pre(s, &network_cfg, l as u64, Direction::Downlink);
        if let Some(error) = map_stream_decision_to_result(s, decision) {
            error
        } else {
            unsafe { (ORIG_RECV)(s, b, l, f) }
        }
    } else {
        unsafe { (ORIG_RECV)(s, b, l, f) }
    };

    if result > 0 {
        record_stream_bytes(s, result as u64);
    }

    exit_hook();
    result
}

#[unsafe(no_mangle)]
pub extern "C" fn connect(s: c_int, a: *const sockaddr, l: socklen_t) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_CONNECT)(s, a, l) };
    }

    initialize();
    let tid = shm::get_thread_id() as usize;
    shm::assign_rule_to_fd(s, tid);

    let result = if let Some(network_cfg) = network_config_for_fd(s) {
        let decision = CHAOS_ENGINE.evaluate_connect(s, &network_cfg);
        if let Some(error) = map_connect_decision_to_result(decision) {
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
pub extern "C" fn sendto(
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
    let mut pending = REORDER_PENDING_SENDTO.lock().remove(&s);
    let result = if let Some(network_cfg) = network_config_for_fd(s) {
        let decision = CHAOS_ENGINE.evaluate_stream_pre(s, &network_cfg, l as u64, Direction::Uplink);
        if let Some(error) = map_stream_decision_to_result(s, decision.clone()) {
            if let Some(pkt) = pending.take() {
                REORDER_PENDING_SENDTO.lock().insert(s, pkt);
            }
            error
        } else if matches!(decision, LayerDecision::StageReorder) && pending.is_none() {
            maybe_stage_reorder_sendto(s, b, l, f, addr, addr_len).unwrap_or(l as ssize_t)
        } else {
            unsafe { (ORIG_SENDTO)(s, b, l, f, addr, addr_len) }
        }
    } else {
        unsafe { (ORIG_SENDTO)(s, b, l, f, addr, addr_len) }
    };

    if result > 0 {
        record_stream_bytes(s, result as u64);
        maybe_duplicate_sendto(s, b, result, f, addr, addr_len);
        if let Some(pkt) = pending.take() {
            let addr_ptr = if pkt.addr.is_empty() {
                std::ptr::null()
            } else {
                pkt.addr.as_ptr().cast::<sockaddr>()
            };
            unsafe {
                let _ = (ORIG_SENDTO)(
                    s,
                    pkt.data.as_ptr().cast::<c_void>(),
                    pkt.data.len(),
                    pkt.flags,
                    addr_ptr,
                    pkt.addr_len,
                );
            }
        }
    }

    exit_hook();
    result
}

#[unsafe(no_mangle)]
pub extern "C" fn recvfrom(
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
    let result = if let Some(network_cfg) = network_config_for_fd(s) {
        let decision =
            CHAOS_ENGINE.evaluate_stream_pre(s, &network_cfg, l as u64, Direction::Downlink);
        if let Some(error) = map_stream_decision_to_result(s, decision) {
            error
        } else {
            unsafe { (ORIG_RECVFROM)(s, b, l, f, addr, addr_len) }
        }
    } else {
        unsafe { (ORIG_RECVFROM)(s, b, l, f, addr, addr_len) }
    };

    if result > 0 {
        record_stream_bytes(s, result as u64);
    }

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
    let tid = shm::get_thread_id();
    if let Some(cfg) = shm::get_config_for_tid(tid) {
        let network_cfg = cfg.into_network_config();
        match CHAOS_ENGINE.evaluate_dns_lookup(&network_cfg) {
            LayerDecision::Continue => {}
            LayerDecision::DelayNs(ns) => {
                std::thread::sleep(std::time::Duration::from_nanos(ns));
            }
            LayerDecision::TimeoutMs(ms) => {
                std::thread::sleep(std::time::Duration::from_millis(ms));
                exit_hook();
                return libc::EAI_AGAIN;
            }
            LayerDecision::NxDomain => {
                exit_hook();
                return libc::EAI_NONAME;
            }
            LayerDecision::Drop
            | LayerDecision::Error(_)
            | LayerDecision::ConnectionErrorKind(_)
            | LayerDecision::StageReorder
            | LayerDecision::Duplicate(_) => {
                exit_hook();
                return libc::EAI_FAIL;
            }
        }
    }

    let result = unsafe { (ORIG_GETADDRINFO)(node, service, hints, res) };
    exit_hook();
    result
}
#[unsafe(no_mangle)]
pub extern "C" fn setpriority(which: c_int, who: c_int, prio: c_int) -> c_int {
    let is_faultcore = matches!(
        which,
        FAULTCORE_SETPRIORITY_LATENCY
            | FAULTCORE_SETPRIORITY_BANDWIDTH
            | FAULTCORE_SETPRIORITY_TIMEOUT
    );

    if is_faultcore {
        let tid = shm::get_thread_id() as usize;
        if let Some(p) = unsafe { shm::get_config_ptr(tid, true) } {
            let mut config = unsafe { p.read() };
            match which {
                FAULTCORE_SETPRIORITY_LATENCY => {
                    config.latency_ns = (who as u64) * 1_000_000;
                    config.packet_loss_ppm = prio as u64;
                }
                FAULTCORE_SETPRIORITY_BANDWIDTH => {
                    config.bandwidth_bps = (prio as u64) * 1024;
                }
                FAULTCORE_SETPRIORITY_TIMEOUT => {
                    if who != -1 {
                        config.connect_timeout_ms = who as u64;
                    }
                    if prio != -1 {
                        config.recv_timeout_ms = prio as u64;
                    }
                }
                _ => {}
            }
            config.magic = shm::FAULTCORE_MAGIC;
            unsafe { p.write(config) };
        }
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
