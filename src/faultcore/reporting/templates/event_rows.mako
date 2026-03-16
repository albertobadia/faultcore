<%def name="render_event_rows(events, safe)">
<%
import json
def format_details(e):
    details = e.get('details', {})
    if isinstance(details, dict):
        return json.dumps(details)
    return str(details)
%>\
% if events:
${''.join("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td><code>{}</code></tr>".format(
    safe(e.get('ts', '')),
    safe(e.get('severity', '')),
    safe(e.get('type', '')),
    safe(e.get('source', '')),
    safe(e.get('name', '')),
    safe(format_details(e))
) for e in events)}
% else:
<tr><td colspan="6">No events</td></tr>
% endif
</%def>
