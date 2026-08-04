"""The automation menu — a separate console for scheduled RF tasks.

Reached via ``rfhound automate`` (or ``rfhound automate menu``). Kept apart from
the main menu so operators can build and run watch tasks without wading through
the analysis tools.
"""

from __future__ import annotations

from . import console, device
from .config import Config
from .exceptions import RFHoundError
from .modules import automation as auto_mod


def _simulate() -> bool:
    if device.is_present():
        return False
    console.warn("No HackRF detected — automations will run in SIMULATE mode.")
    return True


def _list(cfg: Config) -> None:
    if not cfg.automations:
        console.print_("(no automations defined yet)")
        return
    rows = []
    for a in cfg.automations:
        n = auto_mod._norm(a)
        p = n["params"]
        pstr = " ".join(f"{k}={v}" for k, v in p.items()) or "—"
        rows.append([n["name"], n["task"], f"{n['interval_s']}s", n["alert_on"],
                     "on" if n["enabled"] else "off", pstr])
    console.table("Automations", ["Name", "Task", "Every", "Alert", "Enabled", "Params"], rows)


def _add(cfg: Config) -> None:
    console.rule("New automation")
    name = console.ask("Name")
    if not name:
        return
    task = console.ask("Task", default="recon", choices=list(auto_mod.TASKS))
    interval = int(console.ask("Run every N seconds", default="60"))
    params = {}
    if task in ("monitor", "sweep"):
        params["start"] = float(console.ask("Start MHz", default="433"))
        params["stop"] = float(console.ask("Stop MHz", default="435"))
    alert_on = console.ask("Alert when", default="threat", choices=list(auto_mod.ALERT_MODES))
    webhook = console.ask("Webhook URL (blank = none)", default="")
    auto_mod.add_automation(cfg, name, task, interval_s=interval, params=params,
                            alert_on=alert_on, webhook=webhook)
    console.success(f"Added automation '{name}'.")


def _remove(cfg: Config) -> None:
    name = console.ask("Name to remove")
    if name and auto_mod.remove_automation(cfg, name):
        console.success(f"Removed '{name}'.")
    else:
        console.warn("Not found.")


def _toggle(cfg: Config) -> None:
    name = console.ask("Name to enable/disable")
    cur = next((auto_mod._norm(a)["enabled"] for a in cfg.automations
                if a.get("name") == name), None)
    if cur is None:
        console.warn("Not found.")
        return
    auto_mod.set_enabled(cfg, name, not cur)
    console.success(f"'{name}' is now {'disabled' if cur else 'enabled'}.")


def _run_once(cfg: Config, simulate: bool) -> None:
    name = console.ask("Name to run now (blank = all due)", default="")
    autos = [a for a in cfg.automations if not name or a.get("name") == name]
    if not autos:
        console.warn("No matching automation.")
        return
    for a in autos:
        res = auto_mod.run_task(cfg, a, simulate=simulate)
        alerting = auto_mod.should_alert(a, res)
        auto_mod.fire(cfg, a, res, alerting=alerting)
        tag = "ALERT" if alerting else "ok"
        (console.error if alerting else console.success)(
            f"{auto_mod._norm(a)['name']} · {tag}: {res.summary}")


def run_automation_menu(cfg: Config) -> int:
    simulate = _simulate()
    items = [
        "List automations",
        "Add an automation",
        "Remove an automation",
        "Enable / disable",
        "Run one now (or all due)",
        "Start the scheduler (loop)",
        "Back / quit",
    ]
    while True:
        console.rule("RFHound — automation menu")
        _list(cfg)
        for i, label in enumerate(items, 1):
            console.print_(f"  {i}. {label}")
        c = console.ask("Choose", default="1").strip().lower()
        if c in ("7", "q", "quit", "back", "exit"):
            return 0
        try:
            if c == "1":
                pass  # already listed above
            elif c == "2":
                _add(cfg)
            elif c == "3":
                _remove(cfg)
            elif c == "4":
                _toggle(cfg)
            elif c == "5":
                _run_once(cfg, simulate)
            elif c == "6":
                console.print_("Scheduler running — Ctrl-C to return to the menu.")
                auto_mod.run_scheduler(cfg, simulate=simulate)
            else:
                console.warn("Enter a valid number.")
        except (RFHoundError, ValueError) as exc:
            console.error(str(exc))
        except KeyboardInterrupt:
            console.print_("")
            continue
