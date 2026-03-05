use std::time::Duration;

#[derive(Clone, Debug)]
pub struct RetryPolicy {
    pub max_retries: u32,
    pub backoff: Duration,
    pub retry_on: Vec<ErrorClass>,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum ErrorClass {
    Transient,
    Timeout,
    RateLimit,
    Network,
    Permanent,
    Internal,
}

impl ErrorClass {
    pub fn from_error_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "transient" => ErrorClass::Transient,
            "timeout" => ErrorClass::Timeout,
            "rate_limit" | "ratelimit" => ErrorClass::RateLimit,
            "network" => ErrorClass::Network,
            "permanent" => ErrorClass::Permanent,
            _ => ErrorClass::Internal,
        }
    }
}

impl RetryPolicy {
    pub fn new(max_retries: u32, backoff_ms: u64, retry_on: Option<Vec<String>>) -> Self {
        let retry_on = retry_on
            .map(|v| {
                let mut classes: Vec<ErrorClass> = v
                    .into_iter()
                    .map(|s| ErrorClass::from_error_str(&s))
                    .collect();
                if !classes.is_empty() && !classes.contains(&ErrorClass::Permanent) {
                    classes.push(ErrorClass::Transient);
                }
                classes
            })
            .unwrap_or_else(|| {
                vec![
                    ErrorClass::Transient,
                    ErrorClass::Timeout,
                    ErrorClass::Network,
                ]
            });

        Self {
            max_retries,
            backoff: Duration::from_millis(backoff_ms),
            retry_on,
        }
    }

    pub fn should_retry(&self, error: &ErrorClass) -> bool {
        self.retry_on.contains(error)
    }

    pub fn is_custom_retry(&self) -> bool {
        self.retry_on.iter().any(|e| {
            *e != ErrorClass::Transient && *e != ErrorClass::Timeout && *e != ErrorClass::Network
        })
    }

    pub fn backoff_duration(&self, attempt: u32) -> Duration {
        self.backoff * (1u32 << attempt)
    }
}
