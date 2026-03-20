use crate::LayerDecision;
use parking_lot::Mutex;
use std::collections::HashMap;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicU64, Ordering};

pub const LATENCY_BUCKET_UPPER_BOUNDS_NS: [u64; 8] = [
    1_000_000,
    5_000_000,
    10_000_000,
    50_000_000,
    100_000_000,
    250_000_000,
    500_000_000,
    1_000_000_000,
];
pub const LATENCY_BUCKET_COUNT: usize = LATENCY_BUCKET_UPPER_BOUNDS_NS.len() + 1;
pub const TARGET_RULE_TOP_N: usize = 8;

#[repr(C)]
#[derive(Debug, Clone, Copy, Default)]
pub struct FaultTypeCountersSnapshot {
    pub delay_count: u64,
    pub drop_count: u64,
    pub timeout_count: u64,
    pub error_count: u64,
    pub connection_error_count: u64,
    pub reorder_count: u64,
    pub duplicate_count: u64,
    pub nxdomain_count: u64,
    pub mutate_count: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Default)]
pub struct TargetRuleCounterSnapshot {
    pub target_rule_id: u64,
    pub hits: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct FaultOsiAdvancedMetricsSnapshot {
    pub latency_bucket_len: u64,
    pub latency_bucket_upper_bounds_ns: [u64; LATENCY_BUCKET_UPPER_BOUNDS_NS.len()],
    pub latency_bucket_counts: [u64; LATENCY_BUCKET_COUNT],
    pub latency_sample_count: u64,
    pub latency_p50_ns: u64,
    pub latency_p95_ns: u64,
    pub latency_p99_ns: u64,
    pub fault_counters: FaultTypeCountersSnapshot,
    pub target_rule_top_len: u64,
    pub target_rule_top: [TargetRuleCounterSnapshot; TARGET_RULE_TOP_N],
    pub target_rule_other_count: u64,
}

impl Default for FaultOsiAdvancedMetricsSnapshot {
    fn default() -> Self {
        Self {
            latency_bucket_len: LATENCY_BUCKET_COUNT as u64,
            latency_bucket_upper_bounds_ns: LATENCY_BUCKET_UPPER_BOUNDS_NS,
            latency_bucket_counts: [0; LATENCY_BUCKET_COUNT],
            latency_sample_count: 0,
            latency_p50_ns: 0,
            latency_p95_ns: 0,
            latency_p99_ns: 0,
            fault_counters: FaultTypeCountersSnapshot::default(),
            target_rule_top_len: 0,
            target_rule_top: [TargetRuleCounterSnapshot::default(); TARGET_RULE_TOP_N],
            target_rule_other_count: 0,
        }
    }
}

struct FaultCounters {
    delay_count: AtomicU64,
    drop_count: AtomicU64,
    timeout_count: AtomicU64,
    error_count: AtomicU64,
    connection_error_count: AtomicU64,
    reorder_count: AtomicU64,
    duplicate_count: AtomicU64,
    nxdomain_count: AtomicU64,
    mutate_count: AtomicU64,
}

impl FaultCounters {
    fn new() -> Self {
        Self {
            delay_count: AtomicU64::new(0),
            drop_count: AtomicU64::new(0),
            timeout_count: AtomicU64::new(0),
            error_count: AtomicU64::new(0),
            connection_error_count: AtomicU64::new(0),
            reorder_count: AtomicU64::new(0),
            duplicate_count: AtomicU64::new(0),
            nxdomain_count: AtomicU64::new(0),
            mutate_count: AtomicU64::new(0),
        }
    }

    fn reset(&self) {
        self.delay_count.store(0, Ordering::Relaxed);
        self.drop_count.store(0, Ordering::Relaxed);
        self.timeout_count.store(0, Ordering::Relaxed);
        self.error_count.store(0, Ordering::Relaxed);
        self.connection_error_count.store(0, Ordering::Relaxed);
        self.reorder_count.store(0, Ordering::Relaxed);
        self.duplicate_count.store(0, Ordering::Relaxed);
        self.nxdomain_count.store(0, Ordering::Relaxed);
        self.mutate_count.store(0, Ordering::Relaxed);
    }

    fn snapshot(&self) -> FaultTypeCountersSnapshot {
        FaultTypeCountersSnapshot {
            delay_count: self.delay_count.load(Ordering::Relaxed),
            drop_count: self.drop_count.load(Ordering::Relaxed),
            timeout_count: self.timeout_count.load(Ordering::Relaxed),
            error_count: self.error_count.load(Ordering::Relaxed),
            connection_error_count: self.connection_error_count.load(Ordering::Relaxed),
            reorder_count: self.reorder_count.load(Ordering::Relaxed),
            duplicate_count: self.duplicate_count.load(Ordering::Relaxed),
            nxdomain_count: self.nxdomain_count.load(Ordering::Relaxed),
            mutate_count: self.mutate_count.load(Ordering::Relaxed),
        }
    }
}

struct AdvancedMetrics {
    latency_histogram: [AtomicU64; LATENCY_BUCKET_COUNT],
    latency_sample_count: AtomicU64,
    fault_counters: FaultCounters,
    target_rule_hits: Mutex<HashMap<u64, u64>>,
}

impl AdvancedMetrics {
    fn new() -> Self {
        Self {
            latency_histogram: std::array::from_fn(|_| AtomicU64::new(0)),
            latency_sample_count: AtomicU64::new(0),
            fault_counters: FaultCounters::new(),
            target_rule_hits: Mutex::new(HashMap::new()),
        }
    }

