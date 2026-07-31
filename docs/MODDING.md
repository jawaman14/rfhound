# Modding / plugins

RFHound is extensible: drop a Python **mod** into the mods directory and it can
register custom **bands**, **decoder recipes**, and **detectors** — no changes to
the core. This is how a customer or integrator adapts RFHound to a site, a
proprietary radio, or a new signal of interest.

> Mods are ordinary Python code that RFHound executes. **Only install mods you
> trust.** RFHound never auto-loads mods silently — they load when you run
> `rfhound mods list` (or a future explicit `--mods` flag).

## Where mods live

```
$XDG_CONFIG_HOME/rfhound/mods/     (default: ~/.config/rfhound/mods/)
```

Files beginning with `_` are ignored. Get a starter template:

```bash
rfhound mods sample      # writes sample_site.py into the mods directory
rfhound mods list        # loads mods and shows what each one registered
rfhound mods list --dir ./my-mods   # load from a custom directory
```

## Anatomy of a mod

```python
# ~/.config/rfhound/mods/acme.py
NAME = "Acme site profile"
VERSION = "1.0"

def register(api):
    # 1) Add a band -> appears in `rfhound bands`, recon, sweeps.
    api.add_band(
        name="Acme telemetry",
        low_mhz=869.4, high_mhz=869.65, category="ism",
        description="On-site 869 MHz telemetry link",
        center_mhz=869.5, tags=("site", "iot"),
    )

    # 2) Add a receive-only decoder recipe -> appears in `rfhound decode list`.
    def build_cmd(cfg, freq_hz, seconds):
        return ["rtl_433", "-d", "driver=hackrf", "-f", str(freq_hz), "-F", "json"]

    api.add_recipe(
        recipe_id="acme_tlm", name="Acme telemetry decoder", category="ism",
        tool="rtl_433", default_freq_mhz=869.5,
        description="Decode Acme site telemetry", build=build_cmd,
    )

    # 3) Add a named detector callable(cfg) -> anything.
    def site_health(cfg):
        return {"status": "ok"}

    api.add_detector("acme_health", site_health)
```

## The `api` surface

| Method | Registers |
|---|---|
| `api.add_band(name, low_mhz, high_mhz, category, description, decoder=None, center_mhz=None, region="mod", tags=())` | A band in the knowledge base |
| `api.add_recipe(recipe_id, name, category, tool, default_freq_mhz, description, build, note="")` | A decoder recipe (`build(cfg, freq_hz, seconds) -> argv`) |
| `api.add_detector(name, fn)` | A named detector callable |

Keep mods **receive-and-analyse**. The same policy as the core applies: no
jamming, spoofing, or brute-force transmit modules.
