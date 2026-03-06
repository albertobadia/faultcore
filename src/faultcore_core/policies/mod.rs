pub mod rate_limit;
pub mod timeout;

use std::sync::Arc;

use parking_lot::RwLock;

use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

use crate::network::queue::{
    NetworkQueueConfig, NetworkQueueCore as NetworkQueueCoreInner, QueueError, QueueStrategy,
};
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
        py: Python,
        func: Py<PyAny>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let timeout_ms = self.core.timeout_ms();

        if !shm::is_shm_open() {
            let pid = unsafe { libc::getpid() } as u32;
            let _ = shm::create_shm(pid);
        }

        if shm::is_shm_open() {
            let tid = shm::get_thread_id();
            let _ = shm::write_timeouts(tid, timeout_ms, timeout_ms);
            let result = func.call(py, args, kwargs);
            let _ = shm::clear_config(tid);
            result
        } else {
            func.call(py, args, kwargs)
        }
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
        py: Python,
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
                    for (key, value) in kwargs.iter() {
                        fallback_kwargs.set_item(key, value)?;
                    }
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

#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct NetworkQueuePolicy {
    core: NetworkQueueCoreInner,
}

#[pymethods]
impl NetworkQueuePolicy {
    #[new]
    #[pyo3(signature = (rate, capacity, max_queue_size=1000, packet_loss=0.0, latency_ms=0, strategy="wait", fd_limit=1024))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        rate: Bound<'_, PyAny>,
        capacity: Bound<'_, PyAny>,
        max_queue_size: u64,
        packet_loss: f64,
        latency_ms: u64,
        strategy: &str,
        fd_limit: u64,
    ) -> PyResult<Self> {
        let rate_val = if let Ok(s) = rate.extract::<String>() {
            crate::network::queue::parse_rate(&s).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("Invalid rate format: {}", s))
            })?
        } else {
            rate.extract::<f64>()?
        };

        let cap_val = if let Ok(s) = capacity.extract::<String>() {
            crate::network::queue::parse_size(&s).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("Invalid capacity format: {}", s))
            })?
        } else {
            capacity.extract::<u64>()?
        };

        let strategy = match strategy.to_lowercase().as_str() {
            "reject" => QueueStrategy::Reject,
            _ => QueueStrategy::Wait,
        };

        let config = NetworkQueueConfig::new(
            rate_val,
            cap_val,
            max_queue_size,
            latency_ms,
            latency_ms,
            packet_loss,
            strategy.clone(),
        )
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "Invalid config! Rate: {}, Packet Loss: {}, strategy: {:?}",
                rate_val, packet_loss, strategy
            ))
        })?;

        NetworkQueueCoreInner::new(config, fd_limit)
            .map(|core| Self { core })
            .ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err("Failed to create network queue")
            })
    }

    fn __call__(
        &self,
        py: Python,
        func: Py<PyAny>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let core = &self.core;

        if core.config.strategy == QueueStrategy::Wait {
            while !core.try_acquire() {
                std::thread::sleep(std::time::Duration::from_millis(10));
            }
        } else if !core.try_acquire() {
            return Err(pyo3::exceptions::PyResourceWarning::new_err(
                "Network rate limit exceeded",
            ));
        }

        let ticket = core.enqueue();

        match ticket {
            Ok(ticket) => {
                let result = func.call(py, args, kwargs);
                ticket.wait_and_release();
                result
            }
            Err(QueueError::QueueFull) => Err(pyo3::exceptions::PyResourceWarning::new_err(
                "Network queue is full",
            )),
            Err(QueueError::FdLimitExceeded) => Err(pyo3::exceptions::PyResourceWarning::new_err(
                "File descriptor limit exceeded",
            )),
            Err(QueueError::PacketDropped) => Err(pyo3::exceptions::PyConnectionError::new_err(
                "Packet dropped by network simulation",
            )),
            Err(QueueError::Timeout) => Err(pyo3::exceptions::PyTimeoutError::new_err(
                "Queue operation timed out",
            )),
            Err(QueueError::ShmWriteFailed) => Err(pyo3::exceptions::PyIOError::new_err(
                "Failed to write to shared memory",
            )),
        }
    }

    #[getter]
    fn rate(&self) -> f64 {
        self.core.rate()
    }

    #[getter]
    fn capacity(&self) -> u64 {
        self.core.capacity()
    }

    #[getter]
    fn available_tokens(&self) -> f64 {
        self.core.available_tokens()
    }

    #[getter]
    fn queue_size(&self) -> u64 {
        self.core.queue_size()
    }

    fn get_stats(&self) -> Py<PyAny> {
        let stats = self.core.stats();
        Python::attach(|py| {
            let dict = pyo3::types::PyDict::new(py);
            dict.set_item("enqueued", stats.enqueued).unwrap();
            dict.set_item("dequeued", stats.dequeued).unwrap();
            dict.set_item("rejected", stats.rejected).unwrap();
            dict.set_item("dropped", stats.dropped).unwrap();
            dict.set_item("current_queue_size", stats.current_queue_size)
                .unwrap();
            dict.into_py_any(py).unwrap()
        })
    }

    fn _enter_thread_context(&self) {
        let latency_ms = self.core.config.latency_min_ms;
        let packet_loss_ppm = (self.core.config.packet_loss_rate * 1_000_000.0) as u64;
        let bandwidth_bps = self.core.config.rate as u64;

        if !shm::is_shm_open() {
            let pid = unsafe { libc::getpid() } as u32;
            let _ = shm::create_shm(pid);
        }
        let tid = shm::get_thread_id();
        let _ = shm::write_latency(tid, latency_ms);
        let _ = shm::write_packet_loss(tid, packet_loss_ppm);
        let _ = shm::write_bandwidth(tid, bandwidth_bps);
    }

    fn _exit_thread_context(&self) {
        let tid = shm::get_thread_id();
        let _ = shm::clear_config(tid);
    }

    fn _get_latency_ms(&self) -> u64 {
        self.core.config.latency_min_ms
    }

    fn _get_rate(&self) -> f64 {
        self.core.config.rate
    }

    fn _get_packet_loss(&self) -> f64 {
        self.core.config.packet_loss_rate
    }

    fn _prepare_async_ticket(&self) -> PyResult<Py<PyAny>> {
        let core = &self.core;

        if core.config.strategy == QueueStrategy::Wait {
            while !core.try_acquire() {
                std::thread::sleep(std::time::Duration::from_millis(10));
            }
        } else if !core.try_acquire() {
            return Err(pyo3::exceptions::PyResourceWarning::new_err(
                "Network rate limit exceeded",
            ));
        }

        let ticket = core.enqueue();

        match ticket {
            Ok(ticket) => Ok(Python::attach(|py| {
                let dict = pyo3::types::PyDict::new(py);
                dict.set_item("latency_ms", ticket.latency_ms).unwrap();
                dict.set_item("rate", ticket.rate).unwrap();
                dict.set_item("strategy", format!("{:?}", ticket.strategy))
                    .unwrap();
                dict.into_py_any(py).unwrap()
            })),
            Err(QueueError::QueueFull) => Err(pyo3::exceptions::PyResourceWarning::new_err(
                "Network queue is full",
            )),
            Err(QueueError::FdLimitExceeded) => Err(pyo3::exceptions::PyResourceWarning::new_err(
                "File descriptor limit exceeded",
            )),
            Err(QueueError::PacketDropped) => Err(pyo3::exceptions::PyConnectionError::new_err(
                "Packet dropped by network simulation",
            )),
            Err(QueueError::Timeout) => Err(pyo3::exceptions::PyTimeoutError::new_err(
                "Queue operation timed out",
            )),
            Err(QueueError::ShmWriteFailed) => Err(pyo3::exceptions::PyIOError::new_err(
                "Failed to write to shared memory",
            )),
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "NetworkQueuePolicy(rate={}/s, capacity={}, queue_size={})",
            self.core.rate(),
            self.core.capacity(),
            self.core.max_queue_size()
        )
    }
}
