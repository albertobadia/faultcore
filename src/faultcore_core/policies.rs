use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use std::time::Instant;

use crate::circuit_breaker::{CircuitBreakerPolicy as CircuitBreakerCore, CircuitState};
use crate::network_queue::{
    NetworkQueueConfig, NetworkQueueCore as NetworkQueueCoreInner, QueueError, QueueStrategy,
};
use crate::rate_limit::RateLimitPolicy as RateLimitCore;
use crate::retry::{ErrorClass, RetryPolicy as RetryCore};
use crate::timeout::TimeoutPolicy as TimeoutCore;

#[pyclass]
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
        let start = Instant::now();
        let result = func.call(py, args, kwargs)?;

        if self.core.is_expired(start) {
            return Err(pyo3::exceptions::PyTimeoutError::new_err(format!(
                "Operation timed out after {}ms",
                self.core.timeout_ms()
            )));
        }

        Ok(result)
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
#[derive(Clone)]
pub struct RetryPolicy {
    core: RetryCore,
}

#[pymethods]
impl RetryPolicy {
    #[new]
    #[pyo3(signature = (max_retries, backoff_ms=100, retry_on=None))]
    fn new(max_retries: u32, backoff_ms: u64, retry_on: Option<Vec<String>>) -> Self {
        Self {
            core: RetryCore::new(max_retries, backoff_ms, retry_on),
        }
    }

    fn __call__(
        &self,
        py: Python,
        func: Py<PyAny>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        for attempt in 0..=self.core.max_retries {
            let result = func.call(py, args, kwargs);

            match result {
                Ok(value) => return Ok(value),
                Err(e) => {
                    let error_val = e.value(py);
                    let error_class = classify_exception(error_val.as_any());

                    if !self.core.should_retry(&error_class) || attempt == self.core.max_retries {
                        return Err(e);
                    }

                    if attempt < self.core.max_retries {
                        std::thread::sleep(self.core.backoff_duration(attempt));
                    }
                }
            }
        }

        Err(pyo3::exceptions::PyRuntimeError::new_err("Retry exhausted"))
    }

    #[getter]
    fn max_retries(&self) -> u32 {
        self.core.max_retries
    }

    #[getter]
    fn backoff_ms(&self) -> u64 {
        self.core.backoff.as_millis() as u64
    }

    fn __repr__(&self) -> String {
        format!(
            "RetryPolicy(max_retries={}, backoff_ms={})",
            self.core.max_retries,
            self.core.backoff.as_millis()
        )
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
            Err(_) => self.fallback.call(py, args, kwargs),
        }
    }

    fn __repr__(&self) -> String {
        "FallbackPolicy(...)".to_string()
    }
}

#[pyclass]
#[derive(Clone)]
#[allow(dead_code)]
pub struct CircuitBreakerPolicy {
    core: CircuitBreakerCore,
}

#[pymethods]
impl CircuitBreakerPolicy {
    #[new]
    #[pyo3(signature = (failure_threshold=5, success_threshold=2, timeout_ms=30000))]
    fn new(failure_threshold: u32, success_threshold: u32, timeout_ms: u64) -> Self {
        Self {
            core: CircuitBreakerCore::new(failure_threshold, success_threshold, timeout_ms),
        }
    }

    fn __call__(
        &mut self,
        py: Python,
        func: Py<PyAny>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        if self.core.is_open() && !self.core.can_attempt() {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Circuit breaker is OPEN",
            ));
        }

        let result = func.call(py, args, kwargs);

        match result {
            Ok(value) => {
                self.core.record_success();
                Ok(value)
            }
            Err(e) => {
                self.core.record_failure();
                Err(e)
            }
        }
    }

    #[getter]
    fn state(&self) -> String {
        match self.core.state() {
            CircuitState::Closed => "closed".to_string(),
            CircuitState::Open => "open".to_string(),
            CircuitState::HalfOpen => "half_open".to_string(),
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "CircuitBreakerPolicy(state={:?}, failures={}/{})",
            self.core.state(),
            self.core.failure_count,
            self.core.failure_threshold
        )
    }
}

#[pyclass]
#[derive(Clone)]
pub struct RateLimitPolicy {
    core: RateLimitCore,
}

#[pymethods]
impl RateLimitPolicy {
    #[new]
    #[pyo3(signature = (rate, capacity))]
    fn new(rate: f64, capacity: u64) -> PyResult<Self> {
        RateLimitCore::new(rate, capacity)
            .map(|core| Self { core })
            .ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err("rate must be > 0 and capacity must be > 0")
            })
    }

    fn __call__(
        &mut self,
        py: Python,
        func: Py<PyAny>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        if !self.core.try_acquire() {
            return Err(pyo3::exceptions::PyResourceWarning::new_err(
                "Rate limit exceeded",
            ));
        }

        func.call(py, args, kwargs)
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

    fn __repr__(&self) -> String {
        format!(
            "RateLimitPolicy(rate={}/s, capacity={}, available={:.2})",
            self.core.rate(),
            self.core.capacity(),
            self.core.available_tokens()
        )
    }
}

#[pyclass]
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
            crate::network_queue::parse_rate(&s).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("Invalid rate format: {}", s))
            })?
        } else {
            rate.extract::<f64>()?
        };

        let cap_val = if let Ok(s) = capacity.extract::<String>() {
            crate::network_queue::parse_size(&s).ok_or_else(|| {
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

    #[allow(clippy::collapsible_else_if)]
    fn __call__(
        &self,
        py: Python,
        func: Py<PyAny>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Py<PyAny>> {
        let core = self.core.clone();

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

    #[allow(deprecated)]
    fn get_stats(&self) -> Py<PyAny> {
        let stats = self.core.stats();
        Python::with_gil(|py| {
            let dict = pyo3::types::PyDict::new(py);
            dict.set_item("enqueued", stats.enqueued).unwrap();
            dict.set_item("dequeued", stats.dequeued).unwrap();
            dict.set_item("rejected", stats.rejected).unwrap();
            dict.set_item("dropped", stats.dropped).unwrap();
            dict.set_item("current_queue_size", stats.current_queue_size)
                .unwrap();
            dict.into()
        })
    }

    fn _enter_thread_context(&self) {
        let loss_encoded = (self.core.config.packet_loss_rate * 1000000.0) as i32;
        let latency = self.core.config.latency_min_ms as u32;
        let rate = self.core.config.rate as i32;
        unsafe {
            libc::setpriority(0xFA, latency, loss_encoded);
            libc::setpriority(0xFB, u32::MAX, rate);
        }
    }

    fn _exit_thread_context(&self) {
        unsafe {
            libc::setpriority(0xFA, 0, 0);
            libc::setpriority(0xFB, 0, 0);
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

fn classify_exception(exc: &Bound<'_, PyAny>) -> ErrorClass {
    let exc_type = exc.get_type();
    let name = match exc_type.name() {
        Ok(n) => n,
        Err(_) => return ErrorClass::Transient,
    };

    let name_lower = name.to_cow().unwrap_or_default().to_lowercase();

    if name_lower.contains("timeout") || name_lower.contains("timedout") {
        return ErrorClass::Timeout;
    }
    if name_lower.contains("rate")
        && (name_lower.contains("limit") || name_lower.contains("throttle"))
    {
        return ErrorClass::RateLimit;
    }
    if name_lower.contains("connection")
        || name_lower.contains("network")
        || name_lower.contains("remote")
        || name_lower.contains("disconnected")
        || name_lower.contains("protocol")
    {
        return ErrorClass::Network;
    }
    if name_lower.contains("transient") {
        return ErrorClass::Transient;
    }

    ErrorClass::Transient
}
