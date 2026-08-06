# RFHound help & command reference

RFHound is a **defensive** HackRF reconnaissance & RF situational-awareness
toolkit. It drives best-of-breed SDR tools behind one friendly interface, ships a
frequency knowledge base, and adds detection, reporting, a web dashboard, an LLM
copilot, and multi-node linking. **Receive-first**: transmit is off by default
and narrowly gated (see [LEGAL.md](LEGAL.md)).

Run `rfhound` with no arguments for a guided menu, or `rfhound <command> -h` for
per-command help.

## Global flags

| Flag | Effect |
|---|---|
| `--simulate` | Force synthetic data for any command (no hardware needed) |
| `--dev` | Developer mode: verbose debug + full tracebacks |
| `--version` | Print version |

```bash
rfhound --simulate recon        # full offline demo
rfhound --dev sweep 433 435     # verbose
```

## Quick start

```bash
pip install -e .                # installs the `rfhound` command
rfhound doctor                  # what's installed? is a HackRF attached?
rfhound at 433.92               # what's on this frequency + every tool for it
rfhound tune adsb               # what frequency do I need?
rfhound --simulate web --open   # launch the dashboard with no hardware
```

## Command reference

### Orientation
| Command | What it does |
|---|---|
| `doctor` | Check external tools, HackRF device, and config |
| `menu` | Guided interactive menu |
| `dev` | Developer diagnostics (module/tool inventory) |
| `bands [--category C] [--tag T] [--search Q] [-v]` | Browse the knowledge base |
| **`at <MHz> [--json]`** | Identify the band at a frequency and list all its tools |
| **`tune <query> [--json]`** | Find the frequency to tune to for a protocol/name |

### Receive & analyse
| Command | What it does |
|---|---|
| `sweep <start> <stop> [--bin --snr --sweeps --top]` | Spectrogram + peak detection |
| `sweep … --watch [--interval --count]` | Live, continuously-updating spectrum |
| `recon [--category] [--report file.md/html]` | Auto-survey high-value bands |
| `wifi channels [--band 2.4\|5\|both]` | List the Wi-Fi channel plan (DFS flagged) |
| `wifi survey [--band 2.4\|5\|both] [--snr]` | Wi-Fi channel occupancy + clearest-channel pick (RX-only) |
| `capture <MHz> <sec> [--name --rate --note]` | Record IQ + SigMF metadata |
| `decode list` / `decode run <id> [--freq --seconds --dry-run]` | Protocol decoders |
| `gnuradio status\|list\|gen <preset> --freq MHz` | Generate GNU Radio RX flowgraphs |

### Defense & threat detection
| Command | What it does |
|---|---|
| `defense monitor <start> <stop>` | Jamming / interference detection |
| `defense replay-check [--file --fixed]` | Replay-attack detection |
| `defense rolling-assess [--file --kind]` | Fixed vs rolling-code posture |
| `defense resilience --device N` | Lab resilience test (uses gated replay) |
| `defense baseline save\|diff` | TSCM rogue-emitter (bug-sweep) detection |
| `defense spoof-check adsb\|ais` | Ghost-aircraft / vessel spoof detection |
| `defense drone-scan` | Counter-UAS band-activity detection |
| `defense hop-detect` | Frequency-hopping (agile) emitter detection |
| `defense imsi-catcher [--file]` | Rogue base station / IMSI-catcher detection |
| `defense respond <threat>` | Defensive counter-threat playbook |

### Transmit (gated — read LEGAL.md)
| Command | What it does |
|---|---|
| `tx enable --allow MHZ-MHZ` / `tx status` / `tx disable` | Manage transmit authorization |
| `replay <file> --authorized` | Replay YOUR OWN capture (consent + allow-list + flag) |

### Platform
| Command | What it does |
|---|---|
| `web [--host --port --simulate --open]` | Browser dashboard + REST API |
| `ask "<query>" [--provider offline\|anthropic\|local]` | LLM copilot (receive-only) |
| `hub [--host --port --token]` | Run the multi-node aggregator |
| `node --hub URL --id N [--scan recon\|drone\|imsi]` | Push a receiver's findings to a hub |
| `mods list\|sample` | Manage extension mods/plugins |
| `config show\|init\|path` | Configuration |

## The two frequency helpers (new in 1.0)

**"What am I looking at?"** — `rfhound at 1090` prints the band, its decoders
(with tool-ready status), the threat detectors that apply, GNU Radio presets, and
copy-paste commands. `--json` for automation.

**"What frequency do I need?"** — `rfhound tune pager` returns the POCSAG/FLEX
frequencies; `rfhound tune drone`, `rfhound tune ais`, `rfhound tune weather`, etc.

## Where things live
- Config: `~/.config/rfhound/config.json` (`rfhound config path`)
- Captures: `output_dir` (default `~/rfhound-captures`)
- Mods: `~/.config/rfhound/mods/` (`rfhound mods sample`)

## More docs
[README](../README.md) · [USAGE](USAGE.md) · [DEFENSE](DEFENSE.md) ·
[FREQUENCIES](FREQUENCIES.md) · [GNURADIO](GNURADIO.md) · [COPILOT](COPILOT.md) ·
[MULTINODE](MULTINODE.md) · [MODDING](MODDING.md) · [ARCHITECTURE](ARCHITECTURE.md) ·
[LEGAL](LEGAL.md)
