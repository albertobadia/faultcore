use libc::c_int;

use crate::{FAULTCORE_MAGIC, get_thread_id, update_config_for_tid};

pub const FAULTCORE_SETPRIORITY_LATENCY: c_int = 0xFA;
pub const FAULTCORE_SETPRIORITY_BANDWIDTH: c_int = 0xFB;
pub const FAULTCORE_SETPRIORITY_TIMEOUT: c_int = 0xFC;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SetpriorityCompatOutcome {
    NotHandled,
    Handled,
    FaultcoreError { errno: c_int },
}

pub fn handle_setpriority_compat(
    which: c_int,
    who: c_int,
    prio: c_int,
) -> SetpriorityCompatOutcome {
    if !is_faultcore_mode(which) {
        return SetpriorityCompatOutcome::NotHandled;
    }

    if !is_valid_faultcore_args(which, who, prio) {
        return SetpriorityCompatOutcome::FaultcoreError {
            errno: libc::EINVAL,
        };
    }

    let tid = get_thread_id() as usize;
    if update_config_for_tid(tid, |config| {
        match which {
            FAULTCORE_SETPRIORITY_LATENCY => {
                config.latency_ns = (who as u64) * 1_000_000;
                config.packet_loss_ppm = prio as u64;
            }
            FAULTCORE_SETPRIORITY_BANDWIDTH => {
                config.bandwidth_bps = (prio as u64) * 1024;
            }
            FAULTCORE_SETPRIORITY_TIMEOUT => {
                if who != -1 {
                    config.connect_timeout_ms = who as u64;
                }
                if prio != -1 {
                    config.recv_timeout_ms = prio as u64;
                }
            }
            _ => {}
        }
        config.magic = FAULTCORE_MAGIC;
    }) {
        SetpriorityCompatOutcome::Handled
    } else {
        SetpriorityCompatOutcome::FaultcoreError { errno: libc::EIO }
    }
}

pub fn try_handle_setpriority(which: c_int, who: c_int, prio: c_int) -> bool {
    matches!(
        handle_setpriority_compat(which, who, prio),
        SetpriorityCompatOutcome::Handled
    )
}

fn is_faultcore_mode(which: c_int) -> bool {
    matches!(
        which,
        FAULTCORE_SETPRIORITY_LATENCY
            | FAULTCORE_SETPRIORITY_BANDWIDTH
            | FAULTCORE_SETPRIORITY_TIMEOUT
    )
}

fn is_valid_faultcore_args(which: c_int, who: c_int, prio: c_int) -> bool {
    match which {
        FAULTCORE_SETPRIORITY_LATENCY => who >= 0 && prio >= 0,
        FAULTCORE_SETPRIORITY_BANDWIDTH => prio >= 0,
        FAULTCORE_SETPRIORITY_TIMEOUT => who >= -1 && prio >= -1,
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn non_faultcore_modes_are_not_handled() {
        let non_faultcore_which: c_int = 0;
        assert_eq!(
            handle_setpriority_compat(non_faultcore_which, 0, 0),
            SetpriorityCompatOutcome::NotHandled
        );
    }

    #[test]
    fn latency_mode_rejects_negative_values_with_einval() {
        assert_eq!(
            handle_setpriority_compat(FAULTCORE_SETPRIORITY_LATENCY, -1, 1),
            SetpriorityCompatOutcome::FaultcoreError {
                errno: libc::EINVAL
            }
        );
        assert_eq!(
            handle_setpriority_compat(FAULTCORE_SETPRIORITY_LATENCY, 1, -1),
            SetpriorityCompatOutcome::FaultcoreError {
                errno: libc::EINVAL
            }
        );
    }

    #[test]
    fn bandwidth_mode_rejects_negative_priority_with_einval() {
        assert_eq!(
            handle_setpriority_compat(FAULTCORE_SETPRIORITY_BANDWIDTH, 0, -5),
            SetpriorityCompatOutcome::FaultcoreError {
                errno: libc::EINVAL
            }
        );
    }

    #[test]
    fn timeout_mode_rejects_values_below_negative_one_with_einval() {
        assert_eq!(
            handle_setpriority_compat(FAULTCORE_SETPRIORITY_TIMEOUT, -2, -1),
            SetpriorityCompatOutcome::FaultcoreError {
                errno: libc::EINVAL
            }
        );
        assert_eq!(
            handle_setpriority_compat(FAULTCORE_SETPRIORITY_TIMEOUT, -1, -2),
            SetpriorityCompatOutcome::FaultcoreError {
                errno: libc::EINVAL
            }
        );
    }

    #[test]
    fn valid_faultcore_args_are_either_handled_or_report_eio() {
        let outcome = handle_setpriority_compat(FAULTCORE_SETPRIORITY_LATENCY, 5, 1000);
        assert!(
            matches!(
                outcome,
                SetpriorityCompatOutcome::Handled
                    | SetpriorityCompatOutcome::FaultcoreError { errno: libc::EIO }
            ),
            "unexpected outcome for valid faultcore mode: {outcome:?}"
        );
    }

    #[test]
    fn bool_wrapper_is_true_only_for_successful_handling() {
        let non_faultcore_which: c_int = 0;
        assert!(!try_handle_setpriority(
            FAULTCORE_SETPRIORITY_BANDWIDTH,
            0,
            -5
        ));
        assert!(!try_handle_setpriority(
            FAULTCORE_SETPRIORITY_TIMEOUT,
            -2,
            -1
        ));
        assert!(!try_handle_setpriority(non_faultcore_which, 0, 0));
    }
}
