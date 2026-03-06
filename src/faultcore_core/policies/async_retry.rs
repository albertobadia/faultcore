use pyo3::prelude::*;

use crate::policies::retry::ErrorClass;

#[pyclass]
pub struct AsyncRetryPolicy {
    max_retries: u32,
    backoff_ms: u64,
    retry_on: Vec<ErrorClass>,
}

impl AsyncRetryPolicy {
    pub fn new(max_retries: u32, backoff_ms: u64, retry_on: Option<Vec<String>>) -> Self {
        let retry_on = retry_on
            .map(|v| {
                v.into_iter()
                    .map(|s| ErrorClass::from_error_str(&s))
                    .collect()
            })
            .unwrap_or_default();
        Self {
            max_retries,
            backoff_ms,
            retry_on,
        }
    }
}

#[pymethods]
impl AsyncRetryPolicy {
    #[new]
    #[pyo3(signature = (max_retries, backoff_ms=100, retry_on=None))]
    fn new_py(max_retries: u32, backoff_ms: u64, retry_on: Option<Vec<String>>) -> PyResult<Self> {
        Ok(Self::new(max_retries, backoff_ms, retry_on))
    }

    #[getter]
    fn max_retries(&self) -> u32 {
        self.max_retries
    }

    #[getter]
    fn backoff_ms(&self) -> u64 {
        self.backoff_ms
    }

    #[getter]
    fn retry_on(&self) -> Vec<String> {
        self.retry_on
            .iter()
            .map(|e| match e {
                ErrorClass::Transient => "transient".to_string(),
                ErrorClass::Timeout => "timeout".to_string(),
                ErrorClass::RateLimit => "ratelimit".to_string(),
                ErrorClass::Network => "network".to_string(),
                ErrorClass::Permanent => "permanent".to_string(),
                ErrorClass::Internal => "internal".to_string(),
            })
            .collect()
    }

    fn should_retry(&self, error_class: &str) -> bool {
        let error = ErrorClass::from_error_str(error_class);
        self.retry_on.contains(&error)
    }

    fn __repr__(&self) -> String {
        format!(
            "AsyncRetryPolicy(max_retries={}, backoff_ms={})",
            self.max_retries, self.backoff_ms
        )
    }
}
