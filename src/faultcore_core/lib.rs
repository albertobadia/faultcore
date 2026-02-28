mod circuit_breaker;
mod context;
mod policies;
mod rate_limit;
mod retry;
mod timeout;

pub use circuit_breaker::{CircuitBreakerPolicy as CircuitBreakerCore, CircuitState};
pub use rate_limit::RateLimitPolicy as RateLimitCore;
pub use retry::{ErrorClass, RetryPolicy as RetryCore};
pub use timeout::TimeoutPolicy as TimeoutCore;

pub use context::ContextManager;
pub use policies::{
    CircuitBreakerPolicy, FallbackPolicy, RateLimitPolicy, RetryPolicy, TimeoutPolicy,
};

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

#[pymodule]
fn _faultcore(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(classify_exception, m)?)?;
    m.add_function(wrap_pyfunction!(add_keys, m)?)?;
    m.add_function(wrap_pyfunction!(get_keys, m)?)?;
    m.add_function(wrap_pyfunction!(remove_key, m)?)?;
    m.add_function(wrap_pyfunction!(clear_keys, m)?)?;

    m.add_class::<TimeoutPolicy>()?;
    m.add_class::<RetryPolicy>()?;
    m.add_class::<FallbackPolicy>()?;
    m.add_class::<CircuitBreakerPolicy>()?;
    m.add_class::<RateLimitPolicy>()?;
    m.add_class::<ContextManager>()?;

    Ok(())
}
