use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};

use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::circuit_breaker::CircuitBreakerPolicy as CircuitBreakerCore;

thread_local! {
    static FALLBACK_FN: std::cell::RefCell<Option<Py<PyAny>>> = const { std::cell::RefCell::new(None) };
    static THREAD_POLICY: std::cell::RefCell<Option<String>> = const { std::cell::RefCell::new(None) };
}

static CALL_COUNTER: AtomicU64 = AtomicU64::new(0);

static POLICY_REGISTRY: std::sync::OnceLock<PolicyRegistry> = std::sync::OnceLock::new();

pub fn get_policy_registry() -> &'static PolicyRegistry {
    POLICY_REGISTRY.get_or_init(PolicyRegistry::new)
}

#[derive(Clone, Debug)]
pub struct CallContext {
    pub function_name: String,
    pub thread_id: u64,
    pub call_id: u64,
    pub host: Option<String>,
    pub path: Option<String>,
    pub method: Option<String>,
    pub headers: HashMap<String, String>,
}

impl CallContext {
    pub fn new(function_name: String) -> Self {
        let thread_id = unsafe { libc::syscall(libc::SYS_gettid) as u64 };
        let call_id = CALL_COUNTER.fetch_add(1, Ordering::SeqCst);
        Self {
            function_name,
            thread_id,
            call_id,
            host: None,
            path: None,
            method: None,
            headers: HashMap::new(),
        }
    }
}

pub enum PolicyResult {
    Ok(Py<PyAny>),
    Drop {
        reason: &'static str,
    },
    Error {
        message: String,
        exception: Option<Py<PyAny>>,
    },
}

impl PolicyResult {
    pub fn is_ok(&self) -> bool {
        matches!(self, PolicyResult::Ok(_))
    }

    pub fn is_drop(&self) -> bool {
        matches!(self, PolicyResult::Drop { .. })
    }

    pub fn is_error(&self) -> bool {
        matches!(self, PolicyResult::Error { .. })
    }
}

pub trait TransportLayer: Send + Sync {
    fn execute(&self, ctx: &CallContext, next: Next) -> PolicyResult;
    fn name(&self) -> &str {
        "TransportLayer"
    }
}

pub trait RoutingLayer: Send + Sync {
    fn execute(&self, ctx: &CallContext, next: Next) -> PolicyResult;
    fn name(&self) -> &str {
        "RoutingLayer"
    }
}

pub trait QosLayer: Send + Sync {
    fn execute(&self, ctx: &CallContext, next: Next) -> PolicyResult;
    fn name(&self) -> &str {
        "QosLayer"
    }
}

pub trait ChaosLayer: Send + Sync {
    fn execute(&self, ctx: &CallContext, next: Next) -> PolicyResult;
    fn name(&self) -> &str {
        "ChaosLayer"
    }
}

pub struct Next {
    inner: Arc<dyn Fn() -> PolicyResult + Send + Sync>,
}

impl Next {
    pub fn new<F>(f: F) -> Self
    where
        F: Fn() -> PolicyResult + Send + Sync + 'static,
    {
        Next { inner: Arc::new(f) }
    }

    pub fn from_box(box_fn: Box<dyn Fn() -> PolicyResult + Send + Sync>) -> Self {
        Next {
            inner: Arc::from(box_fn),
        }
    }

    pub fn call(&self) -> PolicyResult {
        (self.inner)()
    }
}

impl From<Box<dyn Fn() -> PolicyResult + Send + Sync>> for Next {
    fn from(box_fn: Box<dyn Fn() -> PolicyResult + Send + Sync>) -> Self {
        Next::from_box(box_fn)
    }
}

impl Clone for Next {
    fn clone(&self) -> Self {
        Next {
            inner: self.inner.clone(),
        }
    }
}

impl std::ops::Deref for Next {
    type Target = dyn Fn() -> PolicyResult + Send + Sync;

    fn deref(&self) -> &Self::Target {
        &*self.inner
    }
}

