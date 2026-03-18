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

  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const safe = (str) => String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  
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

  const renderSVG = (series, title, width = 760, height = 120, isMulti = false, events = null) => {
    const xPadding = 10;
    const yPadding = 10;
    const innerWidth = width - xPadding * 2;
    const innerHeight = height - yPadding * 2;
    
    let minV = Infinity, maxV = -Infinity, maxLen = 0;
    const seriesEntries = isMulti ? Object.entries(series) : [[title, series]];
    
    seriesEntries.forEach(([_, values]) => {
      values.forEach(v => { minV = Math.min(minV, v); maxV = Math.max(maxV, v); });
      maxLen = Math.max(maxLen, values.length);
    });
    
    if (maxLen === 0) return "<div class='muted'>No data</div>";
    const scale = (maxV - minV) || 1;
    const span = Math.max(1, maxLen - 1);
    
    const colors = ["#68a7db", "#6bc46d", "#d2b35a", "#de6f6f", "#9ac0ff", "#e9a96d"];
    let colorIdx = 0;
    
    const polylines = seriesEntries.map(([name, values]) => {
      const pts = values.map((v, i) => {
        const x = (i / span) * innerWidth + xPadding;
        const y = (1 - (v - minV) / scale) * innerHeight + yPadding;
        return `${x},${y}`;
      }).join(" ");
      const color = colors[colorIdx++ % colors.length];
      return `<polyline fill='none' stroke='${color}' stroke-width='2' points='${pts}'/>`;
    }).join("");

    const legend = isMulti ? `
      <div class='multi-legend'>
        ${seriesEntries.map((e, i) => `<span class='multi-legend-item'><span class='multi-legend-dot' style='background:${colors[i % colors.length]}'></span>${safe(e[0])}</span>`).join("")}
      </div>` : "";

    return `
      <div class='chart-wrap'>
        <div class='chart-inline-title'>${safe(title)}</div>
        ${legend}
        <svg viewBox='0 0 ${width} ${height}' preserveAspectRatio='none' width='100%' height='${height}' 
             data-series='${safe(JSON.stringify(series))}' 
             data-events='${events ? safe(JSON.stringify(events)) : ""}'
             data-is-multi='${isMulti}' data-title='${safe(title)}'>
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
    const fc = runData.faultcore || {};
    const ic = runData.interceptor || {};
    const scenItems = runData.scenarios || [];

    ov.innerHTML = `
      <div class="compact-grid">
        <div class="compact-card">
          <strong>Run</strong>
          <div>run_id=${safe(runData.run_id)}</div>
          <div>status=<span class="status">${safe(runData.status)}</span></div>
          <div>duration_ms=${runData.duration_ms}</div>
          <div>started_at=${safe(runData.started_at)}</div>
        </div>
        <div class="compact-card compact-card-context">
          <strong>Execution Context</strong>
          <div>command=<code>${safe((tool.command || []).join(" "))}</code></div>
          <div>os/arch=${safe(env.os)}/${safe(env.arch)}</div>
          <div>python=${safe(env.python_version)}</div>
          <div>interceptor_path=<code>${safe(ic.path)}</code></div>
        </div>
        <div class="compact-card">
          <strong>Fault Summary</strong>
          <div>tests_total=${safe(summ.tests_total || 0)}</div>
          <div>tests_passed=${safe(summ.tests_passed || 0)}</div>
          <div>tests_failed=${safe(summ.tests_failed || 0)}</div>
          <div>errors=${safe(summ.errors || 0)}</div>
          <div>fault_events_total=${safe(summ.fault_events_total || 0)}</div>
        </div>
        <div class="compact-card">
          <strong>Applied Configuration</strong>
          <ul class="kv-list">
            <li>seed=${safe(fc.seed || 0)}</li>
            <li>shm_open_mode=${safe(fc.shm_open_mode)}</li>
            <li>record_replay_mode=${safe(fc.record_replay_mode || "off")}</li>
            <li>interceptor_mode=${safe(ic.mode || "none")}</li>
          </ul>
          <div>scenarios=${scenItems.map(s => `${safe(s.name)}:${safe(s.status)}`).join(", ") || "none"}</div>
        </div>
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

    const groupsHTML = Object.entries(groups).map(([name, items]) => {
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
    }).join("");

    return `
      <div class='network-kpi-grid'>${kpiHTML}</div>
      <div class='metric-groups-balanced'>${groupsHTML}</div>`;
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
          panel.innerHTML += renderSVG(chartSeries, base.replace(/_/g, " "), 760, 120, true, faultEventsSeries);
        }
      });

      if (Object.keys(thrGroup).length > 0) {
        panel.innerHTML += renderSVG(thrGroup, "Throughput Timeline (bps)", 760, 120, true, faultEventsSeries);
        Object.keys(thrGroup).forEach(fn => consumed.add(`${fn}_throughput_bps`));
      }

      filtered.sort().forEach(([name, values]) => {
        if (!consumed.has(name) && !name.includes("per_bucket") && !name.includes("cumulative")) {
          panel.innerHTML += renderSVG(values, name.replace(/_/g, " "), 760, 120, false, faultEventsSeries);
        }
      });

    }
 else if (id === "network") {
      panel.innerHTML = renderMetricGrid(runData.network_metrics || {});
      panel.innerHTML += `
        <div class='logs-grid'>
          <div class='log-panel'><div class='log-title'>stdout</div><pre><code>${safe(runData.logs?.stdout_tail || "No stdout")}</code></pre></div>
          <div class='log-panel'><div class='log-title'>stderr</div><pre><code>${safe(runData.logs?.stderr_tail || "No stderr")}</code></pre></div>
        </div>`;
    } else if (id === "site-details") {
      renderSiteAndFunctionDetails(panel);
    } else if (id === "timeline") {
      renderTimeline(panel);
    }
    
    state.renderedTabs.add(id);
    attachChartInteractions(panel);
  };

  const renderSiteAndFunctionDetails = (container) => {
    const sites = runData.site_metrics || {};
    const funcs = runData.function_metrics || {};
    const duration = runData.duration_ms || 1;
    
    container.innerHTML = `
      <div class="details-toolbar">
        <input id="site-search" type="search" placeholder="Search function/site..." />
        <button id="site-expand-all" type="button">Expand all</button>
        <button id="site-collapse-all" type="button">Collapse all</button>
      </div>
      <div class="details-stack">
        ${Object.entries(sites).sort((a,b) => (b[1].fault_events||0) - (a[1].fault_events||0)).map(([name, data]) => {
          const m = { ...data, ...data.decision_counts };
          m.event_rate_eps = (data.total_events || 0) * 1000 / duration;
          return `
          <details class="metric-details site-item" data-name="${safe(name)}">
            <summary>Site: ${safe(name)} - Faults: ${data.fault_events} (${data.fault_rate_pct}%)</summary>
            <div class="site-content">
              ${renderMetricGrid(m)}
              ${data.delay_series_ns ? renderSVG(data.delay_series_ns, "Delay Timeline (ns)", 760, 120, false, data.fault_events_per_bucket) : ""}
              ${data.fault_flag_series ? renderSVG({fault: data.fault_flag_series, continue: data.continue_flag_series}, "Decisions (0/1)", 760, 80, true, data.fault_events_per_bucket) : ""}
              ${data.events_per_bucket ? renderSVG({events: data.events_per_bucket, fault_events: data.fault_events_per_bucket}, "Bucket Counters", 760, 100, true, data.fault_events_per_bucket) : ""}
            </div>
          </details>`;
        }).join("")}
        ${Object.entries(funcs).sort().map(([name, data]) => {
          const m = { ...data };
          m.total_events = (data.series_latency_ms || []).length;
          return `
          <details class="metric-details function-item" data-name="${safe(name)}">
            <summary>Func: ${safe(name)} - Throughput: ${humanize("throughput_bps", data.throughput_bps || 0)}</summary>
            <div class="site-content">
              ${renderMetricGrid(m)}
              ${Object.entries(data).filter(([k]) => k.startsWith("series_")).map(([k, v]) => renderSVG(v, k.slice(7).replace(/_/g, " "), 760, 120, false, data.fault_events_per_bucket)).join("")}
            </div>
          </details>`;
        }).join("")}
      </div>`;
      
    const search = container.querySelector("#site-search");
    const items = container.querySelectorAll(".metric-details");
    search.addEventListener("input", () => {
      const q = search.value.toLowerCase();
      items.forEach(it => it.style.display = it.dataset.name.toLowerCase().includes(q) ? "" : "none");
    });
    container.querySelector("#site-expand-all").onclick = () => items.forEach(it => { if(it.style.display !== "none") it.open = true; });
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

    const update = () => {
      const q = search.value.toLowerCase();
      state.filteredEvents = state.events.filter(e => 
        e.name.toLowerCase().includes(q) || e.type.toLowerCase().includes(q) || JSON.stringify(e.details).toLowerCase().includes(q)
      );
      state.eventPageSize = parseInt(sizeSelect.value);
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
      
      const totalPages = Math.ceil(state.filteredEvents.length / state.eventPageSize);
      info.textContent = `Page ${state.eventPage} / ${totalPages} (${state.filteredEvents.length} matches)`;
      container.querySelector("#events-prev").disabled = state.eventPage <= 1;
      container.querySelector("#events-next").disabled = state.eventPage >= totalPages;
    };

    search.oninput = () => { state.eventPage = 1; update(); };
    sizeSelect.onchange = () => { state.eventPage = 1; update(); };
    container.querySelector("#events-prev").onclick = () => { state.eventPage--; update(); };
    container.querySelector("#events-next").onclick = () => { state.eventPage++; update(); };
    
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
        
        const content = `#${idx + 1} | ${txt}`;
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
