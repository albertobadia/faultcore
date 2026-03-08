pub mod context;
pub mod layer;
pub mod layers;
pub mod matching;
pub mod policy;
pub mod shm_registry;

use log::error;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;
use std::sync::{Arc, Mutex, RwLock};

use crate::registry::context::CallContext;
use crate::registry::layers::latency::LatencyChaosLayer;
use crate::registry::layers::packet_loss::PacketLossChaosLayer;
use crate::registry::layers::rate_limit::RateLimitQosLayer;
use crate::registry::layers::timeout::TimeoutLayer;
use crate::registry::matching::{MatchCondition, MatchingRule};
use crate::registry::policy::Policy;
use crate::registry::shm_registry::get_shm_registry;

thread_local! {
    pub static THREAD_POLICY: std::cell::RefCell<Option<String>> = const { std::cell::RefCell::new(None) };
}

static POLICY_REGISTRY: std::sync::OnceLock<PolicyRegistry> = std::sync::OnceLock::new();

pub fn get_policy_registry() -> &'static PolicyRegistry {
    POLICY_REGISTRY.get_or_init(PolicyRegistry::new)
}

#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct PolicyRegistry {
    policies: Arc<Mutex<HashMap<String, Arc<RwLock<Policy>>>>>,
    rules: Arc<RwLock<Vec<MatchingRule>>>,
}

impl PolicyRegistry {
    pub fn new() -> Self {
        Self {
            policies: Arc::new(Mutex::new(HashMap::new())),
            rules: Arc::new(RwLock::new(Vec::new())),
        }
    }

    fn _get_policy(&self, name: &str) -> Option<Arc<RwLock<Policy>>> {
        self.policies.lock().ok()?.get(name).cloned()
    }

    pub fn get_or_create(&self, name: &str) -> Arc<RwLock<Policy>> {
        let mut policies = self.policies.lock().unwrap();

        if let Some(policy) = policies.get(name) {
            return policy.clone();
        }

        let policy = Arc::new(RwLock::new(Policy::new(name.to_string())));
        policies.insert(name.to_string(), policy.clone());
        policy
    }

    pub fn create_fresh(&self, name: &str) -> Arc<RwLock<Policy>> {
        let policy = Arc::new(RwLock::new(Policy::new(name.to_string())));
        if let Ok(mut policies) = self.policies.lock() {
            policies.insert(name.to_string(), policy.clone());
        }
        policy
    }

    pub fn _set_thread_policy(&self, name: Option<String>) {
        THREAD_POLICY.with(|p| *p.borrow_mut() = name);
    }

    pub fn _get_thread_policy(&self) -> Option<String> {
        THREAD_POLICY.with(|p| p.borrow().clone())
    }
}

impl Default for PolicyRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[pymethods]
impl PolicyRegistry {
    pub fn register_policy(&self, name: String, config: Py<PyDict>) -> PyResult<()> {
        let mut policies = self.policies.lock().map_err(|e| {
            pyo3::exceptions::PyRuntimeError::new_err(format!("Registry lock error: {e}"))
        })?;

        let mut policy = Policy::new(name.clone());

        Python::attach(|py| {
            let config = config.into_bound(py);

            if let Some(layers) = config.get_item("l4_transport")? {
                for item in layers.cast::<PyList>()?.iter() {
                    let dict = item.cast::<PyDict>()?;
                    let ty: String = dict.get_item("type")?.unwrap().extract()?;
                    if ty == "timeout" {
                        let ms: u64 = dict.get_item("timeout_ms")?.unwrap().extract()?;
                        policy.add_transport_layer(Arc::new(TimeoutLayer { timeout_ms: ms }));
                    } else {
                        return Err(pyo3::exceptions::PyValueError::new_err(format!(
                            "Unknown L4 type: {ty}"
                        )));
                    }
                }
            }

            if let Some(layers) = config.get_item("l2_qos")? {
                for item in layers.cast::<PyList>()?.iter() {
                    let dict = item.cast::<PyDict>()?;
                    let ty: String = dict.get_item("type")?.unwrap().extract()?;
                    if ty == "rate_limit" {
                        let rate_bps: u64 = self._extract_rate(dict.get_item("rate")?.unwrap())?;
                        policy.add_qos_layer(Arc::new(RateLimitQosLayer::new(rate_bps)));
                    } else {
                        return Err(pyo3::exceptions::PyValueError::new_err(format!(
                            "Unknown L2 type: {ty}"
                        )));
                    }
                }
            }

            if let Some(layers) = config.get_item("l1_chaos")? {
                for item in layers.cast::<PyList>()?.iter() {
                    let dict = item.cast::<PyDict>()?;
                    let ty: String = dict.get_item("type")?.unwrap().extract()?;
                    match ty.as_str() {
                        "latency" => {
                            let ms: u64 = dict.get_item("latency_ms")?.unwrap().extract()?;
                            policy.add_chaos_layer(Arc::new(LatencyChaosLayer { latency_ms: ms }));
                        }
                        "packet_loss" => {
                            let ppm: u64 = dict.get_item("ppm")?.unwrap().extract()?;
                            policy.add_chaos_layer(Arc::new(PacketLossChaosLayer { ppm }));
                        }
                        _ => {
                            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                                "Unknown L1 type: {ty}"
                            )));
                        }
                    }
                }
            }

