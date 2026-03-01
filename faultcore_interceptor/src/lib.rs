use libc::{c_int, c_short, c_void, pollfd, size_t, ssize_t};
use std::sync::atomic::{AtomicBool, Ordering};

static INITIALIZED: AtomicBool = AtomicBool::new(false);

use std::cell::RefCell;

#[derive(Debug, Clone, Copy)]
struct LimitState {
    packet_loss: f64,
    latency_ms: u64,
}

#[derive(Debug, Clone, Copy)]
struct BandwidthState {
    rate_bps: u64,
}

#[derive(Debug, Clone, Copy)]
struct BandwidthTokenBucket {
    tokens: f64,
    last_update: std::time::Instant,
}

#[derive(Debug, Clone, Copy)]
struct TimeoutState {
    connect_timeout_ms: u64,
    recv_timeout_ms: u64,
}

thread_local! {
    static CURRENT_LIMIT: RefCell<Option<LimitState>> = const { RefCell::new(None) };
    static FD_LIMITS: RefCell<Option<std::collections::HashMap<c_int, LimitState>>> = const { RefCell::new(None) };
    static FD_PACKET_COUNTS: RefCell<Option<std::collections::HashMap<c_int, u64>>> = const { RefCell::new(None) };
    static ACTIVE_TASK_ID: RefCell<Option<u64>> = const { RefCell::new(None) };
    static BANDWIDTH_STATE: RefCell<Option<BandwidthState>> = const { RefCell::new(None) };
    static BANDWIDTH_TOKENS: RefCell<Option<BandwidthTokenBucket>> = const { RefCell::new(None) };
    static TIMEOUT_STATE: RefCell<Option<TimeoutState>> = const { RefCell::new(None) };
}

pub fn get_current_tid() -> u64 {
    unsafe { libc::pthread_self() as u64 }
}

unsafe fn get_original_fn<T>(name: &str) -> T {
    let symbol_name = std::ffi::CString::new(name).unwrap();
    let fn_ptr = unsafe { libc::dlsym(libc::RTLD_NEXT, symbol_name.as_ptr()) };
    if fn_ptr.is_null() {
        let msg = b"[FAULTCORE ERROR] Failed to find original symbol\n";
        unsafe {
            libc::write(2, msg.as_ptr() as *const c_void, msg.len());
            libc::abort();
        }
    }
    unsafe { std::mem::transmute_copy(&fn_ptr) }
}

type SetPriorityFn = unsafe extern "C" fn(c_int, libc::id_t, c_int) -> c_int;
type SendFn = unsafe extern "C" fn(c_int, *const c_void, size_t, c_int) -> ssize_t;
type RecvFn = unsafe extern "C" fn(c_int, *mut c_void, size_t, c_int) -> ssize_t;
type ConnectFn = unsafe extern "C" fn(c_int, *const libc::sockaddr, libc::socklen_t) -> c_int;
type SendToFn = unsafe extern "C" fn(
    c_int,
    *const c_void,
    size_t,
    c_int,
    *const libc::sockaddr,
    libc::socklen_t,
) -> ssize_t;
type RecvFromFn = unsafe extern "C" fn(
    c_int,
    *mut c_void,
    size_t,
    c_int,
    *mut libc::sockaddr,
    *mut libc::socklen_t,
) -> ssize_t;

lazy_static::lazy_static! {
    static ref ORIG_SETPRIORITY: SetPriorityFn = unsafe { get_original_fn("setpriority") };
    static ref ORIG_SEND: SendFn = unsafe { get_original_fn("send") };
    static ref ORIG_RECV: RecvFn = unsafe { get_original_fn("recv") };
    static ref ORIG_CONNECT: ConnectFn = unsafe { get_original_fn("connect") };
    static ref ORIG_SENDTO: SendToFn = unsafe { get_original_fn("sendto") };
    static ref ORIG_RECVFROM: RecvFromFn = unsafe { get_original_fn("recvfrom") };
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
        libc::pthread_setspecific(*RECURSION_GUARD_KEY, 1 as *const c_void);
        true
    }
}

fn exit_hook() {
    unsafe {
        libc::pthread_setspecific(*RECURSION_GUARD_KEY, std::ptr::null());
    }
}

