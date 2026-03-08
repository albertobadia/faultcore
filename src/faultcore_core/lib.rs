pub mod features;
pub mod policies;
pub mod registry;
pub mod system;

pub use features::flag::FeatureFlagManager;
pub use policies::rate_limit::RateLimitPolicy as RateLimitCore;
pub use policies::timeout::TimeoutPolicy as TimeoutCore;

pub use policies::{FallbackPolicy, RateLimitPolicy, TimeoutPolicy};

pub use registry::PolicyRegistry;
pub use system::context::ContextManager;

use log::LevelFilter;
use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;

#[pyfunction]
fn classify_exception(exc: &Bound<'_, PyAny>) -> String {
    let name = exc
        .get_type()
        .name()
        .map(|n| n.to_string())
        .unwrap_or_else(|_| "Transient".into());
    let name_lower = name.to_lowercase();

    match name_lower.as_str() {
        n if n.contains("timeout") || n.contains("timedout") => "Timeout".into(),
        n if n.contains("rate") && (n.contains("limit") || n.contains("throttle")) => {
            "RateLimit".into()
        }
        n if [
            "connection",
            "network",
            "remote",
            "disconnected",
            "protocol",
        ]
        .iter()
        .any(|&s| n.contains(s)) =>
        {
            "Network".into()
        }
        _ => "Transient".into(),
    }
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
    env_logger::Builder::new()
        .filter_level(LevelFilter::Warn)
        .init();

    m.add_function(wrap_pyfunction!(classify_exception, m)?)?;
    m.add_function(wrap_pyfunction!(add_keys, m)?)?;
    m.add_function(wrap_pyfunction!(get_keys, m)?)?;
    m.add_function(wrap_pyfunction!(remove_key, m)?)?;
    m.add_function(wrap_pyfunction!(clear_keys, m)?)?;
    m.add_function(wrap_pyfunction!(get_feature_flag_manager, m)?)?;
    m.add_function(wrap_pyfunction!(get_policy_registry, m)?)?;
    m.add_function(wrap_pyfunction!(set_thread_policy, m)?)?;

    m.add_class::<TimeoutPolicy>()?;
    m.add_class::<FallbackPolicy>()?;
    m.add_class::<RateLimitPolicy>()?;
    m.add_class::<ContextManager>()?;
    m.add_class::<features::flag::FeatureFlagManager>()?;
    m.add_class::<registry::PolicyRegistry>()?;
    m.add_class::<registry::context::CallContext>()?;

    Ok(())
}