            if let Err(e) = crate::system::shm::create_shm() {
                error!("Failed to create SHM: {}", e);
            }
            policies.insert(name.clone(), Arc::new(RwLock::new(policy)));
            get_shm_registry().register_policy(&name, true);
            Ok(())
        })
    }

    fn _extract_rate(&self, rate_any: Bound<'_, PyAny>) -> PyResult<u64> {
        rate_any.extract::<u64>().or_else(|_| {
            rate_any
                .extract::<String>()?
                .parse()
                .map_err(|_| pyo3::exceptions::PyValueError::new_err("Invalid rate format"))
        })
    }

    fn remove_policy(&self, name: &str) -> bool {
        self.policies
            .lock()
            .ok()
            .and_then(|mut p| p.remove(name))
            .is_some()
    }

    fn list_policies(&self) -> Vec<String> {
        self.policies
            .lock()
            .ok()
            .map(|p| p.keys().cloned().collect())
            .unwrap_or_default()
    }

    fn enable(&self, name: &str) -> bool {
        if self._set_enabled(name, true) {
            get_shm_registry().set_enabled(name, true);
            return true;
        }
        false
    }

    fn disable(&self, name: &str) -> bool {
        if self._set_enabled(name, false) {
            get_shm_registry().set_enabled(name, false);
            return true;
        }
        false
    }

    fn _set_enabled(&self, name: &str, enabled: bool) -> bool {
        self._get_policy(name)
            .and_then(|p| {
                p.write().ok().map(|mut policy| {
                    policy.enabled = enabled;
                    true
                })
            })
            .unwrap_or(false)
    }

    fn reset(&self, name: &str) -> bool {
        self.enable(name)
    }

    fn is_enabled(&self, name: &str) -> bool {
        self._get_policy(name)
            .and_then(|p| p.read().ok().map(|p| p.enabled))
            .unwrap_or(false)
    }

    fn set_thread_policy(&self, name: Option<String>) {
        self._set_thread_policy(name);
    }

    fn get_thread_policy(&self) -> Option<String> {
        self._get_thread_policy()
    }

    fn match_policy(&self, ctx: &CallContext) -> Option<String> {
        self.rules
            .read()
            .ok()?
            .iter()
            .find(|rule| {
                rule.conditions.iter().all(|cond| match cond {
                    MatchCondition::Key { key, value } => ctx.tags.get(key) == Some(value),
                    MatchCondition::Prefix { key, prefix } => {
                        ctx.tags.get(key).is_some_and(|v| v.starts_with(prefix))
                    }
                })
            })
            .map(|r| r.policy_name.clone())
    }

    fn execute_policy(&self, py: Python<'_>, name: String, func: Py<PyAny>) -> PyResult<Py<PyAny>> {
        let final_name = self
            ._get_thread_policy()
            .or_else(|| {
                if name == "auto" {
                    self.match_policy(&CallContext::default())
                } else {
                    Some(name)
                }
            })
            .unwrap_or_else(|| "default".to_string());

        let policy = self.get_or_create(&final_name);
        policy
            .read()
            .unwrap()
            .execute(&CallContext::default(), func, py)
    }

    fn add_rule(
        &self,
        policy_name: String,
        conditions: Bound<'_, PyList>,
        priority: i32,
    ) -> PyResult<()> {
        let mut parsed_conditions = Vec::with_capacity(conditions.len());

        for item in conditions.iter() {
            let dict = item.cast::<PyDict>()?;
            let ty: String = dict.get_item("type")?.unwrap().extract()?;

            match ty.as_str() {
                "key" => {
                    parsed_conditions.push(MatchCondition::Key {
                        key: dict.get_item("key")?.unwrap().extract()?,
                        value: dict.get_item("value")?.unwrap().extract()?,
                    });
                }
                "prefix" => {
                    parsed_conditions.push(MatchCondition::Prefix {
                        key: dict.get_item("key")?.unwrap().extract()?,
                        prefix: dict.get_item("prefix")?.unwrap().extract()?,
                    });
                }
                _ => {
                    return Err(pyo3::exceptions::PyValueError::new_err(format!(
                        "Unknown rule type: {ty}"
                    )));
                }
            }
        }

        let mut rules = self.rules.write().map_err(|e| {
            pyo3::exceptions::PyRuntimeError::new_err(format!("Rules lock error: {e}"))
        })?;

        rules.push(MatchingRule {
            conditions: parsed_conditions,
            policy_name,
            priority,
        });
        rules.sort_by_key(|r| std::cmp::Reverse(r.priority));
        Ok(())
    }

    fn remove_all_rules(&self) -> PyResult<()> {
        let mut rules = self.rules.write().map_err(|e| {
            pyo3::exceptions::PyRuntimeError::new_err(format!("Rules lock error: {e}"))
        })?;
        rules.clear();
        Ok(())
    }

    fn get_policy(&self, name: &str) -> bool {
        self._get_policy(name).is_some()
    }

    fn is_policy_enabled(&self, name: &str) -> bool {
        self.is_enabled(name)
    }

    fn register_timeout_layer(&self, policy_name: &str, timeout_ms: u64) -> PyResult<()> {
        if let Err(e) = crate::system::shm::create_shm() {
            error!("Failed to create SHM: {}", e);
        }
        let policy = self.create_fresh(policy_name);
        let mut p = policy.write().map_err(|e| {
            pyo3::exceptions::PyRuntimeError::new_err(format!("Policy lock error: {e}"))
        })?;
        p.add_transport_layer(Arc::new(TimeoutLayer { timeout_ms }));
        Ok(())
    }

    fn register_rate_limit_layer(&self, policy_name: &str, rate: Bound<'_, PyAny>) -> PyResult<()> {
        if let Err(e) = crate::system::shm::create_shm() {
            error!("Failed to create SHM: {}", e);
        }
        let rate_bps = self._extract_rate(rate)?;
        let policy = self.create_fresh(policy_name);
        let mut p = policy.write().map_err(|e| {
            pyo3::exceptions::PyRuntimeError::new_err(format!("Policy lock error: {e}"))
        })?;

        p.add_qos_layer(Arc::new(RateLimitQosLayer::new(rate_bps)));
        Ok(())
    }
}
