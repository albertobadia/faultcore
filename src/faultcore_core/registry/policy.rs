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
                    .unwrap_or_else(|e| PolicyResult::Error {
                        message: e.to_string(),
                        exception: Some(e.into_py_any(py).unwrap()),
                    })
            })
        };

        let mut next = Next::new(inner_call);

        let ctx_arc = Arc::new(ctx.clone());

        for layer in self.l4_transport.iter().rev() {
            let (layer, ctx, prev) = (layer.clone(), ctx_arc.clone(), next.clone());
            next = Next::new(move || layer.execute(&ctx, prev.clone()));
        }
        for layer in self.l3_routing.iter().rev() {
            let (layer, ctx, prev) = (layer.clone(), ctx_arc.clone(), next.clone());
            next = Next::new(move || layer.execute(&ctx, prev.clone()));
        }
        for layer in self.l2_qos.iter().rev() {
            let (layer, ctx, prev) = (layer.clone(), ctx_arc.clone(), next.clone());
            next = Next::new(move || layer.execute(&ctx, prev.clone()));
        }
        for layer in self.l1_chaos.iter().rev() {
            let (layer, ctx, prev) = (layer.clone(), ctx_arc.clone(), next.clone());
            next = Next::new(move || layer.execute(&ctx, prev.clone()));
        }

        let result = next.call();

        crate::registry::shm_registry::get_shm_registry()
            .update_metrics(&self.name, matches!(result, PolicyResult::Ok(_)));

        match result {
            PolicyResult::Ok(val) => Ok(val),
            PolicyResult::Error { message, exception } => {
                if let Some(exc) = exception {
                    Err(PyErr::from_value(exc.into_bound(py)))
                } else {
                    Err(pyo3::exceptions::PyRuntimeError::new_err(message))
                }
            }
            PolicyResult::Drop { reason } => Err(pyo3::exceptions::PyRuntimeError::new_err(
                format!("Dropped: {reason}"),
            )),
        }
    }
}