const MAGIC_WHICH: c_int = 0xFA;
const MAGIC_BANDWIDTH: c_int = 0xFB;
const MAGIC_TIMEOUT: c_int = 0xFC;

fn handle_setpriority(which: c_int, who: libc::id_t, prio: c_int) -> c_int {
    if which == MAGIC_BANDWIDTH {
        if who == u32::MAX && prio >= 0 {
            let rate_bps = (prio as u64) * 1000;
            BANDWIDTH_STATE.with(|s| {
                *s.borrow_mut() = Some(BandwidthState { rate_bps });
            });
            return 0;
        } else if who == 0 && prio == 0 {
            BANDWIDTH_STATE.with(|s| {
                *s.borrow_mut() = None;
            });
            return 0;
        }
        return -1;
    }
    if which == MAGIC_WHICH {
        if who == 0 && prio == 0 {
            CURRENT_LIMIT.with(|l| *l.borrow_mut() = None);
            FD_LIMITS.with(|l| {
                if let Some(ref mut m) = *l.borrow_mut() {
                    m.clear();
                }
            });
            FD_PACKET_COUNTS.with(|c| {
                if let Some(ref mut m) = *c.borrow_mut() {
                    m.clear();
                }
            });
        } else if who == u32::MAX {
            return 0;
        } else {
            CURRENT_LIMIT.with(|l| {
                *l.borrow_mut() = Some(LimitState {
                    packet_loss: (prio as f64) / 1000000.0,
                    latency_ms: who as u64,
                });
            });
        }
        return 0;
    }
    if which == MAGIC_TIMEOUT {
        if who == 0 && prio == 0 {
            TIMEOUT_STATE.with(|t| *t.borrow_mut() = None);
        } else if who == u32::MAX && prio >= 0 {
            let recv_timeout_ms = prio as u64;
            TIMEOUT_STATE.with(|t| {
                *t.borrow_mut() = Some(TimeoutState {
                    connect_timeout_ms: recv_timeout_ms,
                    recv_timeout_ms,
                });
            });
        } else if who != u32::MAX {
            let connect_timeout_ms = who as u64;
            let recv_timeout_ms = prio as u64;
            TIMEOUT_STATE.with(|t| {
                *t.borrow_mut() = Some(TimeoutState {
                    connect_timeout_ms,
                    recv_timeout_ms,
                });
            });
        }
        return 0;
    }
    unsafe { (ORIG_SETPRIORITY)(which, who, prio) }
}

fn initialize() {
    if !INITIALIZED.swap(true, Ordering::SeqCst) {
        unsafe {
            let msg = "[FAULTCORE] Initializing interposer (Atomic Sync Mode)...\n";
            libc::write(2, msg.as_ptr() as *const c_void, msg.len());

            lazy_static::initialize(&ORIG_SETPRIORITY);
            lazy_static::initialize(&ORIG_SEND);
            lazy_static::initialize(&ORIG_RECV);
            lazy_static::initialize(&ORIG_CONNECT);
            lazy_static::initialize(&ORIG_SENDTO);
            lazy_static::initialize(&ORIG_RECVFROM);
        }
    }
}

fn apply_bandwidth_throttle(bytes_to_send: u64) {
    let bandwidth = BANDWIDTH_STATE.with(|s| *s.borrow());
    if let Some(bw_state) = bandwidth {
        let rate = bw_state.rate_bps as f64;
        if rate <= 0.0 {
            return;
        }

        BANDWIDTH_TOKENS.with(|tb| {
            let mut tokens = tb.borrow_mut();
            let now = std::time::Instant::now();

            if tokens.is_none() {
                *tokens = Some(BandwidthTokenBucket {
                    tokens: 0.0,
                    last_update: now,
                });
            }

            if let Some(ref mut bucket) = *tokens {
                let elapsed = bucket.last_update.elapsed().as_secs_f64();
                let new_tokens = elapsed * rate;
                bucket.tokens = (bucket.tokens + new_tokens).min(rate * 2.0);
                bucket.last_update = now;

                let bytes_needed = bytes_to_send as f64 * 8.0;
                if bucket.tokens >= bytes_needed {
                    bucket.tokens -= bytes_needed;
                } else {
                    let deficit = bytes_needed - bucket.tokens;
                    let wait_time = deficit / rate;
                    bucket.tokens = 0.0;
                    std::thread::sleep(std::time::Duration::from_secs_f64(wait_time));
                }
            }
        });
    }
}

