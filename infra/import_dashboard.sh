#!/bin/bash
# Import Grafana Dashboard

DASHBOARD_FILE="/tmp/grafana-security-dashboard.json"
IMPORT_FILE="/tmp/import_dashboard.json"

# Create import JSON
python3 -c "
import json

with open('$DASHBOARD_FILE', 'r') as f:
    dashboard = json.load(f)

import_data = {
    'dashboard': dashboard,
    'overwrite': True,
    'inputs': [
        {
            'name': 'DS_PROMETHEUS',
            'label': 'Prometheus',
            'value': 'prometheus',
            'type': 'datasource'
        }
    ]
}

with open('$IMPORT_FILE', 'w') as f:
    json.dump(import_data, f, indent=2)

print('Import data created')
"

# Import dashboard
curl -s -X POST http://localhost:3000/api/dashboards/db \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Basic YWRtaW46TnVvdGFvX0dyYWZhbmFfMjAyNA==' \
  -d @$IMPORT_FILE | python3 -m json.tool 2>&1 | head -20