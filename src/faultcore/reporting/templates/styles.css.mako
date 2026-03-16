<%
css_status = 'var(--ok)' if status == 'passed' else 'var(--bad)'
%>:root {
  --bg: #12110d;
  --panel: #1f1c14;
  --text: #f2e7c9;
  --muted: #b8aa88;
  --ok: #6bc46d;
  --bad: #de6f6f;
  --warn: #d2b35a;
  --info: #68a7db;
  --border: #463e2c;
}
body {
  margin: 0;
  font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  height: 100vh;
  overflow: hidden;
  overscroll-behavior: none;
}
html {
  height: 100%;
  overflow: hidden;
  overscroll-behavior: none;
}
main {
  display: flex;
  flex-direction: column;
  height: 100vh;
  min-height: 0;
  padding: 4px;
  position: relative;
  z-index: 1;
  box-sizing: border-box;
}
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 5px 8px;
  margin: 0;
}
.tab-btn {
  background: #17150f;
  border: 1px solid var(--border);
  color: var(--muted);
  padding: 4px 8px;
  cursor: pointer;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  font-size: 11px;
  line-height: 1.2;
}
.tab-btn.active {
  color: var(--text);
  border-color: #8a7a57;
  background: #1d1a13;
}
.tab-panel {
  display: none;
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 8px 10px;
  margin: 0;
}
#overview {
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 8px 10px;
  margin: 0;
}
.tab-panel.active {
  display: block;
}
.tab-panel-timeline.active {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 210px);
}
.status { font-weight: 700; color: ${css_status}; }
.muted { color: var(--muted); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border: 1px solid var(--border); padding: 6px; text-align: left; vertical-align: top; }
.events-table-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--border);
  background: #17150f;
}
.events-table-wrap table {
  margin: 0;
  border: 0;
}
.events-table-wrap thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #1a1712;
}
.outputs-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  min-height: 0;
}
.output-panel {
  border: 1px solid var(--border);
  background: #17150f;
  padding: 6px;
  min-height: 0;
  overflow: auto;
}
.output-panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10px;
  color: #cdbb8e;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 6px;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}
