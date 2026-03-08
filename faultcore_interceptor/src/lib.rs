use faultcore_network::{ChaosEngine, LayerResult};
use libc::{c_int, c_short, c_void, pollfd, size_t, sockaddr, socklen_t, ssize_t};
use std::cell::RefCell;
use std::sync::atomic::{AtomicBool, Ordering};

mod shm;

static INITIALIZED: AtomicBool = AtomicBool::new(false);

#[derive(Debug, Clone, Copy)]
struct TimeoutState {
    connect_timeout_ms: u64,
    recv_timeout_ms: u64,
}

thread_local! {
    static TIMEOUT_STATE: RefCell<Option<TimeoutState>> = const { RefCell::new(None) };
    static LATENCY_START: RefCell<std::collections::HashMap<c_int, std::time::Instant>> = RefCell::new(std::collections::HashMap::new());
}

type SendFn = unsafe extern "C" fn(c_int, *const c_void, size_t, c_int) -> ssize_t;
type RecvFn = unsafe extern "C" fn(c_int, *mut c_void, size_t, c_int) -> ssize_t;
type ConnectFn = unsafe extern "C" fn(c_int, *const sockaddr, socklen_t) -> c_int;
type SocketFn = unsafe extern "C" fn(c_int, c_int, c_int) -> c_int;
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

fn apply_chaos_from_shm(fd: c_int, bytes: u64, is_send: bool, is_connect: bool) -> Option<isize> {
    let config = shm::get_config_for_fd(fd)?;

    let network_config = config.into_network_config();

    let result = if is_send {
        CHAOS_ENGINE.process_send(&network_config, bytes)
    } else {
        CHAOS_ENGINE.process_recv(&network_config, bytes)
    };

    match result {
        LayerResult::Drop => return Some(0),
        LayerResult::Error(_) => return Some(0),
        LayerResult::Timeout(_timeout_ms) => {
            set_errno(libc::ETIMEDOUT);
            return Some(-1);
        }
        LayerResult::Delay(latency_ns) => {
            let non_blocking = is_non_blocking(fd);

            if non_blocking && !is_connect {
                let mut elapsed = false;
                LATENCY_START.with(|map| {
                    let mut m = map.borrow_mut();
                    if let Some(start) = m.get(&fd) {
                        if start.elapsed().as_nanos() >= latency_ns as u128 {
                            elapsed = true;
                        }
                    } else {
                        m.insert(fd, std::time::Instant::now());
                    }
                });

                if !elapsed {
                    set_errno(libc::EAGAIN);
                    return Some(-1);
                } else {
                    LATENCY_START.with(|map| {
                        map.borrow_mut().remove(&fd);
                    });
                }
            } else {
                std::thread::sleep(std::time::Duration::from_nanos(latency_ns));
            }
        }
        LayerResult::Continue => {}
    }

    if config.connect_timeout_ms > 0 || config.recv_timeout_ms > 0 {
        TIMEOUT_STATE.with(|t| {
            *t.borrow_mut() = Some(TimeoutState {
                connect_timeout_ms: config.connect_timeout_ms,
                recv_timeout_ms: config.recv_timeout_ms,
            });
        });
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

    let timeout_ms = TIMEOUT_STATE
        .with(|t| t.borrow().map(|state| state.connect_timeout_ms))
        .or_else(|| shm::get_config_for_fd(sock).map(|c| c.connect_timeout_ms))
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
    let timeout_ms = TIMEOUT_STATE
        .with(|t| t.borrow().map(|state| state.recv_timeout_ms))
        .or_else(|| shm::get_config_for_fd(sock).map(|c| c.recv_timeout_ms))
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
pub extern "C" fn send(s: c_int, b: *const c_void, l: size_t, f: c_int) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_SEND)(s, b, l, f) };
    }

    initialize();
    let res = if let Some(e) = apply_chaos_from_shm(s, l as u64, true, false) {
        e
    } else {
        unsafe { (ORIG_SEND)(s, b, l, f) }
    };

    exit_hook();
    res
}

#[unsafe(no_mangle)]
pub extern "C" fn recv(s: c_int, b: *mut c_void, l: size_t, f: c_int) -> ssize_t {
    if !enter_hook() {
        return unsafe { (ORIG_RECV)(s, b, l, f) };
    }

    initialize();
    let res = if let Some(e) = apply_chaos_from_shm(s, l as u64, false, false) {
        e
    } else if let Some(e) = apply_timeout_recv(s) {
        e
    } else {
        unsafe { (ORIG_RECV)(s, b, l, f) }
    };

    exit_hook();
    res
}

#[unsafe(no_mangle)]
pub extern "C" fn connect(s: c_int, a: *const sockaddr, l: socklen_t) -> c_int {
    if !enter_hook() {
        return unsafe { (ORIG_CONNECT)(s, a, l) };
    }

    initialize();
    let tid = shm::get_thread_id() as usize;
    shm::assign_rule_to_fd(s, tid);

    let res = if let Some(e) = apply_chaos_from_shm(s, 0, true, true) {
        if e == -1 && get_errno() != libc::EAGAIN {
            set_errno(libc::ECONNREFUSED);
        }
        e as c_int
    } else if let Some(e) = apply_timeout_connect(s, a, l) {
        e
    } else {
        unsafe { (ORIG_CONNECT)(s, a, l) }
    };

    exit_hook();
    res
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
    let res = if let Some(e) = apply_chaos_from_shm(s, l as u64, true, false) {
        e
    } else {
        unsafe { (ORIG_SENDTO)(s, b, l, f, addr, addr_len) }
    };

    exit_hook();
    res
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
    let res = if let Some(e) = apply_chaos_from_shm(s, l as u64, false, false) {
        e
    } else {
        unsafe { (ORIG_RECVFROM)(s, b, l, f, addr, addr_len) }
    };

    exit_hook();
    res
}
#[unsafe(no_mangle)]
pub extern "C" fn setpriority(which: c_int, who: c_int, prio: c_int) -> c_int {
    if which == 0xFA || which == 0xFB || which == 0xFC {
        let tid = shm::get_thread_id() as usize;
        if let Some(p) = unsafe { shm::get_config_ptr(tid, true) } {
            let mut config = unsafe { p.read() };
            match which {
                0xFA => {
                    config.latency_ns = (who as u64) * 1_000_000;
                    config.packet_loss_ppm = prio as u64;
                }
                0xFB => {
                    config.bandwidth_bps = (prio as u64) * 1024;
                }
                0xFC => {
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
