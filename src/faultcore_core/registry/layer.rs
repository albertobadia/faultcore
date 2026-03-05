use crate::registry::context::{CallContext, PolicyResult};
use std::sync::Arc;

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
