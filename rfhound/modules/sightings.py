"""Sightings tracker — remember the IDs you decode.

Many decoders emit a stable identifier: aircraft ICAO, vessel MMSI, an rtl_433
sensor/TPMS id, a pager capcode, a cell CID. This keeps a small persistent
database of those IDs with first-seen / last-seen / count, so you can build a
picture of the emitters around a site over time.

Purely a log of what you received — no transmit, no lookup services.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


def sightings_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else (Path.home() / ".config")
    return root / "rfhound" / "sightings.json"


@dataclass
class Sighting:
    kind: str
    id: str
    first_seen: float
    last_seen: float
    count: int = 1
    freq_mhz: float | None = None
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id}"


# Where each decoder's identifier lives in its JSON output.
ID_FIELDS: dict[str, list[str]] = {
    "adsb": ["icao", "hex", "ICAO"],
    "uat978": ["icao", "hex"],
    "ais": ["mmsi", "MMSI"],
    "rtl433": ["id", "device_id", "sensor_id"],
    "tpms": ["id"],
    "pocsag": ["address", "capcode"],
    "flex": ["capcode", "address"],
    "cell": ["cid", "cell_id"],
}


class SightingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or sightings_path()
        self.data: dict[str, Sighting] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                self.data = {k: Sighting(**v) for k, v in raw.items()}
            except (json.JSONDecodeError, OSError, TypeError):
                self.data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({k: asdict(v) for k, v in self.data.items()}, indent=2))

    def record(self, kind: str, id: str, *, freq_mhz: float | None = None,
               note: str = "", extra: dict | None = None, when: float | None = None,
               save: bool = True) -> Sighting:
        id = str(id)
        now = when if when is not None else time.time()
        key = f"{kind}:{id}"
        s = self.data.get(key)
        if s:
            s.last_seen = now
            s.count += 1
            if freq_mhz is not None:
                s.freq_mhz = freq_mhz
            if note:
                s.note = note
            if extra:
                s.extra.update(extra)
        else:
            s = Sighting(kind=kind, id=id, first_seen=now, last_seen=now, count=1,
                         freq_mhz=freq_mhz, note=note, extra=extra or {})
            self.data[key] = s
        if save:
            self.save()
        return s

    def list(self, kind: str | None = None) -> list[Sighting]:
        items = [s for s in self.data.values() if kind is None or s.kind == kind]
        return sorted(items, key=lambda s: s.last_seen, reverse=True)

    def get(self, kind: str, id: str) -> Sighting | None:
        return self.data.get(f"{kind}:{id}")

    def clear(self, kind: str | None = None) -> int:
        before = len(self.data)
        if kind is None:
            self.data = {}
        else:
            self.data = {k: v for k, v in self.data.items() if v.kind != kind}
        self.save()
        return before - len(self.data)


def extract_id(kind: str, obj: dict) -> str | None:
    """Pull the identifier for *kind* out of a decoder's JSON object."""
    for field_name in ID_FIELDS.get(kind, ["id"]):
        if field_name in obj and obj[field_name] not in (None, ""):
            return str(obj[field_name])
    return None


def ingest_json_line(store: SightingsStore, kind: str, line: str,
                     *, freq_mhz: float | None = None, save: bool = True) -> Sighting | None:
    """Parse one JSON decoder line and record its ID if present."""
    line = line.strip()
    if not line or not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    ident = extract_id(kind, obj)
    if ident is None:
        return None
    model = obj.get("model") or obj.get("type")
    extra = {"model": model} if model else {}
    return store.record(kind, ident, freq_mhz=freq_mhz, extra=extra, save=save)
