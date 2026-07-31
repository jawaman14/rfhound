"""User configuration for RFHound.

Config lives at ``$XDG_CONFIG_HOME/rfhound/config.json`` (falling back to
``~/.config/rfhound/config.json``). It stores sensible gain defaults, the output
directory, and — importantly — the transmit safety settings.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .exceptions import ConfigError


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "rfhound"
    return Path.home() / ".config" / "rfhound"


def config_path() -> Path:
    return _config_dir() / "config.json"


@dataclass
class TxAllowRange:
    """An operator-declared frequency range in which transmitting is permitted."""

    low_hz: int
    high_hz: int
    note: str = ""

    def contains(self, freq_hz: int) -> bool:
        return self.low_hz <= freq_hz <= self.high_hz


@dataclass
class Config:
    # Output.
    output_dir: str = str(Path.home() / "rfhound-captures")

    # Receive defaults.
    lna_gain: int = 16  # 0-40 dB in 8 dB steps
    vga_gain: int = 20  # 0-62 dB in 2 dB steps
    amp_enable: bool = False  # front-end +14 dB amplifier
    sample_rate: int = 8_000_000  # Hz

    # --- HackRF hardware options --------------------------------------------
    antenna_power: bool = False   # bias-tee: 3.3V / 50mA on the antenna port
    baseband_filter_hz: int = 0   # 0 = auto (<= 0.75 * sample_rate); else Hz
    freq_correction_ppm: int = 0  # internal crystal clock error correction
    device_serial: str = ""       # select a specific HackRF by serial (multi-unit)

    # --- Transmit safety (off by default) -----------------------------------
    tx_enabled: bool = False
    # Operator explicitly acknowledged the legal terms (ISO timestamp string).
    tx_consent_at: str = ""
    # Only these ranges may be transmitted in, even when tx_enabled is True.
    tx_allow_ranges: list[TxAllowRange] = field(default_factory=list)
    tx_gain: int = 20  # 0-47 dB
    # Operator's jurisdiction, printed in reports / warnings.
    jurisdiction: str = ""

    # UX.
    color: bool = True
    dev_mode: bool = False
    simulate_mode: bool = False   # global: run everything against synthetic data

    # --- LLM copilot (optional) ---------------------------------------------
    llm_provider: str = ""    # "anthropic" | "local" (OpenAI-compatible) | ""
    llm_model: str = ""       # e.g. "claude-..." or a local model name
    llm_base_url: str = ""    # local/OpenAI-compatible endpoint base URL

    # --- Multi-node linking -------------------------------------------------
    hub_url: str = ""         # aggregator this node reports to
    node_id: str = ""         # this node's identity in a sensor mesh
    hub_token: str = ""       # shared bearer token for hub auth

    def is_tx_range_allowed(self, freq_hz: int) -> bool:
        return any(r.contains(freq_hz) for r in self.tx_allow_ranges)

    # -- (de)serialisation ---------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        ranges = [TxAllowRange(**r) for r in data.get("tx_allow_ranges", [])]
        data = {**data, "tx_allow_ranges": ranges}
        # Drop unknown keys to stay forward/backward compatible.
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        data = {k: v for k, v in data.items() if k in known}
        return cls(**data)


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"Could not read config at {path}: {exc}") from exc
    return Config.from_dict(data)


def save_config(cfg: Config) -> Path:
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg.to_dict(), indent=2))
    except OSError as exc:
        raise ConfigError(f"Could not write config at {path}: {exc}") from exc
    return path