fn apply_chaos(fd: c_int) -> Option<isize> {
    let limit_state = FD_LIMITS.with(|l| {
        let mut limits = l.borrow_mut();
        if limits.is_none() {
            *limits = Some(std::collections::HashMap::new());
        }
        limits.as_mut().unwrap().get(&fd).cloned()
    });
    if let Some(state) = limit_state {
        if state.latency_ms > 0 {
            std::thread::sleep(std::time::Duration::from_millis(state.latency_ms));
        }
        if state.packet_loss > 0.0 {
            let seen = FD_PACKET_COUNTS.with(|c| {
                let mut counts = c.borrow_mut();
                if counts.is_none() {
                    *counts = Some(std::collections::HashMap::new());
                }
                let counts = counts.as_mut().unwrap();
                let count = counts.entry(fd).or_insert(0);
                *count += 1;
                *count
            });
            let drop_interval = (1.0 / state.packet_loss).round() as u64;
            if drop_interval > 0 && seen % drop_interval == 0 {
                unsafe {
                    let msg = b"[FAULTCORE] Packet dropped (0 bytes)!\n";
                    libc::write(2, msg.as_ptr() as *const c_void, msg.len());
                }
                return Some(0);
            }
        }
    }
    None
}

const POLLIN: c_short = 0x0001;
const POLLOUT: c_short = 0x0004;
const POLLERR: c_short = 0x0008;
const POLLHUP: c_short = 0x0010;
const POLLNVAL: c_short = 0x0020;

