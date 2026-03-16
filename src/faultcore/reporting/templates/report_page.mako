<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>faultcore report - ${safe(run_data.get('run_id', ''))}</title>
  <style>
    <%include file="styles.css.mako"/>
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
          <ul class="kv-list">
            <li>seed=${safe(faultcore.get('seed', 0))}</li>
            <li>shm_open_mode=${safe(faultcore.get('shm_open_mode', ''))}</li>
            <li>record_replay_mode=${safe(faultcore.get('record_replay_mode', 'off'))}</li>
            <li>interceptor_mode=${safe(interceptor.get('mode', 'none'))}</li>
            <li>interceptor_active=${safe(interceptor.get('active', False))}</li>
          </ul>
          <div>scenarios=${', '.join('{}:{} ({}ms)'.format(safe(item.get('name', 'default')), safe(item.get('status', 'unknown')), safe(item.get('duration_ms', 0))) for item in scenarios) or 'none'}</div>
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
            <ul class="output-list">
              % if failures:
                ${''.join('<li>{} {}: {}</li>'.format(safe(item.get('ts', '')), safe(item.get('type', '')), safe(item.get('name', ''))) for item in failures)}
              % else:
                <li>No failures/errors in current view</li>
              % endif
            </ul>
          </div>
          <div class="output-panel">
            <div class="output-panel-title">Artifacts <span class="output-badge">${safe(artifacts_count)}</span></div>
            <ul class="output-list">
              % if artifacts:
                ${''.join('<li>{}: <code>{}</code>'.format(safe(item.get('kind', 'artifact')), safe(item.get('path', ''))) for item in artifacts)}
              % else:
                <li>No artifacts</li>
              % endif
            </ul>
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
              <%include file="event_rows.mako" args="events=viewed_events, safe=safe"/>
            </tbody>
          </table>
        </div>
      </section>
    </div>
    <script src="scripts.js"></script>
  </main>
</body>
</html>
