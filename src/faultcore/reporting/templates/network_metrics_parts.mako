<%def name="metric_row(key, value, formatted_value, width_pct)"><div class='metric-row'>
  <div class='metric-name'>${key}</div>
  <div class='metric-track'>
    <div class='metric-fill' style='width:${width_pct}%'></div>
  </div>
  <div class='metric-value'>${formatted_value}</div>
</div></%def>
<%def name="metric_group(name, rows)"><div class='metric-group'>
  <div class='metric-group-title'>${name}</div>
  ${rows}
</div></%def>
<%def name="kpi_grid(kpis)">${kpis}</%def>
<%def name="balanced_layout(left_blocks, right_blocks)"><div class='metric-groups-balanced'>
  <div class='metric-left-stack'>
    ${left_blocks}
  </div>
  <div class='metric-right-stack'>
    ${right_blocks}
  </div>
</div></%def>
<%def name="network_metrics_panel(kpi_grid_html, groups_html)"><div class='network-metrics-panel'>
  <div class='network-kpi-grid'>${kpi_grid_html}</div>
  <div class='metric-groups-grid-wrap'>${groups_html}</div>
</div></%def>
<%def name="no_data_message(msg)"><p class='muted'>${msg}</p></%def>