fn apply_timeout_connect(
    sock: c_int,
    addr: *const libc::sockaddr,
    len: libc::socklen_t,
) -> Option<c_int> {
    let timeout_ms = TIMEOUT_STATE.with(|t| t.borrow().map(|state| state.connect_timeout_ms));

    if let Some(timeout) = timeout_ms {
        if timeout > 0 && !addr.is_null() && len > 0 {
            unsafe {
                let orig_flags = libc::fcntl(sock, libc::F_GETFL, 0);
                if orig_flags < 0 {
                    return None;
                }
                let nonblock_flags = orig_flags | libc::O_NONBLOCK;
                if libc::fcntl(sock, libc::F_SETFL, nonblock_flags) < 0 {
                    return None;
                }

                let res = (ORIG_CONNECT)(sock, addr, len);

                if res < 0 {
                    let err = *libc::__error();
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
                let timeout_val = (timeout * 1000) as c_int;
                let poll_res = libc::poll(&mut poll_fd, 1, timeout_val);

                if poll_res < 0 {
                    libc::fcntl(sock, libc::F_SETFL, orig_flags);
                    return Some(-1);
                } else if poll_res == 0 {
                    libc::fcntl(sock, libc::F_SETFL, orig_flags);
                    *libc::__error() = libc::ETIMEDOUT;
                    return Some(-1);
                }

                if (poll_fd.revents & POLLERR) != 0 || (poll_fd.revents & POLLHUP) != 0 {
                    libc::fcntl(sock, libc::F_SETFL, orig_flags);
                    let mut sock_err: c_int = 0;
                    let mut sock_err_len = std::mem::size_of::<c_int>() as libc::socklen_t;
                    if libc::getsockopt(
                        sock,
                        libc::SOL_SOCKET,
                        libc::SO_ERROR,
                        &mut sock_err as *mut c_int as *mut c_void,
                        &mut sock_err_len,
                    ) != 0
                    {
                        *libc::__error() = libc::ECONNREFUSED;
                    } else if sock_err != 0 {
                        *libc::__error() = sock_err;
                    } else {
                        *libc::__error() = libc::ECONNREFUSED;
                    }
                    return Some(-1);
                }

                libc::fcntl(sock, libc::F_SETFL, orig_flags);
                return Some(0);
            }
        }
    }
    None
}

fn apply_timeout_recv(sock: c_int) -> Option<isize> {
    let timeout_ms = TIMEOUT_STATE.with(|t| t.borrow().map(|state| state.recv_timeout_ms));

    if let Some(timeout) = timeout_ms {
        if timeout > 0 {
            unsafe {
                let mut poll_fd = pollfd {
                    fd: sock,
                    events: POLLIN | POLLERR,
                    revents: 0,
                };
                let timeout_val = (timeout as c_int) * 1000;
                let poll_res = libc::poll(&mut poll_fd, 1, timeout_val);

                if poll_res < 0 {
                    return Some(-1);
                } else if poll_res == 0 {
                    *libc::__error() = libc::ETIMEDOUT;
                    return Some(-1);
                }

                if (poll_fd.revents & POLLNVAL) != 0 {
                    *libc::__error() = libc::EBADF;
                    return Some(-1);
                }
            }
        }
    }
    None
}

// macOS Interpose
#[cfg(target_os = "macos")]
mod interpose {
    use super::*;

    #[repr(C)]
    struct Interposer(pub *const (), pub *const ());
    unsafe impl Sync for Interposer {}

    #[unsafe(no_mangle)]
    pub extern "C" fn faultcore_setpriority(wh: c_int, wh_val: libc::id_t, pr: c_int) -> c_int {
        initialize();
        handle_setpriority(wh, wh_val, pr)
    }

    #[unsafe(no_mangle)]
    pub extern "C" fn faultcore_send(s: c_int, b: *const c_void, l: size_t, f: c_int) -> ssize_t {
        initialize();
        apply_bandwidth_throttle(l as u64);
        if !enter_hook() {
            return unsafe { libc::send(s, b, l, f) };
        }
        let res = if let Some(e) = apply_chaos(s) {
            e
        } else {
            unsafe { libc::send(s, b, l, f) }
        };
        exit_hook();
        res
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn faultcore_recv(s: c_int, b: *mut c_void, l: size_t, f: c_int) -> ssize_t {
        initialize();
        if !enter_hook() {
            return unsafe { libc::recv(s, b, l, f) };
        }
        if let Some(e) = apply_chaos(s) {
            exit_hook();
            return e;
        }
        if let Some(e) = apply_timeout_recv(s) {
            exit_hook();
            return e;
        }
        let res = unsafe { libc::recv(s, b, l, f) };
        exit_hook();
        res
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn faultcore_connect(
        s: c_int,
        a: *const libc::sockaddr,
        l: libc::socklen_t,
    ) -> c_int {
        initialize();
        if !enter_hook() {
            return unsafe { libc::connect(s, a, l) };
        }
        let _limit = CURRENT_LIMIT.with(|l| {
            let mut limits = l.borrow_mut();
            let state = limits.take();
            if let Some(ref st) = state {
                FD_LIMITS.with(|fl| {
                    if let Some(ref mut m) = *fl.borrow_mut() {
                        if !m.contains_key(&s) {
                            m.insert(s, st.clone());
                        }
                    }
                });
            }
            state
        });
        if let Some(e) = apply_chaos(s) {
            exit_hook();
            if e == -1 {
                unsafe {
                    *libc::__error() = libc::ECONNREFUSED;
                }
            }
            return e as c_int;
        }
        if let Some(e) = apply_timeout_connect(s, a, l) {
            exit_hook();
            return e;
        }
        let res = unsafe { libc::connect(s, a, l) };
        exit_hook();
        res
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn faultcore_sendto(
        s: c_int,
        b: *const c_void,
        l: size_t,
        f: c_int,
        d: *const libc::sockaddr,
        dl: libc::socklen_t,
    ) -> ssize_t {
        initialize();
        apply_bandwidth_throttle(l as u64);
        if !enter_hook() {
            return unsafe { libc::sendto(s, b, l, f, d, dl) };
        }
        let _limit = CURRENT_LIMIT.with(|l| {
            let mut limits = l.borrow_mut();
            let state = limits.take();
            if let Some(ref st) = state {
                FD_LIMITS.with(|fl| {
                    if let Some(ref mut m) = *fl.borrow_mut() {
                        if !m.contains_key(&s) {
                            m.insert(s, st.clone());
                        }
                    }
                });
            }
            state
        });
        let res = if let Some(e) = apply_chaos(s) {
            e
        } else {
            unsafe { libc::sendto(s, b, l, f, d, dl) }
        };
        exit_hook();
        res
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn faultcore_recvfrom(
        s: c_int,
        b: *mut c_void,
        l: size_t,
        f: c_int,
        a: *mut libc::sockaddr,
        al: *mut libc::socklen_t,
    ) -> ssize_t {
        initialize();
        if !enter_hook() {
            return unsafe { libc::recvfrom(s, b, l, f, a, al) };
        }
        let res = if let Some(e) = apply_chaos(s) {
            e
        } else {
            unsafe { libc::recvfrom(s, b, l, f, a, al) }
        };
        exit_hook();
        res
    }

    #[used]
    #[unsafe(link_section = "__DATA,__interpose")]
    static INTERPOSITIONS: [Interposer; 6] = [
        Interposer(
            faultcore_setpriority as *const (),
            libc::setpriority as *const (),
        ),
        Interposer(faultcore_send as *const (), libc::send as *const ()),
        Interposer(faultcore_recv as *const (), libc::recv as *const ()),
        Interposer(faultcore_connect as *const (), libc::connect as *const ()),
        Interposer(faultcore_sendto as *const (), libc::sendto as *const ()),
        Interposer(faultcore_recvfrom as *const (), libc::recvfrom as *const ()),
    ];
}

// Linux Hooks
#[cfg(not(target_os = "macos"))]
mod linux {
    use super::*;

    #[unsafe(no_mangle)]
    pub extern "C" fn setpriority(wh: c_int, wh_val: c_int, pr: c_int) -> c_int {
        initialize();
        handle_setpriority(wh, wh_val, pr)
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn send(s: c_int, b: *const c_void, l: size_t, f: c_int) -> ssize_t {
        initialize();
        if let Some(e) = apply_chaos(s) {
            return e;
        }
        unsafe { (ORIG_SEND)(s, b, l, f) }
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn recv(s: c_int, b: *mut c_void, l: size_t, f: c_int) -> ssize_t {
        initialize();
        if let Some(e) = apply_chaos(s) {
            return e;
        }
        if let Some(e) = apply_timeout_recv(s) {
            return e;
        }
        unsafe { (ORIG_RECV)(s, b, l, f) }
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn connect(s: c_int, a: *const libc::sockaddr, l: libc::socklen_t) -> c_int {
        initialize();
        let limit = CURRENT_LIMIT.with(|l| {
            let mut limits = l.borrow_mut();
            let state = limits.take();
            if let Some(ref st) = state {
                FD_LIMITS.with(|fl| {
                    if let Some(ref mut m) = *fl.borrow_mut() {
                        if !m.contains_key(&s) {
                            m.insert(s, st.clone());
                        }
                    }
                });
            }
            state
        });
        if let Some(e) = apply_chaos(s) {
            if e == -1 {
                unsafe {
                    *libc::__error() = libc::ECONNREFUSED;
                }
            }
            return e as c_int;
        }
        if let Some(e) = apply_timeout_connect(s, a, l) {
            return e;
        }
        unsafe { (ORIG_CONNECT)(s, a, l) }
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn sendto(
        s: c_int,
        b: *const c_void,
        l: size_t,
        f: c_int,
        d: *const libc::sockaddr,
        dl: libc::socklen_t,
    ) -> ssize_t {
        initialize();
        let limit = CURRENT_LIMIT.with(|l| {
            let mut limits = l.borrow_mut();
            let state = limits.take();
            if let Some(ref st) = state {
                FD_LIMITS.with(|fl| {
                    if let Some(ref mut m) = *fl.borrow_mut() {
                        if !m.contains_key(&s) {
                            m.insert(s, st.clone());
                        }
                    }
                });
            }
            state
        });
        if let Some(e) = apply_chaos(s) {
            return e;
        }
        unsafe { (ORIG_SENDTO)(s, b, l, f, d, dl) }
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn recvfrom(
        s: c_int,
        b: *mut c_void,
        l: size_t,
        f: c_int,
        a: *mut libc::sockaddr,
        al: *mut libc::socklen_t,
    ) -> ssize_t {
        initialize();
        if let Some(e) = apply_chaos(s) {
            return e;
        }
        unsafe { (ORIG_RECVFROM)(s, b, l, f, a, al) }
    }
}
