use faultcore_network::{ChaosEngine, LayerResult};
use libc::{c_int, c_short, c_void, pollfd, size_t, sockaddr, socklen_t, ssize_t};
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
    static ref HALF_OPEN_BYTES: parking_lot::Mutex<HashMap<c_int, u64>> = parking_lot::Mutex::new(HashMap::new());
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

lazy_static::lazy_static! {
    pub static ref ORIG_SOCKET: SocketFn = unsafe { get_original_fn("socket") };
    pub static ref ORIG_CLOSE: CloseFn = unsafe { get_original_fn("close") };
    pub static ref ORIG_CONNECT: ConnectFn = unsafe { get_original_fn("connect") };
    pub static ref ORIG_SEND: SendFn = unsafe { get_original_fn("send") };
    pub static ref ORIG_RECV: RecvFn = unsafe { get_original_fn("recv") };
    pub static ref ORIG_SENDTO: SendToFn = unsafe { get_original_fn("sendto") };
    pub static ref ORIG_RECVFROM: RecvFromFn = unsafe { get_original_fn("recvfrom") };

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

fn get_errno() -> i32 {
    unsafe { *libc::__errno_location() }
}

fn set_errno(val: i32) {
    unsafe {
        *libc::__errno_location() = val;
    }
}

fn random_ppm_hit(prob_ppm: u64) -> bool {
    if prob_ppm == 0 {
        return false;
    }
    if prob_ppm >= 1_000_000 {
        return true;
    }
    (rand::random::<u32>() % 1_000_000) < prob_ppm as u32
}

fn err_kind_to_errno(kind: u64) -> Option<i32> {
    match kind {
        1 => Some(libc::ECONNRESET),
        2 => Some(libc::ECONNREFUSED),
        3 => Some(libc::ENETUNREACH),
        _ => None,
    }
}

fn should_fail_connection(fd: c_int) -> Option<i32> {
    let cfg = shm::get_config_for_fd(fd)?;
    let errno = err_kind_to_errno(cfg.conn_err_kind)?;
    if random_ppm_hit(cfg.conn_err_prob_ppm) {
        Some(errno)
    } else {
        None
    }
}

fn should_fail_stream(fd: c_int) -> Option<i32> {
    let cfg = shm::get_config_for_fd(fd)?;
    if cfg.half_open_after_bytes > 0 {
        let current = HALF_OPEN_BYTES.lock().get(&fd).copied().unwrap_or(0);
        if current >= cfg.half_open_after_bytes {
            return err_kind_to_errno(if cfg.half_open_err_kind == 0 {
                1
            } else {
                cfg.half_open_err_kind
            });
        }
    }
    let errno = err_kind_to_errno(cfg.conn_err_kind)?;
    if random_ppm_hit(cfg.conn_err_prob_ppm) {
        Some(errno)
    } else {
        None
    }
}

fn record_stream_bytes(fd: c_int, bytes: u64) {
    if bytes == 0 {
        return;
    }
    let mut map = HALF_OPEN_BYTES.lock();
    let current = map.get(&fd).copied().unwrap_or(0);
    map.insert(fd, current.saturating_add(bytes));
}

fn maybe_duplicate_send(fd: c_int, b: *const c_void, sent: ssize_t, f: c_int) {
    if sent <= 0 {
        return;
    }
    let Some(cfg) = shm::get_config_for_fd(fd) else {
        return;
    };
    if cfg.dup_prob_ppm == 0 {
        return;
    }
    let max_extra = if cfg.dup_max_extra == 0 {
        1
    } else {
        cfg.dup_max_extra
    };
    for _ in 0..max_extra {
        if random_ppm_hit(cfg.dup_prob_ppm) {
            unsafe {
                let _ = (ORIG_SEND)(fd, b, sent as size_t, f);
            }
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
    if cfg.dup_prob_ppm == 0 {
        return;
    }
    let max_extra = if cfg.dup_max_extra == 0 {
        1
    } else {
        cfg.dup_max_extra
    };
    for _ in 0..max_extra {
        if random_ppm_hit(cfg.dup_prob_ppm) {
            unsafe {
                let _ = (ORIG_SENDTO)(fd, b, sent as size_t, f, addr, addr_len);
            }
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
    let cfg = shm::get_config_for_fd(fd)?;
    if cfg.reorder_prob_ppm == 0 || !random_ppm_hit(cfg.reorder_prob_ppm) {
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
    static ref DEFAULT_CONNECT_TIMEOUT_MS: u64 = {
        std::env::var("FAULTCORE_DEFAULT_CONNECT_TIMEOUT_MS")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(1000)
    };
    static ref DEFAULT_RECV_TIMEOUT_MS: u64 = {
        std::env::var("FAULTCORE_DEFAULT_RECV_TIMEOUT_MS")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(1000)
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

fn apply_chaos_from_shm(fd: c_int, bytes: u64, is_send: bool, is_connect: bool) -> Option<(isize, LayerResult)> {
    let config = shm::get_config_for_fd(fd)?;
    let network_config = config.into_network_config();

    let result = if is_send {
        CHAOS_ENGINE.process_send(&network_config, bytes)
    } else {
        CHAOS_ENGINE.process_recv(&network_config, bytes)
    };

    match result {
        LayerResult::Drop | LayerResult::Error(_) => return Some((0, result)),
        LayerResult::Timeout(_) => {
            set_errno(libc::ETIMEDOUT);
            return Some((-1, result));
        }
        LayerResult::Delay(latency_ns) => {
            if is_non_blocking(fd) && !is_connect {
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
                    return Some((-1, result));
                }
            } else {
                std::thread::sleep(std::time::Duration::from_nanos(latency_ns));
            }
        }
        LayerResult::Continue => {}
    }

    None
}

const POLLIN: c_short = 0x0001;
const POLLOUT: c_short = 0x0004;
const POLLERR: c_short = 0x0008;

const POLLNVAL: c_short = 0x0020;

fn apply_timeout_connect(sock: c_int, addr: *const sockaddr, len: socklen_t) -> Option<c_int> {
    if !addr.is_null() {
        let family = unsafe { (*addr).sa_family as i32 };
        if family != libc::AF_INET && family != libc::AF_INET6 {
            return None;
        }
    }

    let timeout_ms = shm::get_config_for_fd(sock)
        .map(|c| c.connect_timeout_ms)
        .unwrap_or_else(|| {
            if !shm::is_shm_open() {
                return 0;
            }
            *DEFAULT_CONNECT_TIMEOUT_MS
        });

    if timeout_ms > 0 && !addr.is_null() && len > 0 {
        unsafe {
            let orig_flags = libc::fcntl(sock, libc::F_GETFL, 0);
            let nonblock_flags = orig_flags | libc::O_NONBLOCK;
            libc::fcntl(sock, libc::F_SETFL, nonblock_flags);

            let res = (ORIG_CONNECT)(sock, addr, len);

            if res < 0 {
                let err = get_errno();
                if err != libc::EINPROGRESS && err != libc::EISCONN {
                    libc::fcntl(sock, libc::F_SETFL, orig_flags);
                    return Some(res);
                }
            }

            let mut poll_fd = pollfd {
                fd: sock,
                events: POLLOUT | POLLERR,
                revents: 0,
            };
            let poll_res = libc::poll(&mut poll_fd, 1, timeout_ms as c_int);

            if poll_res < 0 {
                libc::fcntl(sock, libc::F_SETFL, orig_flags);
                return Some(-1);
            } else if poll_res == 0 {
                libc::fcntl(sock, libc::F_SETFL, orig_flags);
                set_errno(libc::ETIMEDOUT);
                return Some(-1);
            }

            let mut result: c_int = 0;
            let mut result_len = std::mem::size_of::<c_int>() as socklen_t;
            if libc::getsockopt(
                sock,
                libc::SOL_SOCKET,
                libc::SO_ERROR,
                &mut result as *mut _ as *mut c_void,
                &mut result_len,
            ) < 0
            {
                libc::fcntl(sock, libc::F_SETFL, orig_flags);
                return Some(-1);
            }

            if result != 0 {
                set_errno(result);
                libc::fcntl(sock, libc::F_SETFL, orig_flags);
                return Some(-1);
            }

            libc::fcntl(sock, libc::F_SETFL, orig_flags);
            return Some(0);
        }
    }
    None
}

fn apply_timeout_recv(sock: c_int) -> Option<isize> {
    let timeout_ms = shm::get_config_for_fd(sock)
        .map(|c| c.recv_timeout_ms)
        .unwrap_or_else(|| {
            if !shm::is_shm_open() {
                return 0;
            }
            *DEFAULT_RECV_TIMEOUT_MS
        });

    if timeout_ms > 0 {
        unsafe {
            let mut poll_fd = pollfd {
                fd: sock,
                events: POLLIN | POLLERR,
                revents: 0,
            };
            let poll_res = libc::poll(&mut poll_fd, 1, timeout_ms as c_int);

            if poll_res < 0 {
                return Some(-1);
            } else if poll_res == 0 {
                set_errno(libc::ETIMEDOUT);
                return Some(-1);
            }

            if (poll_fd.revents & POLLNVAL) != 0 {
                set_errno(libc::EBADF);
                return Some(-1);
            }
        }
    }
    None
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
    HALF_OPEN_BYTES.lock().remove(&fd);
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
    let result = if let Some(errno) = should_fail_stream(s) {
        set_errno(errno);
        -1
    } else if let Some((error, _)) = apply_chaos_from_shm(s, l as u64, true, false) {
        error
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
    let result = if let Some(errno) = should_fail_stream(s) {
        set_errno(errno);
        -1
    } else if let Some((error, _)) = apply_chaos_from_shm(s, l as u64, false, false) {
        error
    } else if let Some(error) = apply_timeout_recv(s) {
        error
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

    let result = if let Some(errno) = should_fail_connection(s) {
        set_errno(errno);
        -1
    } else if let Some((error, layer_result)) = apply_chaos_from_shm(s, 0, true, true) {
        match layer_result {
            LayerResult::Timeout(_) => {}
            LayerResult::Drop | LayerResult::Error(_) => {
                if error == -1 {
                    set_errno(libc::ECONNREFUSED);
                }
            }
            _ => {}
        }
        error as c_int
    } else if let Some(timeout_result) = apply_timeout_connect(s, a, l) {
        timeout_result
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
    let result = if let Some(errno) = should_fail_stream(s) {
        set_errno(errno);
        if let Some(pkt) = pending.take() {
            REORDER_PENDING_SENDTO.lock().insert(s, pkt);
        }
        -1
    } else if let Some((error, _)) = apply_chaos_from_shm(s, l as u64, true, false) {
        if let Some(pkt) = pending.take() {
            REORDER_PENDING_SENDTO.lock().insert(s, pkt);
        }
        error
    } else if pending.is_none() {
        if let Some(staged) = maybe_stage_reorder_sendto(s, b, l, f, addr, addr_len) {
            staged
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
    let result = if let Some(errno) = should_fail_stream(s) {
        set_errno(errno);
        -1
    } else if let Some((error, _)) = apply_chaos_from_shm(s, l as u64, false, false) {
        error
    } else if let Some(error) = apply_timeout_recv(s) {
        error
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
