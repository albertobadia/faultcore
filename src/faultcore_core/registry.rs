use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};

use pyo3::prelude::*;
use pyo3::types::PyDict;

static CALL_COUNTER: AtomicU64 = AtomicU64::new(0);

#[allow(dead_code)]
#[derive(Clone, Debug)]
pub enum Scope {
    Policy,
    Function,
    Thread,
    Call,
}

#[allow(dead_code)]
impl Scope {
    pub fn from_str(s: &str) -> Self {
        match s {
            "function" => Scope::Function,
            "thread" => Scope::Thread,
            "call" => Scope::Call,
            _ => Scope::Policy,
        }
    }
}

#[derive(Clone, Debug)]
pub struct CallContext {
    pub function_name: String,
    pub thread_id: u64,
    pub call_id: u64,
}

impl CallContext {
    pub fn new(function_name: String) -> Self {
        let thread_id = std::process::id() as u64;
        let call_id = CALL_COUNTER.fetch_add(1, Ordering::SeqCst);
        Self {
            function_name,
            thread_id,
            call_id,
        }
    }
}

pub enum PolicyResult {
    Ok(Py<PyAny>),
    Drop { reason: &'static str },
    Error(String),
}

impl PolicyResult {
    pub fn is_ok(&self) -> bool {
        matches!(self, PolicyResult::Ok(_))
    }

    pub fn is_drop(&self) -> bool {
        matches!(self, PolicyResult::Drop { .. })
    }

    pub fn is_error(&self) -> bool {
        matches!(self, PolicyResult::Error(..))
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

pub type Next = Arc<dyn Fn() -> PolicyResult + Send + Sync>;

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
        _ctx: &CallContext,
        func: Py<PyAny>,
        py: Python<'_>,
    ) -> PyResult<Py<PyAny>> {
        if !self.enabled {
            return func.call(py, (), None);
        }

        for _ in &self.l4_transport {}
        for _ in &self.l3_routing {}
        for _ in &self.l2_qos {}
        for _ in &self.l1_chaos {}

        func.call(py, (), None)
    }
}

#[pyclass]
pub struct PolicyRegistry {
    policies: Arc<Mutex<std::collections::HashMap<String, Arc<RwLock<Policy>>>>>,
}

impl PolicyRegistry {
    pub fn new() -> Self {
        Self {
            policies: Arc::new(Mutex::new(std::collections::HashMap::new())),
        }
    }

    pub fn get_policy(&self, name: &str) -> Option<Arc<RwLock<Policy>>> {
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
        if let Some(policy) = self.get_policy(name) {
            return policy;
        }

        let policy = Policy::new(name.to_string());
        let policy = Arc::new(RwLock::new(policy));

        if let Ok(mut policies) = self.policies.lock() {
            policies.insert(name.to_string(), policy.clone());
        }

        policy
    }

    pub fn enable(&self, name: &str) -> bool {
        self.get_policy(name)
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
        self.get_policy(name)
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
        self.get_policy(name)
            .map(|p| p.read().map(|policy| policy.enabled).unwrap_or(false))
            .unwrap_or(false)
    }

    pub fn reset(&self, name: &str) -> bool {
        self.get_policy(name)
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
}

impl Default for PolicyRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[pymethods]
impl PolicyRegistry {
    fn register_timeout_layer(&self, policy_name: &str, timeout_ms: u64) -> PyResult<()> {
        let policy = self.get_or_create(policy_name);
        let mut p = policy
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        struct TimeoutLayer {
            timeout_ms: u64,
        }

        impl TransportLayer for TimeoutLayer {
            fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
                let timeout = std::time::Duration::from_millis(self.timeout_ms);
                let start = std::time::Instant::now();
                let result = std::thread::spawn(move || next()).join();

                match result {
                    Ok(r) => {
                        if start.elapsed() > timeout {
                            return PolicyResult::Error("Timeout exceeded".to_string());
                        }
                        r
                    }
                    Err(_) => PolicyResult::Error("Thread panicked".to_string()),
                }
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
    ) -> PyResult<()> {
        let policy = self.get_or_create(policy_name);
        let mut p = policy
            .write()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        struct RetryTransportLayer {
            max_retries: u32,
            backoff_ms: u64,
        }

        impl TransportLayer for RetryTransportLayer {
            fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
                let mut last_error: Option<String> = None;

                for attempt in 0..=self.max_retries {
                    let result = next();

                    match result {
                        PolicyResult::Ok(_) => return result,
                        PolicyResult::Error(e) => {
                            last_error = Some(e);
                            if attempt < self.max_retries {
                                std::thread::sleep(std::time::Duration::from_millis(
                                    self.backoff_ms,
                                ));
                            }
                        }
                        PolicyResult::Drop { reason } => {
                            last_error = Some(reason.to_string());
                            if attempt < self.max_retries {
                                std::thread::sleep(std::time::Duration::from_millis(
                                    self.backoff_ms,
                                ));
                            }
                        }
                    }
                }

                PolicyResult::Error(last_error.unwrap_or_else(|| "Retry exhausted".to_string()))
            }

            fn name(&self) -> &str {
                "RetryTransport"
            }
        }

        p.add_transport_layer(Arc::new(RetryTransportLayer {
            max_retries,
            backoff_ms,
        }));
        Ok(())
    }

    fn register_rate_limit_layer(
        &self,
        policy_name: &str,
        rate: f64,
        capacity: u64,
    ) -> PyResult<()> {
        let policy = self.get_or_create(policy_name);
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
        let policy = self.get_policy(policy_name).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!("Policy '{}' not found", policy_name))
        })?;

        let p = policy
            .read()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Lock error: {}", e)))?;

        let ctx = CallContext::new("execute".to_string());

        p.execute(&ctx, func, py)
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
