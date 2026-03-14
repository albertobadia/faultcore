import html
import json
from pathlib import Path
from typing import Any

from mako.template import Template

from .core import apply_event_view

_REPORT_TEMPLATE_PATH = Path(__file__).parent / "templates" / "report_page.mako"
_REPORT_PAGE_TEMPLATE = Template(filename=str(_REPORT_TEMPLATE_PATH), input_encoding="utf-8")
_NO_DATA_HTML = "<div class='muted'>No data</div>"
_PROTOCOL_ORDER = ("tcp", "udp", "http", "total")


def _render_line_chart_svg(
    values: list[int], *, width: int = 760, height: int = 120, stroke: str = "#68a7db", title: str = ""
) -> str:
    values = _normalize_chart_series(values)
    if not values:
        return _NO_DATA_HTML
    if len(values) == 1:
        values = [values[0], values[0]]
    min_v = min(values)
    max_v = max(values)
    scale = (max_v - min_v) or 1
    points: list[str] = []
    span = max(1, len(values) - 1)
    for idx, value in enumerate(values):
        x = int((idx / span) * (width - 20)) + 10
        y_norm = (value - min_v) / scale
        y = int((1 - y_norm) * (height - 20)) + 10
        points.append(f"{x},{y}")
    points_attr = " ".join(points)
    values_attr = html.escape(",".join(str(value) for value in values))
    series_name_attr = html.escape(title, quote=True)
    title_html = f"<div class='chart-inline-title'>{_safe(title)}</div>" if title else ""
    return (
        "<div class='chart-wrap'>"
        f"{title_html}"
        f"<svg viewBox='0 0 {width} {height}' preserveAspectRatio='none' "
        f"width='100%' height='{height}' role='img' aria-label='line chart' "
        f"data-series-name='{series_name_attr}' data-series-values='{values_attr}' "
        f"data-min='{min_v}' data-max='{max_v}' data-width='{width}' "
        f"data-height='{height}'>"
        "<rect x='0' y='0' width='100%' height='100%' fill='#17150f'/>"
        f"<polyline fill='none' stroke='{stroke}' stroke-width='2' points='{points_attr}'/>"
        f"<line class='chart-hover-line' x1='0' y1='10' x2='0' y2='{height - 10}' stroke='#b7a982' stroke-width='1' "
        "stroke-dasharray='3 3' visibility='hidden'/>"
        "<circle class='chart-hover-dot' cx='0' cy='0' r='3.5' fill='#efe0b8' "
        "stroke='#17150f' stroke-width='1' visibility='hidden'/>"
        "</svg>"
        "<div class='chart-tooltip' aria-hidden='true'></div>"
        "<div class='chart-inspector' aria-live='polite'></div>"
        "</div>"
    )


def _render_metric_chart(title: str, values: list[int], *, stroke: str = "#68a7db") -> str:
    return f"<div class='metric-chart'>{_render_line_chart_svg(values, stroke=stroke, title=title)}</div>"


