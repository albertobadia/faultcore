use libc::c_int;

use crate::{FAULTCORE_MAGIC, get_thread_id, update_config_for_tid};

pub const FAULTCORE_SETPRIORITY_LATENCY: c_int = 0xFA;
pub const FAULTCORE_SETPRIORITY_BANDWIDTH: c_int = 0xFB;
pub const FAULTCORE_SETPRIORITY_TIMEOUT: c_int = 0xFC;

pub fn try_handle_setpriority(which: c_int, who: c_int, prio: c_int) -> bool {
    let is_faultcore = matches!(
        which,
        FAULTCORE_SETPRIORITY_LATENCY
            | FAULTCORE_SETPRIORITY_BANDWIDTH
            | FAULTCORE_SETPRIORITY_TIMEOUT
    );
    if !is_faultcore {
        return false;
    }

    let tid = get_thread_id() as usize;
    let _ = update_config_for_tid(tid, |config| {
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
    });
    true
}

