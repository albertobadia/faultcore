use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;

#[derive(Clone)]
pub struct PolicyBundle {
    pub timeout_ms: Option<u64>,
    pub retry_max_retries: Option<u32>,
    pub retry_backoff_ms: Option<u64>,
    pub retry_on: Option<Vec<String>>,
    pub circuit_breaker_failure_threshold: Option<u32>,
    pub circuit_breaker_success_threshold: Option<u32>,
    pub circuit_breaker_timeout_ms: Option<u64>,
    pub rate_limit_rate: Option<f64>,
    pub rate_limit_capacity: Option<u64>,
    pub enabled: Arc<AtomicBool>,
}

impl PolicyBundle {
    fn is_enabled(&self) -> bool {
        self.enabled.load(Ordering::SeqCst)
    }

    fn set_enabled(&self, enabled: bool) {
        self.enabled.store(enabled, Ordering::SeqCst);
    }
}

#[pyclass]
pub struct FeatureFlagManager {
    bundles: Mutex<std::collections::HashMap<String, PolicyBundle>>,
}

impl Clone for FeatureFlagManager {
    fn clone(&self) -> Self {
        Self {
            bundles: Mutex::new(std::collections::HashMap::new()),
        }
    }
}

impl FeatureFlagManager {
    fn new() -> Self {
        Self {
            bundles: Mutex::new(std::collections::HashMap::new()),
        }
    }
}

#[pymethods]
impl FeatureFlagManager {
    #[new]
    fn new_() -> PyResult<Self> {
        Ok(Self::new())
    }

    #[allow(clippy::too_many_arguments)]
    fn register(
        &self,
        key: String,
        timeout_ms: Option<u64>,
        retry_max_retries: Option<u32>,
        retry_backoff_ms: Option<u64>,
        retry_on: Option<Vec<String>>,
        circuit_breaker_failure_threshold: Option<u32>,
        circuit_breaker_success_threshold: Option<u32>,
        circuit_breaker_timeout_ms: Option<u64>,
        rate_limit_rate: Option<f64>,
        rate_limit_capacity: Option<u64>,
    ) -> PyResult<()> {
        let mut bundles = self
            .bundles
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        let bundle = PolicyBundle {
            timeout_ms,
            retry_max_retries,
            retry_backoff_ms,
            retry_on,
            circuit_breaker_failure_threshold,
            circuit_breaker_success_threshold,
            circuit_breaker_timeout_ms,
            rate_limit_rate,
            rate_limit_capacity,
            enabled: Arc::new(AtomicBool::new(true)),
        };

        bundles.insert(key, bundle);
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    fn update(
        &self,
        key: String,
        timeout_ms: Option<u64>,
        retry_max_retries: Option<u32>,
        retry_backoff_ms: Option<u64>,
        retry_on: Option<Vec<String>>,
        circuit_breaker_failure_threshold: Option<u32>,
        circuit_breaker_success_threshold: Option<u32>,
        circuit_breaker_timeout_ms: Option<u64>,
        rate_limit_rate: Option<f64>,
        rate_limit_capacity: Option<u64>,
    ) -> PyResult<bool> {
        let mut bundles = self
            .bundles
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        if let Some(bundle) = bundles.get_mut(&key) {
            if let Some(v) = timeout_ms {
                bundle.timeout_ms = Some(v);
            }
            if let Some(v) = retry_max_retries {
                bundle.retry_max_retries = Some(v);
            }
            if let Some(v) = retry_backoff_ms {
                bundle.retry_backoff_ms = Some(v);
            }
            if let Some(v) = retry_on {
                bundle.retry_on = Some(v);
            }
            if let Some(v) = circuit_breaker_failure_threshold {
                bundle.circuit_breaker_failure_threshold = Some(v);
            }
            if let Some(v) = circuit_breaker_success_threshold {
                bundle.circuit_breaker_success_threshold = Some(v);
            }
            if let Some(v) = circuit_breaker_timeout_ms {
                bundle.circuit_breaker_timeout_ms = Some(v);
            }
            if let Some(v) = rate_limit_rate {
                bundle.rate_limit_rate = Some(v);
            }
            if let Some(v) = rate_limit_capacity {
                bundle.rate_limit_capacity = Some(v);
            }
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn enable(&self, key: String) -> PyResult<bool> {
        let bundles = self
            .bundles
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;
        if let Some(bundle) = bundles.get(&key) {
            bundle.set_enabled(true);
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn disable(&self, key: String) -> PyResult<bool> {
        let bundles = self
            .bundles
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;
        if let Some(bundle) = bundles.get(&key) {
            bundle.set_enabled(false);
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn is_enabled(&self, key: String) -> PyResult<bool> {
        let bundles = self
            .bundles
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;
        if let Some(bundle) = bundles.get(&key) {
            Ok(bundle.is_enabled())
        } else {
            Ok(false)
        }
    }

    fn get(&self, key: String) -> PyResult<Option<Py<PyAny>>> {
        let bundles = self
            .bundles
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        if let Some(bundle) = bundles.get(&key) {
            let dict: Py<PyAny> = Python::attach(|py| {
                let dict = pyo3::types::PyDict::new(py);
                if let Some(v) = bundle.timeout_ms {
                    dict.set_item("timeout_ms", v).unwrap();
                }
                if let Some(v) = bundle.retry_max_retries {
                    dict.set_item("retry_max_retries", v).unwrap();
                }
                if let Some(v) = bundle.retry_backoff_ms {
                    dict.set_item("retry_backoff_ms", v).unwrap();
                }
                if let Some(ref v) = bundle.retry_on {
                    dict.set_item("retry_on", v.clone()).unwrap();
                }
                if let Some(v) = bundle.circuit_breaker_failure_threshold {
                    dict.set_item("circuit_breaker_failure_threshold", v)
                        .unwrap();
                }
                if let Some(v) = bundle.circuit_breaker_success_threshold {
                    dict.set_item("circuit_breaker_success_threshold", v)
                        .unwrap();
                }
                if let Some(v) = bundle.circuit_breaker_timeout_ms {
                    dict.set_item("circuit_breaker_timeout_ms", v).unwrap();
                }
                if let Some(v) = bundle.rate_limit_rate {
                    dict.set_item("rate_limit_rate", v).unwrap();
                }
                if let Some(v) = bundle.rate_limit_capacity {
                    dict.set_item("rate_limit_capacity", v).unwrap();
                }
                dict.set_item("enabled", bundle.is_enabled()).unwrap();
                dict.into_py_any(py).unwrap()
            });
            Ok(Some(dict))
        } else {
            Ok(None)
        }
    }

    fn list_keys(&self) -> PyResult<Vec<String>> {
        let bundles = self
            .bundles
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;
        Ok(bundles.keys().cloned().collect())
    }

    fn remove(&self, key: String) -> PyResult<bool> {
        let mut bundles = self
            .bundles
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;
        Ok(bundles.remove(&key).is_some())
    }

    fn clear(&self) -> PyResult<()> {
        let mut bundles = self
            .bundles
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;
        bundles.clear();
        Ok(())
    }

    fn __repr__(&self) -> String {
        "FeatureFlagManager(...)".to_string()
    }
}

static FEATURE_FLAG_MANAGER: std::sync::OnceLock<FeatureFlagManager> = std::sync::OnceLock::new();

pub fn get_feature_flag_manager() -> &'static FeatureFlagManager {
    FEATURE_FLAG_MANAGER.get_or_init(FeatureFlagManager::new)
}
