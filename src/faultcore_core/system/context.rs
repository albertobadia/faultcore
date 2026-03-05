#![allow(clippy::collapsible_if)]
#![allow(clippy::redundant_closure)]

use pyo3::prelude::*;

#[pyclass]
pub struct ContextManager;

#[pymethods]
impl ContextManager {
    #[staticmethod]
    fn get_keys(py: Python<'_>) -> Vec<String> {
        let faultcore = match py.import("faultcore") {
            Ok(m) => m,
            Err(_) => return Vec::new(),
        };
        let var = match faultcore.getattr("_FAULTCORE_CONTEXT_KEYS") {
            Ok(v) => v,
            Err(_) => return Vec::new(),
        };
        match var.call_method0("get") {
            Ok(r) => {
                let val: Option<Vec<String>> = r.extract().unwrap_or_default();
                val.unwrap_or_default()
            }
            Err(_) => Vec::new(),
        }
    }

    #[staticmethod]
    fn add_keys(py: Python<'_>, keys: Vec<String>) {
        let faultcore = match py.import("faultcore") {
            Ok(m) => m,
            Err(_) => return,
        };
        let var = match faultcore.getattr("_FAULTCORE_CONTEXT_KEYS") {
            Ok(v) => v,
            Err(_) => return,
        };
        let current: Option<Vec<String>> = match var.call_method0("get") {
            Ok(r) => r.extract().unwrap_or_default(),
            Err(_) => None,
        };
        let mut all_keys: std::collections::HashSet<String> =
            current.unwrap_or_default().into_iter().collect();
        for key in keys {
            all_keys.insert(key);
        }
        let new_keys: Vec<String> = all_keys.into_iter().collect();
        let _ = var.call_method1("set", (Some(new_keys),));
    }

    #[staticmethod]
    fn remove_key(py: Python<'_>, key: String) -> bool {
        let faultcore = match py.import("faultcore") {
            Ok(m) => m,
            Err(_) => return false,
        };
        let var = match faultcore.getattr("_FAULTCORE_CONTEXT_KEYS") {
            Ok(v) => v,
            Err(_) => return false,
        };
        let current: Option<Vec<String>> = match var.call_method0("get") {
            Ok(r) => r.extract().unwrap_or_default(),
            Err(_) => return false,
        };
        let mut keys_set: std::collections::HashSet<String> =
            current.unwrap_or_default().into_iter().collect();
        let removed = keys_set.remove(&key);
        if removed {
            let new_keys: Vec<String> = keys_set.into_iter().collect();
            let _ = var.call_method1("set", (Some(new_keys),));
        }
        removed
    }

    #[staticmethod]
    fn clear_keys(py: Python<'_>) {
        let faultcore = match py.import("faultcore") {
            Ok(m) => m,
            Err(_) => return,
        };
        let var = match faultcore.getattr("_FAULTCORE_CONTEXT_KEYS") {
            Ok(v) => v,
            Err(_) => return,
        };
        let _ = var.call_method1("set", (None::<Vec<String>>,));
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
