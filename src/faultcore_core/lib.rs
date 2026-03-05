pub mod features;
pub mod network;
pub mod policies;
pub mod registry;
pub mod system;

pub use features::flag::FeatureFlagManager;
pub use network::queue::{NetworkQueueCore as NetworkQueueCoreInner, QueueError, QueueStats};
pub use policies::circuit_breaker::{CircuitBreakerPolicy as CircuitBreakerCore, CircuitState};
pub use policies::rate_limit::RateLimitPolicy as RateLimitCore;
pub use policies::retry::{ErrorClass, RetryPolicy as RetryCore};
pub use policies::timeout::TimeoutPolicy as TimeoutCore;

pub use policies::{
    CircuitBreakerPolicy, FallbackPolicy, NetworkQueuePolicy, RateLimitPolicy, RetryPolicy,
    TimeoutPolicy,
};

pub use registry::PolicyRegistry;
pub use system::context::ContextManager;

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
    system::context::add_context_keys(keys);
}

#[pyfunction]
fn get_keys() -> Vec<String> {
    system::context::get_context_keys()
}

#[pyfunction]
fn remove_key(key: String) -> bool {
    system::context::remove_context_key(&key)
}

#[pyfunction]
fn clear_keys() {
    system::context::clear_context_keys();
}

#[pyfunction]
fn get_feature_flag_manager(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let manager = features::flag::get_feature_flag_manager();
    manager.clone().into_py_any(py)
}

#[pyfunction]
fn get_policy_registry(py: Python<'_>) -> PyResult<Py<registry::PolicyRegistry>> {
    let registry = crate::registry::get_policy_registry();
    Py::new(py, (*registry).clone())
}

#[pyfunction]
fn set_thread_policy(name: Option<String>) {
    registry::get_policy_registry()._set_thread_policy(name);
}

#[pymodule]
fn _faultcore(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(classify_exception, m)?)?;
    m.add_function(wrap_pyfunction!(add_keys, m)?)?;
    m.add_function(wrap_pyfunction!(get_keys, m)?)?;
    m.add_function(wrap_pyfunction!(remove_key, m)?)?;
    m.add_function(wrap_pyfunction!(clear_keys, m)?)?;
    m.add_function(wrap_pyfunction!(get_feature_flag_manager, m)?)?;
    m.add_function(wrap_pyfunction!(get_policy_registry, m)?)?;
    m.add_function(wrap_pyfunction!(set_thread_policy, m)?)?;

    m.add_class::<TimeoutPolicy>()?;
    m.add_class::<RetryPolicy>()?;
    m.add_class::<FallbackPolicy>()?;
    m.add_class::<CircuitBreakerPolicy>()?;
    m.add_class::<RateLimitPolicy>()?;
    m.add_class::<NetworkQueuePolicy>()?;
    m.add_class::<ContextManager>()?;
    m.add_class::<features::flag::FeatureFlagManager>()?;
    m.add_class::<registry::PolicyRegistry>()?;
    m.add_class::<registry::context::CallContext>()?;

    Ok(())
}
