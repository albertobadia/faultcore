use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::{Duration, Instant};

use libc::{EAGAIN, EAI_AGAIN, EAI_FAIL, EAI_NONAME, ECONNREFUSED, ECONNRESET, EIO, ENETUNREACH, ETIMEDOUT};
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
    reorder_pending_by_fd: Mutex<HashMap<i32, VecDeque<PendingDatagram>>>,
    reorder_pending_recv_by_fd: Mutex<HashMap<i32, VecDeque<PendingDatagram>>>,
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
        self.reorder_pending_by_fd
            .lock()
            .remove(&fd)
            .unwrap_or_default()
    }

    pub fn put_reorder_pending(&self, fd: i32, pending: VecDeque<PendingDatagram>) {
        if pending.is_empty() {
            return;
        }
        self.reorder_pending_by_fd.lock().insert(fd, pending);
    }

    pub fn take_reorder_pending_recv(&self, fd: i32) -> VecDeque<PendingDatagram> {
        self.reorder_pending_recv_by_fd
            .lock()
            .remove(&fd)
            .unwrap_or_default()
    }

    pub fn put_reorder_pending_recv(&self, fd: i32, pending: VecDeque<PendingDatagram>) {
        if pending.is_empty() {
            return;
        }
        self.reorder_pending_recv_by_fd.lock().insert(fd, pending);
    }

    pub fn stage_reorder_datagram(
        &self,
        pending: &mut VecDeque<PendingDatagram>,
        data: Vec<u8>,
        flags: i32,
        addr: Vec<u8>,
        addr_len: u32,
    ) {
        pending.push_back(PendingDatagram::new(data, flags, addr, addr_len));
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
            LayerDecision::Drop => StreamDirective::ReturnValue(0),
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
