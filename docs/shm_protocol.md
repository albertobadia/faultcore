# Faultcore Shared Memory Protocol

Este documento define el contrato binario compartido entre:
- `src/faultcore/shm_writer.py` (writer Python)
- `faultcore_interceptor/src/shm.rs` (reader/interceptor Rust)

## Segmento
- Nombre: `FAULTCORE_CONFIG_SHM` o `"/faultcore_<pid>_config"`
- Tipo: POSIX SHM (`/dev/shm/...`)
- Tamaño:
  - Tabla de FDs + tabla hash de TIDs: `(MAX_FDS + MAX_TIDS) * CONFIG_SIZE`
  - En el interceptor además se reserva una región para `PolicyState`.

## FaultcoreConfig (152 bytes)
- Endianness: little-endian
- Layout fijo (packed)

| Campo | Offset | Tamaño | Tipo |
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
| `reserved` | 148 | 4 | `u32` |

Constantes:
- `FAULTCORE_MAGIC = 0xFACC0DE`
- `CONFIG_SIZE = 152`
- `MAX_FDS = 131072`
- `MAX_TIDS = 65536`

## Consistencia de escritura/lectura
- Python usa versionado optimista:
  - marca `version` impar durante escritura;
  - escribe `magic` + payload;
  - publica `version` par al finalizar.
- Rust valida lectura estable con doble lectura de `version` y fences.

## Regla de compatibilidad
Todo cambio en offsets/tamaño debe:
1. actualizar este documento,
2. actualizar Python y Rust juntos,
3. mantener tests de contrato en verde.
