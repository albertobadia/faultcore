use libc::{c_int, c_void, size_t, ssize_t};
use std::sync::atomic::{AtomicBool, Ordering};

static INITIALIZED: AtomicBool = AtomicBool::new(false);

use std::cell::RefCell;

#[derive(Debug, Clone, Copy)]
struct LimitState {
    packet_loss: f64,
    latency_ms: u64,
}

thread_local! {
    static CURRENT_LIMIT: RefCell<Option<LimitState>> = const { RefCell::new(None) };
    static FD_LIMITS: RefCell<Option<std::collections::HashMap<c_int, LimitState>>> = const { RefCell::new(None) };
    static FD_PACKET_COUNTS: RefCell<Option<std::collections::HashMap<c_int, u64>>> = const { RefCell::new(None) };
    static ACTIVE_TASK_ID: RefCell<Option<u64>> = const { RefCell::new(None) };
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

type SetPriorityFn = unsafe extern "C" fn(c_int, c_int, c_int) -> c_int;
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

fn handle_setpriority(which: c_int, who: c_int, prio: c_int) -> c_int {
    if which == MAGIC_WHICH {
        // who = latency_ms, prio = (loss * 1000000) as i32
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

// macOS Interpose
#[cfg(target_os = "macos")]
mod interpose {
    use super::*;

    #[repr(C)]
    struct Interposer(pub *const (), pub *const ());
    unsafe impl Sync for Interposer {}

    #[unsafe(no_mangle)]
    pub extern "C" fn faultcore_setpriority(wh: c_int, wh_val: c_int, pr: c_int) -> c_int {
        initialize();
        handle_setpriority(wh, wh_val, pr)
    }

    #[unsafe(no_mangle)]
    pub extern "C" fn faultcore_send(s: c_int, b: *const c_void, l: size_t, f: c_int) -> ssize_t {
        initialize();
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
        let res = if let Some(e) = apply_chaos(s) {
            e
        } else {
            unsafe { libc::recv(s, b, l, f) }
        };
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
        let res = if let Some(e) = apply_chaos(s) {
            if e == -1 {
                unsafe {
                    *libc::__error() = libc::ECONNREFUSED;
                }
            }
            e as c_int
        } else {
            unsafe { libc::connect(s, a, l) }
        };
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
