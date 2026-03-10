use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::{Duration, Instant};

use libc::{
    EAGAIN, EAI_AGAIN, EAI_FAIL, EAI_NONAME, ECONNREFUSED, ECONNRESET, EIO, ENETUNREACH, ETIMEDOUT,
    c_void, sockaddr, socklen_t, ssize_t,
};
use parking_lot::Mutex;

use crate::LayerDecision;

#[derive(Clone)]
pub struct PendingDatagram {
    pub data: Arc<[u8]>,
    pub flags: i32,
    pub addr: Arc<[u8]>,
    pub addr_len: u32,
    staged_at: Instant,
}

impl PendingDatagram {
    pub fn new(data: Vec<u8>, flags: i32, addr: Vec<u8>, addr_len: u32) -> Self {
        Self {
            data: Arc::from(data),
            flags,
            addr: Arc::from(addr),
            addr_len,
            staged_at: Instant::now(),
        }
    }
}

pub struct InterceptorRuntime {
    latency_start_by_fd: Mutex<HashMap<i32, Instant>>,
    reorder_pending_by_fd: Mutex<HashMap<i32, Arc<Mutex<VecDeque<PendingDatagram>>>>>,
    reorder_pending_recv_by_fd: Mutex<HashMap<i32, Arc<Mutex<VecDeque<PendingDatagram>>>>>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConnectDirective {
    Continue,
    SleepNs(u64),
    ReturnErrno { errno: i32, ret: i32 },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StreamDirective {
    Continue,
    SleepNs(u64),
    ReturnValue(isize),
    ReturnErrno { errno: i32, ret: isize },
}

fn set_errno(val: i32) {
    unsafe {
        *libc::__errno_location() = val;
    }
}

pub fn set_errno_value(val: i32) {
    set_errno(val);
}

/// # Safety
/// `b` must point to a readable buffer of `l` bytes.
pub unsafe fn stage_reorder_send(
    pending: &mut VecDeque<PendingDatagram>,
    b: *const c_void,
    l: usize,
    flags: i32,
) -> Option<ssize_t> {
    if l == 0 || b.is_null() {
        return None;
    }
    let data = unsafe { std::slice::from_raw_parts(b.cast::<u8>(), l).to_vec() };
    pending.push_back(PendingDatagram::new(data, flags, Vec::new(), 0));
    Some(l as ssize_t)
}

/// # Safety
/// `b` must point to a readable buffer of `l` bytes.
/// `addr` must be null or point to a readable socket address with `addr_len` bytes.
pub unsafe fn stage_reorder_sendto(
    pending: &mut VecDeque<PendingDatagram>,
    b: *const c_void,
    l: usize,
    flags: i32,
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
    pending.push_back(PendingDatagram::new(data, flags, addr_bytes, addr_len));
    Some(l as ssize_t)
}

/// # Safety
/// `b` must point to a writable buffer of `l` bytes.
pub unsafe fn write_pending_recv_result(
    pkt: &PendingDatagram,
    b: *mut c_void,
    l: usize,
) -> ssize_t {
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
/// `b` must point to a writable buffer of `l` bytes.
/// `addr`/`addr_len` must be null together or a valid writable socket address pair.
pub unsafe fn write_pending_recvfrom_result(
    pkt: &PendingDatagram,
    b: *mut c_void,
    l: usize,
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
/// `b` must point to a readable buffer with at least `recv_len` bytes.
pub unsafe fn snapshot_recv_datagram(
    b: *mut c_void,
    recv_len: ssize_t,
    flags: i32,
) -> Option<PendingDatagram> {
    if recv_len <= 0 || b.is_null() {
        return None;
    }
    let data = unsafe { std::slice::from_raw_parts(b.cast::<u8>(), recv_len as usize).to_vec() };
    Some(PendingDatagram::new(data, flags, Vec::new(), 0))
}

/// # Safety
/// `b` must point to a readable buffer with at least `recv_len` bytes.
/// `addr`/`addr_len` must be null together or a valid readable socket address pair.
pub unsafe fn snapshot_recvfrom_datagram(
    b: *mut c_void,
    recv_len: ssize_t,
    flags: i32,
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

pub fn apply_connect_directive(directive: ConnectDirective) -> Option<i32> {
    match directive {
        ConnectDirective::Continue => None,
        ConnectDirective::SleepNs(ns) => {
            if ns > 0 {
                std::thread::sleep(Duration::from_nanos(ns));
            }
            None
        }
        ConnectDirective::ReturnErrno { errno, ret } => {
            set_errno(errno);
            Some(ret)
        }
    }
}

pub fn apply_stream_directive(directive: StreamDirective) -> Option<isize> {
    match directive {
        StreamDirective::Continue => None,
        StreamDirective::SleepNs(ns) => {
            if ns > 0 {
                std::thread::sleep(Duration::from_nanos(ns));
            }
            None
        }
        StreamDirective::ReturnValue(v) => Some(v),
        StreamDirective::ReturnErrno { errno, ret } => {
            set_errno(errno);
            Some(ret)
        }
    }
}

impl InterceptorRuntime {
    pub fn new() -> Self {
        Self {
            latency_start_by_fd: Mutex::new(HashMap::new()),
            reorder_pending_by_fd: Mutex::new(HashMap::new()),
            reorder_pending_recv_by_fd: Mutex::new(HashMap::new()),
        }
    }

    pub fn clear_fd_state(&self, fd: i32) {
        self.latency_start_by_fd.lock().remove(&fd);
        self.reorder_pending_by_fd.lock().remove(&fd);
        self.reorder_pending_recv_by_fd.lock().remove(&fd);
    }

    pub fn nonblocking_delay_pending(&self, fd: i32, latency_ns: u64) -> bool {
        if latency_ns == 0 {
            return false;
        }
        let mut map = self.latency_start_by_fd.lock();
        if let Some(start) = map.get(&fd) {
            if start.elapsed().as_nanos() >= latency_ns as u128 {
                map.remove(&fd);
                return false;
            }
            return true;
        }
        map.insert(fd, Instant::now());
        true
    }

    pub fn take_reorder_pending(&self, fd: i32) -> VecDeque<PendingDatagram> {
        self.with_reorder_pending(fd, std::mem::take)
    }

    pub fn put_reorder_pending(&self, fd: i32, pending: VecDeque<PendingDatagram>) {
        if pending.is_empty() {
            return;
        }
        let mut incoming = pending;
        self.with_reorder_pending(fd, |queue| {
            queue.append(&mut incoming);
        });
    }

    pub fn take_reorder_pending_recv(&self, fd: i32) -> VecDeque<PendingDatagram> {
        self.with_reorder_pending_recv(fd, std::mem::take)
    }

    pub fn put_reorder_pending_recv(&self, fd: i32, pending: VecDeque<PendingDatagram>) {
        if pending.is_empty() {
            return;
        }
        let mut incoming = pending;
        self.with_reorder_pending_recv(fd, |queue| {
            queue.append(&mut incoming);
        });
    }

    pub fn with_reorder_pending<F, R>(&self, fd: i32, op: F) -> R
    where
        F: FnOnce(&mut VecDeque<PendingDatagram>) -> R,
    {
        let queue = {
            let mut map = self.reorder_pending_by_fd.lock();
            map.entry(fd)
                .or_insert_with(|| Arc::new(Mutex::new(VecDeque::new())))
                .clone()
        };

        let mut guard = queue.lock();
        let out = op(&mut guard);
        let cleanup = guard.is_empty();
        drop(guard);

        if cleanup {
            let mut map = self.reorder_pending_by_fd.lock();
            if map
                .get(&fd)
                .is_some_and(|current| Arc::ptr_eq(current, &queue))
            {
                map.remove(&fd);
            }
        }

        out
    }

    pub fn with_reorder_pending_recv<F, R>(&self, fd: i32, op: F) -> R
    where
        F: FnOnce(&mut VecDeque<PendingDatagram>) -> R,
    {
        let queue = {
            let mut map = self.reorder_pending_recv_by_fd.lock();
            map.entry(fd)
                .or_insert_with(|| Arc::new(Mutex::new(VecDeque::new())))
                .clone()
        };

        let mut guard = queue.lock();
        let out = op(&mut guard);
        let cleanup = guard.is_empty();
        drop(guard);

        if cleanup {
            let mut map = self.reorder_pending_recv_by_fd.lock();
            if map
                .get(&fd)
                .is_some_and(|current| Arc::ptr_eq(current, &queue))
            {
                map.remove(&fd);
            }
        }

        out
    }

    pub fn flush_expired_reorder(
        &self,
        pending: &mut VecDeque<PendingDatagram>,
        max_delay_ns: u64,
    ) -> Vec<PendingDatagram> {
        if max_delay_ns == 0 {
            return Vec::new();
        }
        let max_delay = Duration::from_nanos(max_delay_ns);
        let mut flushed = Vec::new();
        while pending
            .front()
            .is_some_and(|pkt| pkt.staged_at.elapsed() >= max_delay)
        {
            if let Some(pkt) = pending.pop_front() {
                flushed.push(pkt);
            }
        }
        flushed
    }

    pub fn enforce_reorder_window(
        &self,
        pending: &mut VecDeque<PendingDatagram>,
        window: usize,
    ) -> Vec<PendingDatagram> {
        let limit = window.max(1);
        let mut flushed = Vec::new();
        while pending.len() > limit {
            if let Some(pkt) = pending.pop_front() {
                flushed.push(pkt);
            }
        }
        flushed
    }

    pub fn pop_reorder_after_success(
        &self,
        pending: &mut VecDeque<PendingDatagram>,
        staged_reorder: bool,
    ) -> Option<PendingDatagram> {
        if staged_reorder {
            return None;
        }
        pending.pop_front()
    }

    pub fn map_connect_decision(&self, decision: LayerDecision) -> ConnectDirective {
        match decision {
            LayerDecision::Continue => ConnectDirective::Continue,
            LayerDecision::Drop => ConnectDirective::ReturnErrno {
                errno: ECONNREFUSED,
                ret: -1,
            },
            LayerDecision::DelayNs(latency_ns) => ConnectDirective::SleepNs(latency_ns),
            LayerDecision::TimeoutMs(_) => ConnectDirective::ReturnErrno {
                errno: ETIMEDOUT,
                ret: -1,
            },
            LayerDecision::Error(_) => ConnectDirective::ReturnErrno {
                errno: EIO,
                ret: -1,
            },
            LayerDecision::ConnectionErrorKind(kind) => ConnectDirective::ReturnErrno {
                errno: err_kind_to_errno(kind),
                ret: -1,
            },
            LayerDecision::StageReorder | LayerDecision::Duplicate(_) | LayerDecision::NxDomain => {
                ConnectDirective::ReturnErrno {
                    errno: EIO,
                    ret: -1,
                }
            }
        }
    }

    pub fn map_stream_decision(
        &self,
        fd: i32,
        decision: LayerDecision,
        is_non_blocking: bool,
    ) -> StreamDirective {
        match decision {
            LayerDecision::Continue | LayerDecision::StageReorder | LayerDecision::Duplicate(_) => {
                StreamDirective::Continue
            }
            LayerDecision::Drop => StreamDirective::ReturnErrno {
                errno: EIO,
                ret: -1,
            },
            LayerDecision::DelayNs(latency_ns) => {
                if is_non_blocking && self.nonblocking_delay_pending(fd, latency_ns) {
                    return StreamDirective::ReturnErrno {
                        errno: EAGAIN,
                        ret: -1,
                    };
                }
                StreamDirective::SleepNs(latency_ns)
            }
            LayerDecision::TimeoutMs(_) => StreamDirective::ReturnErrno {
                errno: ETIMEDOUT,
                ret: -1,
            },
            LayerDecision::Error(_) => StreamDirective::ReturnErrno {
                errno: EIO,
                ret: -1,
            },
            LayerDecision::ConnectionErrorKind(kind) => StreamDirective::ReturnErrno {
                errno: err_kind_to_errno(kind),
                ret: -1,
            },
            LayerDecision::NxDomain => StreamDirective::ReturnErrno {
                errno: EIO,
                ret: -1,
            },
        }
    }

    pub fn map_dns_decision_to_eai(&self, decision: &LayerDecision) -> Option<i32> {
        match decision {
            LayerDecision::Continue | LayerDecision::DelayNs(_) => None,
            LayerDecision::TimeoutMs(_) => Some(EAI_AGAIN),
            LayerDecision::NxDomain => Some(EAI_NONAME),
            LayerDecision::Drop
            | LayerDecision::Error(_)
            | LayerDecision::ConnectionErrorKind(_)
            | LayerDecision::StageReorder
            | LayerDecision::Duplicate(_) => Some(EAI_FAIL),
        }
    }
}

impl Default for InterceptorRuntime {
    fn default() -> Self {
        Self::new()
    }
}

fn err_kind_to_errno(kind: u64) -> i32 {
    match kind {
        1 => ECONNRESET,
        2 => ECONNREFUSED,
        3 => ENETUNREACH,
        _ => EIO,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pkt(data: &[u8]) -> PendingDatagram {
        PendingDatagram::new(data.to_vec(), 0, Vec::new(), 0)
    }

    #[test]
    fn enforce_reorder_window_flushes_oldest_over_limit() {
        let runtime = InterceptorRuntime::new();
        let mut pending = VecDeque::from([pkt(b"a"), pkt(b"b"), pkt(b"c")]);

        let flushed = runtime.enforce_reorder_window(&mut pending, 2);

        assert_eq!(flushed.len(), 1);
        assert_eq!(flushed[0].data.as_ref(), b"a");
        assert_eq!(pending.len(), 2);
        assert_eq!(pending[0].data.as_ref(), b"b");
        assert_eq!(pending[1].data.as_ref(), b"c");
    }

    #[test]
    fn enforce_reorder_window_uses_minimum_one_when_zero() {
        let runtime = InterceptorRuntime::new();
        let mut pending = VecDeque::from([pkt(b"a"), pkt(b"b")]);

        let flushed = runtime.enforce_reorder_window(&mut pending, 0);

        assert_eq!(flushed.len(), 1);
        assert_eq!(flushed[0].data.as_ref(), b"a");
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].data.as_ref(), b"b");
    }

    #[test]
    fn pop_reorder_after_success_only_pops_when_not_staged() {
        let runtime = InterceptorRuntime::new();
        let mut pending = VecDeque::from([pkt(b"a"), pkt(b"b")]);

        assert!(
            runtime
                .pop_reorder_after_success(&mut pending, true)
                .is_none()
        );
        assert_eq!(pending.len(), 2);

        let popped = runtime.pop_reorder_after_success(&mut pending, false);
        assert!(popped.is_some());
        assert_eq!(popped.expect("popped").data.as_ref(), b"a");
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].data.as_ref(), b"b");
    }

    #[test]
    fn flush_expired_reorder_zero_delay_is_noop() {
        let runtime = InterceptorRuntime::new();
        let mut pending = VecDeque::from([pkt(b"a"), pkt(b"b")]);

        let flushed = runtime.flush_expired_reorder(&mut pending, 0);

        assert!(flushed.is_empty());
        assert_eq!(pending.len(), 2);
    }

    #[test]
    fn with_reorder_pending_is_atomic_per_fd_under_concurrency() {
        let runtime = Arc::new(InterceptorRuntime::new());
        let fd = 11;
        let threads = 8;
        let per_thread = 200;

        let mut joins = Vec::new();
        for _ in 0..threads {
            let runtime = Arc::clone(&runtime);
            joins.push(std::thread::spawn(move || {
                for _ in 0..per_thread {
                    runtime.with_reorder_pending(fd, |pending| {
                        pending.push_back(PendingDatagram::new(vec![1], 0, Vec::new(), 0));
                    });
                }
            }));
        }

        for handle in joins {
            handle.join().expect("thread should complete");
        }

        let total = runtime.with_reorder_pending(fd, |pending| pending.len());
        assert_eq!(total, (threads * per_thread) as usize);
    }
}