    fn record_delay_ns(&self, delay_ns: u64) {
        let idx = LATENCY_BUCKET_UPPER_BOUNDS_NS
            .iter()
            .position(|bound| delay_ns <= *bound)
            .unwrap_or(LATENCY_BUCKET_COUNT - 1);
        self.latency_histogram[idx].fetch_add(1, Ordering::Relaxed);
        self.latency_sample_count.fetch_add(1, Ordering::Relaxed);
        self.fault_counters.delay_count.fetch_add(1, Ordering::Relaxed);
    }

    fn record_fault_decision(&self, decision: &LayerDecision) {
        match decision {
            LayerDecision::Continue => {}
            LayerDecision::DelayNs(ns) => self.record_delay_ns(*ns),
            LayerDecision::Drop => {
                self.fault_counters.drop_count.fetch_add(1, Ordering::Relaxed);
            }
            LayerDecision::TimeoutMs(_) => {
                self.fault_counters.timeout_count.fetch_add(1, Ordering::Relaxed);
            }
            LayerDecision::Error(_) => {
                self.fault_counters.error_count.fetch_add(1, Ordering::Relaxed);
            }
            LayerDecision::ConnectionErrorKind(_) => {
                self.fault_counters
                    .connection_error_count
                    .fetch_add(1, Ordering::Relaxed);
            }
            LayerDecision::StageReorder => {
                self.fault_counters.reorder_count.fetch_add(1, Ordering::Relaxed);
            }
            LayerDecision::Duplicate(_) => {
                self.fault_counters.duplicate_count.fetch_add(1, Ordering::Relaxed);
            }
            LayerDecision::NxDomain => {
                self.fault_counters.nxdomain_count.fetch_add(1, Ordering::Relaxed);
            }
            LayerDecision::Mutate(_) => {
                self.fault_counters.mutate_count.fetch_add(1, Ordering::Relaxed);
            }
        }
    }

    fn record_target_rule_hit(&self, target_rule_id: u64) {
        let mut map = self.target_rule_hits.lock();
        let entry = map.entry(target_rule_id).or_insert(0);
        *entry = entry.saturating_add(1);
    }

    fn percentile_from_histogram(
        counts: &[u64; LATENCY_BUCKET_COUNT],
        sample_count: u64,
        percentile: u64,
    ) -> u64 {
        if sample_count == 0 {
            return 0;
        }
        let rank = sample_count.saturating_mul(percentile).div_ceil(100);
        let mut cumulative = 0u64;
        for (idx, count) in counts.iter().enumerate() {
            cumulative = cumulative.saturating_add(*count);
            if cumulative >= rank {
                if idx < LATENCY_BUCKET_UPPER_BOUNDS_NS.len() {
                    return LATENCY_BUCKET_UPPER_BOUNDS_NS[idx];
                }
                return LATENCY_BUCKET_UPPER_BOUNDS_NS[LATENCY_BUCKET_UPPER_BOUNDS_NS.len() - 1];
            }
        }
        LATENCY_BUCKET_UPPER_BOUNDS_NS[LATENCY_BUCKET_UPPER_BOUNDS_NS.len() - 1]
    }

    fn snapshot(&self) -> FaultOsiAdvancedMetricsSnapshot {
        let mut out = FaultOsiAdvancedMetricsSnapshot::default();
        let mut counts = [0u64; LATENCY_BUCKET_COUNT];
        for (idx, item) in self.latency_histogram.iter().enumerate() {
            counts[idx] = item.load(Ordering::Relaxed);
        }
        out.latency_bucket_counts = counts;
        out.latency_sample_count = self.latency_sample_count.load(Ordering::Relaxed);
        out.latency_p50_ns = Self::percentile_from_histogram(&counts, out.latency_sample_count, 50);
        out.latency_p95_ns = Self::percentile_from_histogram(&counts, out.latency_sample_count, 95);
        out.latency_p99_ns = Self::percentile_from_histogram(&counts, out.latency_sample_count, 99);
        out.fault_counters = self.fault_counters.snapshot();

        let map = self.target_rule_hits.lock();
        if !map.is_empty() {
            let mut entries: Vec<(u64, u64)> = map.iter().map(|(rule_id, hits)| (*rule_id, *hits)).collect();
            entries.sort_unstable_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
            let top_len = usize::min(entries.len(), TARGET_RULE_TOP_N);
            out.target_rule_top_len = top_len as u64;
            for (idx, (rule_id, hits)) in entries.iter().take(top_len).enumerate() {
                out.target_rule_top[idx] = TargetRuleCounterSnapshot {
                    target_rule_id: *rule_id,
                    hits: *hits,
                };
            }
            out.target_rule_other_count = entries
                .iter()
                .skip(top_len)
                .fold(0u64, |acc, (_, hits)| acc.saturating_add(*hits));
        }

        out
    }

