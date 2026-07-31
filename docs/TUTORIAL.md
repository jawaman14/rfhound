# Tutorial — set up RFHound from scratch

This walks you from nothing to a working RFHound, **with or without a HackRF**.
It takes about 5 minutes. Everything works in *simulate mode* first, so you can
learn the tool before any hardware arrives.

> RFHound is receive-first. Before you ever transmit, read [LEGAL.md](LEGAL.md).

---

## Step 0 — What you need

- **Python 3.9 or newer** (`python3 --version`).
- Optional: a **HackRF One** and an antenna. Not required to follow this tutorial.
- Optional later: SDR decoder tools (`rtl_433`, `dump1090`, …) — RFHound tells
  you which to install, when you need them.

---

## Step 1 — Get the code

```bash
git clone https://github.com/jawaman14/rfhound.git
cd rfhound
```

## Step 2 — Install (one command)

The installer creates an isolated virtual environment and installs RFHound into
it, so nothing touches your system Python:

```bash
./install.sh            # add --dev if you want to run the tests too
```

Prefer to do it by hand, or on Windows? That's fine:

```bash
python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e .
```

You should now have the `rfhound` command:

```bash
rfhound --version
```

> **Tip:** each new terminal, re-activate the environment with
> `source .venv/bin/activate` (or use `make` targets, below).

## Step 3 — First-run setup

```bash
rfhound setup
```

This writes a default config, tells you how many SDR tools are installed, whether
a HackRF is detected, and prints your next steps.

## Step 4 — Try it with no hardware

Everything runs in **simulate mode** with `--simulate`:

```bash
rfhound --simulate recon        # survey the spectrum (synthetic data)
rfhound --simulate sweep 433 435
rfhound at 433.92               # what's on this frequency + every tool for it
rfhound tune adsb               # what frequency do I need? → 1090 MHz
rfhound --simulate defense drone-scan
```

Open the **dashboard** in your browser (also simulated):

```bash
rfhound --simulate web --open   # http://127.0.0.1:8000
```

You'll get a live spectrum + waterfall, a recon panel, threat detection, and the
frequency knowledge base — all from synthetic data, no radio needed.

## Step 5 — Plug in a HackRF (optional)

1. Connect the HackRF and antenna.
2. Install the host tools so RFHound can see it:
   - **Linux:** `sudo apt install hackrf` (you may also need to be in the
     `plugdev` group — `rfhound doctor` will hint if so).
   - **macOS:** `brew install hackrf`.
3. Confirm it's detected:
   ```bash
   rfhound doctor        # shows device + which tools are installed
   ```
4. Now drop the `--simulate` flag to use the real radio:
   ```bash
   rfhound recon
   rfhound sweep 430 440
   ```

## Step 6 — Add decoders as you need them

RFHound drives best-of-breed decoders. Install only what you want:

```bash
sudo apt install rtl-433 multimon-ng soapysdr-module-hackrf   # common ones
rfhound decode list                # see recipes + which tools are ready
rfhound decode run rtl433          # decode 433 MHz devices
```

`rfhound at <freq>` always shows exactly which decoders apply to the band you're
on and whether their tool is installed.

## Handy shortcuts (Makefile)

If you have `make`:

```bash
make help        # list all tasks
make dev         # install + test/lint tools
make test        # run the 125-test suite
make dashboard   # launch the simulated dashboard
make demo        # run a simulated recon survey
```

## Where things live

- Config: `~/.config/rfhound/config.json` (`rfhound config path`)
- Captures: `~/rfhound-captures` by default (change `output_dir` in config)
- Mods/plugins: `~/.config/rfhound/mods/` (`rfhound mods sample`)

## Where to go next

- [HELP.md](HELP.md) — every command, with examples
- [DEFENSE.md](DEFENSE.md) — the detection & hardening suite
- [FREQUENCIES.md](FREQUENCIES.md) — what lives across 1 MHz – 6 GHz
- [COPILOT.md](COPILOT.md) — drive RFHound with an LLM
- [MULTINODE.md](MULTINODE.md) — link several receivers into one hub
