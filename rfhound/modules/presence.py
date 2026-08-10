"""Presence / geofence detection — alert when a watched identifier appears,
disappears, or comes into proximity.

Watch a specific emitter by its identifier — a Wi-Fi BSSID or SSID, a BLE
address or device name, or any decoded ID — and get told when it shows up,
leaves, or crosses an RSSI proximity threshold. Built on the passive Wi-Fi/BLE
scanners and the sightings tracker; observe-only.

Use cases: know when an unwanted tracker is near you, when a known device
enters/leaves a site, or when an expected AP disappears (jamming/theft).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WatchItem:
    kind: str                       # wifi | ble | any (or a sightings kind)
    id: str                         # BSSID / address / SSID / name / decoded ID
    on: str = "appear"              # appear | disappear | near
    rssi_threshold: float = -60.0   # for on="near": present only when >= this
    label: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id}".lower()


@dataclass
class PresenceFinding:
    kind: str
    id: str
    label: str
    event: str                      # appeared | disappeared | near
    detail: str
    rssi_dbm: float | None = None


def _matches(item: WatchItem, obs: dict) -> bool:
    """A watch item matches an observation by kind + (id equality or label/id substring)."""
    if item.kind not in ("any", "") and obs.get("kind") != item.kind:
        return False
    target = item.id.lower()
    oid = str(obs.get("id", "")).lower()
    olabel = str(obs.get("label", "")).lower()
    return target == oid or (target and (target in oid or target in olabel))


def observations_from(*, aps=None, devices=None) -> list:
    """Unify current Wi-Fi APs / BLE devices into {kind,id,label,rssi_dbm} dicts."""
    obs = []
    for a in aps or []:
        obs.append({"kind": "wifi", "id": a.bssid, "label": a.ssid, "rssi_dbm": a.rssi_dbm})
    for d in devices or []:
        obs.append({"kind": "ble", "id": d.addr, "label": d.name, "rssi_dbm": d.rssi_dbm})
    return obs


def check_presence(watchlist: list, observations: list, *, prev_present: set | None = None):
    """Evaluate a watchlist against current observations.

    Returns ``(findings, present_keys)``. ``present_keys`` is the set of watch-item
    keys currently satisfied (for "near", only when RSSI ≥ threshold) — pass it
    back as ``prev_present`` next round so transitions (appear/disappear) fire once.
    """
    prev = prev_present or set()
    present: set = set()
    matched_obs: dict = {}
    for item in watchlist:
        for obs in observations:
            if not _matches(item, obs):
                continue
            rssi = obs.get("rssi_dbm")
            if item.on == "near" and (rssi is None or rssi < item.rssi_threshold):
                continue
            present.add(item.key)
            matched_obs[item.key] = obs
            break

    findings: list = []
    for item in watchlist:
        k = item.key
        obs = matched_obs.get(k)
        name = item.label or (obs.get("label") if obs else "") or item.id
        rssi = obs.get("rssi_dbm") if obs else None
        if item.on in ("appear",) and k in present and k not in prev:
            findings.append(PresenceFinding(item.kind, item.id, name, "appeared",
                            f"'{name}' ({item.id}) appeared"
                            + (f" at {rssi:.0f} dBm" if rssi is not None else ""), rssi))
        elif item.on == "near" and k in present and k not in prev:
            findings.append(PresenceFinding(item.kind, item.id, name, "near",
                            f"'{name}' ({item.id}) is near ({rssi:.0f} dBm ≥ "
                            f"{item.rssi_threshold:.0f})", rssi))
        elif item.on == "disappear" and k in prev and k not in present:
            findings.append(PresenceFinding(item.kind, item.id, name, "disappeared",
                            f"'{name}' ({item.id}) disappeared", None))
    return findings, present


def simulate_watchlist() -> list:
    return [WatchItem("ble", "AirTag", on="near", rssi_threshold=-70.0),
            WatchItem("wifi", "HomeNet", on="appear")]
