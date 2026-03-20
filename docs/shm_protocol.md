# Faultcore Shared Memory Protocol

This document defines the shared binary contract between:
- `src/faultcore/shm_writer.py` (Python writer)
- `faultcore_network/src/shm_contract.rs` (Rust contract)
- `faultcore_network/src/shm_runtime.rs` (Rust SHM runtime)

## Segment
- Name: `FAULTCORE_CONFIG_SHM` or `"/faultcore_<pid>_config"`
- Type: POSIX SHM (`/dev/shm/...`)
- Size:
  - FD table + TID hash table: `(MAX_FDS + MAX_TIDS) * CONFIG_SIZE`
  - Policy state region: `MAX_POLICIES * sizeof(PolicyState)`
  - Target rules region: `MAX_TIDS * MAX_TARGET_RULES_PER_TID * sizeof(TargetRule)`
  - FD owner region (`fd -> tid_slot`): `MAX_FDS * sizeof(u64)`

### Region Layout Diagram

```mermaid
flowchart LR
    SHM["SHM Segment"]
    FD["FD table + TID hash<br/>(FaultcoreConfig rows)"]
    PS["Policy state region"]
    TR["Target rules region"]
    FO["FD owner region<br/>(fd -> tid_slot)"]

    SHM --> FD
    SHM --> PS
    SHM --> TR
    SHM --> FO
```

Diagram focus: top-level SHM memory regions consumed by writer/runtime.

## FaultcoreConfig (880 bytes)
- Endianness: little-endian
- Fixed packed layout

| Field | Offset | Size | Type |
|---|---:|---:|---|
| `magic` | 0 | 4 | `u32` |
| `version` | 4 | 8 | `u64` (legacy, reserved; unused for consistency) |
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
| `target_enabled` | 284 | 8 | `u64` |
| `target_kind` | 292 | 8 | `u64` |
| `target_ipv4` | 300 | 8 | `u64` (legacy compatibility; operational matching uses `target_address_family` + `target_addr`) |
| `target_prefix_len` | 308 | 8 | `u64` |
| `target_port` | 316 | 8 | `u64` |
| `target_protocol` | 324 | 8 | `u64` |
| `schedule_type` | 332 | 8 | `u64` |
| `schedule_param_a_ns` | 340 | 8 | `u64` |
| `schedule_param_b_ns` | 348 | 8 | `u64` |
| `schedule_param_c_ns` | 356 | 8 | `u64` |
| `schedule_started_monotonic_ns` | 364 | 8 | `u64` |
| `reserved` | 372 | 4 | `u32` |
| `ruleset_generation` | 376 | 8 | `u64` |
| `target_address_family` | 384 | 8 | `u64` |
| `target_addr` | 392 | 16 | `[u8;16]` |
| `target_hostname` | 408 | 32 | `[u8;32]` (final size for the vNext cycle) |
| `target_sni` | 440 | 32 | `[u8;32]` (final size for the vNext cycle) |
| `session_budget_enabled` | 472 | 8 | `u64` (`0/1`) |
| `session_max_bytes_tx` | 480 | 8 | `u64` (`0` = disabled) |
| `session_max_bytes_rx` | 488 | 8 | `u64` (`0` = disabled) |
| `session_max_ops` | 496 | 8 | `u64` (`0` = disabled) |
| `session_max_duration_ms` | 504 | 8 | `u64` (`0` = disabled) |
| `session_action` | 512 | 8 | `u64` (`1=drop`, `2=timeout`, `3=connection_error`) |
| `session_budget_timeout_ms` | 520 | 8 | `u64` (`action=timeout`) |
| `session_error_kind` | 528 | 8 | `u64` (`1=reset`, `2=refused`, `3=unreachable`) |
| `policy_seed` | 536 | 8 | `u64` (random seed for deterministic behavior) |
| `payload_mutation_enabled` | 544 | 8 | `u64` (`0/1`) |
| `payload_mutation_prob_ppm` | 552 | 8 | `u64` (`0..1_000_000`) |
| `payload_mutation_type` | 560 | 8 | `u64` (`0=none`, `1=truncate`, `2=corrupt_bytes`, `3=inject_bytes`, `4=replace_pattern`, `5=corrupt_encoding`, `6=swap_bytes`) |
| `payload_mutation_target` | 568 | 8 | `u64` (`0=both`, `1=uplink_only`, `2=downlink_only`) |
| `payload_mutation_truncate_size` | 576 | 8 | `u64` |
| `payload_mutation_corrupt_count` | 584 | 8 | `u64` |
| `payload_mutation_corrupt_seed` | 592 | 8 | `u64` |
| `payload_mutation_inject_position` | 600 | 8 | `u64` |
| `payload_mutation_inject_data` | 608 | 64 | `[u8;64]` |
| `payload_mutation_inject_len` | 672 | 8 | `u64` |
| `payload_mutation_replace_find` | 680 | 32 | `[u8;32]` |
| `payload_mutation_replace_find_len` | 712 | 8 | `u64` |
| `payload_mutation_replace_with` | 720 | 32 | `[u8;32]` |
| `payload_mutation_replace_with_len` | 752 | 8 | `u64` |
| `payload_mutation_swap_pos1` | 760 | 8 | `u64` |
| `payload_mutation_swap_pos2` | 768 | 8 | `u64` |
| `payload_mutation_min_size` | 776 | 8 | `u64` |
| `payload_mutation_max_size` | 784 | 8 | `u64` |
| `payload_mutation_every_n_packets` | 792 | 8 | `u64` |
| `payload_mutation_dry_run` | 800 | 8 | `u64` (`0/1`) |
| `payload_mutation_max_buffer_size` | 808 | 8 | `u64` |
| `payload_mutation_reserved` | 816 | 64 | `[u64;8]` |

