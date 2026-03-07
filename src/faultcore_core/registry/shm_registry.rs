use crate::system::shm;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

pub struct ShmPolicyRegistry {
    name_to_idx: Arc<Mutex<HashMap<String, usize>>>,
}

impl Default for ShmPolicyRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl ShmPolicyRegistry {
    pub fn new() -> Self {
        Self {
            name_to_idx: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub fn register_policy(&self, name: &str, enabled: bool) {
        let mut map = self.name_to_idx.lock().unwrap();
        if !map.contains_key(name) {
            let idx = map.len();
            if idx < shm::MAX_POLICIES {
                map.insert(name.to_string(), idx);
                let _ = shm::write_policy_state(idx, name, enabled, 0, 0);
            }
        } else {
            let idx = *map.get(name).unwrap();
            let _ = shm::write_policy_state(idx, name, enabled, 0, 0);
        }
    }

    pub fn update_metrics(&self, name: &str, success: bool) {
        let map = self.name_to_idx.lock().unwrap();
        if let Some(&idx) = map.get(name) {
            let _ = shm::update_policy_metrics(idx, success);
        }
    }

    pub fn set_enabled(&self, name: &str, enabled: bool) {
        let map = self.name_to_idx.lock().unwrap();
        if let Some(&idx) = map.get(name) {
            let _ = shm::write_policy_state(idx, name, enabled, 0, 0);
        }
    }
}

static SHM_REGISTRY: std::sync::OnceLock<ShmPolicyRegistry> = std::sync::OnceLock::new();

pub fn get_shm_registry() -> &'static ShmPolicyRegistry {
    SHM_REGISTRY.get_or_init(ShmPolicyRegistry::new)
}
