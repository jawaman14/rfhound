# Automation

Run RF tasks on a schedule, with triggers and alerting — a separate console from
the main menu. Define named automations, and a runner executes each when it's
due, evaluates a condition, and fires actions: **log** to a JSONL file, **print**
an alert, and/or **POST to a webhook**. All tasks are receive-and-analyse.

## The automation menu

```bash
rfhound automate            # opens the interactive automation menu
```

Add / remove / enable-disable automations, run one on demand, or start the
scheduler loop — all guided.

## Scriptable commands

```bash
# define automations
rfhound automate add sitewatch monitor --start 433 --stop 435 --interval 30 --alert-on threat
rfhound automate add droney   drone   --interval 60 --webhook https://example/hook
rfhound automate add survey    recon   --interval 300 --alert-on change

rfhound automate list                 # see them
rfhound automate once droney --simulate   # run one now
rfhound automate disable survey
rfhound automate run                  # start the scheduler (Ctrl-C to stop)
```

## Tasks

| Task | What it watches | Alerts when |
|------|------------------|-------------|
| `recon` | high-value bands | `change`: a new band goes active |
| `monitor` | a band's noise floor (needs `--start/--stop`) | `threat`: jamming/interference |
| `sweep` | peaks in a range (`--start/--stop`) | `change`: a new peak appears |
| `drone` | drone control/video bands | `threat`: drone RF detected |
| `imsi` | cellular parameters | `threat`: rogue-BTS indicators |
| `hop` | frequency-agile emitters | `threat`: hopping suspected |
| `gnss` | GNSS integrity (`--param file=obs.json`, or a sim `--param scenario=…`) | `threat`: jamming/spoofing |
| `emitters` | builds the emitter catalogue / EOB from a range (`--start/--stop`) | `change`: a new emitter appears |

Extra task parameters go through `--param KEY=VALUE` (repeatable), e.g.
`--param file=obs.json`, `--param scenario=spoofing`, `--param static=true`.

## Alert modes

- `threat` — fire only when the task detects something (default).
- `change` — fire when the result changes vs. the previous run (new band/peak).
- `always` — fire every run (useful for heartbeat logging).

Add `--cooldown N` to suppress repeat alerts within N seconds, so a standing
condition (e.g. a persistent jammer) alerts once instead of every interval.

## Where things go

- Definitions persist in `~/.config/rfhound/config.json` (`automations`).
- Every run appends a JSON line to `~/.config/rfhound/automations.log`.
- Webhooks receive the event JSON (`name`, `task`, `alert`, `summary`, `data`).
- Email alerts go through the configured SMTP server (`rfhound config smtp …`).
- `rfhound automate run --ndjson` streams each event as one JSON line to stdout —
  a SIEM feed you can pipe into a collector: `rfhound automate run --ndjson | vector`.

Automations never transmit. Pair a `monitor`/`drone`/`imsi` automation with a
webhook to wire RF alerts straight into a SIEM or chat channel.