    fn reset(&self) {
        for item in &self.latency_histogram {
            item.store(0, Ordering::Relaxed);
        }
        self.latency_sample_count.store(0, Ordering::Relaxed);
        self.fault_counters.reset();
        self.target_rule_hits.lock().clear();
    }
}

static ADVANCED_METRICS: OnceLock<AdvancedMetrics> = OnceLock::new();

fn global_metrics() -> &'static AdvancedMetrics {
    ADVANCED_METRICS.get_or_init(AdvancedMetrics::new)
}

pub fn record_fault_decision(decision: &LayerDecision) {
    global_metrics().record_fault_decision(decision);
}

pub fn record_target_rule_hit(target_rule_id: u64) {
    global_metrics().record_target_rule_hit(target_rule_id);
}

pub fn advanced_metrics_snapshot() -> FaultOsiAdvancedMetricsSnapshot {
    global_metrics().snapshot()
}

pub fn reset_advanced_metrics() {
    global_metrics().reset();
}

#[cfg(test)]
pub(crate) fn advanced_metrics_test_guard() -> parking_lot::MutexGuard<'static, ()> {
    static TEST_GUARD: OnceLock<Mutex<()>> = OnceLock::new();
    TEST_GUARD.get_or_init(|| Mutex::new(())).lock()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn latency_histogram_and_percentiles_are_bucketed() {
        let _guard = advanced_metrics_test_guard();
        reset_advanced_metrics();
        record_fault_decision(&LayerDecision::DelayNs(800_000));
        record_fault_decision(&LayerDecision::DelayNs(2_000_000));
        record_fault_decision(&LayerDecision::DelayNs(900_000_000));

        let snapshot = advanced_metrics_snapshot();
        assert_eq!(snapshot.latency_sample_count, 3);
        assert_eq!(snapshot.latency_bucket_counts[0], 1);
        assert_eq!(snapshot.latency_bucket_counts[1], 1);
        assert_eq!(snapshot.latency_bucket_counts[7], 1);
        assert_eq!(snapshot.fault_counters.delay_count, 3);
        assert_eq!(snapshot.latency_p50_ns, 5_000_000);
        assert_eq!(snapshot.latency_p95_ns, 1_000_000_000);
        assert_eq!(snapshot.latency_p99_ns, 1_000_000_000);
    }

    #[test]
    fn rule_top_n_and_other_are_computed() {
        let _guard = advanced_metrics_test_guard();
        const RULE_A: u64 = 9_000_000_001;
        const RULE_B: u64 = 9_000_000_002;
        reset_advanced_metrics();
        for _ in 0..2_000 {
            record_target_rule_hit(RULE_A);
        }
        for _ in 0..1_000 {
            record_target_rule_hit(RULE_B);
        }
        for i in 0..12 {
            record_target_rule_hit(9_000_001_000 + i);
        }

        let snapshot = advanced_metrics_snapshot();
        assert_eq!(snapshot.target_rule_top_len, TARGET_RULE_TOP_N as u64);
        let top = &snapshot.target_rule_top[..snapshot.target_rule_top_len as usize];
        let top_a = top.iter().find(|entry| entry.target_rule_id == RULE_A);
        let top_b = top.iter().find(|entry| entry.target_rule_id == RULE_B);
        assert_eq!(top_a.map(|entry| entry.hits), Some(2_000));
        assert_eq!(top_b.map(|entry| entry.hits), Some(1_000));
        assert!(snapshot.target_rule_other_count > 0);
    }

    #[test]
    fn reset_clears_all_advanced_metrics() {
        let _guard = advanced_metrics_test_guard();
        reset_advanced_metrics();
        record_fault_decision(&LayerDecision::Drop);
        record_target_rule_hit(7);

        let before = advanced_metrics_snapshot();
        assert_eq!(before.fault_counters.drop_count, 1);
        assert_eq!(before.target_rule_top_len, 1);

        reset_advanced_metrics();
        let after = advanced_metrics_snapshot();
        assert_eq!(after.latency_sample_count, 0);
        assert_eq!(after.fault_counters.drop_count, 0);
        assert_eq!(after.target_rule_top_len, 0);
        assert_eq!(after.target_rule_other_count, 0);
    }
}
