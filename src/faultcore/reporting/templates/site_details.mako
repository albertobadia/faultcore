<%def name="site_item(name, fault_rate, fault_events, delay_chart, decision_flags, bucket_counters)"><details class='metric-details site-item' data-item-name='${name.lower()}' data-fault-events='${fault_events}'>
  <summary><code>${name}</code> | fault_rate=${fault_rate}% | fault_events=${fault_events}</summary>
  ${delay_chart}
  ${decision_flags}
  ${bucket_counters}
</details></%def>
<%def name="function_item(name, throughput, network_panel, timeline_charts)"><details class='metric-details function-item' data-item-name='${name.lower()}' data-fault-events='0'>
  <summary><code>${name}</code> | throughput_bps=${throughput}</summary>
  ${network_panel}
  ${timeline_charts}
</details></%def>
