use log::{error, warn};
use pyo3::prelude::*;

#[pyclass]
pub struct ContextManager;

#[pymethods]
impl ContextManager {
    #[staticmethod]
    fn get_keys(py: Python<'_>) -> Vec<String> {
        let faultcore = match py.import("faultcore") {
            Ok(m) => m,
            Err(e) => {
                error!("Failed to import faultcore module: {}", e);
                return Vec::new();
            }
        };
        let var = match faultcore.getattr("_FAULTCORE_CONTEXT_KEYS") {
            Ok(v) => v,
            Err(e) => {
                error!("Failed to get _FAULTCORE_CONTEXT_KEYS: {}", e);
                return Vec::new();
            }
        };
        match var.call_method0("get") {
            Ok(r) => {
                let val: Option<Vec<String>> = r.extract().unwrap_or_default();
                val.unwrap_or_default()
            }
            Err(e) => {
                error!("Failed to call get() on context keys: {}", e);
                Vec::new()
            }
        }
    }

    #[staticmethod]
    fn add_keys(py: Python<'_>, keys: Vec<String>) {
        let faultcore = match py.import("faultcore") {
            Ok(m) => m,
            Err(e) => {
                error!("Failed to import faultcore module: {}", e);
                return;
            }
        };
        let var = match faultcore.getattr("_FAULTCORE_CONTEXT_KEYS") {
            Ok(v) => v,
            Err(e) => {
                error!("Failed to get _FAULTCORE_CONTEXT_KEYS: {}", e);
                return;
            }
        };
        let current: Option<Vec<String>> = match var.call_method0("get") {
            Ok(r) => r.extract().unwrap_or_default(),
            Err(e) => {
                warn!("Failed to get current context keys: {}", e);
                None
            }
        };
        let mut all_keys: std::collections::HashSet<String> =
            current.unwrap_or_default().into_iter().collect();
        for key in keys {
            all_keys.insert(key);
        }
        let new_keys: Vec<String> = all_keys.into_iter().collect();
        if let Err(e) = var.call_method1("set", (Some(new_keys),)) {
            error!("Failed to set context keys: {}", e);
        }
    }

    #[staticmethod]
    fn remove_key(py: Python<'_>, key: String) -> bool {
        let faultcore = match py.import("faultcore") {
            Ok(m) => m,
            Err(e) => {
                error!("Failed to import faultcore module: {}", e);
                return false;
            }
        };
        let var = match faultcore.getattr("_FAULTCORE_CONTEXT_KEYS") {
            Ok(v) => v,
            Err(e) => {
                error!("Failed to get _FAULTCORE_CONTEXT_KEYS: {}", e);
                return false;
            }
        };
        let current: Option<Vec<String>> = match var.call_method0("get") {
            Ok(r) => r.extract().unwrap_or_default(),
            Err(e) => {
                error!("Failed to get current context keys: {}", e);
                return false;
            }
        };
        let mut keys_set: std::collections::HashSet<String> =
            current.unwrap_or_default().into_iter().collect();
        let removed = keys_set.remove(&key);
        if removed {
            let new_keys: Vec<String> = keys_set.into_iter().collect();
            if let Err(e) = var.call_method1("set", (Some(new_keys),)) {
                error!("Failed to set context keys after removal: {}", e);
            }
        }
        removed
    }

    #[staticmethod]
    fn clear_keys(py: Python<'_>) {
        let faultcore = match py.import("faultcore") {
            Ok(m) => m,
            Err(e) => {
                error!("Failed to import faultcore module: {}", e);
                return;
            }
        };
        let var = match faultcore.getattr("_FAULTCORE_CONTEXT_KEYS") {
            Ok(v) => v,
            Err(e) => {
                error!("Failed to get _FAULTCORE_CONTEXT_KEYS: {}", e);
                return;
            }
        };
        if let Err(e) = var.call_method1("set", (None::<Vec<String>>,)) {
            error!("Failed to clear context keys: {}", e);
        }
    }

    #[staticmethod]
    fn has_key(py: Python<'_>, key: String) -> bool {
        Self::get_keys(py).contains(&key)
    }
}

pub fn get_context_keys() -> Vec<String> {
    Python::attach(ContextManager::get_keys)
}

pub fn add_context_keys(keys: Vec<String>) {
    Python::attach(|py| ContextManager::add_keys(py, keys))
}

pub fn remove_context_key(key: &str) -> bool {
    Python::attach(|py| ContextManager::remove_key(py, key.to_string()))
}

pub fn clear_context_keys() {
    Python::attach(ContextManager::clear_keys)
}
