use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{Next, TransportLayer};
use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;

pub struct FallbackLayer {
    pub fallback_func: Py<PyAny>,
}

impl TransportLayer for FallbackLayer {
    fn execute(&self, ctx: &CallContext, next: Next) -> PolicyResult {
        let result = next();
        if result.is_error() {
            Python::attach(|py| {
                let fallback_func = ctx.fallback_func.as_ref().unwrap_or(&self.fallback_func);

                let kwargs = pyo3::types::PyDict::new(py);
                if let PolicyResult::Error {
                    exception: Some(ref exc),
                    ..
                } = result
                {
                    kwargs.set_item("exception", exc.clone_ref(py)).unwrap();
                }

                match fallback_func.call(py, (), Some(&kwargs)) {
                    Ok(val) => PolicyResult::Ok(val),
                    Err(e) => PolicyResult::Error {
                        message: format!("Fallback failed: {}", e),
                        exception: Some(e.into_py_any(py).unwrap()),
                    },
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
