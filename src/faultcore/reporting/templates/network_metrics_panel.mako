<%def name="kpi_card(label, value)"><div class='network-kpi-card'>
  <div class='network-kpi-label'>${label}</div>
  <div class='network-kpi-value'>${value}</div>
</div></%def>
<%def name="metric_row(key, value, max_value)"><%
width_pct = min(96.0, (abs(value) / max_value) * 96.0) if max_value else 0
width_str = "{:.2f}".format(width_pct)
%><div class='metric-row'>
  <div class='metric-name'>${key}</div>
  <div class='metric-track'>
    <div class='metric-fill' style='width:${width_str}%'></div>
  </div>
  <div class='metric-value'>${value}</div>
</div></%def>
<%def name="metric_group(name, items, max_value)"><div class='metric-group'>
  <div class='metric-group-title'>${name}</div>
  ${''.join(metric_row(k, v, max_value) for k, v in items)}
</div></%def>
<%def name="render_kpis(kpis)">${''.join(kpi_card(label, value) for label, value in kpis)}</%def>
<%def name="render_groups(groups)">${''.join(metric_group(name, items, max(abs(v) for _, v in items) if items else 1) for name, items in groups)}</%def>
<%def name="network_metrics_panel(kpis, groups)"><div class='network-metrics-panel'>
  <div class='network-kpi-grid'>${render_kpis(kpis)}</div>
  <div class='metric-groups-grid-wrap'>${render_groups(groups)}</div>
</div></%def>
