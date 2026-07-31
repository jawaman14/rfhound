# Multi-node linking

Connect several RFHound receivers / operators / computers into one shared
picture. Each receiver runs as a **node** and pushes its status and findings to a
central **hub** over HTTP. The hub keeps a live roster of nodes and a rolling feed
of reports, exposed as JSON and a small auto-refreshing status page.

With several geographically separated nodes this is the foundation for
**distributed spectrum monitoring** and RSSI-based localisation.

## Run a hub

```bash
rfhound hub --host 0.0.0.0 --port 8787 --token SECRET
# status page: http://<hub>:8787/      JSON: http://<hub>:8787/api/hub/state
```

`--token` sets a shared bearer token that nodes must present to write. Bind to
`127.0.0.1` unless you intend to expose it, and put TLS/auth in front for
anything beyond a trusted LAN.

## Link a node to it

```bash
# register + run a scan + push the result
rfhound node --hub http://HUB:8787 --id north --name "North roof" \
    --location "Bldg A" --scan drone --token SECRET --simulate

rfhound node --hub http://HUB:8787 --id north --scan recon   # survey + push
rfhound node --hub http://HUB:8787 --id north --scan imsi     # rogue-BTS score + push
```

Set defaults in config so nodes are one command:

```json
{ "hub_url": "http://10.0.0.5:8787", "node_id": "north", "hub_token": "SECRET" }
```

## API

| Method / path | Purpose |
|---|---|
| `POST /api/hub/register` | `{node_id, name, location}` — join the mesh |
| `POST /api/hub/report` | `{node_id, kind, data}` — push a finding |
| `GET /api/hub/state` | aggregated `{nodes, reports}` for dashboards/SIEM |

Transport is receive-only telemetry (JSON). The hub never commands a node and
there is no transmit path anywhere in the link.
