(function() {
  const clamp = function(value, min, max) { return Math.max(min, Math.min(max, value)); };
  const toNumber = function(value, fallback) {
    fallback = fallback === undefined ? 0 : fallback;
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  };
  var xPadding = 10;

  var tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
  var tabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));
  var activateTab = function(tabId) {
    tabButtons.forEach(function(btn) {
      btn.classList.toggle("active", btn.getAttribute("data-tab-target") === tabId);
    });
    tabPanels.forEach(function(panel) {
      panel.classList.toggle("active", panel.getAttribute("data-tab-panel") === tabId);
    });
  };
  tabButtons.forEach(function(btn) {
    btn.addEventListener("click", function() {
      var tabId = btn.getAttribute("data-tab-target");
      if (tabId) activateTab(tabId);
    });
  });

  var siteSearch = document.getElementById("site-search");
  var siteKind = document.getElementById("site-kind");
  var siteFaults = document.getElementById("site-faults");
  var siteExpandAll = document.getElementById("site-expand-all");
  var siteCollapseAll = document.getElementById("site-collapse-all");
  var siteCount = document.getElementById("site-details-count");
  var siteDetailItems = Array.from(document.querySelectorAll("#site-details .metric-details"));
  var applySiteFilters = function() {
    var query = (siteSearch && siteSearch.value || "").trim().toLowerCase();
    var kind = (siteKind && siteKind.value || "").trim().toLowerCase();
    var faultsOnly = (siteFaults && siteFaults.value || "") === "faults";
    var visible = 0;

    siteDetailItems.forEach(function(item) {
      var name = (item.getAttribute("data-item-name") || "").toLowerCase();
      var faultEvents = toNumber(item.getAttribute("data-fault-events"), 0);
      var isFunction = item.classList.contains("function-item");
      var isSite = item.classList.contains("site-item");

      var matchesQuery = !query || name.includes(query);
      var matchesKind = (kind !== "function" || isFunction) && (kind !== "site" || isSite);
      var matchesFaults = !faultsOnly || faultEvents > 0;
      var isVisible = matchesQuery && matchesKind && matchesFaults;

      item.style.display = isVisible ? "" : "none";
      if (isVisible) visible += 1;
    });

    if (siteCount) siteCount.textContent = "visible=" + visible;
  };

  if (siteSearch) siteSearch.addEventListener("input", applySiteFilters);
  if (siteKind) siteKind.addEventListener("change", applySiteFilters);
  if (siteFaults) siteFaults.addEventListener("change", applySiteFilters);
  if (siteExpandAll) siteExpandAll.addEventListener("click", function() {
    siteDetailItems.forEach(function(item) {
      if (item.style.display !== "none") item.open = true;
    });
  });
  if (siteCollapseAll) siteCollapseAll.addEventListener("click", function() {
    siteDetailItems.forEach(function(item) {
      if (item.style.display !== "none") item.open = false;
    });
  });
  applySiteFilters();

  var tbody = document.getElementById("events-body");
  if (!tbody) return;

  var allRows = Array.from(tbody.querySelectorAll("tr"));
  var searchInput = document.getElementById("events-search");
  var severitySelect = document.getElementById("events-severity");
  var typeInput = document.getElementById("events-type");
  var pageSizeSelect = document.getElementById("events-page-size");
  var prevBtn = document.getElementById("events-prev");
  var nextBtn = document.getElementById("events-next");
  var pageInfo = document.getElementById("events-page-info");
  var page = 1;

  var rowText = function(row) { return (row.textContent || "").toLowerCase(); };
  var filteredRows = function() {
    var query = (searchInput && searchInput.value || "").trim().toLowerCase();
    var severityFilter = (severitySelect && severitySelect.value || "").trim().toLowerCase();
    var typeQuery = (typeInput && typeInput.value || "").trim().toLowerCase();
    return allRows.filter(function(row) {
      var cells = row.querySelectorAll("td");
      var severity = (cells[1] && cells[1].textContent || "").trim().toLowerCase();
      var type = (cells[2] && cells[2].textContent || "").trim().toLowerCase();
      if (severityFilter && severity !== severityFilter) return false;
      if (typeQuery && !type.includes(typeQuery)) return false;
      if (query && !rowText(row).includes(query)) return false;
      return true;
    });
  };

  var renderEvents = function() {
    var rows = filteredRows();
    var pageSize = Math.max(1, parseInt((pageSizeSelect && pageSizeSelect.value || "50"), 10) || 50);
    var totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    page = clamp(page, 1, totalPages);

    var start = (page - 1) * pageSize;
    var pageRows = new Set(rows.slice(start, start + pageSize));
    allRows.forEach(function(row) {
      row.style.display = pageRows.has(row) ? "" : "none";
    });

    if (pageInfo) pageInfo.textContent = "page " + page + " / " + totalPages + " | matches=" + rows.length;
    if (prevBtn) prevBtn.disabled = page <= 1;
    if (nextBtn) nextBtn.disabled = page >= totalPages;
  };

  var onFilterChange = function() {
    page = 1;
    renderEvents();
  };

  if (searchInput) searchInput.addEventListener("input", onFilterChange);
  if (severitySelect) severitySelect.addEventListener("change", onFilterChange);
  if (typeInput) typeInput.addEventListener("input", onFilterChange);
  if (pageSizeSelect) pageSizeSelect.addEventListener("change", onFilterChange);
  if (prevBtn) prevBtn.addEventListener("click", function() {
    page -= 1;
    renderEvents();
  });
  if (nextBtn) nextBtn.addEventListener("click", function() {
    page += 1;
    renderEvents();
  });
  renderEvents();

  var intFmt = new Intl.NumberFormat("en-US");
  var dec2Fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
  var dec3Fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });

  var humanizeNs = function(value) {
    var absValue = Math.abs(value);
    if (absValue < 1000) return intFmt.format(Math.round(value)) + "ns";
    if (absValue < 1000000) return dec2Fmt.format(value / 1000) + "us";
    if (absValue < 1000000000) return dec2Fmt.format(value / 1000000) + "ms";
    return dec2Fmt.format(value / 1000000000) + "s";
  };
  var humanizeMs = function(value) {
    var absValue = Math.abs(value);
    if (absValue < 1) return dec3Fmt.format(value) + "ms";
    if (absValue < 1000) return dec2Fmt.format(value) + "ms";
    return dec2Fmt.format(value / 1000) + "s";
  };
  var humanizeBps = function(value) {
    var absValue = Math.abs(value);
    if (absValue < 1000) return intFmt.format(Math.round(value)) + "bps";
    if (absValue < 1000000) return dec2Fmt.format(value / 1000) + "Kbps";
    if (absValue < 1000000000) return dec2Fmt.format(value / 1000000) + "Mbps";
    return dec2Fmt.format(value / 1000000000) + "Gbps";
  };
  var humanizeBytes = function(value) {
    var absValue = Math.abs(value);
    if (absValue < 1024) return intFmt.format(Math.round(value)) + "B";
    if (absValue < 1048576) return dec2Fmt.format(value / 1024) + "KiB";
    if (absValue < 1073741824) return dec2Fmt.format(value / 1048576) + "MiB";
    return dec2Fmt.format(value / 1073741824) + "GiB";
  };
  var humanizeBySeries = function(seriesName, value) {
    var name = (seriesName || "").toLowerCase();
    var hasMsToken = /(^|[^a-z])ms([^a-z]|$)/.test(name);
    var hasNsToken = /(^|[^a-z])ns([^a-z]|$)/.test(name);

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

  var pointerIndex = function(svg, evt, length, width) {
    var rect = svg.getBoundingClientRect();
    if (!rect.width) return { idx: -1, x: 0, rect: rect };
    var ctm = svg.getScreenCTM();
    if (!ctm) return { idx: -1, x: 0, rect: rect };
    var point = svg.createSVGPoint();
    point.x = evt.clientX;
    point.y = evt.clientY;
    var local = point.matrixTransform(ctm.inverse());
    var xLocal = clamp(local.x, xPadding, width - xPadding);
    var span = Math.max(1, length - 1);
    var ratio = (xLocal - xPadding) / Math.max(1, width - xPadding * 2);
    var idx = clamp(Math.round(ratio * span), 0, length - 1);
    var x = ((idx / span) * (width - xPadding * 2)) + xPadding;
    return { idx: idx, x: x, rect: rect };
  };

  var attachSingleSeriesChart = function(svg) {
    var wrap = svg.closest(".chart-wrap");
    var tooltip = wrap && wrap.querySelector(".chart-tooltip");
    var inspector = wrap && wrap.querySelector(".chart-inspector");
    if (!tooltip) return;

    var seriesName = svg.getAttribute("data-series-name") || "";
    var values = (svg.getAttribute("data-series-values") || "")
      .split(",")
      .map(function(item) { return Number(item.trim()); })
      .filter(function(item) { return Number.isFinite(item); });
    if (!values.length) return;

    var minValue = toNumber(svg.getAttribute("data-min"), 0);
    var maxValue = toNumber(svg.getAttribute("data-max"), 0);
    var width = toNumber(svg.getAttribute("data-width"), 760);
    var height = toNumber(svg.getAttribute("data-height"), 150);
    var scale = (maxValue - minValue) || 1;
    var dot = svg.querySelector(".chart-hover-dot");
    var vline = svg.querySelector(".chart-hover-line");
    if (!dot || !vline) return;

    var pinnedIdx = -1;
    var renderInspector = function(idx) {
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

    var update = function(evt) {
      var point = pointerIndex(svg, evt, values.length, width);
      if (point.idx < 0) return;

      var value = values[point.idx];
      var y = ((1 - ((value - minValue) / scale)) * (height - xPadding * 2)) + xPadding;
      dot.setAttribute("cx", String(point.x));
      dot.setAttribute("cy", String(y));
      dot.setAttribute("visibility", "visible");
      vline.setAttribute("x1", String(point.x));
      vline.setAttribute("x2", String(point.x));
      vline.setAttribute("visibility", "visible");

      tooltip.textContent = "#" + (point.idx + 1) + " " + humanizeBySeries(seriesName, value);
      tooltip.style.display = "block";
      var xPx = ((point.x - xPadding) / Math.max(1, width - xPadding * 2)) * point.rect.width;
      var tooltipWidth = tooltip.offsetWidth || 220;
      var left = clamp(xPx + 12, 8, point.rect.width - tooltipWidth - 8);
      tooltip.style.left = left + "px";

      if (pinnedIdx >= 0) renderInspector(pinnedIdx);
    };

    var onClick = function(evt) {
      var point = pointerIndex(svg, evt, values.length, width);
      if (point.idx < 0) return;
      pinnedIdx = pinnedIdx === point.idx ? -1 : point.idx;
      renderInspector(pinnedIdx);
    };

    svg.addEventListener("mouseenter", update);
    svg.addEventListener("mousemove", update);
    svg.addEventListener("mouseleave", function() {
      dot.setAttribute("visibility", "hidden");
      vline.setAttribute("visibility", "hidden");
      tooltip.style.display = "none";
    });
    svg.addEventListener("click", onClick);
  };

  var attachMultiSeriesChart = function(svg) {
    var wrap = svg.closest(".chart-wrap");
    var tooltip = wrap && wrap.querySelector(".chart-tooltip");
    var inspector = wrap && wrap.querySelector(".chart-inspector");
    if (!tooltip) return;

    var groupName = svg.getAttribute("data-series-name") || "";
    var seriesObject = {};
    try {
      var parsed = JSON.parse(svg.getAttribute("data-multi-series") || "{}");
      if (parsed && typeof parsed === "object") seriesObject = parsed;
    } catch (_error) {
      return;
    }

    var entries = Object.entries(seriesObject)
      .map(function(_ref) {
        var name = _ref[0];
        var values = _ref[1];
        return [
          String(name),
          Array.isArray(values)
            ? values.map(function(item) { return Number(item); }).filter(function(item) { return Number.isFinite(item); })
            : [],
        ];
      })
      .filter(function(_ref2) {
        var values = _ref2[1];
        return values.length > 0;
      });
    if (!entries.length) return;

    var width = toNumber(svg.getAttribute("data-width"), 760);
    var vline = svg.querySelector(".chart-hover-line");
    if (!vline) return;

    var maxLength = entries.reduce(function(acc, _ref2) {
      var values = _ref2[1];
      return Math.max(acc, values.length);
    }, 0);
    var pinnedIdx = -1;

    var entryParts = function(idx) {
      return entries.map(function(_ref3) {
        var name = _ref3[0];
        var values = _ref3[1];
        if (idx >= values.length) return name + "=n/a";
        return name + "=" + humanizeBySeries(name + " " + groupName, values[idx]);
      });
    };

    var renderInspector = function(idx) {
      if (!inspector) return;
      if (idx < 0 || idx >= maxLength) {
        inspector.style.display = "none";
        inspector.textContent = "";
        return;
      }
      inspector.textContent = "point=#" + (idx + 1) + " | events=" + entries.length + " | " + entryParts(idx).join(" | ");
      inspector.style.display = "block";
    };

    var update = function(evt) {
      var point = pointerIndex(svg, evt, maxLength, width);
      if (point.idx < 0) return;

      vline.setAttribute("x1", String(point.x));
      vline.setAttribute("x2", String(point.x));
      vline.setAttribute("visibility", "visible");
      tooltip.textContent = "#" + (point.idx + 1) + " " + entryParts(point.idx).join(" | ");
      tooltip.style.display = "block";

      var xPx = ((point.x - xPadding) / Math.max(1, width - xPadding * 2)) * point.rect.width;
      var tooltipWidth = tooltip.offsetWidth || 320;
      var left = clamp(xPx + 12, 8, point.rect.width - tooltipWidth - 8);
      tooltip.style.left = left + "px";

      if (pinnedIdx >= 0) renderInspector(pinnedIdx);
    };

    var onClick = function(evt) {
      var point = pointerIndex(svg, evt, maxLength, width);
      if (point.idx < 0) return;
      pinnedIdx = pinnedIdx === point.idx ? -1 : point.idx;
      renderInspector(pinnedIdx);
    };

    svg.addEventListener("mouseenter", update);
    svg.addEventListener("mousemove", update);
    svg.addEventListener("mouseleave", function() {
      vline.setAttribute("visibility", "hidden");
      tooltip.style.display = "none";
    });
    svg.addEventListener("click", onClick);
  };

  Array.from(document.querySelectorAll("svg[data-series-values]")).forEach(attachSingleSeriesChart);
  Array.from(document.querySelectorAll("svg[data-multi-series]")).forEach(attachMultiSeriesChart);
})();
