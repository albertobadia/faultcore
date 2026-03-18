<%text>
(function() {
  const runData = JSON.parse(document.getElementById('run-data').textContent);
  const state = {
    renderedTabs: new Set(),
    events: runData.events || [],
    filteredEvents: [],
    eventPage: 1,
    eventPageSize: 50
  };

  const htmlEntities = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  };
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const safe = (value) => String(value).replace(/[&<>"']/g, (char) => htmlEntities[char]);
  
  const intFmt = new Intl.NumberFormat("en-US");
  const dec2Fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
  const dec3Fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });

  const humanizeNs = (v) => {
    const a = Math.abs(v);
    if (a < 1000) return intFmt.format(Math.round(v)) + "ns";
    if (a < 1000000) return dec2Fmt.format(v / 1000) + "us";
    if (a < 1000000000) return dec2Fmt.format(v / 1000000) + "ms";
    return dec2Fmt.format(v / 1000000000) + "s";
  };
  const humanizeMs = (v) => {
    const a = Math.abs(v);
    if (a < 1) return dec3Fmt.format(v) + "ms";
    if (a < 1000) return dec2Fmt.format(v) + "ms";
    return dec2Fmt.format(v / 1000) + "s";
  };
  const humanizeBps = (v) => {
    const a = Math.abs(v);
    if (a < 1000) return intFmt.format(Math.round(v)) + "bps";
    if (a < 1000000) return dec2Fmt.format(v / 1000) + "Kbps";
    if (a < 1000000000) return dec2Fmt.format(v / 1000000) + "Mbps";
    return dec2Fmt.format(v / 1000000000) + "Gbps";
  };
  const humanizeBytes = (v) => {
    const a = Math.abs(v);
    if (a < 1024) return intFmt.format(Math.round(v)) + "B";
    if (a < 1048576) return dec2Fmt.format(v / 1024) + "KiB";
    if (a < 1073741824) return dec2Fmt.format(v / 1048576) + "MiB";
    return dec2Fmt.format(v / 1073741824) + "GiB";
  };

  const humanize = (name, v) => {
    const n = name.toLowerCase();
    if (n.includes("0/1") || n.includes("flag")) return intFmt.format(Math.round(v));
    if (n.includes("rate_pct") || n.includes("%")) return dec2Fmt.format(v) + "%";
    if (n.includes("_ns") || n.includes("latency_p") || n.includes("delay")) return humanizeNs(v);
    if (n.includes("_ms") || n.includes("jitter")) return humanizeMs(v);
    if (n.includes("bps") || n.includes("throughput")) return humanizeBps(v);
    if (n.includes("byte")) return humanizeBytes(v);
    return intFmt.format(Math.round(v));
  };

  const chartLabel = (label) => String(label)
    .replace(/_/g, " ")
    .replace(/\s*\((ns|us|ms|s|bps|kbps|mbps|gbps|bytes?)\)\s*$/i, "")
    .replace(/\s+(ns|us|ms|s|bps|kbps|mbps|gbps)\s*$/i, "")
    .trim();

  const renderSVG = (series, title, width = 760, height = 120, isMulti = false, events = null) => {
    const xPadding = 10;
    const yPadding = 10;
    const innerWidth = width - xPadding * 2;
    const innerHeight = height - yPadding * 2;

    let minV = Infinity;
    let maxV = -Infinity;
    let maxLen = 0;
    const seriesEntries = isMulti ? Object.entries(series) : [[title, series]];

    seriesEntries.forEach(([_, values]) => {
      values.forEach(v => { minV = Math.min(minV, v); maxV = Math.max(maxV, v); });
      maxLen = Math.max(maxLen, values.length);
    });

    if (maxLen === 0) return "<div class='muted'>No data</div>";
    const useLogScale = isMulti;
    const logOffset = useLogScale ? Math.max(0, -minV) : 0;
    const transformY = useLogScale ? (v) => Math.log1p(v + logOffset) : (v) => v;
    const transformedMin = transformY(minV);
    const transformedMax = transformY(maxV);
    const scale = (transformedMax - transformedMin) || 1;
    const span = Math.max(1, maxLen - 1);

    const colors = ["#68a7db", "#6bc46d", "#d2b35a", "#de6f6f", "#9ac0ff", "#e9a96d"];
    let colorIdx = 0;

    const polylines = seriesEntries.map(([name, values]) => {
      const pts = values.map((v, i) => {
        const x = (i / span) * innerWidth + xPadding;
        const y = (1 - (transformY(v) - transformedMin) / scale) * innerHeight + yPadding;
        return `${x},${y}`;
      }).join(" ");
      const color = colors[colorIdx++ % colors.length];
      return `<polyline fill='none' stroke='${color}' stroke-width='2' points='${pts}'/>`;
    }).join("");

    const legend = isMulti ? `
      <div class='multi-legend'>
        ${seriesEntries.map((e, i) => `<span class='multi-legend-item'><span class='multi-legend-dot' style='background:${colors[i % colors.length]}'></span>${safe(chartLabel(e[0]))}</span>`).join("")}
      </div>` : "";
    const scaleMode = useLogScale ? "log1p" : "linear";
    const titleSuffix = useLogScale ? " (log scale)" : "";

    return `
      <div class='chart-wrap'>
        <div class='chart-inline-title'>${safe(chartLabel(title) + titleSuffix)}</div>
        ${legend}
        <svg viewBox='0 0 ${width} ${height}' preserveAspectRatio='none' width='100%' height='${height}' 
             data-series='${safe(JSON.stringify(series))}' 
              data-events='${events ? safe(JSON.stringify(events)) : ""}'
             data-is-multi='${isMulti}' data-title='${safe(title)}' data-scale-mode='${scaleMode}'>
          <rect x='0' y='0' width='100%' height='100%' fill='#17150f'/>
          ${polylines}
          <line class='chart-hover-line' x1='0' y1='${yPadding}' x2='0' y2='${height - yPadding}' stroke='#b7a982' stroke-width='1' stroke-dasharray='3 3' visibility='hidden'/>
          <circle class='chart-hover-dot' cx='0' cy='0' r='3.5' fill='#efe0b8' stroke='#17150f' stroke-width='1' visibility='hidden'/>
        </svg>
        <div class='chart-tooltip' aria-hidden='true'></div>
        <div class='chart-inspector' aria-live='polite'></div>
      </div>`;
  };

  const renderHeader = () => {
    const ov = document.getElementById("overview");
    const tool = runData.tool || {};
    const env = runData.environment || {};
    const summ = runData.summary || {};
    const net = runData.network_metrics || {};
    const fc = runData.faultcore || {};
    const ic = runData.interceptor || {};
    const eventsTotal = Number(net.recorded_events_total || net.total_events || 0);
    const durationMs = Number(runData.duration_ms || 0);
    const durationSeconds = durationMs > 0 ? durationMs / 1000 : 0;
    const rawFaultEvents = Number(summ.fault_events_total || net.fault_events_total || 0);
    const decisionCounts = {
      delay_ns: Number(net.delay_count || 0),
      drop: Number(net.drop_count || 0),
      timeout_ms: Number(net.timeout_count || 0),
      stage_reorder: Number(net.reorder_count || 0),
      duplicate: Number(net.duplicate_count || 0),
      nxdomain: Number(net.nxdomain_count || 0),
      error: Number(net.error_count || 0),
      connection_error_kind: Number(net.connection_error_count || 0)
    };
    const decisionEntries = Object.entries(decisionCounts).filter(([, value]) => value > 0);
    const decisionsTotal = decisionEntries.reduce((acc, [, value]) => acc + value, 0);
    const faultEventsTotal = rawFaultEvents > 0 ? rawFaultEvents : decisionsTotal;
    const faultRatePct = eventsTotal > 0 ? (faultEventsTotal / eventsTotal) * 100 : 0;
    const faultEventsPerSec = durationSeconds > 0 ? faultEventsTotal / durationSeconds : 0;
    const topFaults = decisionEntries
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([name, value]) => {
        const label = name
          .replace(/_ns|_ms/g, "")
          .replace("stage_reorder", "reorder")
          .replace("connection_error_kind", "conn_error")
          .replace(/_/g, " ");
        const pct = decisionsTotal > 0 ? (value / decisionsTotal) * 100 : 0;
        return `${safe(label)} ${dec2Fmt.format(pct)}%`;
      });

    const siteMetrics = runData.site_metrics || {};
    const functionMetrics = runData.function_metrics || {};
    const series = runData.network_series || {};
    const affectedSitesCount = Object.keys(siteMetrics).length || (runData.observed_sites || []).length;
    const affectedFunctionsCount = Object.keys(functionMetrics).length;
    const protocolSet = new Set();
    ["tcp", "udp", "http"].forEach((proto) => {
      const hasMetric = Object.keys(net).some((key) => key.startsWith(`${proto}_`));
      const hasSeries = Object.keys(series).some((key) => key.startsWith(`${proto}_`));
      if (hasMetric || hasSeries) protocolSet.add(proto);
    });
    const affectedProtocolsCount = protocolSet.size;

    const streamIntegrity = runData.events_truncated
      ? "partial"
      : ((runData.events || []).length > 0 ? "complete" : "none");

    const scenarioName = (tool.command && tool.command.length) ? tool.command[0].split("/").pop() : "none";
    const fullCommand = safe((tool.command || []).join(" "));

    ov.innerHTML = `
      <div class="overview-shell">
        <div class="overview-kpi-grid">
          <div class="overview-kpi-card">
            <div class="overview-kpi-label">Run status</div>
            <div class="overview-kpi-value"><span class="status">${safe(runData.status || "unknown")}</span></div>
          </div>
          <div class="overview-kpi-card">
            <div class="overview-kpi-label">Duration</div>
            <div class="overview-kpi-value">${humanizeMs(durationMs)}</div>
          </div>
          <div class="overview-kpi-card overview-kpi-card-emphasis">
            <div class="overview-kpi-label">Fault events</div>
            <div class="overview-kpi-value">${intFmt.format(Math.round(faultEventsTotal))}</div>
          </div>
          <div class="overview-kpi-card overview-kpi-card-emphasis">
            <div class="overview-kpi-label">Fault rate</div>
            <div class="overview-kpi-value">${dec2Fmt.format(faultRatePct)}%</div>
          </div>
        </div>
        <div class="overview-strip-grid">
          <div class="overview-strip-card">
            <div class="overview-strip-title">Top faults</div>
            <div class="overview-strip-value">${topFaults.length ? topFaults.join(" | ") : "none"}</div>
          </div>
          <div class="overview-strip-card">
            <div class="overview-strip-title">Affected scope</div>
            <div class="overview-strip-value">${intFmt.format(affectedProtocolsCount)} protocols | ${intFmt.format(affectedSitesCount)} sites | ${intFmt.format(affectedFunctionsCount)} functions</div>
          </div>
          <div class="overview-strip-card">
            <div class="overview-strip-title">Fault density</div>
            <div class="overview-strip-value">${dec2Fmt.format(faultEventsPerSec)} events/s</div>
          </div>
        </div>

        <div class="overview-main-grid">
          <section class="overview-panel">
            <h3>Health</h3>
            <ul class="kv-list">
              <li><span>tests_failed</span><span>${safe(summ.tests_failed || 0)}</span></li>
              <li><span>errors</span><span>${safe(summ.errors || 0)}</span></li>
              <li><span>event_stream</span><span>${safe(streamIntegrity)}</span></li>
            </ul>
          </section>
          <section class="overview-panel">
            <h3>Execution context</h3>
            <ul class="kv-list">
              <li><span>scenario</span><span>${safe(scenarioName)}</span></li>
              <li><span>os/arch</span><span>${safe(env.os)}/${safe(env.arch)}</span></li>
              <li><span>python</span><span>${safe(env.python_version)}</span></li>
              <li><span>seed</span><span>${safe(fc.seed || 0)}</span></li>
            </ul>
          </section>
        </div>

        <details class="overview-tech-details">
          <summary>Applied Configuration & Technical Details</summary>
          <div class="overview-tech-grid">
            <div>
              <div class="overview-tech-label">command</div>
              <code>${fullCommand || "none"}</code>
            </div>
            <div>
              <div class="overview-tech-label">interceptor_path</div>
              <code>${safe(ic.path || "")}</code>
            </div>
            <div>
              <div class="overview-tech-label">interceptor_mode</div>
              <div>${safe(ic.mode || "none")}</div>
            </div>
            <div>
              <div class="overview-tech-label">interceptor_active</div>
              <div>${safe(ic.active || false)}</div>
            </div>
            <div>
              <div class="overview-tech-label">shm_open_mode</div>
              <div>${safe(fc.shm_open_mode || "")}</div>
            </div>
            <div>
              <div class="overview-tech-label">record_replay_mode</div>
              <div>${safe(fc.record_replay_mode || "off")}</div>
            </div>
          </div>
        </details>
      </div>`;
  };

  const splitProtocol = (name) => {
    const order = ["tcp", "udp", "http", "total"];
    const ln = name.toLowerCase();
    for (const p of order) {
      if (ln.startsWith(p + "_")) {
        let base = name.slice(p.length + 1);
        if (base.endsWith("_series")) base = base.slice(0, -7);
        return [p, base];
      }
    }
    return null;
  };

  const renderMetricGrid = (metrics) => {
    const kpiOrder = [
      ["total_throughput_bps", "Throughput"], ["total_bytes", "Bytes"],
      ["throughput_bps", "Throughput"], ["bytes_total", "Bytes"],
      ["recorded_events_total", "Recorded Events"], ["fault_events_total", "Fault Events"],
      ["total_events", "Events"], ["fault_events", "Fault Events"],
      ["latency_p95_ns", "P95 Latency"], ["latency_p95_ms", "P95 Latency"],
      ["latency_avg_ms", "Avg Latency"], ["jitter_ms", "Jitter"],
      ["tcp_latency_avg_ms", "TCP Avg"], ["udp_latency_avg_ms", "UDP Avg"], ["http_latency_avg_ms", "HTTP Avg"]
    ];

    const kpiHTML = kpiOrder.map(([key, label]) => {
      if (metrics[key] === undefined) return "";
      return `<div class='network-kpi-card'><div class='network-kpi-label'>${safe(label)}</div><div class='network-kpi-value'>${humanize(key, metrics[key])}</div></div>`;
    }).join("");

    const groups = { Traffic: [], "Latency/Jitter": [], "Events/Counters": [], Other: [] };
    Object.entries(metrics).forEach(([k, v]) => {
      if (typeof v !== "number") return;
      let g = "Other";
      const l = k.toLowerCase();
      if (l.includes("throughput") || l.includes("bytes")) g = "Traffic";
      else if (l.includes("latency") || l.includes("jitter")) g = "Latency/Jitter";
      else if (l.includes("events") || l.endsWith("_count")) g = "Events/Counters";
      groups[g].push([k, v]);
    });

    const buildGroup = (name, items) => {
      if (!items.length) return "";
      const sorted = items.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 10);
      const maxVal = Math.max(...sorted.map(it => Math.abs(it[1]))) || 1;
      const rows = sorted.map(([k, v]) => {
        const pct = Math.min(96, (Math.abs(v) / maxVal) * 96);
        return `
          <div class="metric-row">
            <div class="metric-name">${safe(k.replace(/_/g, " "))}</div>
            <div class="metric-track"><div class="metric-fill" style="width:${pct}%"></div></div>
             <div class="metric-value">${humanize(k, v)}</div>
           </div>`;
      }).join("");
      return `<div class="metric-group"><div class="metric-group-title">${safe(name)}</div>${rows}</div>`;
    };

    const leftBlocks = [
      buildGroup("Events/Counters", groups["Events/Counters"]),
      buildGroup("Other", groups.Other)
    ].join("");

    const rightBlocks = [
      buildGroup("Traffic", groups.Traffic),
      buildGroup("Latency/Jitter", groups["Latency/Jitter"])
    ].join("");

    return `
      <div class='network-kpi-grid'>${kpiHTML}</div>
      <div class='metric-groups-balanced'>
        <div class='metric-left-stack'>${leftBlocks}</div>
        <div class='metric-right-stack'>${rightBlocks}</div>
      </div>`;
  };

  const renderTab = (id) => {
    if (state.renderedTabs.has(id)) return;
    const panel = document.querySelector(`[data-tab-panel="${id}"]`);
    panel.innerHTML = "";
    
    if (id === "charts") {
      const series = runData.network_series || {};
      const funcMetrics = runData.function_metrics || {};
      const faultEventsSeries = series.fault_events_per_bucket || [];
      
      const extra = {...series};
      const thrGroup = {};
      Object.entries(funcMetrics).forEach(([fn, data]) => {
        const s = data.series_throughput_bps || [];
        if (s.length) thrGroup[fn] = s;
      });

      const grouped = {};
      const consumed = new Set();
      const filtered = Object.entries(extra).filter(([k]) => !k.toLowerCase().includes("bytes_cumulative"));
      
      filtered.forEach(([name, values]) => {
        const res = splitProtocol(name);
        if (res) {
          const [proto, base] = res;
          if (!grouped[base]) grouped[base] = {};
          grouped[base][proto] = values;
        }
      });

      const order = ["tcp", "udp", "http", "total"];
      Object.entries(grouped).sort().forEach(([base, map]) => {
        if (Object.keys(map).length >= 2) {
          const chartSeries = {};
          order.forEach(p => { if (map[p]) { chartSeries[p] = map[p]; consumed.add(`${p}_${base}`); consumed.add(`${p}_${base}_series`); } });
          panel.innerHTML += renderSVG(chartSeries, base, 760, 120, true, faultEventsSeries);
        }
      });

      if (Object.keys(thrGroup).length > 0) {
        panel.innerHTML += renderSVG(thrGroup, "Throughput Timeline", 760, 120, true, faultEventsSeries);
        Object.keys(thrGroup).forEach(fn => consumed.add(`${fn}_throughput_bps`));
      }

      filtered.sort().forEach(([name, values]) => {
        if (!consumed.has(name) && !name.includes("per_bucket") && !name.includes("cumulative")) {
          panel.innerHTML += renderSVG(values, name, 760, 120, false, faultEventsSeries);
        }
      });

    } else if (id === "network") {
      panel.innerHTML = renderMetricGrid(runData.network_metrics || {});
      panel.innerHTML += `
        <div class='logs-grid'>
          <div class='log-panel'><div class='log-title'>stdout</div><pre><code>${safe(runData.logs?.stdout_tail || "No stdout")}</code></pre></div>
          <div class='log-panel'><div class='log-title'>stderr</div><pre><code>${safe(runData.logs?.stderr_tail || "No stderr")}</code></pre></div>
        </div>`;
    } else if (id === "site-details") {
      renderSiteAndFunctionDetails(panel, "site");
    } else if (id === "function-details") {
      renderSiteAndFunctionDetails(panel, "function");
    } else if (id === "timeline") {
      renderTimeline(panel);
    }
    
    state.renderedTabs.add(id);
    attachChartInteractions(panel);
  };

  const renderSiteAndFunctionDetails = (container, detailType) => {
    const sites = runData.site_metrics || {};
    const funcs = runData.function_metrics || {};
    const duration = runData.duration_ms || 1;
    const isSiteView = detailType === "site";
    const searchPlaceholder = isSiteView ? "Search site..." : "Search function...";
    const detailsHTML = isSiteView
      ? Object.entries(sites).sort((a, b) => (b[1].fault_events || 0) - (a[1].fault_events || 0)).map(([name, data]) => {
          const m = { ...data, ...data.decision_counts };
          m.event_rate_eps = (data.total_events || 0) * 1000 / duration;
          return `
          <details class="metric-details site-item" data-name="${safe(name)}">
            <summary>Site: ${safe(name)} - Faults: ${data.fault_events} (${data.fault_rate_pct}%)</summary>
            <div class="site-content">
              ${renderMetricGrid(m)}
              ${data.delay_series_ns ? renderSVG(data.delay_series_ns, "Delay Timeline", 760, 120, false, data.fault_events_per_bucket) : ""}
              ${data.fault_flag_series ? renderSVG({fault: data.fault_flag_series, continue: data.continue_flag_series}, "Decisions (0/1)", 760, 80, true, data.fault_events_per_bucket) : ""}
              ${data.events_per_bucket ? renderSVG({events: data.events_per_bucket, fault_events: data.fault_events_per_bucket}, "Bucket Counters", 760, 100, true, data.fault_events_per_bucket) : ""}
            </div>
          </details>`;
        }).join("")
      : Object.entries(funcs).sort().map(([name, data]) => {
          const m = { ...data };
          m.total_events = (data.series_latency_ms || []).length;
          return `
          <details class="metric-details function-item" data-name="${safe(name)}">
            <summary>Func: ${safe(name)} - Throughput: ${humanize("throughput_bps", data.throughput_bps || 0)}</summary>
            <div class="site-content">
              ${renderMetricGrid(m)}
              ${Object.entries(data).filter(([k]) => k.startsWith("series_")).map(([k, v]) => renderSVG(v, k.slice(7), 760, 120, false, data.fault_events_per_bucket)).join("")}
            </div>
          </details>`;
        }).join("");
    
    container.innerHTML = `
      <div class="details-toolbar">
        <input id="site-search" type="search" placeholder="${searchPlaceholder}" />
        <button id="site-expand-all" type="button">Expand all</button>
        <button id="site-collapse-all" type="button">Collapse all</button>
      </div>
      <div class="details-stack">
        ${detailsHTML}
      </div>`;
      
    const search = container.querySelector("#site-search");
    const items = container.querySelectorAll(".metric-details");
    search.addEventListener("input", () => {
      const q = search.value.toLowerCase();
      items.forEach(it => it.style.display = it.dataset.name.toLowerCase().includes(q) ? "" : "none");
    });
    container.querySelector("#site-expand-all").onclick = () => items.forEach((it) => {
      if (it.style.display !== "none") it.open = true;
    });
    container.querySelector("#site-collapse-all").onclick = () => items.forEach(it => it.open = false);
  };

  const renderTimeline = (container) => {
    container.innerHTML = `
      <div class="controls">
        <input id="events-search" type="search" placeholder="Search events..." />
        <select id="events-page-size"><option value="50">50 / page</option><option value="200">200 / page</option></select>
        <button id="events-prev">Prev</button><button id="events-next">Next</button>
        <span id="events-info"></span>
      </div>
      <div class="events-table-wrap">
        <table>
          <thead><tr><th>ts</th><th>severity</th><th>type</th><th>name</th><th>details</th></tr></thead>
          <tbody id="events-body"></tbody>
        </table>
      </div>`;
    
    const body = container.querySelector("#events-body");
    const search = container.querySelector("#events-search");
    const info = container.querySelector("#events-info");
    const sizeSelect = container.querySelector("#events-page-size");
    const prevButton = container.querySelector("#events-prev");
    const nextButton = container.querySelector("#events-next");

    const update = () => {
      const q = search.value.toLowerCase();
      state.filteredEvents = state.events.filter(e => 
        e.name.toLowerCase().includes(q) || e.type.toLowerCase().includes(q) || JSON.stringify(e.details).toLowerCase().includes(q)
      );
      state.eventPageSize = parseInt(sizeSelect.value, 10);
      const start = (state.eventPage - 1) * state.eventPageSize;
      const page = state.filteredEvents.slice(start, start + state.eventPageSize);
      
      body.innerHTML = page.map(e => `
        <tr>
          <td>${safe(e.ts)}</td>
          <td><span class="severity-${e.severity}">${safe(e.severity)}</span></td>
          <td>${safe(e.type)}</td>
          <td>${safe(e.name)}</td>
          <td><code>${safe(JSON.stringify(e.details))}</code></td>
        </tr>`).join("");
      
      const totalPages = Math.max(1, Math.ceil(state.filteredEvents.length / state.eventPageSize));
      info.textContent = `Page ${state.eventPage} / ${totalPages} (${state.filteredEvents.length} matches)`;
      prevButton.disabled = state.eventPage <= 1;
      nextButton.disabled = state.eventPage >= totalPages;
    };

    search.oninput = () => { state.eventPage = 1; update(); };
    sizeSelect.onchange = () => { state.eventPage = 1; update(); };
    prevButton.onclick = () => { state.eventPage -= 1; update(); };
    nextButton.onclick = () => { state.eventPage += 1; update(); };
    
    update();
  };

  const attachChartInteractions = (container) => {
    container.querySelectorAll("svg[data-series]").forEach(svg => {
      const wrap = svg.closest(".chart-wrap");
      const tooltip = wrap.querySelector(".chart-tooltip");
      const inspector = wrap.querySelector(".chart-inspector");
      const line = svg.querySelector(".chart-hover-line");
      const dot = svg.querySelector(".chart-hover-dot");
      const series = JSON.parse(svg.getAttribute("data-series"));
      const eventAttr = svg.getAttribute("data-events");
      const eventSeries = eventAttr ? JSON.parse(eventAttr) : [];
      const isMulti = svg.getAttribute("data-is-multi") === "true";
      const title = svg.getAttribute("data-title");
      const scaleMode = svg.getAttribute("data-scale-mode") || "linear";
      
      const data = isMulti ? Object.values(series)[0] : series;
      const len = data.length;
      let pinnedIdx = -1;

      const update = (idx, pin = false) => {
        const x = (idx / (len - 1)) * 740 + 10;
        line.setAttribute("x1", x);
        line.setAttribute("x2", x);
        line.setAttribute("visibility", "visible");
        dot.setAttribute("cx", x);
        dot.setAttribute("visibility", "hidden");

        let txt = isMulti ? Object.entries(series).map(([n,v]) => `${n}: ${humanize(n, v[idx])}`).join(" | ") : humanize(title, series[idx]);
        if (eventSeries[idx]) txt += ` | Events: ${eventSeries[idx]}`;
        
        const content = `#${idx + 1} | ${txt} | Y-scale: ${scaleMode}`;
        tooltip.textContent = content;
        tooltip.style.display = "block";
        
        if (pin) {
          inspector.textContent = "PINNED: " + content;
          inspector.style.display = "block";
        }
      };

      svg.onmousemove = (e) => {
        if (pinnedIdx >= 0) return;
        const rect = svg.getBoundingClientRect();
        const xRel = (e.clientX - rect.left) / rect.width;
        const idx = clamp(Math.round(xRel * (len - 1)), 0, len - 1);
        update(idx);
        tooltip.style.left = clamp(e.clientX - rect.left + 10, 0, rect.width - 200) + "px";
      };
      
      svg.onclick = (e) => {
        const rect = svg.getBoundingClientRect();
        const xRel = (e.clientX - rect.left) / rect.width;
        const idx = clamp(Math.round(xRel * (len - 1)), 0, len - 1);
        pinnedIdx = (pinnedIdx === idx) ? -1 : idx;
        if (pinnedIdx >= 0) {
          update(pinnedIdx, true);
        } else {
          inspector.style.display = "none";
          update(idx);
        }
      };

      svg.onmouseleave = () => {
        if (pinnedIdx < 0) {
          line.setAttribute("visibility", "hidden");
          tooltip.style.display = "none";
        }
      };
    });
  };

  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".tab-btn, .tab-panel").forEach(el => el.classList.remove("active"));
      btn.classList.add("active");
      const id = btn.dataset.tabTarget;
      document.querySelector(`[data-tab-panel="${id}"]`).classList.add("active");
      renderTab(id);
    };
  });

  renderHeader();
  renderTab("charts");
})();
</%text>
