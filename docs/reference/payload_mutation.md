# payload_mutation

## Signature

```python
faultcore.payload_mutation(
    *,
    enabled: bool,
    prob: str = "100%",
    type: str,
    target: str = "both",
    truncate_size: str | None = None,
    corrupt_count: int | None = None,
    corrupt_seed: str | int | None = None,
    inject_position: int | None = None,
    inject_data: str | bytes | None = None,
    replace_find: str | bytes | None = None,
    replace_with: str | bytes | None = None,
    swap_pos1: int | None = None,
    swap_pos2: int | None = None,
    min_size: str | None = None,
    max_size: str | None = None,
    every_n_packets: int = 1,
    dry_run: bool = False,
    max_buffer_size: str = "64kb",
)
```

## Purpose

Applies deterministic payload mutations for stream send/recv test paths.

## Defaults and validation

- `type` values: `none`, `truncate`, `corrupt_bytes`, `inject_bytes`, `replace_pattern`, `corrupt_encoding`, `swap_bytes`.
- `target` values: `both`, `uplink_only`, `downlink_only`.
- `every_n_packets` must be `>= 0`.
- Byte fields are clipped: `inject_data` max 64 bytes, `replace_find`/`replace_with` max 32 bytes.

## Example (protocol decoder robustness test)

```python
import faultcore


@faultcore.payload_mutation(enabled=True, type="truncate", truncate_size="48b", prob="5%", dry_run=False)
def decode_frame(payload: bytes) -> bool:
    return len(payload) >= 48


def test_decoder_handles_mutated_payload() -> None:
    ok = decode_frame(b"x" * 64)
    assert isinstance(ok, bool)
```