pub struct Policy {
    pub name: String,
    pub l4_transport: Vec<Arc<dyn TransportLayer>>,
    pub l3_routing: Vec<Arc<dyn RoutingLayer>>,
    pub l2_qos: Vec<Arc<dyn QosLayer>>,
    pub l1_chaos: Vec<Arc<dyn ChaosLayer>>,
    pub enabled: bool,
    pub auto_disable_on_panic: bool,
}

impl Policy {
    pub fn new(name: String) -> Self {
        Self {
            name,
            l4_transport: Vec::new(),
            l3_routing: Vec::new(),
            l2_qos: Vec::new(),
            l1_chaos: Vec::new(),
            enabled: true,
            auto_disable_on_panic: true,
        }
    }

    pub fn add_transport_layer(&mut self, layer: Arc<dyn TransportLayer>) {
        self.l4_transport.push(layer);
    }

    pub fn add_routing_layer(&mut self, layer: Arc<dyn RoutingLayer>) {
        self.l3_routing.push(layer);
    }

    pub fn add_qos_layer(&mut self, layer: Arc<dyn QosLayer>) {
        self.l2_qos.push(layer);
    }

    pub fn add_chaos_layer(&mut self, layer: Arc<dyn ChaosLayer>) {
        self.l1_chaos.push(layer);
    }

    pub fn execute(
        &self,
        ctx: &CallContext,
        func: Py<PyAny>,
        py: Python<'_>,
    ) -> PyResult<Py<PyAny>> {
        if !self.enabled {
            return func.call(py, (), None);
        }

        let func = func.clone_ref(py);

        let inner_call = move || -> PolicyResult {
            Python::attach(|py| {
                func.call(py, (), None)
                    .map(PolicyResult::Ok)
                    .unwrap_or_else(|e: pyo3::PyErr| {
                        let err_type = e
                            .get_type(py)
                            .name()
                            .map(|s| s.to_string())
                            .unwrap_or_else(|_| "RuntimeError".to_string());
                        let err_msg = e
                            .value(py)
                            .str()
                            .map(|s| s.to_string())
                            .unwrap_or_else(|_| e.to_string());
                        PolicyResult::Error {
                            message: format!("{}: {}", err_type, err_msg),
                            exception: Some(e.into_py_any(py).unwrap()),
                        }
                    })
            })
        };

        let base_next = Next::new(inner_call);

        let next_l1: Next = if self.l1_chaos.is_empty() {
            base_next.clone()
        } else {
            let mut next = base_next.clone();
            for layer in self.l1_chaos.iter().rev() {
                let layer = layer.clone();
                let ctx = ctx.clone();
                let prev_next = next.clone();
                next = Next::new(move || layer.execute(&ctx, prev_next.clone()));
            }
            next
        };

        let next_l2: Next = if self.l2_qos.is_empty() {
            next_l1.clone()
        } else {
            let mut next = next_l1.clone();
            for layer in self.l2_qos.iter().rev() {
                let layer = layer.clone();
                let ctx = ctx.clone();
                let prev_next = next.clone();
                next = Next::new(move || layer.execute(&ctx, prev_next.clone()));
            }
            next
        };

        let next_l3: Next = if self.l3_routing.is_empty() {
            next_l2.clone()
        } else {
            let mut next = next_l2.clone();
            for layer in self.l3_routing.iter().rev() {
                let layer = layer.clone();
                let ctx = ctx.clone();
                let prev_next = next.clone();
                next = Next::new(move || layer.execute(&ctx, prev_next.clone()));
            }
            next
        };

        let final_next: Next = if self.l4_transport.is_empty() {
            next_l3.clone()
        } else {
            let mut next = next_l3.clone();
            for layer in self.l4_transport.iter().rev() {
                let layer = layer.clone();
                let ctx = ctx.clone();
                let prev_next = next.clone();
                next = Next::new(move || layer.execute(&ctx, prev_next.clone()));
            }
            next
        };

        let result = final_next.call();

        match result {
            PolicyResult::Ok(value) => Ok(value),
            PolicyResult::Error { message, exception } => {
                if let Some(exc) = exception {
                    Python::attach(|py| {
                        let err = exc.into_bound(py);
                        Err(PyErr::from_value(err))
                    })
                } else {
                    let (err_type, err_msg) = if let Some(pos) = message.find(':') {
                        (
                            message[..pos].trim().to_string(),
                            message[pos + 1..].trim().to_string(),
                        )
                    } else {
                        ("RuntimeError".to_string(), message.clone())
                    };

                    Python::attach(|py| {
                        if let Ok(exc_type) = py.import("builtins")?.getattr(err_type)
                            && let Ok(instance) = exc_type.call1((err_msg,))
                        {
                            return Err(PyErr::from_value(instance));
                        }
                        Err(pyo3::exceptions::PyRuntimeError::new_err(message))
                    })
                }
            }
            PolicyResult::Drop { reason } => Err(pyo3::exceptions::PyRuntimeError::new_err(
                format!("Request dropped: {}", reason),
            )),
        }
    }
}

