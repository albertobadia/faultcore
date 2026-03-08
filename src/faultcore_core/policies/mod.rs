pub mod rate_limit;
pub mod timeout;

use std::sync::Arc;

use parking_lot::RwLock;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

use crate::policies::rate_limit::RateLimitPolicy as RateLimitCore;
use crate::policies::timeout::TimeoutPolicy as TimeoutCore;
use crate::system::shm;

#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct TimeoutPolicy {
    core: TimeoutCore,
}

#[pymethods]
impl TimeoutPolicy {
    #[new]
    fn new(timeout_ms: u64) -> PyResult<Self> {
        TimeoutCore::new(timeout_ms)
            .map(|core| Self { core })
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("timeout_ms must be > 0"))
    }

    fn __call__(
        &self,
        py: Python<'_>,
        func: Py<PyAny>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let timeout_ms = self.core.timeout_ms();

        let tid = if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::write_timeouts(tid, timeout_ms, timeout_ms);
            Some(tid)
        } else {
            None
        };

        let result = func.call(py, args, kwargs);

        if let Some(tid) = tid {
            let _ = shm::clear_config(tid);
        }

        result
    }

    #[getter]
    fn timeout_ms(&self) -> u64 {
        self.core.timeout_ms()
    }

    fn __repr__(&self) -> String {
        format!("TimeoutPolicy({}ms)", self.core.timeout_ms())
    }
}

#[pyclass]
pub struct FallbackPolicy {
    fallback: Py<PyAny>,
}

#[pymethods]
impl FallbackPolicy {
    #[new]
    fn new(fallback: Py<PyAny>) -> Self {
        Self { fallback }
    }

    fn __call__(
        &self,
        py: Python<'_>,
        func: Py<PyAny>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let result = func.call(py, args, kwargs);

        match result {
            Ok(value) => Ok(value),
            Err(e) => {
                let fallback_kwargs = PyDict::new(py);
                if let Some(kwargs) = kwargs {
                    fallback_kwargs.update(kwargs.as_mapping())?;
                }

                let fallback_result = self.fallback.call(py, args, Some(&fallback_kwargs));
                if fallback_result.is_err() {
                    fallback_kwargs.set_item("exception", e.value(py))?;
                    self.fallback.call(py, args, Some(&fallback_kwargs))
                } else {
                    fallback_result
                }
            }
        }
    }

    fn __repr__(&self) -> String {
        "FallbackPolicy(...)".to_string()
    }
}

#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct RateLimitPolicy {
    core: Arc<RwLock<RateLimitCore>>,
}

#[pymethods]
impl RateLimitPolicy {
    #[new]
    #[pyo3(signature = (rate, capacity))]
    fn new(rate: f64, capacity: u64) -> PyResult<Self> {
        RateLimitCore::new(rate, capacity)
            .map(|core| Self {
                core: Arc::new(RwLock::new(core)),
            })
            .ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err("rate must be > 0 and capacity must be > 0")
            })
    }

    fn __call__(
        &self,
        py: Python,
        func: Py<PyAny>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        if !self.core.write().try_acquire() {
            return Err(pyo3::exceptions::PyResourceWarning::new_err(
                "Rate limit exceeded",
            ));
        }

        func.call(py, args, kwargs)
    }

    #[getter]
    fn rate(&self) -> f64 {
        self.core.read().rate()
    }

    #[getter]
    fn capacity(&self) -> u64 {
        self.core.read().capacity()
    }

    #[getter]
    fn available_tokens(&self) -> f64 {
        self.core.read().available_tokens()
    }

    fn __repr__(&self) -> String {
        let guard = self.core.read();
        format!(
            "RateLimitPolicy(rate={}/s, capacity={}, available={:.2})",
            guard.rate(),
            guard.capacity(),
            guard.available_tokens()
        )
    }
}
