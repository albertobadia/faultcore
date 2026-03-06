use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};

static CALL_COUNTER: AtomicU64 = AtomicU64::new(0);

#[pyclass(from_py_object)]
pub struct CallContext {
    #[pyo3(get, set)]
    pub function_name: String,
    #[pyo3(get, set)]
    pub thread_id: u64,
    #[pyo3(get, set)]
    pub call_id: u64,
    #[pyo3(get, set)]
    pub host: Option<String>,
    #[pyo3(get, set)]
    pub path: Option<String>,
    #[pyo3(get, set)]
    pub method: Option<String>,
    #[pyo3(get, set)]
    pub headers: HashMap<String, String>,
    pub fallback_func: Option<pyo3::Py<pyo3::PyAny>>,
}

impl Clone for CallContext {
    fn clone(&self) -> Self {
        Python::attach(|py| Self {
            function_name: self.function_name.clone(),
            thread_id: self.thread_id,
            call_id: self.call_id,
            host: self.host.clone(),
            path: self.path.clone(),
            method: self.method.clone(),
            headers: self.headers.clone(),
            fallback_func: self.fallback_func.as_ref().map(|f| f.clone_ref(py)),
        })
    }
}

impl std::fmt::Debug for CallContext {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("CallContext")
            .field("function_name", &self.function_name)
            .field("thread_id", &self.thread_id)
            .field("call_id", &self.call_id)
            .field("host", &self.host)
            .field("path", &self.path)
            .field("method", &self.method)
            .field("headers", &self.headers)
            .field(
                "fallback_func",
                &self.fallback_func.as_ref().map(|_| "Py<PyAny>"),
            )
            .finish()
    }
}

#[pymethods]
impl CallContext {
    #[new]
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
            fallback_func: None,
        }
    }

    pub fn set_header(&mut self, key: String, value: String) {
        self.headers.insert(key, value);
    }
}

impl Default for CallContext {
    fn default() -> Self {
        Self::new("unknown".to_string())
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
