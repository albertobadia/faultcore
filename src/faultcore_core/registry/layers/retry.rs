use crate::registry::context::{CallContext, PolicyResult};
use crate::registry::layer::{Next, TransportLayer};
use pyo3::prelude::*;

pub struct RetryTransportLayer {
    pub max_retries: u32,
    pub backoff_ms: u64,
    pub retry_on: Vec<String>,
}

impl TransportLayer for RetryTransportLayer {
    fn execute(&self, _ctx: &CallContext, next: Next) -> PolicyResult {
        let mut last_error: Option<(String, Option<Py<PyAny>>)> = None;

        for attempt in 0..=self.max_retries {
            let result = next();

            match result {
                PolicyResult::Ok(_) => return result,
                PolicyResult::Error { message, exception } => {
                    let msg_lower = message.to_lowercase();
                    let exc_type = msg_lower.split(':').next().unwrap_or("").trim();

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
                        if cats.is_empty()
                            || exc_type.contains("transient")
                            || exc_type.contains("runtime")
                            || exc_type.contains("os")
                            || exc_type.contains("io")
                            || exc_type.contains("file")
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
                        exc_type.starts_with(&exc_lower)
                            || exc_type.contains(&exc_lower)
                            || categories.contains(&exc_lower.as_str())
                    });

                    if !should_retry {
                        return PolicyResult::Error { message, exception };
                    }

                    last_error = Some((message, exception));
                    if attempt < self.max_retries {
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
