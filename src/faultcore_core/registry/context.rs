use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};

static CALL_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug)]
pub struct CallContext {
    pub function_name: String,
    pub thread_id: u64,
    pub call_id: u64,
    pub host: Option<String>,
    pub path: Option<String>,
    pub method: Option<String>,
    pub headers: HashMap<String, String>,
}

impl CallContext {
    pub fn new(function_name: String) -> Self {
        let thread_id = unsafe { libc::syscall(libc::SYS_gettid) as u64 };
        let call_id = CALL_COUNTER.fetch_add(1, Ordering::SeqCst);
        Self {
            function_name,
            thread_id,
            call_id,
            host: None,
            path: None,
            method: None,
            headers: HashMap::new(),
        }
    }
}

pub enum PolicyResult {
    Ok(Py<PyAny>),
    Drop {
        reason: &'static str,
    },
    Error {
        message: String,
        exception: Option<Py<PyAny>>,
    },
}

impl PolicyResult {
    pub fn is_ok(&self) -> bool {
        matches!(self, PolicyResult::Ok(_))
    }

    pub fn is_drop(&self) -> bool {
        matches!(self, PolicyResult::Drop { .. })
    }

    pub fn is_error(&self) -> bool {
        matches!(self, PolicyResult::Error { .. })
    }
}
