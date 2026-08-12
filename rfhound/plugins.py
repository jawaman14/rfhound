"""Mod / plugin system.

Lets operators and integrators extend RFHound without touching the core: drop a
``*.py`` mod into a mods directory (default ``$XDG_CONFIG_HOME/rfhound/mods``)
and it can register custom **bands**, **decoder recipes**, and **detectors**.

A mod is a normal Python module exposing a ``register(api)`` function:

    # ~/.config/rfhound/mods/my_site.py
    NAME = "Acme site profile"
    VERSION = "1.0"

    def register(api):
        api.add_band(name="Acme telemetry", low_mhz=869.4, high_mhz=869.6,
                     category="ism", description="On-site 869 MHz telemetry",
                     tags=("site", "iot"))
        api.add_detector("acme_health", lambda cfg: {"ok": True})

Mods are code you choose to run — only load mods you trust.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import bandplan
from .bandplan import Band
from .modules import decode as decode_mod
from .modules import demod as demod_mod


def mods_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else (Path.home() / ".config")
    return root / "rfhound" / "mods"


@dataclass
class ModAPI:
    """The surface a mod uses to extend RFHound."""

    _detectors: dict[str, Callable] = field(default_factory=dict)
    added_bands: list[str] = field(default_factory=list)
    added_recipes: list[str] = field(default_factory=list)
    added_decoders: list[str] = field(default_factory=list)

    def add_band(self, *, name, low_mhz, high_mhz, category, description,
                 decoder=None, center_mhz=None, region="mod", tags=()) -> None:
        band = Band(
            name=name,
            low_hz=int(low_mhz * 1e6),
            high_hz=int(high_mhz * 1e6),
            category=category,
            description=description,
            decoder=decoder,
            center_hz=int(center_mhz * 1e6) if center_mhz else None,
            region=region,
            tags=tuple(tags),
        )
        bandplan.BANDS.append(band)
        self.added_bands.append(name)

    def add_recipe(self, *, recipe_id, name, category, tool, default_freq_mhz,
                   description, build, note="") -> None:
        recipe = decode_mod.Recipe(
            id=recipe_id, name=name, category=category, tool=tool,
            default_freq_hz=int(default_freq_mhz * 1e6),
            description=description, build=build, note=note,
        )
        decode_mod.RECIPES[recipe_id] = recipe
        self.added_recipes.append(recipe_id)

    def add_detector(self, name: str, fn: Callable) -> None:
        self._detectors[name] = fn

    def add_soft_decoder(self, decoder_id: str, name: str, fn: Callable, *,
                         kind: str = "bits", description: str = "") -> None:
        """Register a pure-Python decode/demod function (see ``modules.demod``).

        ``fn(payload, **opts)`` runs in-process; ``kind`` is ``bits``/``bytes``/
        ``iq``. It shows up in ``rfhound mods decoders`` and ``mods run``.
        """
        demod_mod.register(decoder_id, name, fn, kind=kind, description=description,
                           source="mod")
        self.added_decoders.append(decoder_id)

    # Handy re-exports so a mod can build decoders without importing internals.
    demod = demod_mod


@dataclass
class LoadedMod:
    name: str
    version: str
    path: str
    bands: list[str]
    recipes: list[str]
    detectors: list[str]
    decoders: list[str] = field(default_factory=list)
    error: str | None = None


def load_mods(directory: Path | None = None) -> list[LoadedMod]:
    """Import every ``*.py`` mod in *directory* and apply its registrations."""
    directory = directory or mods_dir()
    loaded: list[LoadedMod] = []
    if not directory.exists():
        return loaded
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        api = ModAPI()
        name = path.stem
        version = "?"
        error = None
        try:
            spec = importlib.util.spec_from_file_location(f"rfhound_mod_{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(module)
            name = getattr(module, "NAME", path.stem)
            version = str(getattr(module, "VERSION", "?"))
            register = getattr(module, "register", None)
            if callable(register):
                register(api)
            else:
                error = "no register(api) function"
        except Exception as exc:  # a bad mod must not crash RFHound
            error = f"{type(exc).__name__}: {exc}"
        loaded.append(LoadedMod(
            name=name, version=version, path=str(path),
            bands=api.added_bands, recipes=api.added_recipes,
            detectors=list(api._detectors.keys()), decoders=api.added_decoders,
            error=error,
        ))
    return loaded


SAMPLE_MOD = '''\
"""Sample RFHound mod. Copy to ~/.config/rfhound/mods/ and edit."""

NAME = "Sample site profile"
VERSION = "1.0"


def register(api):
    # Add a custom band that will show up in `rfhound bands`.
    api.add_band(
        name="Sample site telemetry",
        low_mhz=869.4, high_mhz=869.65, category="ism",
        description="Example on-site 869 MHz telemetry link",
        center_mhz=869.5, tags=("site", "iot"),
    )

    # Register a custom named detector callable (cfg) -> result.
    def health_check(cfg):
        return {"status": "ok"}

    api.add_detector("sample_health", health_check)

    # Register your own decode function. It runs in-process on a payload
    # (kind="bits" | "bytes" | "iq"). Here: Manchester-decode, pack to bytes,
    # and verify a trailing CRC8 — using the built-in demod primitives.
    def acme_decode(bits):
        d = api.demod
        payload = d.manchester_decode(bits)
        data = d.bits_to_bytes([b or 0 for b in payload])
        if not data:
            return {"ok": False, "reason": "empty"}
        body, crc = data[:-1], data[-1]
        return {"ok": d.crc8(body) == crc, "bytes": data.hex()}

    api.add_soft_decoder("acme", "Acme telemetry frame", acme_decode,
                         kind="bits", description="Manchester + CRC8 frame")
'''


def write_sample_mod(directory: Path | None = None) -> Path:
    directory = directory or mods_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "sample_site.py"
    path.write_text(SAMPLE_MOD)
    return path
