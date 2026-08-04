# LLM copilot

RFHound can be driven in natural language by a **Claude API** or a **local
(OpenAI-compatible) model** — or an offline keyword planner that needs no network.

> **Safety model.** The copilot can only call a fixed set of **receive-and-analyse
> actions** (`llm/actions.py`). It **cannot transmit, replay, capture, or run
> arbitrary code** — those actions are simply not in its registry. The only
> authoring action, `draft_mod`, writes proposed code to `mods/pending/` for a
> human to review; nothing the model writes is ever auto-loaded or executed.

## Usage

**Interactive AI console** (a chat REPL, separate from the main menu):

```bash
rfhound ai                       # offline by default
rfhound ai --provider anthropic  # or local
```

Inside it, type plain English, or use slash commands:
`/help` · `/actions` (list what it can call) · `/provider <offline|anthropic|local>` ·
`/history` · `/clear` · `/quit`. The offline planner handles the common asks
(jamming, drones, IMSI catchers, spoofing, "what's at 1090 MHz?") with no network.

**One-shot** queries:

```bash
rfhound ask "is there a jammer on the 433 band?"        # offline planner (default)
rfhound ask "check for an IMSI catcher" --provider offline
rfhound ask "survey the spectrum and flag anything odd" --provider anthropic
rfhound ask "scan for drones" --provider local
```

## Providers

| Provider | How to configure |
|---|---|
| `offline` | Default; no network. Routes common requests to one action. |
| `anthropic` | Set `ANTHROPIC_API_KEY`; optional `llm_model` in config (default a current Claude model). Uses the Messages API tool-use loop. |
| `local` | Set `llm_base_url` (e.g. `http://localhost:11434/v1` for Ollama) and `llm_model`; optional `RFHOUND_LLM_API_KEY`. Uses OpenAI-compatible tool calls. |

Configure defaults in `~/.config/rfhound/config.json`:

```json
{ "llm_provider": "local", "llm_base_url": "http://localhost:11434/v1", "llm_model": "llama3.1" }
```

## Available actions (all receive/analysis)

`status`, `list_bands`, `find_band`, `sweep`, `recon`, `list_decoders`,
`drone_scan`, `spoof_check`, `imsi_catcher_check`, `hop_detect`, `respond`,
and `draft_mod` (pending-review only). Add your own analysis actions by editing
`rfhound/llm/actions.py`.
