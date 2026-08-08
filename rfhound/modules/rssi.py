"""RSSI utilities: distance estimation and single-node foxhunt trend.

RSSI (received signal strength) is a source-agnostic proximity cue — a HackRF
sweep peak, a Wi-Fi AP, or a BLE device all report it. This turns RSSI into a
coarse distance (log-distance path-loss model) and a "hotter/colder" hunt trend
you can walk with, and feeds multi-node RSSI into the geolocation centroid.

Receive/observe-only; nothing here transmits.
"""

from __future__ import annotations

from dataclasses import dataclass


def estimate_distance_m(rssi_dbm: float, *, tx_power_dbm: float = -40.0,
                        path_loss_n: float = 2.5) -> float:
    """Coarse distance from RSSI via the log-distance path-loss model.

    ``tx_power_dbm`` is the expected RSSI at 1 m (calibrate per device/band);
    ``path_loss_n`` is the environment exponent (~2 free space, 2.5–4 indoors).
    d = 10^((TxPower - RSSI) / (10 * n)). Environment-dependent — a range, not a
    survey-grade measurement.
    """
    return round(10 ** ((tx_power_dbm - rssi_dbm) / (10.0 * path_loss_n)), 2)


@dataclass
class HuntTrend:
    samples: int
    latest_dbm: float
    best_dbm: float
    trend: str            # hotter | colder | steady
    est_distance_m: float
    detail: str


def hunt_trend(rssi_series: list, *, tx_power_dbm: float = -40.0,
               path_loss_n: float = 2.5, delta_db: float = 2.0) -> HuntTrend:
    """Summarise an RSSI time-series for foxhunting (walk toward 'hotter')."""
    xs = [float(r) for r in rssi_series if r is not None]
    if not xs:
        return HuntTrend(0, 0.0, 0.0, "steady", 0.0, "no samples")
    latest, best = xs[-1], max(xs)
    trend = "steady"
    if len(xs) >= 2:
        prev = xs[-4:-1] or xs[-2:-1]
        baseline = sum(prev) / len(prev)
        if latest - baseline >= delta_db:
            trend = "hotter"
        elif baseline - latest >= delta_db:
            trend = "colder"
    dist = estimate_distance_m(latest, tx_power_dbm=tx_power_dbm, path_loss_n=path_loss_n)
    return HuntTrend(len(xs), round(latest, 1), round(best, 1), trend, dist,
                     f"{latest:.0f} dBm (~{dist:.0f} m), {trend}; best {best:.0f} dBm")


def reports_from_nodes(node_observations: list) -> list:
    """Turn per-node source observations into geolocation reports.

    Each item: {"node","lat","lon","rssi_dbm"} → {"node","lat","lon","rssi"} for
    ``sigint.geolocate`` (multi-node RSSI-weighted centroid).
    """
    out = []
    for o in node_observations:
        if o.get("lat") is None or o.get("lon") is None:
            continue
        rssi = o.get("rssi_dbm", o.get("rssi"))
        if rssi is None:
            continue
        out.append({"node": o.get("node", ""), "lat": o["lat"], "lon": o["lon"],
                    "rssi": rssi})
    return out
