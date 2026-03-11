use crate::LayerDecision;
use flate2::Compression;
use flate2::read::MultiGzDecoder;
use flate2::write::GzEncoder;
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::fs::File;
use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RecordReplayMode {
    Off,
    Record,
    Replay,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RecordReplayEvent {
    pub site: String,
    pub decision: String,
    pub value: u64,
}

impl RecordReplayEvent {
    pub fn from_decision(site: &str, decision: &LayerDecision) -> Self {
        let (kind, value) = match decision {
            LayerDecision::Continue => ("continue", 0),
            LayerDecision::Drop => ("drop", 0),
            LayerDecision::DelayNs(ns) => ("delay_ns", *ns),
            LayerDecision::TimeoutMs(ms) => ("timeout_ms", *ms),
            LayerDecision::Error(_) => ("error", 0),
            LayerDecision::ConnectionErrorKind(kind) => ("connection_error_kind", *kind),
            LayerDecision::StageReorder => ("stage_reorder", 0),
            LayerDecision::Duplicate(extra) => ("duplicate", *extra),
            LayerDecision::NxDomain => ("nxdomain", 0),
        };
        Self {
            site: site.to_string(),
            decision: kind.to_string(),
            value,
        }
    }

    pub fn to_decision(&self) -> Option<LayerDecision> {
        Some(match self.decision.as_str() {
            "continue" => LayerDecision::Continue,
            "drop" => LayerDecision::Drop,
            "delay_ns" => LayerDecision::DelayNs(self.value),
            "timeout_ms" => LayerDecision::TimeoutMs(self.value),
            "error" => LayerDecision::Error("record_replay_error".to_string()),
            "connection_error_kind" => LayerDecision::ConnectionErrorKind(self.value),
            "stage_reorder" => LayerDecision::StageReorder,
            "duplicate" => LayerDecision::Duplicate(self.value),
            "nxdomain" => LayerDecision::NxDomain,
            _ => return None,
        })
    }
}

pub struct RecordReplayCore {
    mode: RecordReplayMode,
    fail_fast: bool,
    replay_events: VecDeque<RecordReplayEvent>,
}

impl RecordReplayCore {
    pub fn new(mode: RecordReplayMode, replay_events: VecDeque<RecordReplayEvent>) -> Self {
        Self {
            mode,
            fail_fast: false,
            replay_events,
        }
    }

    pub fn fail_fast_decision() -> LayerDecision {
        LayerDecision::Error("record_replay_fail_fast".to_string())
    }

    pub fn evaluate_or_replay<F>(
        &mut self,
        site: &str,
        evaluate: F,
    ) -> (LayerDecision, Option<RecordReplayEvent>)
    where
        F: FnOnce() -> LayerDecision,
    {
        if self.fail_fast {
            return (Self::fail_fast_decision(), None);
        }

        match self.mode {
            RecordReplayMode::Off => (evaluate(), None),
            RecordReplayMode::Record => {
                let decision = evaluate();
                let event = RecordReplayEvent::from_decision(site, &decision);
                (decision, Some(event))
            }
            RecordReplayMode::Replay => {
                let Some(event) = self.replay_events.pop_front() else {
                    self.fail_fast = true;
                    return (Self::fail_fast_decision(), None);
                };
                if event.site != site {
                    self.fail_fast = true;
                    return (Self::fail_fast_decision(), None);
                }
                let Some(decision) = event.to_decision() else {
                    self.fail_fast = true;
                    return (Self::fail_fast_decision(), None);
                };
                (decision, None)
            }
        }
    }
}

struct RecordReplaySession {
    core: RecordReplayCore,
    record_path: Option<String>,
}

impl RecordReplaySession {
    fn mode_from_env() -> RecordReplayMode {
        match std::env::var("FAULTCORE_RECORD_REPLAY_MODE")
            .unwrap_or_default()
            .to_ascii_lowercase()
            .as_str()
        {
            "record" => RecordReplayMode::Record,
            "replay" => RecordReplayMode::Replay,
            _ => RecordReplayMode::Off,
        }
    }

    fn path_from_env() -> String {
        std::env::var("FAULTCORE_RECORD_REPLAY_PATH")
            .unwrap_or_else(|_| "/tmp/faultcore_record_replay.jsonl.gz".to_string())
    }

    fn load_replay_events(path: &str) -> VecDeque<RecordReplayEvent> {
        let mut out = VecDeque::new();
        let Ok(file) = File::open(path) else {
            return out;
        };
        let reader = BufReader::new(MultiGzDecoder::new(file));
        for line in reader.lines().map_while(Result::ok) {
            if let Ok(event) = serde_json::from_str::<RecordReplayEvent>(&line) {
                out.push_back(event);
            }
        }
        out
    }

    fn new() -> Self {
        let mode = Self::mode_from_env();
        let path = Self::path_from_env();

        match mode {
            RecordReplayMode::Off => Self {
                core: RecordReplayCore::new(mode, VecDeque::new()),
                record_path: None,
            },
            RecordReplayMode::Record => {
                let record_path = if File::create(&path).is_ok() {
                    Some(path)
                } else {
                    None
                };
                Self {
                    core: RecordReplayCore::new(mode, VecDeque::new()),
                    record_path,
                }
            }
            RecordReplayMode::Replay => Self {
                core: RecordReplayCore::new(mode, Self::load_replay_events(&path)),
                record_path: None,
            },
        }
    }

    fn persist_event(&mut self, event: RecordReplayEvent) {
        let Some(path) = self.record_path.as_ref() else {
            return;
        };
        let Ok(line) = serde_json::to_string(&event) else {
            return;
        };
        let Ok(file) = OpenOptions::new().append(true).create(true).open(path) else {
            return;
        };
        let mut encoder = GzEncoder::new(file, Compression::default());
        let _ = encoder.write_all(line.as_bytes());
        let _ = encoder.write_all(b"\n");
        let _ = encoder.finish();
    }

    fn evaluate_or_replay<F>(&mut self, site: &str, evaluate: F) -> LayerDecision
    where
        F: FnOnce() -> LayerDecision,
    {
        let (decision, maybe_event) = self.core.evaluate_or_replay(site, evaluate);
        if let Some(event) = maybe_event {
            self.persist_event(event);
        }
        decision
    }
}

lazy_static::lazy_static! {
    static ref RECORD_REPLAY: parking_lot::Mutex<RecordReplaySession> =
        parking_lot::Mutex::new(RecordReplaySession::new());
}

pub fn record_replay_evaluate_or_replay<F>(site: &str, evaluate: F) -> LayerDecision
where
    F: FnOnce() -> LayerDecision,
{
    RECORD_REPLAY.lock().evaluate_or_replay(site, evaluate)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn event_roundtrip_for_delay() {
        let decision = LayerDecision::DelayNs(42);
        let event = RecordReplayEvent::from_decision("stream_uplink_pre", &decision);
        assert_eq!(event.site, "stream_uplink_pre");
        let decoded = event.to_decision().expect("decode");
        assert_eq!(decoded, decision);
    }

    #[test]
    fn replay_mode_fail_fast_on_site_mismatch() {
        let mut replay_events = VecDeque::new();
        replay_events.push_back(RecordReplayEvent {
            site: "connect_pre".to_string(),
            decision: "continue".to_string(),
            value: 0,
        });
        let mut core = RecordReplayCore::new(RecordReplayMode::Replay, replay_events);
        let (decision, record) = core.evaluate_or_replay("dns_lookup", || LayerDecision::Continue);
        assert!(matches!(decision, LayerDecision::Error(_)));
        assert!(record.is_none());
    }
}