.output-badge {
  border: 1px solid #5a4d31;
  padding: 0 5px;
  color: #e5d4ad;
  background: #1a1711;
  font-size: 10px;
}
.output-list {
  margin: 0;
  padding-left: 18px;
  font-size: 11px;
  color: #e2d4b2;
}
.logs-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 16px;
  min-height: 0;
}
.log-panel {
  border: 1px solid var(--border);
  background: #17150f;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.log-title {
  font-size: 10px;
  color: #cdbb8e;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 5px 6px;
  border-bottom: 1px solid var(--border);
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}
.log-panel pre {
  margin: 0;
  border: 0;
  background: transparent;
  padding: 6px;
  max-height: 260px;
  overflow: auto;
  font-size: 10px;
  line-height: 1.3;
}
pre {
  white-space: pre-wrap;
  word-break: break-word;
  background: #17150f;
  border: 1px solid var(--border);
  padding: 10px;
}
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}
.controls input, .controls select, .controls button {
  background: #17150f;
  color: var(--text);
  border: 1px solid var(--border);
  padding: 6px 8px;
}
.compact-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 6px;
}
.compact-card {
  border: 1px solid var(--border);
  background: #17150f;
  padding: 5px;
  font-size: 11px;
  line-height: 1.25;
}
.compact-card-context {
  font-size: 10px;
  line-height: 1.25;
}
.compact-card-context code {
  font-size: 10px;
  color: #dec89a;
  word-break: break-word;
}
.network-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: 6px;
  margin-bottom: 8px;
}
.network-kpi-card {
  border: 1px solid var(--border);
  background: #17150f;
  padding: 5px 6px;
}
.network-kpi-label {
  font-size: 10px;
  color: var(--muted);
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.network-kpi-value {
  font-size: 13px;
  color: #f2e7c9;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}
.metric-groups-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(300px, 1fr));
  gap: 8px;
}
.metric-groups-balanced {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  align-items: stretch;
  margin-bottom: 8px;
}
.metric-left-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
}
.metric-right-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
}
.metric-left-stack .metric-group,
.metric-right-stack .metric-group {
  height: 100%;
  box-sizing: border-box;
}
.metric-group {
  border: 1px solid var(--border);
  background: #17150f;
  padding: 6px;
}
.metric-group-title {
  font-size: 10px;
  text-transform: uppercase;
  color: #c6b588;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  margin-bottom: 4px;
}
.metric-row {
  display: grid;
  grid-template-columns: 180px 1fr 130px;
  gap: 6px;
  align-items: center;
  margin: 3px 0;
}
.metric-name {
  font-size: 10px;
  color: var(--muted);
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}
.metric-track {
  height: 8px;
  border: 1px solid var(--border);
  background: #14120e;
}
.metric-fill {
  height: 100%;
  background: #7c6a42;
  box-shadow: inset 0 0 0 1px #5e5134;
}
.metric-value {
  text-align: right;
  font-size: 10px;
  color: #e2d3b2;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}
.chart-wrap {
  position: relative;
  overflow: visible;
  width: 100%;
}
.metric-chart {
  margin: 4px 0 8px;
}
.chart-inline-title {
  position: absolute;
  z-index: 3;
  display: inline-flex;
  top: 6px;
  left: 8px;
  padding: 1px 5px;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  font-size: 10px;
  line-height: 1.2;
  color: #e7d8b4;
  background: rgba(19, 17, 12, 0.9);
  border: 1px solid #4b412e;
}
.multi-legend {
  position: absolute;
  top: 24px;
  right: 8px;
  z-index: 3;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
  max-width: 60%;
}
.multi-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 4px;
  border: 1px solid #4b412e;
  background: rgba(19, 17, 12, 0.85);
  font-size: 9px;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  color: #e7d8b4;
  text-transform: uppercase;
}
.multi-mode {
  position: absolute;
  top: 6px;
  right: 8px;
  left: auto;
  z-index: 3;
  padding: 1px 4px;
  border: 1px solid #4b412e;
  background: rgba(19, 17, 12, 0.85);
  font-size: 9px;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  color: #c7b68b;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.multi-legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 1px;
  display: inline-block;
}
svg {
  display: block;
}
.chart-tooltip {
  position: absolute;
  top: 8px;
  left: 8px;
  display: none;
  z-index: 9999;
  pointer-events: none;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  font-size: 11px;
  color: #f2e7c9;
  background: rgba(20, 17, 12, 0.95);
  border: 1px solid var(--border);
  padding: 1px 5px;
  white-space: nowrap;
  max-width: min(85vw, 760px);
  overflow: hidden;
  text-overflow: ellipsis;
}
.chart-inspector {
  display: none;
  margin-top: 4px;
  border: 1px solid var(--border);
  background: #16140f;
  padding: 4px 6px;
  font-size: 10px;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  color: #dccca7;
  white-space: pre-wrap;
  line-height: 1.35;
}
.kv-list {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
}
.kv-list li {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px dotted #3e3728;
  padding: 1px 0;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  font-size: 10px;
  color: #d8c9a8;
  word-break: break-word;
}
code { font-family: "JetBrains Mono", "Cascadia Mono", monospace; color: #f6ddb2; }
details {
  border: 1px solid var(--border);
  padding: 8px;
  margin: 6px 0;
  background: #1a1712;
}
summary {
  cursor: pointer;
  font-weight: 600;
}
.site-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(160px, 1fr));
  gap: 10px;
}
.details-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--bg);
  padding: 2px 0 6px;
}
.details-toolbar input, .details-toolbar select, .details-toolbar button {
  background: #17150f;
  color: var(--text);
  border: 1px solid var(--border);
  padding: 4px 6px;
  font-size: 11px;
}
.details-toolbar .count {
  color: var(--muted);
  font-size: 10px;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}
.details-stack {
  border: 1px solid var(--border);
  padding: 6px;
  background: #17150f;
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.details-column-title {
  font-size: 10px;
  color: #cdbb8e;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 6px;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}
.tab-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  margin-top: 0;
}
.tab-content .tab-panel.active {
  height: 100%;
  box-sizing: border-box;
  overflow: auto;
  overscroll-behavior: contain;
}
#site-details.tab-panel.active {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
h2 {
  margin: 0 0 6px;
  font-size: 18px;
}
h3 {
  margin: 6px 0 4px;
  font-size: 14px;
}
@media (max-width: 900px) {
  .tabs { position: static; }
  .site-grid { grid-template-columns: 1fr; }
  .compact-grid { grid-template-columns: 1fr; }
  .network-kpi-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
  .metric-groups-grid { grid-template-columns: 1fr; }
  .metric-groups-balanced { grid-template-columns: 1fr; }
  .metric-row { grid-template-columns: 1fr; }
  .outputs-grid { grid-template-columns: 1fr; }
  .logs-grid { grid-template-columns: 1fr; }
  .tab-panel-timeline.active { min-height: 60vh; }
}
