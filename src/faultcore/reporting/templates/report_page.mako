<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>faultcore report - ${safe(run_data.get('run_id', ''))}</title>
  <style>
    :root {
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
    .status { font-weight: 700; color: ${'var(--ok)' if status == 'passed' else 'var(--bad)'}; }
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
      margin-top: 8px;
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
    }
    .metric-left-stack .metric-group,
    .metric-right-single .metric-group {
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
  </style>
</head>
<body>
  <main>
    <section id="overview">
      <div class="compact-grid">
        <div class="compact-card">
          <strong>Run</strong>
          <div>run_id=${safe(run_data.get('run_id', ''))}</div>
          <div>status=<span class="status">${safe(status)}</span></div>
          <div>duration_ms=${duration_ms}</div>
          <div>started_at=${safe(run_data.get('started_at', ''))}</div>
          <div>ended_at=${safe(run_data.get('ended_at', ''))}</div>
        </div>
        <div class="compact-card compact-card-context">
          <strong>Execution Context</strong>
          <div>command=<code>${safe(' '.join(tool.get('command', [])))}</code></div>
          <div>os/arch=${safe(environment.get('os', ''))}/${safe(environment.get('arch', ''))}</div>
          <div>python=${safe(environment.get('python_version', ''))}</div>
          <div>interceptor_path=<code>${safe(interceptor.get('path', ''))}</code></div>
        </div>
        <div class="compact-card">
          <strong>Fault Summary</strong>
          <div>tests_total=${safe(summary.get('tests_total', 0))}</div>
          <div>tests_passed=${safe(summary.get('tests_passed', 0))}</div>
          <div>tests_failed=${safe(summary.get('tests_failed', 0))}</div>
          <div>errors=${safe(summary.get('errors', 0))}</div>
          <div>fault_events_total=${safe(summary.get('fault_events_total', 0))}</div>
        </div>
        <div class="compact-card">
          <strong>Applied Configuration</strong>
          <ul class="kv-list">${config_items}</ul>
          <div>scenarios=${scenario_compact}</div>
        </div>
      </div>
    </section>
    <div class="tabs" role="tablist" aria-label="Report tabs">
      <button type="button" class="tab-btn active" data-tab-target="charts">Network Timeline</button>
      <button type="button" class="tab-btn" data-tab-target="network">Network Metrics</button>
      <button type="button" class="tab-btn" data-tab-target="site-details">Per Function/Site</button>
      <button type="button" class="tab-btn" data-tab-target="timeline">Decisions Timeline</button>
    </div>
    <div class="tab-content">
      <section id="charts" class="tab-panel active" data-tab-panel="charts">
        ${delay_chart}
        ${extra_charts_html}
      </section>
      <section id="network" class="tab-panel" data-tab-panel="network">
        ${network_metrics_html}
        <div class="outputs-grid">
          <div class="output-panel">
            <div class="output-panel-title">Failures/Errors <span class="output-badge">${safe(failures_count)}</span></div>
            <ul class="output-list">${failure_items}</ul>
          </div>
          <div class="output-panel">
            <div class="output-panel-title">Artifacts <span class="output-badge">${safe(artifacts_count)}</span></div>
            <ul class="output-list">${artifact_items}</ul>
          </div>
        </div>
        <div class="logs-grid">
          <div class="log-panel">
            <div class="log-title">stdout (tail)</div>
            <pre><code>${safe(stdout_tail) if stdout_tail else 'No stdout captured'}</code></pre>
          </div>
          <div class="log-panel">
            <div class="log-title">stderr (tail)</div>
            <pre><code>${safe(stderr_tail) if stderr_tail else 'No stderr captured'}</code></pre>
          </div>
        </div>
      </section>
      <section id="site-details" class="tab-panel" data-tab-panel="site-details">
        <div class="details-toolbar" id="site-details-toolbar">
          <input id="site-search" type="search" placeholder="Search function/site..." />
          <select id="site-kind">
            <option value="">All types</option>
            <option value="function">Functions</option>
            <option value="site">Sites</option>
          </select>
          <select id="site-faults">
            <option value="">All items</option>
            <option value="faults">With faults only</option>
          </select>
          <button id="site-expand-all" type="button">Expand all</button>
          <button id="site-collapse-all" type="button">Collapse all</button>
          <span class="count" id="site-details-count">visible=0</span>
        </div>
        <div class="details-stack">
          <div class="details-column-title">Functions</div>
          ${function_details_html}
          <div class="details-column-title">Sites</div>
          ${site_details_html}
        </div>
      </section>
      <section id="timeline" class="tab-panel tab-panel-timeline" data-tab-panel="timeline">
        <div class="controls" id="events-controls">
          <input id="events-search" type="search" placeholder="Search events..." />
          <select id="events-severity">
            <option value="">All severities</option>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
          </select>
          <input id="events-type" type="search" placeholder="Type contains..." />
          <select id="events-page-size">
            <option value="25">25 / page</option>
            <option value="50" selected>50 / page</option>
            <option value="100">100 / page</option>
            <option value="200">200 / page</option>
          </select>
          <button id="events-prev" type="button">Prev</button>
          <button id="events-next" type="button">Next</button>
          <span class="muted" id="events-page-info">page 1</span>
        </div>
        <div class="events-table-wrap">
          <table>
            <thead><tr><th>ts</th><th>severity</th><th>type</th><th>source</th><th>name</th><th>details</th></tr></thead>
            <tbody id="events-body">
              ${render_event_rows(viewed_events)}
            </tbody>
          </table>
        </div>
      </section>
    </div>
      <script>
          (() => {
            const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
            const toNumber = (value, fallback = 0) => {
              const parsed = Number(value);
              return Number.isFinite(parsed) ? parsed : fallback;
            };
            const xPadding = 10;

            const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
            const tabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));
            const activateTab = (tabId) => {
              tabButtons.forEach((btn) => {
                btn.classList.toggle("active", btn.getAttribute("data-tab-target") === tabId);
              });
              tabPanels.forEach((panel) => {
                panel.classList.toggle("active", panel.getAttribute("data-tab-panel") === tabId);
              });
            };
            tabButtons.forEach((btn) => {
              btn.addEventListener("click", () => {
                const tabId = btn.getAttribute("data-tab-target");
                if (tabId) activateTab(tabId);
              });
            });

            const siteSearch = document.getElementById("site-search");
            const siteKind = document.getElementById("site-kind");
            const siteFaults = document.getElementById("site-faults");
            const siteExpandAll = document.getElementById("site-expand-all");
            const siteCollapseAll = document.getElementById("site-collapse-all");
            const siteCount = document.getElementById("site-details-count");
            const siteDetailItems = Array.from(document.querySelectorAll("#site-details .metric-details"));
            const applySiteFilters = () => {
              const query = (siteSearch?.value || "").trim().toLowerCase();
              const kind = (siteKind?.value || "").trim().toLowerCase();
              const faultsOnly = (siteFaults?.value || "") === "faults";
              let visible = 0;

              siteDetailItems.forEach((item) => {
                const name = (item.getAttribute("data-item-name") || "").toLowerCase();
                const faultEvents = toNumber(item.getAttribute("data-fault-events"), 0);
                const isFunction = item.classList.contains("function-item");
                const isSite = item.classList.contains("site-item");

                const matchesQuery = !query || name.includes(query);
                const matchesKind = (kind !== "function" || isFunction) && (kind !== "site" || isSite);
                const matchesFaults = !faultsOnly || faultEvents > 0;
                const isVisible = matchesQuery && matchesKind && matchesFaults;

                item.style.display = isVisible ? "" : "none";
                if (isVisible) visible += 1;
              });

              if (siteCount) siteCount.textContent = "visible=" + visible;
            };

            siteSearch?.addEventListener("input", applySiteFilters);
            siteKind?.addEventListener("change", applySiteFilters);
            siteFaults?.addEventListener("change", applySiteFilters);
            siteExpandAll?.addEventListener("click", () => {
              siteDetailItems.forEach((item) => {
                if (item.style.display !== "none") item.open = true;
              });
            });
            siteCollapseAll?.addEventListener("click", () => {
              siteDetailItems.forEach((item) => {
                if (item.style.display !== "none") item.open = false;
              });
            });
            applySiteFilters();

            const tbody = document.getElementById("events-body");
            if (!tbody) return;

            const allRows = Array.from(tbody.querySelectorAll("tr"));
            const searchInput = document.getElementById("events-search");
            const severitySelect = document.getElementById("events-severity");
            const typeInput = document.getElementById("events-type");
            const pageSizeSelect = document.getElementById("events-page-size");
            const prevBtn = document.getElementById("events-prev");
            const nextBtn = document.getElementById("events-next");
            const pageInfo = document.getElementById("events-page-info");
            let page = 1;

            const rowText = (row) => (row.textContent || "").toLowerCase();
            const filteredRows = () => {
              const query = (searchInput?.value || "").trim().toLowerCase();
              const severityFilter = (severitySelect?.value || "").trim().toLowerCase();
              const typeQuery = (typeInput?.value || "").trim().toLowerCase();
              return allRows.filter((row) => {
                const cells = row.querySelectorAll("td");
                const severity = (cells[1]?.textContent || "").trim().toLowerCase();
                const type = (cells[2]?.textContent || "").trim().toLowerCase();
                if (severityFilter && severity !== severityFilter) return false;
                if (typeQuery && !type.includes(typeQuery)) return false;
                if (query && !rowText(row).includes(query)) return false;
                return true;
              });
            };

            const renderEvents = () => {
              const rows = filteredRows();
              const pageSize = Math.max(1, parseInt(pageSizeSelect?.value || "50", 10) || 50);
              const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
              page = clamp(page, 1, totalPages);

              const start = (page - 1) * pageSize;
              const pageRows = new Set(rows.slice(start, start + pageSize));
              allRows.forEach((row) => {
                row.style.display = pageRows.has(row) ? "" : "none";
              });

              if (pageInfo) pageInfo.textContent = "page " + page + " / " + totalPages + " | matches=" + rows.length;
              if (prevBtn) prevBtn.disabled = page <= 1;
              if (nextBtn) nextBtn.disabled = page >= totalPages;
            };

            const onFilterChange = () => {
              page = 1;
              renderEvents();
            };

            searchInput?.addEventListener("input", onFilterChange);
            severitySelect?.addEventListener("change", onFilterChange);
            typeInput?.addEventListener("input", onFilterChange);
            pageSizeSelect?.addEventListener("change", onFilterChange);
            prevBtn?.addEventListener("click", () => {
              page -= 1;
              renderEvents();
            });
            nextBtn?.addEventListener("click", () => {
              page += 1;
              renderEvents();
            });
            renderEvents();

            const intFmt = new Intl.NumberFormat("en-US");
            const dec2Fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
            const dec3Fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });

            const humanizeNs = (value) => {
              const absValue = Math.abs(value);
              if (absValue < 1_000) return intFmt.format(Math.round(value)) + "ns";
              if (absValue < 1_000_000) return dec2Fmt.format(value / 1_000) + "us";
              if (absValue < 1_000_000_000) return dec2Fmt.format(value / 1_000_000) + "ms";
              return dec2Fmt.format(value / 1_000_000_000) + "s";
            };
            const humanizeMs = (value) => {
              const absValue = Math.abs(value);
              if (absValue < 1) return dec3Fmt.format(value) + "ms";
              if (absValue < 1_000) return dec2Fmt.format(value) + "ms";
              return dec2Fmt.format(value / 1_000) + "s";
            };
            const humanizeBps = (value) => {
              const absValue = Math.abs(value);
              if (absValue < 1_000) return intFmt.format(Math.round(value)) + "bps";
              if (absValue < 1_000_000) return dec2Fmt.format(value / 1_000) + "Kbps";
              if (absValue < 1_000_000_000) return dec2Fmt.format(value / 1_000_000) + "Mbps";
              return dec2Fmt.format(value / 1_000_000_000) + "Gbps";
            };
            const humanizeBytes = (value) => {
              const absValue = Math.abs(value);
              if (absValue < 1024) return intFmt.format(Math.round(value)) + "B";
              if (absValue < 1024 ** 2) return dec2Fmt.format(value / 1024) + "KiB";
              if (absValue < 1024 ** 3) return dec2Fmt.format(value / (1024 ** 2)) + "MiB";
              return dec2Fmt.format(value / (1024 ** 3)) + "GiB";
            };
            const humanizeBySeries = (seriesName, value) => {
              const name = (seriesName || "").toLowerCase();
              const hasMsToken = /(^|[^a-z])ms([^a-z]|$)/.test(name);
              const hasNsToken = /(^|[^a-z])ns([^a-z]|$)/.test(name);

              if (name.includes("0/1") || name.includes("flag")) return intFmt.format(Math.round(value));
              if (name.includes("rate_pct") || name.includes("percent") || name.includes("%")) return dec2Fmt.format(value) + "%";
              if (name.includes("(ns)") || name.endsWith("_ns") || hasNsToken || name.includes("latency_p") || name.includes("delay")) {
                return humanizeNs(value);
              }
              if (name.includes("(ms)") || name.endsWith("_ms") || hasMsToken || name.includes("jitter")) return humanizeMs(value);
              if (name.includes("bps") || name.includes("throughput")) return humanizeBps(value);
              if (name.includes("byte")) return humanizeBytes(value);
              return intFmt.format(Math.round(value));
            };

            const pointerIndex = (svg, evt, length, width) => {
              const rect = svg.getBoundingClientRect();
              if (!rect.width) return { idx: -1, x: 0, rect };
              const ctm = svg.getScreenCTM();
              if (!ctm) return { idx: -1, x: 0, rect };
              const point = svg.createSVGPoint();
              point.x = evt.clientX;
              point.y = evt.clientY;
              const local = point.matrixTransform(ctm.inverse());
              const xLocal = clamp(local.x, xPadding, width - xPadding);
              const span = Math.max(1, length - 1);
              const ratio = (xLocal - xPadding) / Math.max(1, width - xPadding * 2);
              const idx = clamp(Math.round(ratio * span), 0, length - 1);
              const x = ((idx / span) * (width - xPadding * 2)) + xPadding;
              return { idx, x, rect };
            };

            const attachSingleSeriesChart = (svg) => {
              const wrap = svg.closest(".chart-wrap");
              const tooltip = wrap?.querySelector(".chart-tooltip");
              const inspector = wrap?.querySelector(".chart-inspector");
              if (!tooltip) return;

              const seriesName = svg.getAttribute("data-series-name") || "";
              const values = (svg.getAttribute("data-series-values") || "")
                .split(",")
                .map((item) => Number(item.trim()))
                .filter((item) => Number.isFinite(item));
              if (!values.length) return;

              const minValue = toNumber(svg.getAttribute("data-min"), 0);
              const maxValue = toNumber(svg.getAttribute("data-max"), 0);
              const width = toNumber(svg.getAttribute("data-width"), 760);
              const height = toNumber(svg.getAttribute("data-height"), 150);
              const scale = (maxValue - minValue) || 1;
              const dot = svg.querySelector(".chart-hover-dot");
              const vline = svg.querySelector(".chart-hover-line");
              if (!dot || !vline) return;

              let pinnedIdx = -1;
              const renderInspector = (idx) => {
                if (!inspector) return;
                if (idx < 0 || idx >= values.length) {
                  inspector.style.display = "none";
                  inspector.textContent = "";
                  return;
                }
                inspector.textContent = [
                  "point=#" + (idx + 1),
                  "events=1",
                  "value=" + humanizeBySeries(seriesName, values[idx]),
                ].join(" | ");
                inspector.style.display = "block";
              };

              const update = (evt) => {
                const point = pointerIndex(svg, evt, values.length, width);
                if (point.idx < 0) return;

                const value = values[point.idx];
                const y = ((1 - ((value - minValue) / scale)) * (height - xPadding * 2)) + xPadding;
                dot.setAttribute("cx", String(point.x));
                dot.setAttribute("cy", String(y));
                dot.setAttribute("visibility", "visible");
                vline.setAttribute("x1", String(point.x));
                vline.setAttribute("x2", String(point.x));
                vline.setAttribute("visibility", "visible");

                tooltip.textContent = "#" + (point.idx + 1) + " " + humanizeBySeries(seriesName, value);
                tooltip.style.display = "block";
                const xPx = ((point.x - xPadding) / Math.max(1, width - xPadding * 2)) * point.rect.width;
                const tooltipWidth = tooltip.offsetWidth || 220;
                const left = clamp(xPx + 12, 8, point.rect.width - tooltipWidth - 8);
                tooltip.style.left = left + "px";

                if (pinnedIdx >= 0) renderInspector(pinnedIdx);
              };

              const onClick = (evt) => {
                const point = pointerIndex(svg, evt, values.length, width);
                if (point.idx < 0) return;
                pinnedIdx = pinnedIdx === point.idx ? -1 : point.idx;
                renderInspector(pinnedIdx);
              };

              svg.addEventListener("mouseenter", update);
              svg.addEventListener("mousemove", update);
              svg.addEventListener("mouseleave", () => {
                dot.setAttribute("visibility", "hidden");
                vline.setAttribute("visibility", "hidden");
                tooltip.style.display = "none";
              });
              svg.addEventListener("click", onClick);
            };

            const attachMultiSeriesChart = (svg) => {
              const wrap = svg.closest(".chart-wrap");
              const tooltip = wrap?.querySelector(".chart-tooltip");
              const inspector = wrap?.querySelector(".chart-inspector");
              if (!tooltip) return;

              const groupName = svg.getAttribute("data-series-name") || "";
              let seriesObject = {};
              try {
                const parsed = JSON.parse(svg.getAttribute("data-multi-series") || "{}");
                if (parsed && typeof parsed === "object") seriesObject = parsed;
              } catch (_error) {
                return;
              }

              const entries = Object.entries(seriesObject)
                .map(([name, values]) => [
                  String(name),
                  Array.isArray(values)
                    ? values.map((item) => Number(item)).filter((item) => Number.isFinite(item))
                    : [],
                ])
                .filter(([, values]) => values.length > 0);
              if (!entries.length) return;

              const width = toNumber(svg.getAttribute("data-width"), 760);
              const vline = svg.querySelector(".chart-hover-line");
              if (!vline) return;

              const maxLength = entries.reduce((acc, [, values]) => Math.max(acc, values.length), 0);
              let pinnedIdx = -1;

              const entryParts = (idx) => {
                return entries.map(([name, values]) => {
                  if (idx >= values.length) return name + "=n/a";
                  return name + "=" + humanizeBySeries(name + " " + groupName, values[idx]);
                });
              };

              const renderInspector = (idx) => {
                if (!inspector) return;
                if (idx < 0 || idx >= maxLength) {
                  inspector.style.display = "none";
                  inspector.textContent = "";
                  return;
                }
                inspector.textContent = "point=#" + (idx + 1) + " | events=" + entries.length + " | " + entryParts(idx).join(" | ");
                inspector.style.display = "block";
              };

              const update = (evt) => {
                const point = pointerIndex(svg, evt, maxLength, width);
                if (point.idx < 0) return;

                vline.setAttribute("x1", String(point.x));
                vline.setAttribute("x2", String(point.x));
                vline.setAttribute("visibility", "visible");
                tooltip.textContent = "#" + (point.idx + 1) + " " + entryParts(point.idx).join(" | ");
                tooltip.style.display = "block";

                const xPx = ((point.x - xPadding) / Math.max(1, width - xPadding * 2)) * point.rect.width;
                const tooltipWidth = tooltip.offsetWidth || 320;
                const left = clamp(xPx + 12, 8, point.rect.width - tooltipWidth - 8);
                tooltip.style.left = left + "px";

                if (pinnedIdx >= 0) renderInspector(pinnedIdx);
              };

              const onClick = (evt) => {
                const point = pointerIndex(svg, evt, maxLength, width);
                if (point.idx < 0) return;
                pinnedIdx = pinnedIdx === point.idx ? -1 : point.idx;
                renderInspector(pinnedIdx);
              };

              svg.addEventListener("mouseenter", update);
              svg.addEventListener("mousemove", update);
              svg.addEventListener("mouseleave", () => {
                vline.setAttribute("visibility", "hidden");
                tooltip.style.display = "none";
              });
              svg.addEventListener("click", onClick);
            };

            Array.from(document.querySelectorAll("svg[data-series-values]")).forEach(attachSingleSeriesChart);
            Array.from(document.querySelectorAll("svg[data-multi-series]")).forEach(attachMultiSeriesChart);
          })();
      </script>
  </main>
</body>
</html>
