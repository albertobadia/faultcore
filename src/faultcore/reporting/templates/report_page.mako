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
      <button type="button" class="tab-btn" data-tab-target="site-details">Per Site</button>
      <button type="button" class="tab-btn" data-tab-target="function-details">Per Function / Test</button>
      <button type="button" class="tab-btn" data-tab-target="timeline">Decisions Timeline</button>
    </div>
    <div class="tab-content">
      <section id="charts" class="tab-panel active" data-tab-panel="charts">
        <div id="charts-loading" class="muted">Initializing timeline...</div>
      </section>
      <section id="network" class="tab-panel" data-tab-panel="network">
        <div id="network-loading" class="muted">Initializing network metrics...</div>
      </section>
      <section id="site-details" class="tab-panel" data-tab-panel="site-details">
        <div id="site-details-loading" class="muted">Initializing per-site details...</div>
      </section>
      <section id="function-details" class="tab-panel" data-tab-panel="function-details">
        <div id="function-details-loading" class="muted">Initializing per-function details...</div>
      </section>
      <section id="timeline" class="tab-panel tab-panel-timeline" data-tab-panel="timeline">
        <div id="timeline-loading" class="muted">Initializing decisions timeline...</div>
      </section>
    </div>
    <script id="run-data" type="application/json">
      ${run_data_json}
    </script>
    <script>
      <%include file="scripts.js"/>
    </script>
  </main>
</body>
</html>
