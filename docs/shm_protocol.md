# Faultcore Shared Memory Protocol

This document defines the shared binary contract between:
- `src/faultcore/shm_writer.py` (Python writer)
- `faultcore_interceptor/src/shm.rs` (Rust reader/interceptor)

## Segment
- Name: `FAULTCORE_CONFIG_SHM` or `"/faultcore_<pid>_config"`
- Type: POSIX SHM (`/dev/shm/...`)
- Size:
  - FD table + TID hash table: `(MAX_FDS + MAX_TIDS) * CONFIG_SIZE`
  - The interceptor also reserves a region for `PolicyState`.

## FaultcoreConfig (288 bytes)
- Endianness: little-endian
- Fixed packed layout

| Field | Offset | Size | Type |
|---|---:|---:|---|
| `magic` | 0 | 4 | `u32` |
| `version` | 4 | 8 | `u64` |
| `latency_ns` | 12 | 8 | `u64` |
| `jitter_ns` | 20 | 8 | `u64` |
| `packet_loss_ppm` | 28 | 8 | `u64` |
| `burst_loss_len` | 36 | 8 | `u64` |
| `bandwidth_bps` | 44 | 8 | `u64` |
| `connect_timeout_ms` | 52 | 8 | `u64` |
| `recv_timeout_ms` | 60 | 8 | `u64` |
| `uplink_latency_ns` | 68 | 8 | `u64` |
| `uplink_jitter_ns` | 76 | 8 | `u64` |
| `uplink_packet_loss_ppm` | 84 | 8 | `u64` |
| `uplink_burst_loss_len` | 92 | 8 | `u64` |
| `uplink_bandwidth_bps` | 100 | 8 | `u64` |
| `downlink_latency_ns` | 108 | 8 | `u64` |
| `downlink_jitter_ns` | 116 | 8 | `u64` |
| `downlink_packet_loss_ppm` | 124 | 8 | `u64` |
| `downlink_burst_loss_len` | 132 | 8 | `u64` |
| `downlink_bandwidth_bps` | 140 | 8 | `u64` |
| `ge_enabled` | 148 | 8 | `u64` |
| `ge_p_good_to_bad_ppm` | 156 | 8 | `u64` |
| `ge_p_bad_to_good_ppm` | 164 | 8 | `u64` |
| `ge_loss_good_ppm` | 172 | 8 | `u64` |
| `ge_loss_bad_ppm` | 180 | 8 | `u64` |
| `conn_err_kind` | 188 | 8 | `u64` |
| `conn_err_prob_ppm` | 196 | 8 | `u64` |
| `half_open_after_bytes` | 204 | 8 | `u64` |
| `half_open_err_kind` | 212 | 8 | `u64` |
| `dup_prob_ppm` | 220 | 8 | `u64` |
| `dup_max_extra` | 228 | 8 | `u64` |
| `reorder_prob_ppm` | 236 | 8 | `u64` |
| `reorder_max_delay_ns` | 244 | 8 | `u64` |
| `reorder_window` | 252 | 8 | `u64` |
| `dns_delay_ns` | 260 | 8 | `u64` |
| `dns_timeout_ms` | 268 | 8 | `u64` |
| `dns_nxdomain_ppm` | 276 | 8 | `u64` |
| `reserved` | 284 | 4 | `u32` |

Constants:
- `FAULTCORE_MAGIC = 0xFACC0DE`
- `CONFIG_SIZE = 288`
- `MAX_FDS = 131072`
- `MAX_TIDS = 65536`

## Write/Read Consistency
- Python uses optimistic versioning:
  - marks `version` as odd during write;
  - writes `magic` + payload;
  - publishes `version` as even when done.
- Rust validates stable reads using a double-read of `version` plus fences.

## Compatibility Rule
Any change in offsets/size must:
1. update this document,
2. update Python and Rust together,
3. keep SHM contract tests green.

## Runtime Model over SHM

The SHM layout is stable, and runtime consumption is consolidated:

- The engine builds `PacketContext` by operation (`Connect`, `Send`, `Recv`, `DnsLookup`).
- The FaultOSI pipeline applies layers in fixed OSI order `L1..L7`.
- All fault decisions flow through a single `LayerDecision` enum.
- The interceptor only maps `LayerDecision` to return values/errno (`syscalls` and `getaddrinfo`).

This reduces duplicated logic between engine/interceptor and keeps behavior verifiable through mapping tests.
