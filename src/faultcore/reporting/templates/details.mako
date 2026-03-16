<%def name="details_item(class_name, item_name, fault_events, summary_html, content_html)"><details class='metric-details ${class_name}' data-item-name='${item_name.lower()}' data-fault-events='${fault_events}'>
  <summary>${summary_html}</summary>
  ${content_html}
</details></%def>
<%def name="site_summary(name, fault_rate, fault_events)"><code>${name}</code> | fault_rate=${fault_rate}% | fault_events=${fault_events}</%def>
<%def name="function_summary(name, throughput)"><code>${name}</code> | throughput_bps=${throughput}</%def>
<%def name="no_data(msg)"><p class='muted'>${msg}</p></%def>
