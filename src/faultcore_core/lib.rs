mod circuit_breaker;
mod context;
pub mod network;
mod network_queue;
mod policies;
mod rate_limit;
mod registry;
mod retry;
mod shm;
mod timeout;

mod feature_flag;
pub use feature_flag::FeatureFlagManager;

pub use circuit_breaker::{CircuitBreakerPolicy as CircuitBreakerCore, CircuitState};
pub use network_queue::{NetworkQueueCore as NetworkQueueCoreInner, QueueError, QueueStats};
pub use rate_limit::RateLimitPolicy as RateLimitCore;
pub use retry::{ErrorClass, RetryPolicy as RetryCore};
pub use timeout::TimeoutPolicy as TimeoutCore;

pub use context::ContextManager;
pub use policies::{
    CircuitBreakerPolicy, FallbackPolicy, NetworkQueuePolicy, RateLimitPolicy, RetryPolicy,
    TimeoutPolicy,
};

pub use registry::PolicyRegistry;

use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;

#[pyfunction]
fn classify_exception(exc: &Bound<'_, PyAny>) -> String {
    let exc_type = exc.get_type();
    let name = match exc_type.name() {
        Ok(n) => n,
        Err(_) => return "Transient".to_string(),
    };

    let name_lower = name.to_cow().unwrap_or_default().to_lowercase();

    if name_lower.contains("timeout") || name_lower.contains("timedout") {
        return "Timeout".to_string();
    }
    if name_lower.contains("rate")
        && (name_lower.contains("limit") || name_lower.contains("throttle"))
    {
        return "RateLimit".to_string();
    }
    if name_lower.contains("connection")
        || name_lower.contains("network")
        || name_lower.contains("remote")
        || name_lower.contains("disconnected")
        || name_lower.contains("protocol")
    {
        return "Network".to_string();
    }
    if name_lower.contains("transient") {
        return "Transient".to_string();
    }

    "Transient".to_string()
}

#[pyfunction]
fn add_keys(keys: Vec<String>) {
    context::add_context_keys(keys);
}

#[pyfunction]
fn get_keys() -> Vec<String> {
    context::get_context_keys()
}

#[pyfunction]
fn remove_key(key: String) -> bool {
    context::remove_context_key(&key)
}

#[pyfunction]
fn clear_keys() {
    context::clear_context_keys();
}

#[pyfunction]
fn get_feature_flag_manager(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let manager = feature_flag::get_feature_flag_manager();
    manager.clone().into_py_any(py)
}

#[pymodule]
fn _faultcore(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(classify_exception, m)?)?;
    m.add_function(wrap_pyfunction!(add_keys, m)?)?;
    m.add_function(wrap_pyfunction!(get_keys, m)?)?;
    m.add_function(wrap_pyfunction!(remove_key, m)?)?;
    m.add_function(wrap_pyfunction!(clear_keys, m)?)?;
    m.add_function(wrap_pyfunction!(get_feature_flag_manager, m)?)?;

    m.add_class::<TimeoutPolicy>()?;
    m.add_class::<RetryPolicy>()?;
    m.add_class::<FallbackPolicy>()?;
    m.add_class::<CircuitBreakerPolicy>()?;
    m.add_class::<RateLimitPolicy>()?;
    m.add_class::<NetworkQueuePolicy>()?;
    m.add_class::<ContextManager>()?;
    m.add_class::<feature_flag::FeatureFlagManager>()?;
    m.add_class::<registry::PolicyRegistry>()?;

    Ok(())
}
