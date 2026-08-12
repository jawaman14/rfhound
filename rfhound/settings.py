"""User-editable settings registry.

A single source of truth for the configuration fields a user may safely change
from the CLI (``rfhound config set/get/list``) and the interactive Settings
menu. Each entry knows its type, help text, and how to validate a value — so
both front ends share the same coercion and error messages.

Transmit-safety fields are deliberately *not* here: those go through the gated
``tx enable`` flow, never a generic setter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .config import Config


@dataclass(frozen=True)
class Setting:
    key: str
    kind: str                       # "str" | "int" | "float" | "bool"
    help: str
    choices: tuple = ()             # allowed string values (empty = any)
    minimum: float | None = None
    maximum: float | None = None
    step: int | None = None         # value must be a multiple of this (ints)
    validate: Callable[[Any], None] | None = None


def _positive_or_zero(v):
    if v < 0:
        raise ValueError("must be >= 0")


# The editable surface. Order is the display order in `config list` / the menu.
EDITABLE: tuple[Setting, ...] = (
    Setting("output_dir", "str", "Where captures and reports are written"),
    Setting("lna_gain", "int", "RX LNA gain (dB)", minimum=0, maximum=40, step=8),
    Setting("vga_gain", "int", "RX VGA/baseband gain (dB)", minimum=0, maximum=62, step=2),
    Setting("amp_enable", "bool", "Front-end +14 dB amplifier"),
    Setting("sample_rate", "int", "Sample rate (Hz)", minimum=2_000_000, maximum=20_000_000),
    Setting("antenna_power", "bool", "Bias-tee (3.3V) on the antenna port"),
    Setting("baseband_filter_hz", "int", "Baseband filter (Hz; 0 = auto)", validate=_positive_or_zero),
    Setting("freq_correction_ppm", "int", "Crystal clock error correction (ppm)"),
    Setting("device_serial", "str", "Select a specific HackRF by serial"),
    Setting("scan_workers", "int", "Parallel worker threads for combined scans",
            minimum=1, maximum=16),
    Setting("color", "bool", "Colourised terminal output"),
    Setting("simulate_mode", "bool", "Global simulate mode (synthetic data everywhere)"),
    Setting("dev_mode", "bool", "Developer mode: verbose debug + tracebacks"),
    Setting("jurisdiction", "str", "Operator jurisdiction (printed in reports)"),
    Setting("llm_provider", "str", "AI copilot backend", choices=("", "anthropic", "local")),
    Setting("llm_model", "str", "AI copilot model name"),
    Setting("llm_base_url", "str", "AI copilot endpoint base URL (local/OpenAI-compatible)"),
    Setting("hub_url", "str", "Aggregator hub this node reports to"),
    Setting("node_id", "str", "This node's identity in a sensor mesh"),
)

_BY_KEY = {s.key: s for s in EDITABLE}

_TRUE = {"1", "true", "yes", "on", "y", "t"}
_FALSE = {"0", "false", "no", "off", "n", "f"}


def get_setting(key: str) -> Setting:
    if key not in _BY_KEY:
        raise KeyError(key)
    return _BY_KEY[key]


def coerce(setting: Setting, raw: Any) -> Any:
    """Parse and validate *raw* for *setting*; return the typed value or raise ValueError."""
    if setting.kind == "bool":
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in _TRUE:
            return True
        if s in _FALSE:
            return False
        raise ValueError(f"'{raw}' is not a boolean (use on/off, true/false, yes/no)")
    if setting.kind == "int":
        try:
            val: Any = int(str(raw).strip())
        except ValueError:
            raise ValueError(f"'{raw}' is not an integer")
    elif setting.kind == "float":
        try:
            val = float(str(raw).strip())
        except ValueError:
            raise ValueError(f"'{raw}' is not a number")
    else:  # str
        val = str(raw)
        if setting.choices and val not in setting.choices:
            raise ValueError(f"must be one of: {', '.join(repr(c) for c in setting.choices)}")
        return val

    if setting.minimum is not None and val < setting.minimum:
        raise ValueError(f"must be >= {setting.minimum:g}")
    if setting.maximum is not None and val > setting.maximum:
        raise ValueError(f"must be <= {setting.maximum:g}")
    if setting.step and val % setting.step != 0:
        raise ValueError(f"must be a multiple of {setting.step}")
    if setting.validate:
        setting.validate(val)
    return val


def set_value(cfg: Config, key: str, raw: Any) -> Any:
    """Validate and apply a single setting on *cfg* in place. Returns the stored value."""
    setting = get_setting(key)
    value = coerce(setting, raw)
    setattr(cfg, key, value)
    return value


def current(cfg: Config) -> list[dict]:
    """Snapshot of every editable setting: {key, kind, value, help, choices}."""
    out = []
    for s in EDITABLE:
        out.append({"key": s.key, "kind": s.kind, "value": getattr(cfg, s.key, None),
                    "help": s.help, "choices": list(s.choices)})
    return out
