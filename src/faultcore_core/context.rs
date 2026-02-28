use once_cell::sync::Lazy;
use std::collections::HashSet;
use std::sync::RwLock;

use pyo3::prelude::*;

static CONTEXT_KEYS: Lazy<RwLock<HashSet<String>>> = Lazy::new(|| RwLock::new(HashSet::new()));

pub fn get_context_keys() -> Vec<String> {
    CONTEXT_KEYS.read().unwrap().iter().cloned().collect()
}

pub fn add_context_keys(keys: Vec<String>) {
    let mut guard = CONTEXT_KEYS.write().unwrap();
    for key in keys {
        guard.insert(key);
    }
}

pub fn remove_context_key(key: &str) -> bool {
    CONTEXT_KEYS.write().unwrap().remove(key)
}

pub fn clear_context_keys() {
    CONTEXT_KEYS.write().unwrap().clear();
}

#[pyclass]
pub struct ContextManager;

#[pymethods]
impl ContextManager {
    #[staticmethod]
    fn get_keys() -> Vec<String> {
        get_context_keys()
    }

    #[staticmethod]
    fn add_keys(keys: Vec<String>) {
        add_context_keys(keys);
    }

    #[staticmethod]
    fn remove_key(key: String) -> bool {
        remove_context_key(&key)
    }

    #[staticmethod]
    fn clear_keys() {
        clear_context_keys()
    }

    #[staticmethod]
    fn has_key(key: String) -> bool {
        CONTEXT_KEYS.read().unwrap().contains(&key)
    }
}