#[derive(Clone, Debug)]
pub enum MatchCondition {
    Host(String),
    Path(String),
    Method(String),
    Header(String, String),
}

#[derive(Clone, Debug)]
pub struct MatchingRule {
    pub conditions: Vec<MatchCondition>,
    pub policy_name: String,
    pub priority: i32,
}

#[pyclass]
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

    pub fn register_policy(&self, name: String, _config: Py<PyDict>) -> PyResult<()> {
        let mut policies = self
            .policies
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        let policy = Policy::new(name.clone());
        policies.insert(name, Arc::new(RwLock::new(policy)));
        Ok(())
    }

    pub fn remove_policy(&self, name: &str) -> bool {
        self.policies
            .lock()
            .map(|mut p| p.remove(name).is_some())
            .unwrap_or(false)
    }

    pub fn list_policies(&self) -> Vec<String> {
        self.policies
            .lock()
            .map(|p| p.keys().cloned().collect())
            .unwrap_or_default()
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

    /// Always creates a fresh policy, replacing any existing one.
    /// Used by decorator register_*_layer methods to avoid layer accumulation
    /// when Python reuses memory addresses (id(func)) between test runs.
    pub fn create_fresh(&self, name: &str) -> Arc<RwLock<Policy>> {
        let policy = Policy::new(name.to_string());
        let policy = Arc::new(RwLock::new(policy));

        if let Ok(mut policies) = self.policies.lock() {
            policies.insert(name.to_string(), policy.clone());
        }

        policy
    }

    pub fn enable(&self, name: &str) -> bool {
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

    pub fn disable(&self, name: &str) -> bool {
        self._get_policy(name)
            .map(|p| {
                if let Ok(mut policy) = p.write() {
                    policy.enabled = false;
                    true
                } else {
                    false
                }
            })
            .unwrap_or(false)
    }

    pub fn is_enabled(&self, name: &str) -> bool {
        self._get_policy(name)
            .map(|p| p.read().map(|policy| policy.enabled).unwrap_or(false))
            .unwrap_or(false)
    }

    pub fn reset(&self, name: &str) -> bool {
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
    pub fn match_policy(&self, ctx: &CallContext) -> Option<String> {
        let rules = self.rules.read().ok()?;
        let mut best_rule: Option<&MatchingRule> = None;

        for rule in rules.iter() {
            let matches = rule.conditions.iter().all(|cond| match cond {
                MatchCondition::Host(h) => ctx.host.as_ref().map(|ch| ch == h).unwrap_or(false),
                MatchCondition::Path(p) => ctx
                    .path
                    .as_ref()
                    .map(|cp| cp.starts_with(p))
                    .unwrap_or(false),
                MatchCondition::Method(m) => ctx.method.as_ref().map(|cm| cm == m).unwrap_or(false),
                MatchCondition::Header(k, v) => {
                    ctx.headers.get(k).map(|cv| cv == v).unwrap_or(false)
                }
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
    fn set_thread_policy(&self, name: Option<String>) {
        self._set_thread_policy(name);
    }

    fn get_thread_policy(&self) -> Option<String> {
        self._get_thread_policy()
    }

    fn add_rule(
        &self,
        policy_name: String,
        conditions: Bound<'_, PyList>,
        priority: i32,
    ) -> PyResult<()> {
        let mut parsed_conditions = Vec::new();

        for item in conditions.iter() {
            #[allow(deprecated)]
            let dict = item.downcast::<PyDict>().map_err(|_| {
                pyo3::exceptions::PyTypeError::new_err("Condition must be a dictionary")
            })?;

            let type_str: String = dict
                .get_item("type")?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("type is required"))?
                .extract()?;

            match type_str.as_str() {
                "host" => {
                    let host: String = dict
                        .get_item("value")?
                        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("value is required"))?
                        .extract()?;
                    parsed_conditions.push(MatchCondition::Host(host));
                }
                "path" => {
                    let path: String = dict
                        .get_item("value")?
                        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("value is required"))?
                        .extract()?;
                    parsed_conditions.push(MatchCondition::Path(path));
                }
                "method" => {
                    let method: String = dict
                        .get_item("value")?
                        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("value is required"))?
                        .extract()?;
                    parsed_conditions.push(MatchCondition::Method(method));
                }
                "header" => {
                    let name: String = dict
                        .get_item("name")?
                        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("name is required"))?
                        .extract()?;
                    let value: String = dict
                        .get_item("value")?
                        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("value is required"))?
                        .extract()?;
                    parsed_conditions.push(MatchCondition::Header(name, value));
                }
                _ => {
                    return Err(pyo3::exceptions::PyValueError::new_err(format!(
                        "Unknown condition type: {}",
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

        // Keep rules sorted by priority (highest first)
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

        struct TimeoutLayer {
            timeout_ms: u64,
        }

        impl TransportLayer for TimeoutLayer {
            fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
                let start = std::time::Instant::now();
                let result = next.call();

                if start.elapsed().as_millis() > self.timeout_ms as u128 {
                    return PolicyResult::Error {
                        message: "Timeout exceeded".to_string(),
                        exception: None,
                    };
                }
                result
            }

            fn name(&self) -> &str {
                "TimeoutTransport"
            }
        }

        p.add_transport_layer(Arc::new(TimeoutLayer { timeout_ms }));
        Ok(())
    }

    fn register_retry_layer(
        &self,
        policy_name: &str,
        max_retries: u32,
        backoff_ms: u64,
        retry_on: Option<Vec<String>>,
    ) -> PyResult<()> {
        let policy = self.create_fresh(policy_name);
        let mut p = policy
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        let retry_on = retry_on.unwrap_or_else(|| {
            vec![
                "Transient".to_string(),
                "Timeout".to_string(),
                "Network".to_string(),
                "Connection".to_string(),
                "Error".to_string(),
                "Exception".to_string(),
            ]
        });

        struct RetryTransportLayer {
            max_retries: u32,
            backoff_ms: u64,
            retry_on: Vec<String>,
        }

        impl TransportLayer for RetryTransportLayer {
            fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
                let mut last_error: Option<(String, Option<Py<PyAny>>)> = None;

                for attempt in 0..=self.max_retries {
                    let result = next();

                    match result {
                        PolicyResult::Ok(_) => return result,
                        PolicyResult::Error { message, exception } => {
                            // message format is "ExcTypeName: message"
                            // retry_on can contain type names (e.g. "ValueError") or
                            // category keywords (e.g. "timeout", "network")
                            let msg_lower = message.to_lowercase();
                            // Extract the exception type name (before the colon)
                            let exc_type = msg_lower.split(':').next().unwrap_or("").trim();

                            // Semantic classification: map exception type names to categories
                            let categories: Vec<&str> = {
                                let mut cats = vec![];
                                if exc_type.contains("timeout") || exc_type.contains("timedout") {
                                    cats.push("timeout");
                                }
                                if exc_type.contains("connection")
                                    || exc_type.contains("network")
                                    || exc_type.contains("remote")
                                    || exc_type.contains("disconnected")
                                    || exc_type.contains("protocol")
                                {
                                    cats.push("network");
                                    cats.push("connection");
                                }
                                if exc_type.contains("ratelimit") || exc_type.contains("throttle") {
                                    cats.push("ratelimit");
                                }
                                // Default: transient covers most runtime errors
                                if cats.is_empty()
                                    || exc_type.contains("transient")
                                    || exc_type.contains("runtime")
                                    || exc_type.contains("value")
                                    || exc_type.contains("os")
                                    || exc_type.contains("io")
                                    || exc_type.contains("file")
                                    || exc_type.contains("attribute")
                                    || exc_type.contains("key")
                                    || exc_type.contains("permission")
                                {
                                    cats.push("transient");
                                    cats.push("error");
                                    cats.push("exception");
                                }
                                cats
                            };

                            let should_retry = self.retry_on.iter().any(|exc| {
                                let exc_lower = exc.to_lowercase();
                                // Direct type name match
                                exc_type.starts_with(&exc_lower)
                                    || exc_type.contains(&exc_lower)
                                    // Semantic category match
                                    || categories.contains(&exc_lower.as_str())
                            });

                            if !should_retry {
                                return PolicyResult::Error { message, exception };
                            }

                            last_error = Some((message, exception));
                            if attempt < self.max_retries {
                                // Exponential backoff: backoff_ms * 2^attempt
                                let delay_ms = self.backoff_ms * (1u64 << attempt);
                                std::thread::sleep(std::time::Duration::from_millis(delay_ms));
                            }
                        }
                        PolicyResult::Drop { reason } => {
                            last_error = Some((reason.to_string(), None));
                            if attempt < self.max_retries {
                                let delay_ms = self.backoff_ms * (1u64 << attempt);
                                std::thread::sleep(std::time::Duration::from_millis(delay_ms));
                            }
                        }
                    }
                }

                if let Some((message, exception)) = last_error {
                    PolicyResult::Error { message, exception }
                } else {
                    PolicyResult::Error {
                        message: "Retry exhausted".to_string(),
                        exception: None,
                    }
                }
            }

            fn name(&self) -> &str {
                "RetryTransport"
            }
        }

        p.add_transport_layer(Arc::new(RetryTransportLayer {
            max_retries,
            backoff_ms,
            retry_on,
        }));
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

        use std::time::Instant;

        struct RateLimitQosLayer {
            rate: f64,
            capacity: f64,
            tokens: Arc<Mutex<(f64, Instant)>>,
        }

        impl QosLayer for RateLimitQosLayer {
            fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
                let mut tokens = self.tokens.lock().unwrap();
                let elapsed = tokens.1.elapsed().as_secs_f64();
                let new_tokens = elapsed * self.rate;
                tokens.0 = (tokens.0 + new_tokens).min(self.capacity);
                tokens.1 = Instant::now();

                if tokens.0 >= 1.0 {
                    tokens.0 -= 1.0;
                    drop(tokens);
                    next()
                } else {
                    PolicyResult::Drop {
                        reason: "Rate limit exceeded",
                    }
                }
            }

            fn name(&self) -> &str {
                "RateLimitQoS"
            }
        }

        p.add_qos_layer(Arc::new(RateLimitQosLayer {
            rate,
            capacity: capacity as f64,
            tokens: Arc::new(Mutex::new((capacity as f64, Instant::now()))),
        }));
        Ok(())
    }

    fn register_circuit_breaker_layer(
        &self,
        policy_name: &str,
        failure_threshold: u32,
        success_threshold: u32,
        timeout_ms: u64,
    ) -> PyResult<()> {
        let policy = self.create_fresh(policy_name);
        let mut p = policy
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        struct CircuitBreakerTransportLayer {
            core: Arc<RwLock<CircuitBreakerCore>>,
        }

        impl TransportLayer for CircuitBreakerTransportLayer {
            fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
                {
                    let mut guard = self.core.write().unwrap();
                    if guard.is_open() && !guard.can_attempt() {
                        return PolicyResult::Error {
                            message: "RuntimeError: Circuit breaker is OPEN".to_string(),
                            exception: None,
                        };
                    }
                }

                let result = next();

                let is_ok = result.is_ok();
                {
                    let mut guard = self.core.write().unwrap();
                    if is_ok {
                        guard.record_success();
                    } else {
                        guard.record_failure();
                    }
                }
                result
            }

            fn name(&self) -> &str {
                "CircuitBreakerTransport"
            }
        }

        let core = Arc::new(RwLock::new(CircuitBreakerCore::new(
            failure_threshold,
            success_threshold,
            timeout_ms,
        )));

        p.add_transport_layer(Arc::new(CircuitBreakerTransportLayer { core }));
        Ok(())
    }

    fn register_fallback_layer(&self, policy_name: &str, _fallback: Py<PyAny>) -> PyResult<()> {
        let policy = self.create_fresh(policy_name);
        let mut p = policy
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        struct FallbackTransportLayer;

        impl TransportLayer for FallbackTransportLayer {
            fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
                let result = next();

                // Extract original exception before consuming result
                let orig_exc: Option<Py<PyAny>> = match &result {
                    PolicyResult::Error {
                        exception: Some(exc),
                        ..
                    } => Python::attach(|py| Some(exc.clone_ref(py))),
                    _ => None,
                };

                let should_fallback = matches!(
                    &result,
                    PolicyResult::Error { .. } | PolicyResult::Drop { .. }
                );

                if !should_fallback {
                    return result;
                }

                // Get the fallback closure injected by execute_policy_with_fallback
                let fallback_opt: Option<Py<PyAny>> = FALLBACK_FN.with(|f| {
                    f.borrow()
                        .as_ref()
                        .map(|fb| Python::attach(|py| fb.clone_ref(py)))
                });

                if let Some(fallback) = fallback_opt {
                    Python::attach(|py| {
                        // First attempt: call fallback without exception kwarg
                        match fallback.call(py, (), None) {
                            Ok(value) => PolicyResult::Ok(value),
                            Err(_fb_err) => {
                                // Second attempt: inject the original exception
                                let kwargs = pyo3::types::PyDict::new(py);
                                if let Some(exc) = orig_exc {
                                    let _ = kwargs.set_item("exception", exc.into_bound(py));
                                }
                                match fallback.call(py, (), Some(&kwargs)) {
                                    Ok(value) => PolicyResult::Ok(value),
                                    Err(e) => {
                                        let err_type: String = e
                                            .get_type(py)
                                            .name()
                                            .map(|s: pyo3::Bound<'_, pyo3::types::PyString>| {
                                                s.to_string()
                                            })
                                            .unwrap_or_else(|_| "RuntimeError".to_string());
                                        let err_msg: String = e
                                            .value(py)
                                            .str()
                                            .map(|s: pyo3::Bound<'_, pyo3::types::PyString>| {
                                                s.to_string()
                                            })
                                            .unwrap_or_else(|_| e.to_string());
                                        PolicyResult::Error {
                                            message: format!("{}: {}", err_type, err_msg),
                                            exception: Some(e.into_py_any(py).unwrap()),
                                        }
                                    }
                                }
                            }
                        }
                    })
                } else {
                    result
                }
            }

            fn name(&self) -> &str {
                "FallbackTransport"
            }
        }

        p.add_transport_layer(Arc::new(FallbackTransportLayer));
        Ok(())
    }

    fn register_chaos_layer(
        &self,
        policy_name: &str,
        packet_loss_rate: f64,
        latency_ms: u64,
    ) -> PyResult<()> {
        let policy = self.get_or_create(policy_name);
        let mut p = policy
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        struct ChaosQosLayer {
            packet_loss_rate: f64,
            latency_ms: u64,
        }

        impl ChaosLayer for ChaosQosLayer {
            fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
                let random: f64 = rand::random();

                if random < self.packet_loss_rate {
                    return PolicyResult::Drop {
                        reason: "Packet lost (chaos)",
                    };
                }

                if self.latency_ms > 0 {
                    std::thread::sleep(std::time::Duration::from_millis(self.latency_ms));
                }

                next()
            }

            fn name(&self) -> &str {
                "ChaosInjection"
            }
        }

        p.add_chaos_layer(Arc::new(ChaosQosLayer {
            packet_loss_rate,
            latency_ms,
        }));
        Ok(())
    }

    fn execute_policy(
        &self,
        py: Python<'_>,
        policy_name: &str,
        func: Py<PyAny>,
    ) -> PyResult<Py<PyAny>> {
        let ctx = CallContext::new("execute".to_string());

        // 1. Thread-local override
        let final_policy_name = if let Some(thread_policy) = self._get_thread_policy() {
            thread_policy
        } else if policy_name.is_empty() || policy_name == "auto" {
            // 2. Dynamic matching via rules
            self.match_policy(&ctx).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err("No matching policy found for this context")
            })?
        } else {
            policy_name.to_string()
        };

        let policy = self._get_policy(&final_policy_name).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "Policy '{}' not found",
                final_policy_name
            ))
        })?;

        let p = policy
            .read()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        p.execute(&ctx, func, py)
    }

    fn execute_policy_with_fallback(
        &self,
        py: Python<'_>,
        policy_name: &str,
        func: Py<PyAny>,
        fallback: Py<PyAny>,
    ) -> PyResult<Py<PyAny>> {
        let ctx = CallContext::new("execute".to_string());

        // 1. Thread-local override
        let final_policy_name = if let Some(thread_policy) = self._get_thread_policy() {
            thread_policy
        } else if policy_name.is_empty() || policy_name == "auto" {
            // 2. Dynamic matching via rules
            self.match_policy(&ctx).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err("No matching policy found for this context")
            })?
        } else {
            policy_name.to_string()
        };

        let policy = self._get_policy(&final_policy_name).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "Policy '{}' not found",
                final_policy_name
            ))
        })?;

        let p = policy
            .read()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        // Inject the fallback closure via thread_local so FallbackTransportLayer can access it
        FALLBACK_FN.with(|f| {
            *f.borrow_mut() = Some(fallback);
        });

        let result = p.execute(&ctx, func, py);

        // Clean up the thread_local
        FALLBACK_FN.with(|f| {
            *f.borrow_mut() = None;
        });

        result
    }

    fn add_layer(&self, policy_name: &str, layer_type: &str, layer_name: String) -> PyResult<()> {
        let policy = self.get_or_create(policy_name);
        let mut p = policy
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        match layer_type {
            "transport" | "l4" => {
                p.add_transport_layer(
                    Arc::new(TransportLayerWrapper { name: layer_name }) as Arc<dyn TransportLayer>
                );
            }
            "routing" | "l3" => {
                p.add_routing_layer(
                    Arc::new(RoutingLayerWrapper { name: layer_name }) as Arc<dyn RoutingLayer>
                );
            }
            "qos" | "l2" => {
                p.add_qos_layer(Arc::new(QosLayerWrapper { name: layer_name }) as Arc<dyn QosLayer>);
            }
            "chaos" | "l1" => {
                p.add_chaos_layer(
                    Arc::new(ChaosLayerWrapper { name: layer_name }) as Arc<dyn ChaosLayer>
                );
            }
            _ => {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Unknown layer type: {}",
                    layer_type
                )));
            }
        }

        Ok(())
    }
}

struct TransportLayerWrapper {
    name: String,
}

impl TransportLayer for TransportLayerWrapper {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        next()
    }

    fn name(&self) -> &str {
        &self.name
    }
}

struct RoutingLayerWrapper {
    name: String,
}

impl RoutingLayer for RoutingLayerWrapper {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        next()
    }

    fn name(&self) -> &str {
        &self.name
    }
}

struct QosLayerWrapper {
    name: String,
}

impl QosLayer for QosLayerWrapper {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        next()
    }

    fn name(&self) -> &str {
        &self.name
    }
}

struct ChaosLayerWrapper {
    name: String,
}

impl ChaosLayer for ChaosLayerWrapper {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        next()
    }

    fn name(&self) -> &str {
        &self.name
    }
}
