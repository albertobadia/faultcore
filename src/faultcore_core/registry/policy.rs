use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;
use std::sync::Arc;

use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{ChaosLayer, Next, QosLayer, RoutingLayer, TransportLayer};

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