def _render_multi_line_chart_svg(
    series_map: dict[str, list[int]], *, width: int = 760, height: int = 120, title: str = ""
) -> str:
    if not series_map:
        return _NO_DATA_HTML
    normalized_series = {key: coerced for key, values in series_map.items() if (coerced := _coerce_int_series(values))}
    if not normalized_series:
        return _NO_DATA_HTML

    min_v = min(min(values) for values in normalized_series.values())
    max_v = max(max(values) for values in normalized_series.values())
    scale = (max_v - min_v) or 1
    ranges = [max(values) - min(values) for values in normalized_series.values()]
    non_zero_ranges = [value for value in ranges if value > 0]
    max_range = max(non_zero_ranges) if non_zero_ranges else 0
    min_range = min(non_zero_ranges) if non_zero_ranges else 0
    should_normalize = bool(non_zero_ranges and min_range > 0 and (max_range / min_range) >= 8.0)
    max_len = max(len(values) for values in normalized_series.values())
    span = max(1, max_len - 1)
    palette = {
        "tcp": "#68a7db",
        "udp": "#6bc46d",
        "http": "#d2b35a",
        "total": "#de6f6f",
    }
    fallback_palette = ["#9ac0ff", "#84d487", "#e9a96d", "#d98b8b"]
    fallback_idx = 0
    polylines: list[str] = []
    legend_items: list[str] = []

    for name, values in sorted(normalized_series.items()):
        color, fallback_idx = _resolve_series_color(name, palette, fallback_palette, fallback_idx)
        points: list[str] = []
        line_min = min(values)
        line_max = max(values)
        line_scale = (line_max - line_min) or 1
        for idx, value in enumerate(values):
            x = int((idx / span) * (width - 20)) + 10
            if should_normalize:
                y_norm = (value - line_min) / line_scale
            else:
                y_norm = (value - min_v) / scale
            y = int((1 - y_norm) * (height - 20)) + 10
            points.append(f"{x},{y}")
        polylines.append(f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{' '.join(points)}'/>")
        legend_items.append(
            "<span class='multi-legend-item'>"
            f"<span class='multi-legend-dot' style='background:{color}'></span>{_safe(name)}"
            "</span>"
        )

    mode_html = "<div class='multi-mode'>normalized</div>" if should_normalize else ""
    title_html = f"<div class='chart-inline-title'>{_safe(title)}</div>" if title else ""
    multi_series_attr = html.escape(json.dumps(normalized_series, ensure_ascii=True), quote=True)
    series_name_attr = html.escape(title, quote=True)
    return (
        "<div class='chart-wrap'>"
        f"{title_html}"
        f"{mode_html}"
        "<div class='multi-legend'>"
        f"{''.join(legend_items)}"
        "</div>"
        f"<svg viewBox='0 0 {width} {height}' preserveAspectRatio='none' "
        f"width='100%' height='{height}' role='img' aria-label='multi line chart' "
        f"data-series-name='{series_name_attr}' data-multi-series='{multi_series_attr}' "
        f"data-width='{width}' data-height='{height}'>"
        "<rect x='0' y='0' width='100%' height='100%' fill='#17150f'/>"
        f"{''.join(polylines)}"
        f"<line class='chart-hover-line' x1='0' y1='10' x2='0' y2='{height - 10}' stroke='#b7a982' stroke-width='1' "
        "stroke-dasharray='3 3' visibility='hidden'/>"
        "</svg>"
        "<div class='chart-tooltip' aria-hidden='true'></div>"
        "<div class='chart-inspector' aria-live='polite'></div>"
        "</div>"
    )


def _render_multi_metric_chart(title: str, series_map: dict[str, list[int]]) -> str:
    return f"<div class='metric-chart'>{_render_multi_line_chart_svg(series_map, title=title)}</div>"


def _render_series_charts(series_map: dict[str, list[int]]) -> str:
    if not series_map:
        return ""
    filtered_series = {name: values for name, values in series_map.items() if "bytes_cumulative" not in name.lower()}
    if not filtered_series:
        return ""
    series_chart_blocks: list[str] = []
    grouped: dict[str, dict[str, tuple[str, list[int]]]] = {}
    for series_name, values in filtered_series.items():
        proto_and_base = _split_protocol_series_name(series_name)
        if not proto_and_base:
            continue
        proto, base = proto_and_base
        grouped.setdefault(base, {})[proto] = (series_name, values)

    consumed: set[str] = set()
    for base_name, proto_map in sorted(grouped.items()):
        if len(proto_map) < 2:
            continue
        chart_series: dict[str, list[int]] = {}
        for proto in _PROTOCOL_ORDER:
            if proto in proto_map:
                original_name, proto_values = proto_map[proto]
                chart_series[proto] = proto_values
                consumed.add(original_name)
        pretty_title = base_name.replace("_", " ")
        series_chart_blocks.append(_render_multi_metric_chart(pretty_title, chart_series))

    palette = ["#68a7db", "#6bc46d", "#d2b35a", "#de6f6f", "#9ac0ff", "#e9a96d"]
    palette_idx = 0
    for series_name, values in sorted(filtered_series.items()):
        if series_name in consumed:
            continue
        color = palette[palette_idx % len(palette)]
        palette_idx += 1
        series_chart_blocks.append(_render_metric_chart(series_name, values, stroke=color))
    return "".join(series_chart_blocks)


def _normalize_series_units(series_name: str, values: list[int]) -> list[int]:
    lowered = series_name.lower()
    if not values:
        return values
    if "ms" in lowered:
        non_zero = [abs(value) for value in values if value != 0]
        if non_zero:
            sorted_vals = sorted(non_zero)
            median = sorted_vals[len(sorted_vals) // 2]
            if median >= 100_000:
                return [int(round(value / 1_000_000.0)) for value in values]
    return values


def _normalize_chart_series(values: list[int]) -> list[int]:
    if not values:
        return []
    normalized = _coerce_int_series(values)
    first_non_zero_idx = next((idx for idx, value in enumerate(normalized) if value != 0), 0)
    if first_non_zero_idx > 0:
        normalized = normalized[first_non_zero_idx:]
    normalized = _trim_initial_warmup_outlier(normalized)
    return normalized


def _coerce_int_series(values: list[Any]) -> list[int]:
    return [_int_or_zero(item) for item in values]


def _coerce_optional_int_series(values: Any) -> list[int]:
    return _coerce_int_series(values) if isinstance(values, list) else []


def _coerce_rounded_int_series(values: Any) -> list[int]:
    return [_rounded_int_or_zero(item) for item in values] if isinstance(values, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _rounded_int_or_zero(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _split_protocol_series_name(series_name: str) -> tuple[str, str] | None:
    lowered = series_name.lower()
    for candidate in ("tcp_", "udp_", "http_", "total_"):
        if not lowered.startswith(candidate):
            continue
        base = series_name[len(candidate) :]
        if base.endswith("_series"):
            base = base[: -len("_series")]
        return candidate[:-1], base
    return None


def _resolve_series_color(
    name: str,
    palette: dict[str, str],
    fallback_palette: list[str],
    fallback_idx: int,
) -> tuple[str, int]:
    key = name.lower()
    for proto, proto_color in palette.items():
        if key.startswith(proto):
            return proto_color, fallback_idx
    color = fallback_palette[fallback_idx % len(fallback_palette)]
    return color, fallback_idx + 1


def _trim_initial_warmup_outlier(values: list[int]) -> list[int]:
    if len(values) < 5:
        return values
    window = values[1 : min(len(values), 11)]
    if not window:
        return values
    sorted_window = sorted(window)
    median = sorted_window[len(sorted_window) // 2]
    if median == 0:
        return values
    first = values[0]
    deviation = abs(first - median) / abs(median)
    spread = (max(window) - min(window)) / abs(median)
    if deviation >= 0.08 and spread <= 0.12:
        return values[1:]
    return values


def _safe(value: Any) -> str:
    return html.escape(str(value))


def _sum_series_by_index(series_by_name: dict[str, list[int]]) -> list[int]:
    if not series_by_name:
        return []
    max_len = max(len(values) for values in series_by_name.values())
    return [
        sum(values[idx] if idx < len(values) else 0 for values in series_by_name.values()) for idx in range(max_len)
    ]


def _render_kpi_card(label: str, value: str) -> str:
    return (
        "<div class='network-kpi-card'>"
        f"<div class='network-kpi-label'>{_safe(label)}</div>"
        f"<div class='network-kpi-value'>{_safe(value)}</div>"
        "</div>"
    )


def _render_event_rows(events: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for event in events:
        details = event.get("details", {})
        details_str = json.dumps(details, ensure_ascii=True) if isinstance(details, dict) else str(details)
        rows.append(
            "<tr>"
            f"<td>{_safe(event.get('ts', ''))}</td>"
            f"<td>{_safe(event.get('severity', ''))}</td>"
            f"<td>{_safe(event.get('type', ''))}</td>"
            f"<td>{_safe(event.get('source', ''))}</td>"
            f"<td>{_safe(event.get('name', ''))}</td>"
            f"<td><code>{_safe(details_str)}</code></td>"
            "</tr>"
        )
    return "\n".join(rows) or "<tr><td colspan='6'>No events</td></tr>"


def _metric_group_for_key(key: str) -> str:
    lowered = key.lower()
    if "throughput" in lowered or "bytes" in lowered:
        return "Traffic"
    if "latency" in lowered or "jitter" in lowered:
        return "Latency/Jitter"
    if "events" in lowered or lowered.endswith("_count"):
        return "Events/Counters"
    return "Other"


def _format_metric_value(key: str, value: float) -> str:
    lowered = key.lower()
    if lowered.endswith("_ns"):
        return f"{int(value):,} ns"
    if lowered.endswith("_ms") or "jitter" in lowered or "latency" in lowered:
        return f"{value:.3f} ms" if abs(value) < 1000 else f"{value:,.2f} ms"
    if lowered.endswith("_bps") or "throughput" in lowered:
        return f"{int(value):,} bps"
    if "bytes" in lowered:
        return f"{int(value):,} B"
    if value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.3f}"


def _render_network_metrics_panel(
    metrics: dict[str, Any],
    *,
    max_items_per_group: int = 12,
    group_limits_override: dict[str, int] | None = None,
    balanced_layout: bool = False,
) -> str:
    if not isinstance(metrics, dict) or not metrics:
        return "<p class='muted'>No network metrics captured</p>"
    numeric_items = [
        (str(key), float(value))
        for key, value in metrics.items()
        if not isinstance(value, bool) and isinstance(value, (int, float))
    ]
    if not numeric_items:
        return "<p class='muted'>No numeric metrics captured</p>"
    metric_map = dict(numeric_items)
    kpi_order = [
        ("total_throughput_bps", "Throughput"),
        ("total_bytes", "Bytes"),
        ("throughput_bps", "Throughput"),
        ("bytes_total", "Bytes"),
        ("recorded_events_total", "Recorded Events"),
        ("fault_events_total", "Fault Events"),
        ("total_events", "Events"),
        ("fault_events", "Fault Events"),
        ("latency_p95_ns", "P95 Latency"),
        ("latency_p95_ms", "P95 Latency"),
        ("latency_avg_ms", "Avg Latency"),
        ("jitter_ms", "Jitter"),
        ("tcp_latency_avg_ms", "TCP Avg"),
        ("udp_latency_avg_ms", "UDP Avg"),
        ("http_latency_avg_ms", "HTTP Avg"),
    ]
    kpi_cards: list[str] = []
    for metric_key, label in kpi_order:
        if metric_key not in metric_map:
            continue
        kpi_cards.append(_render_kpi_card(label, _format_metric_value(metric_key, metric_map[metric_key])))
    if not kpi_cards:
        fallback_items = sorted(metric_map.items(), key=lambda kv: abs(kv[1]), reverse=True)[:4]
        for key, value in fallback_items:
            kpi_cards.append(_render_kpi_card(key, _format_metric_value(key, value)))

    grouped: dict[str, list[tuple[str, float]]] = {}
    for key, value in numeric_items:
        group = _metric_group_for_key(key)
        grouped.setdefault(group, []).append((key, value))

    group_order = ["Traffic", "Latency/Jitter", "Events/Counters", "Other"]
    group_limits = {
        "Latency/Jitter": max(4, min(max_items_per_group, 6)),
        "Other": max(4, min(max_items_per_group, 6)),
    }
    if isinstance(group_limits_override, dict):
        for group_name, group_limit in group_limits_override.items():
            try:
                parsed_limit = int(group_limit)
            except (TypeError, ValueError):
                continue
            group_limits[str(group_name)] = max(1, parsed_limit)
    group_blocks: list[str] = []
    group_block_map: dict[str, str] = {}
    for group_name in group_order:
        items = grouped.get(group_name, [])
        if not items:
            continue
        limit = group_limits.get(group_name, max_items_per_group)
        items = sorted(items, key=lambda kv: abs(kv[1]), reverse=True)[:limit]
        local_max = max(abs(value) for _, value in items) or 1.0
        rows: list[str] = []
        for key, value in items:
            width_pct = min(96.0, (abs(value) / local_max) * 96.0)
            rows.append(
                "<div class='metric-row'>"
                f"<div class='metric-name'>{_safe(key)}</div>"
                "<div class='metric-track'>"
                f"<div class='metric-fill' style='width:{width_pct:.2f}%'></div>"
                "</div>"
                f"<div class='metric-value'>{_safe(_format_metric_value(key, value))}</div>"
                "</div>"
            )
        group_html = (
            f"<div class='metric-group'><div class='metric-group-title'>{_safe(group_name)}</div>{''.join(rows)}</div>"
        )
        group_blocks.append(group_html)
        group_block_map[group_name] = group_html

    groups_html = "".join(group_blocks)
    if balanced_layout and "Events/Counters" in group_block_map:
        left_blocks: list[str] = []
        for name in ("Latency/Jitter", "Other"):
            block = group_block_map.get(name)
            if block:
                left_blocks.append(block)
        if left_blocks:
            consumed = {"Events/Counters", "Latency/Jitter", "Other"}
            rest_blocks = [
                group_block_map[name] for name in group_order if name in group_block_map and name not in consumed
            ]
            rest_html = "<div class='metric-groups-grid'>" + "".join(rest_blocks) + "</div>" if rest_blocks else ""
            groups_html = (
                "<div class='metric-groups-balanced'>"
                "<div class='metric-left-stack'>"
                f"{''.join(left_blocks)}"
                "</div>"
                "<div class='metric-right-single'>"
                f"{group_block_map['Events/Counters']}"
                "</div>"
                "</div>"
                f"{rest_html}"
            )

    kpi_html = "".join(kpi_cards) or "<div class='muted'>No KPI metrics</div>"
    return (
        "<div class='network-metrics-panel'>"
        f"<div class='network-kpi-grid'>{kpi_html}</div>"
        f"<div class='metric-groups-grid-wrap'>{groups_html}</div>"
        "</div>"
    )


def _render_site_details(site_metrics: dict[str, Any], *, run_duration_ms: int = 0) -> str:
    if not isinstance(site_metrics, dict) or not site_metrics:
        return "<p class='muted'>No per-site metrics captured</p>"
    blocks: list[str] = []
    ordered_sites = sorted(
        site_metrics.items(),
        key=lambda kv: int(kv[1].get("fault_events", 0)) if isinstance(kv[1], dict) else 0,
        reverse=True,
    )
    for site_name, raw_data in ordered_sites:
        if not isinstance(raw_data, dict):
            continue
        decision_counts = _as_dict(raw_data.get("decision_counts", {}))
        delay_values = _coerce_optional_int_series(raw_data.get("delay_series_ns", []))
        fault_flag_values = _coerce_optional_int_series(raw_data.get("fault_flag_series", []))
        continue_flag_values = _coerce_optional_int_series(raw_data.get("continue_flag_series", []))
        events_per_bucket_values = _coerce_optional_int_series(raw_data.get("events_per_bucket", []))
        fault_bucket_values = _coerce_optional_int_series(raw_data.get("fault_events_per_bucket", []))
        continue_bucket_values = _coerce_optional_int_series(raw_data.get("continue_events_per_bucket", []))
        delay_chart_values = delay_values
        if not delay_chart_values:
            fallback_len = max(
                len(fault_flag_values),
                len(continue_flag_values),
                int(raw_data.get("total_events", 0)),
                1,
            )
            delay_chart_values = [0] * min(fallback_len, 120)
        total_events = int(raw_data.get("total_events", 0))
        event_rate_eps = (total_events * 1000.0 / run_duration_ms) if run_duration_ms > 0 else 0.0
        site_panel_metrics = {
            "total_events": total_events,
            "fault_events": int(raw_data.get("fault_events", 0)),
            "continue_count": int(raw_data.get("continue_events", 0)),
            "fault_rate_pct": float(raw_data.get("fault_rate_pct", 0.0)),
            "event_rate_eps": float(round(event_rate_eps, 2)),
            "delay_avg_ns": int(raw_data.get("delay_avg_ns", 0)),
            "latency_p50_ns": int(raw_data.get("latency_p50_ns", 0)),
            "latency_p95_ns": int(raw_data.get("latency_p95_ns", 0)),
            "latency_p99_ns": int(raw_data.get("latency_p99_ns", 0)),
            "delay_count": int(decision_counts.get("delay_ns", 0)),
            "drop_count": int(decision_counts.get("drop", 0)),
            "timeout_count": int(decision_counts.get("timeout_ms", 0)),
            "duplicate_count": int(decision_counts.get("duplicate", 0)),
            "reorder_count": int(decision_counts.get("stage_reorder", 0)),
        }
        network_panel_html = _render_network_metrics_panel(
            site_panel_metrics,
            max_items_per_group=8,
            group_limits_override={"Latency/Jitter": 3},
            balanced_layout=True,
        )
        decision_flags_html = _render_multi_metric_chart(
            "Decision Flags (0/1)",
            {"fault": fault_flag_values, "continue": continue_flag_values},
        )
        bucket_counters_html = _render_multi_metric_chart(
            "Bucket Counters",
            {
                "events": events_per_bucket_values,
                "fault_events": fault_bucket_values,
                "continue_events": continue_bucket_values,
            },
        )
        blocks.append(
            f"<details class='metric-details site-item' "
            f"data-item-name='{_safe(site_name.lower())}' "
            f"data-fault-events='{_safe(raw_data.get('fault_events', 0))}'>"
            f"<summary><code>{_safe(site_name)}</code> | fault_rate={_safe(raw_data.get('fault_rate_pct', 0.0))}% | "
            f"fault_events={_safe(raw_data.get('fault_events', 0))}</summary>"
            f"{network_panel_html}"
            f"{_render_metric_chart('Delay Timeline (ns)', delay_chart_values, stroke='#8dd0a8')}"
            f"{decision_flags_html}"
            f"{bucket_counters_html}"
            "</details>"
        )
    return "".join(blocks) or "<p class='muted'>No per-site metrics captured</p>"


def _render_function_metrics_details(function_metrics: dict[str, Any]) -> str:
    if not isinstance(function_metrics, dict) or not function_metrics:
        return "<p class='muted'>No function-level network metrics captured</p>"
    blocks: list[str] = []
    for func_name, raw_data in sorted(function_metrics.items()):
        if not isinstance(raw_data, dict):
            continue
        timeline_series: dict[str, list[int]] = {}
        latency_values: list[int] = []
        for key, value in raw_data.items():
            if not (isinstance(key, str) and key.startswith("series_") and isinstance(value, list)):
                continue
            series_name = key[len("series_") :]
            numeric_values = _normalize_series_units(series_name, _coerce_rounded_int_series(value))
            timeline_series[series_name] = numeric_values
            if series_name == "latency_ms":
                latency_values = numeric_values
        function_panel_metrics = {
            "throughput_bps": float(raw_data.get("throughput_bps", 0)),
            "bytes_total": float(raw_data.get("bytes_total", 0)),
            "latency_avg_ms": float(raw_data.get("latency_avg_ms", 0)),
            "latency_p95_ms": float(raw_data.get("latency_p95_ms", 0)),
            "jitter_ms": float(raw_data.get("jitter_ms", 0)),
            "total_events": len(latency_values),
        }
        timeline_charts_html = _render_series_charts(timeline_series)
        network_panel_html = _render_network_metrics_panel(
            function_panel_metrics,
            max_items_per_group=8,
            group_limits_override={"Latency/Jitter": 3},
            balanced_layout=True,
        )
        blocks.append(
            f"<details class='metric-details function-item' data-item-name='{_safe(func_name.lower())}' "
            f"data-fault-events='{_safe(raw_data.get('fault_events', 0))}'>"
            "<summary>"
            f"<code>{_safe(func_name)}</code> | "
            f"throughput_bps={_safe(raw_data.get('throughput_bps', 0))}"
            "</summary>"
            f"{network_panel_html}"
            f"{timeline_charts_html}"
            "</details>"
        )
    return "".join(blocks) or "<p class='muted'>No function-level network metrics captured</p>"


def _render_report_html_document(
    run_data: dict[str, Any],
    *,
    max_events: int = 0,
    reverse_events: bool = False,
) -> str:
    raw_events = run_data.get("events", [])
    events = raw_events if isinstance(raw_events, list) else []

    viewed_events, truncated, original_count, order = apply_event_view(
        events,
        max_events=max_events,
        reverse_events=reverse_events,
    )
    run_data["events"] = viewed_events
    run_data["events_truncated"] = truncated
    run_data["events_total_original"] = original_count
    run_data["events_included"] = len(viewed_events)
    run_data["events_order"] = order

    status = run_data.get("status", "unknown")
    tool = _as_dict(run_data.get("tool", {}))
    environment = _as_dict(run_data.get("environment", {}))
    interceptor = _as_dict(run_data.get("interceptor", {}))
    summary = _as_dict(run_data.get("summary", {}))
    faultcore = _as_dict(run_data.get("faultcore", {}))
    scenarios = run_data.get("scenarios", [])
    artifacts = run_data.get("artifacts", [])
    logs_data = _as_dict(run_data.get("logs", {}))
    stdout_tail = str(logs_data.get("stdout_tail", ""))
    stderr_tail = str(logs_data.get("stderr_tail", ""))
    network_metrics = run_data.get("network_metrics", {})
    network_series = run_data.get("network_series", {})
    site_metrics = run_data.get("site_metrics", {})
    function_metrics = run_data.get("function_metrics", {})
    network_metrics_html = _render_network_metrics_panel(network_metrics)
    config_items = "".join(
        (
            f"<li>seed={_safe(faultcore.get('seed', 0))}</li>",
            f"<li>shm_open_mode={_safe(faultcore.get('shm_open_mode', ''))}</li>",
            f"<li>record_replay_mode={_safe(faultcore.get('record_replay_mode', 'off'))}</li>",
            f"<li>interceptor_mode={_safe(interceptor.get('mode', 'none'))}</li>",
            f"<li>interceptor_active={_safe(interceptor.get('active', False))}</li>",
        )
    )
    delay_values = network_series.get("delay_ns", []) if isinstance(network_series, dict) else []
    delay_chart = ""
    if isinstance(delay_values, list) and delay_values:
        delay_chart = _render_metric_chart("Delay (ns)", delay_values, stroke="#d2b35a")
    extra_series: dict[str, list[int]] = {}
    if isinstance(network_series, dict):
        for series_name, series_values in network_series.items():
            if series_name in {"delay_ns", "fault_events_cumulative", "fault_events_per_bucket"}:
                continue
            if not isinstance(series_values, list):
                continue
            extra_series[series_name] = _normalize_series_units(series_name, _coerce_int_series(series_values))
    if isinstance(function_metrics, dict):
        throughput_by_func: dict[str, list[int]] = {}
        for func_name, raw_data in function_metrics.items():
            if not isinstance(raw_data, dict):
                continue
            raw_series = raw_data.get("series_throughput_bps", [])
            if not isinstance(raw_series, list):
                continue
            normalized = _coerce_int_series(raw_series)
            if not normalized:
                continue
            throughput_by_func[f"{func_name}_throughput_bps"] = normalized
        if throughput_by_func:
            throughput_by_func["total_throughput_bps_series"] = _sum_series_by_index(throughput_by_func)
            for series_name, values in sorted(throughput_by_func.items()):
                extra_series[series_name] = values
    extra_charts_html = _render_series_charts(extra_series)
    site_details_html = _render_site_details(site_metrics, run_duration_ms=int(run_data.get("duration_ms", 0) or 0))
    function_details_html = _render_function_metrics_details(function_metrics)
    failures = [
        event
        for event in viewed_events
        if str(event.get("severity", "")).lower() == "error" or "fail" in str(event.get("type", "")).lower()
    ]
    failures_count = len(failures)
    artifacts_count = len(artifacts)
    scenario_compact = (
        ", ".join(
            f"{_safe(item.get('name', 'default'))}:"
            f"{_safe(item.get('status', 'unknown'))}"
            f"({_safe(item.get('duration_ms', 0))}ms)"
            for item in scenarios
        )
        or "none"
    )
    artifact_items = (
        "".join(
            f"<li>{_safe(item.get('kind', 'artifact'))}: <code>{_safe(item.get('path', ''))}</code></li>"
            for item in artifacts
        )
        or "<li>No artifacts</li>"
    )
    failure_items = (
        "".join(
            f"<li>{_safe(item.get('ts', ''))} {_safe(item.get('type', ''))}: {_safe(item.get('name', ''))}</li>"
            for item in failures
        )
        or "<li>No failures/errors in current view</li>"
    )

    duration_ms = _safe(run_data.get("duration_ms", 0))
    events_meta = (
        f"events_included={len(viewed_events)} | "
        f"events_total_original={original_count} | "
        f"events_order={order} | "
        f"events_truncated={str(truncated).lower()}"
    )

    return str(
        _REPORT_PAGE_TEMPLATE.render(
            run_data=run_data,
            viewed_events=viewed_events,
            status=status,
            tool=tool,
            environment=environment,
            interceptor=interceptor,
            summary=summary,
            faultcore=faultcore,
            scenarios=scenarios,
            artifacts=artifacts,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            network_metrics_html=network_metrics_html,
            config_items=config_items,
            delay_chart=delay_chart,
            extra_charts_html=extra_charts_html,
            site_details_html=site_details_html,
            function_details_html=function_details_html,
            failures_count=failures_count,
            artifacts_count=artifacts_count,
            scenario_compact=scenario_compact,
            artifact_items=artifact_items,
            failure_items=failure_items,
            duration_ms=duration_ms,
            events_meta=events_meta,
            safe=_safe,
            render_event_rows=_render_event_rows,
        )
    )


def render_report_html(
    run_data: dict[str, Any],
    *,
    max_events: int = 0,
    reverse_events: bool = False,
) -> str:
    return _render_report_html_document(
        run_data,
        max_events=max_events,
        reverse_events=reverse_events,
    )
