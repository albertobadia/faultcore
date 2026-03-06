pub mod context;
pub mod layer;
pub mod layers;
pub mod matching;
pub mod policy;
pub mod shm_registry;

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
        self.policies.lock().ok().and_then(|p| p.get(name).cloned())
    }

    pub fn get_or_create(&self, name: &str) -> Arc<RwLock<Policy>> {
        if let Some(policy) = self._get_policy(name) {
            return policy;
        }

        let policy = Policy::new(name.to_string());
        let policy = Arc::new(RwLock::new(policy));

        if let Ok(mut policies) = self.policies.lock() {
            policies.insert(name.to_string(), policy.clone());
        }

        policy
    }

    pub fn create_fresh(&self, name: &str) -> Arc<RwLock<Policy>> {
        let policy = Policy::new(name.to_string());
        let policy = Arc::new(RwLock::new(policy));

        if let Ok(mut policies) = self.policies.lock() {
            policies.insert(name.to_string(), policy.clone());
        }

        policy
    }

    pub fn _set_thread_policy(&self, name: Option<String>) {
        THREAD_POLICY.with(|p| {
            *p.borrow_mut() = name;
        });
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
        let mut policies = self
            .policies
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        let mut policy = Policy::new(name.clone());

        Python::attach(move |py| {
            let config_bound = config.into_bound(py);

            // Parse L4 Transport
            if let Some(l4) = config_bound.get_item("l4_transport")? {
                let list = l4.cast::<PyList>()?;
                for item in list.iter() {
                    let dict = item.cast::<PyDict>()?;
                    let type_str: String = dict.get_item("type")?.unwrap().extract()?;
                    match type_str.as_str() {
                        "timeout" => {
                            let ms: u64 = dict.get_item("timeout_ms")?.unwrap().extract()?;
                            policy.add_transport_layer(Arc::new(TimeoutLayer { timeout_ms: ms }));
                        }
                        _ => {
                            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                                "Unknown L4 type: {}",
                                type_str
                            )));
                        }
                    }
                }
            }

            // Parse L3 Routing (currently no layers)
            if let Some(l3) = config_bound.get_item("l3_routing")? {
                let list = l3.cast::<PyList>()?;
                if !list.is_empty() {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "L3 Routing layers are not supported in this version",
                    ));
                }
            }

            // Parse L2 QoS
            if let Some(l2) = config_bound.get_item("l2_qos")? {
                let list = l2.cast::<PyList>()?;
                for item in list.iter() {
                    let dict = item.cast::<PyDict>()?;
                    let type_str: String = dict.get_item("type")?.unwrap().extract()?;
                    match type_str.as_str() {
                        "rate_limit" => {
                            let rate: f64 = dict.get_item("rate")?.unwrap().extract()?;
                            let capacity: f64 = dict.get_item("capacity")?.unwrap().extract()?;
                            policy.add_qos_layer(Arc::new(RateLimitQosLayer {
                                rate,
                                capacity,
                                tokens: Arc::new(Mutex::new((capacity, std::time::Instant::now()))),
                            }));
                        }
                        _ => {
                            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                                "Unknown L2 type: {}",
                                type_str
                            )));
                        }
                    }
                }
            }

            // Parse L1 Chaos
            if let Some(l1) = config_bound.get_item("l1_chaos")? {
                let list = l1.cast::<PyList>()?;
                for item in list.iter() {
                    let dict = item.cast::<PyDict>()?;
                    let type_str: String = dict.get_item("type")?.unwrap().extract()?;
                    match type_str.as_str() {
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
                                "Unknown L1 type: {}",
                                type_str
                            )));
                        }
                    }
                }
            }

            policies.insert(name.clone(), Arc::new(RwLock::new(policy)));
            get_shm_registry().register_policy(&name, true);
            Ok(())
        })?;

        Ok(())
    }

    fn remove_policy(&self, name: &str) -> bool {
        if let Ok(mut policies) = self.policies.lock() {
            policies.remove(name).is_some()
        } else {
            false
        }
    }

    fn list_policies(&self) -> Vec<String> {
        if let Ok(policies) = self.policies.lock() {
            policies.keys().cloned().collect()
        } else {
            Vec::new()
        }
    }

    fn enable(&self, name: &str) -> bool {
        let result = self
            ._get_policy(name)
            .map(|p| {
                if let Ok(mut policy) = p.write() {
                    policy.enabled = true;
                    true
                } else {
                    false
                }
            })
            .unwrap_or(false);
        if result {
            get_shm_registry().set_enabled(name, true);
        }
        result
    }

    fn disable(&self, name: &str) -> bool {
        let result = self
            ._get_policy(name)
            .map(|p| {
                if let Ok(mut policy) = p.write() {
                    policy.enabled = false;
                    true
                } else {
                    false
                }
            })
            .unwrap_or(false);
        if result {
            get_shm_registry().set_enabled(name, false);
        }
        result
    }

    fn reset(&self, name: &str) -> bool {
        self._get_policy(name)
            .map(|p| {
                if let Ok(mut policy) = p.write() {
                    policy.enabled = true;
                    true
                } else {
                    false
                }
            })
            .unwrap_or(false)
    }

    fn is_enabled(&self, name: &str) -> bool {
        self._get_policy(name)
            .map(|p| p.read().map(|policy| policy.enabled).unwrap_or(false))
            .unwrap_or(false)
    }

    fn set_thread_policy(&self, name: Option<String>) {
        self._set_thread_policy(name);
    }

    fn get_thread_policy(&self) -> Option<String> {
        self._get_thread_policy()
    }

    fn match_policy(&self, ctx: &CallContext) -> Option<String> {
        let rules = self.rules.read().ok()?;
        let mut best_rule: Option<&MatchingRule> = None;

        for rule in rules.iter() {
            let matches = rule.conditions.iter().all(|cond| match cond {
                MatchCondition::Key { key, value } => {
                    ctx.tags.get(key).map(|v| v == value).unwrap_or(false)
                }
                MatchCondition::Prefix { key, prefix } => ctx
                    .tags
                    .get(key)
                    .map(|v| v.starts_with(prefix))
                    .unwrap_or(false),
            });

            if matches {
                if let Some(best) = best_rule {
                    if rule.priority > best.priority {
                        best_rule = Some(rule);
                    }
                } else {
                    best_rule = Some(rule);
                }
            }
        }

        best_rule.map(|r| r.policy_name.clone())
    }

    fn execute_policy(&self, py: Python<'_>, name: String, func: Py<PyAny>) -> PyResult<Py<PyAny>> {
        let mut final_name = self._get_thread_policy().unwrap_or(name);
        let ctx = CallContext::default();

        if final_name == "auto"
            && let Some(matched) = self.match_policy(&ctx)
        {
            final_name = matched;
        }

        let policy = self.get_or_create(&final_name);
        let p = policy.read().unwrap();
        p.execute(&ctx, func, py)
    }

    fn add_rule(
        &self,
        policy_name: String,
        conditions: Bound<'_, PyList>,
        priority: i32,
    ) -> PyResult<()> {
        let mut parsed_conditions = Vec::new();

        for item in conditions.iter() {
            let dict = item.cast::<PyDict>().map_err(|_| {
                pyo3::exceptions::PyTypeError::new_err("Condition must be a dictionary")
            })?;

            let type_str: String = dict
                .get_item("type")?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("type is required"))?
                .extract()?;

            match type_str.as_str() {
                "key" => {
                    let key: String = dict
                        .get_item("key")?
                        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("key is required"))?
                        .extract()?;
                    let value: String = dict
                        .get_item("value")?
                        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("value is required"))?
                        .extract()?;
                    parsed_conditions.push(MatchCondition::Key { key, value });
                }
                "prefix" => {
                    let key: String = dict
                        .get_item("key")?
                        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("key is required"))?
                        .extract()?;
                    let prefix: String = dict
                        .get_item("prefix")?
                        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("prefix is required"))?
                        .extract()?;
                    parsed_conditions.push(MatchCondition::Prefix { key, prefix });
                }
                _ => {
                    return Err(pyo3::exceptions::PyValueError::new_err(format!(
                        "Unknown condition type: {}. Valid types are: key, prefix",
                        type_str
                    )));
                }
            }
        }

        let mut rules = self
            .rules
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        rules.push(MatchingRule {
            conditions: parsed_conditions,
            policy_name,
            priority,
        });

        rules.sort_by(|a, b| b.priority.cmp(&a.priority));

        Ok(())
    }

    fn remove_all_rules(&self) -> PyResult<()> {
        let mut rules = self
            .rules
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;
        rules.clear();
        Ok(())
    }
    fn get_policy(&self, name: &str) -> bool {
        self._get_policy(name).is_some()
    }

    fn is_policy_enabled(&self, name: &str) -> bool {
        self._get_policy(name)
            .map(|p| p.read().map(|policy| policy.enabled).unwrap_or(false))
            .unwrap_or(false)
    }

    fn register_timeout_layer(&self, policy_name: &str, timeout_ms: u64) -> PyResult<()> {
        let policy = self.create_fresh(policy_name);
        let mut p = policy
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        p.add_transport_layer(Arc::new(TimeoutLayer { timeout_ms }));
        Ok(())
    }

    fn register_rate_limit_layer(
        &self,
        policy_name: &str,
        rate: f64,
        capacity: u64,
    ) -> PyResult<()> {
        let policy = self.create_fresh(policy_name);
        let mut p = policy
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        p.add_qos_layer(Arc::new(RateLimitQosLayer {
            rate,
            capacity: capacity as f64,
            tokens: Arc::new(Mutex::new((capacity as f64, std::time::Instant::now()))),
        }));
        Ok(())
    }

    fn add_layer(&self, policy_name: &str, layer_type: &str, _layer_name: String) -> PyResult<()> {
        let _policy = self.get_or_create(policy_name);
        match layer_type {
            "timeout" => self.register_timeout_layer(policy_name, 1000),
            _ => Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Unknown layer type: {}",
                layer_type
            ))),
        }
    }
}