Constants:
- `FAULTCORE_MAGIC = 0xFACC0DE`
- `CONFIG_SIZE = 880`
- `MAX_FDS = 131072`
- `MAX_TIDS = 65536`
- `MAX_POLICIES = 1024`
- `MAX_TARGET_RULES_PER_TID = 8`

### Payload Mutation Notes

- Mutation is applied only on stream operations (`send*`/`recv*`) and never on `connect` or DNS resolution.
- Uplink mutation is evaluated before the send syscall and reorder staging stores the mutated payload.
- Downlink mutation is evaluated after the recv syscall using only the received byte span.
- If mutation cannot be applied (invalid params, out-of-bounds, size gate, `dry_run`), payload is preserved.
- `payload_mutation_reserved` keeps ABI space for future additions without immediate row-size change.

## Target Rules Region

`TargetRule` is a fixed 152-byte row stored in a per-TID-slot table:

| Field | Type | Notes |
|---|---|---|
| `enabled` | `u64` | `0/1` |
| `priority` | `u64` | Higher wins |
| `kind` | `u64` | `1=host`, `2=cidr` |
| `ipv4` | `u64` | IPv4 address (lower 32 bits) |
| `prefix_len` | `u64` | CIDR prefix (`0..32`) |
| `port` | `u64` | `0` means any |
| `protocol` | `u64` | `0=any`, `1=tcp`, `2=udp` |
| `reserved` | `u64` | reserved |
| `address_family` | `u64` | `0=unset`, `1=ipv4`, `2=ipv6` |
| `addr` | `[u8;16]` | unified IP bytes (network order) |
| `hostname` | `[u8;32]` | normalized hostname buffer (NUL padded, final vNext size) |
| `sni` | `[u8;32]` | normalized SNI buffer (NUL padded, final vNext size) |

Selection semantics for `targets[]`:
- consider first `target_enabled` rules;
- choose matching rule with greatest `priority`;
- ties are resolved by first rule in registration order.

## Write/Read Consistency
- All SHM writers (Python and Rust) use `ruleset_generation` as the optimistic publish marker:
  - mark `ruleset_generation` as odd during write;
  - write `magic` + payload;
  - publish `ruleset_generation` as even when done.
- Rust readers validate stable reads using a double-read of `ruleset_generation` plus fences.

### Consistency Sequence Diagram

```mermaid
sequenceDiagram
    participant Py as Python writer
    participant SHM as SHM row
    participant Rs as Rust reader

    Py->>SHM: set ruleset_generation = odd
    Py->>SHM: write magic + payload
    Py->>SHM: set ruleset_generation = even

    Rs->>SHM: read generation_before
    Rs->>SHM: read payload
    Rs->>SHM: read generation_after
    alt stable even snapshot
        Rs-->>Rs: accept row
    else changed or odd
        Rs-->>Rs: retry read
    end
```

Diagram focus: odd/even publish protocol over `ruleset_generation` and reader stability check.

## Compatibility Rule
Any change in offsets/size must:
1. update this document,
2. update Python and Rust together,
3. keep SHM contract tests green.

### Compatibility Update Flow

```mermaid
flowchart TD
    Change["Offset/size change proposed"] --> Doc["Update docs/shm_protocol.md"]
    Doc --> Code["Update Python writer + Rust contract/runtime"]
    Code --> Tests["Run SHM contract tests"]
    Tests --> Gate{"Tests green?"}
    Gate -->|Yes| Merge["Safe to merge"]
    Gate -->|No| Fix["Fix layout mismatch and re-test"]
    Fix --> Tests
```

Diagram focus: mandatory synchronization path for SHM schema changes.

## Runtime Model over SHM

The SHM layout is stable, and runtime consumption is consolidated:

- The engine builds `PacketContext` by operation (`Connect`, `Send`, `Recv`, `DnsLookup`).
- The FaultOSI pipeline applies layers in fixed OSI order `L1..L7`.
- All fault decisions flow through a single `LayerDecision` enum.
- The interceptor only maps `LayerDecision` to return values/errno (`syscalls` and `getaddrinfo`).

This reduces duplicated logic between engine/interceptor and keeps behavior verifiable through mapping tests.

For module-level ownership and dataflow, see `docs/architecture.md`.
