"""TDOA multilateration — precise passive emitter geolocation.

The upgrade from the RSSI-weighted centroid in ``sigint.geolocate``. Given short,
time-aligned IQ snippets from >=3 synchronised receivers (shared 10 MHz reference
+ PPS), it:

  1. **measures** the time-difference-of-arrival between each node and a reference
     node by FFT cross-correlation (with sub-sample parabolic interpolation),
  2. **solves** the hyperbolic system for the emitter position via Gauss-Newton
     least squares (in a local ENU plane), and
  3. reports a **GDOP**-based confidence radius from the geometry.

It is simulator-first (synthetic TDOAs / delayed captures from a known geometry)
so the whole pipeline is testable with no hardware, and it degrades gracefully to
the RSSI centroid when fewer than 3 synchronised nodes are available.

Passive collection only. Needs NumPy (``pip install rfhound[iq]``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SPEED_OF_LIGHT = 299_792_458.0  # m/s
_EARTH_R = 6_371_000.0          # m


def _np():
    try:
        import numpy as np
        return np
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "TDOA needs NumPy. Install it with: pip install 'rfhound[iq]'."
        ) from exc


@dataclass
class Node:
    node: str
    lat: float
    lon: float
    tdoa_s: float | None = None   # arrival time relative to the reference node
    rssi: float | None = None


@dataclass
class TDOAFix:
    lat: float | None
    lon: float | None
    method: str                   # "tdoa" | "rssi-fallback" | "none"
    n_nodes: int
    gdop: float | None = None
    confidence_m: float | None = None
    residual_m: float | None = None
    iterations: int = 0
    detail: str = ""


# --------------------------------------------------------------------------- #
# Local geodesy (equirectangular ENU around a reference point)
# --------------------------------------------------------------------------- #
def latlon_to_enu(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple:
    east = math.radians(lon - ref_lon) * _EARTH_R * math.cos(math.radians(ref_lat))
    north = math.radians(lat - ref_lat) * _EARTH_R
    return east, north


def enu_to_latlon(east: float, north: float, ref_lat: float, ref_lon: float) -> tuple:
    lat = ref_lat + math.degrees(north / _EARTH_R)
    lon = ref_lon + math.degrees(east / (_EARTH_R * math.cos(math.radians(ref_lat))))
    return lat, lon


# --------------------------------------------------------------------------- #
# TDOA estimation by cross-correlation
# --------------------------------------------------------------------------- #
def estimate_tdoa(iq_ref, iq_other, sample_rate: int) -> float:
    """Delay of *iq_other* relative to *iq_ref*, in seconds (sub-sample).

    Positive means the other node's copy arrives later than the reference's.
    """
    np = _np()
    a = np.asarray(iq_ref)
    b = np.asarray(iq_other)
    L = a.size + b.size
    n = 1
    while n < L:
        n <<= 1
    A = np.fft.fft(a, n)
    B = np.fft.fft(b, n)
    corr = np.fft.ifft(A * np.conj(B))
    mag = np.abs(corr)
    peak = int(np.argmax(mag))
    # Parabolic interpolation around the peak for sub-sample precision.
    ym1 = mag[(peak - 1) % n]
    y0 = mag[peak]
    yp1 = mag[(peak + 1) % n]
    denom = (ym1 - 2 * y0 + yp1)
    frac = 0.5 * (ym1 - yp1) / denom if denom != 0 else 0.0
    lag = peak + frac
    if lag > n / 2:  # wrap negative lags
        lag -= n
    # corr peak at k means ref[m] ~ other[m-k]; a *later* (delayed) other gives a
    # negative k, so the delay of `other` relative to `ref` is -lag.
    return -lag / sample_rate


# --------------------------------------------------------------------------- #
# Hyperbolic solver (Gauss-Newton least squares in ENU meters)
# --------------------------------------------------------------------------- #
def solve_tdoa(nodes: list[Node], *, ref_index: int = 0,
               sigma_tdoa_s: float = 1e-7, max_iter: int = 60) -> TDOAFix | None:
    """Solve for the emitter position from TDOA measurements.

    nodes[ref_index] is the reference; every other node's ``tdoa_s`` is its
    arrival time relative to the reference. Needs >=2 non-reference TDOAs (i.e.
    >=3 positioned nodes) for a 2-D fix.
    """
    np = _np()
    ref = nodes[ref_index]
    pos = [latlon_to_enu(nd.lat, nd.lon, ref.lat, ref.lon) for nd in nodes]
    x0, y0 = pos[ref_index]
    others = [i for i in range(len(nodes))
              if i != ref_index and nodes[i].tdoa_s is not None]
    if len(others) < 2:
        return None
    d = {i: SPEED_OF_LIGHT * nodes[i].tdoa_s for i in others}  # range diffs (m)

    # Initial guess: centroid of node positions, nudged off any node.
    ex = sum(p[0] for p in pos) / len(pos) + 1.0
    ey = sum(p[1] for p in pos) / len(pos) + 1.0

    Jm = rm = None
    iters = 0
    for iters in range(1, max_iter + 1):
        r0 = math.hypot(ex - x0, ey - y0) or 1e-6
        J, res = [], []
        for i in others:
            xi, yi = pos[i]
            ri = math.hypot(ex - xi, ey - yi) or 1e-6
            res.append((ri - r0) - d[i])
            J.append([(ex - xi) / ri - (ex - x0) / r0,
                      (ey - yi) / ri - (ey - y0) / r0])
        Jm = np.array(J)
        rm = np.array(res)
        JTJ = Jm.T @ Jm
        try:
            delta = -np.linalg.solve(JTJ, Jm.T @ rm)
        except np.linalg.LinAlgError:
            break
        ex += float(delta[0])
        ey += float(delta[1])
        if math.hypot(float(delta[0]), float(delta[1])) < 1e-3:
            break

    residual = float(np.sqrt(np.mean(rm ** 2))) if rm is not None else None
    gdop = conf = None
    try:
        cov = np.linalg.inv(Jm.T @ Jm)
        gdop = float(np.sqrt(np.trace(cov)))
        conf = gdop * SPEED_OF_LIGHT * sigma_tdoa_s
    except (np.linalg.LinAlgError, ValueError, TypeError):
        pass

    lat, lon = enu_to_latlon(ex, ey, ref.lat, ref.lon)
    return TDOAFix(
        lat=round(lat, 6), lon=round(lon, 6), method="tdoa", n_nodes=len(nodes),
        gdop=round(gdop, 2) if gdop is not None else None,
        confidence_m=round(conf, 1) if conf is not None else None,
        residual_m=round(residual, 2) if residual is not None else None,
        iterations=iters,
        detail=f"multilateration over {len(others) + 1} synchronised nodes",
    )


def geolocate_tdoa(nodes: list[Node], *, sigma_tdoa_s: float = 1e-7) -> TDOAFix:
    """Top-level: TDOA fix when >=3 synced nodes, else RSSI-centroid fallback."""
    with_tdoa = [nd for nd in nodes if nd.tdoa_s is not None]
    if len(with_tdoa) >= 3:
        # Use the earliest-arriving (most negative / zero tdoa) node as reference.
        ref_index = min(range(len(nodes)),
                        key=lambda i: (nodes[i].tdoa_s if nodes[i].tdoa_s is not None else 1e9))
        fix = solve_tdoa(nodes, ref_index=ref_index, sigma_tdoa_s=sigma_tdoa_s)
        if fix:
            return fix
    # Fallback: RSSI centroid.
    from . import sigint
    reports = [{"node": nd.node, "lat": nd.lat, "lon": nd.lon, "rssi": nd.rssi}
               for nd in nodes if nd.rssi is not None]
    est = sigint.geolocate(reports)
    return TDOAFix(lat=est.lat, lon=est.lon, method="rssi-fallback",
                   n_nodes=len(nodes), confidence_m=None, residual_m=None,
                   detail="fewer than 3 synchronised nodes — RSSI centroid")


# --------------------------------------------------------------------------- #
# Full pipeline: TDOAs from time-aligned captures
# --------------------------------------------------------------------------- #
def tdoa_from_captures(captures: list[dict], sample_rate: int) -> list[Node]:
    """Compute per-node TDOAs from time-aligned IQ snippets.

    Each capture: {"node", "lat", "lon", "iq"}. The first is the reference.
    Returns Node objects with tdoa_s filled by cross-correlation.
    """
    ref = captures[0]
    nodes = [Node(ref["node"], ref["lat"], ref["lon"], tdoa_s=0.0)]
    for cap in captures[1:]:
        tau = estimate_tdoa(ref["iq"], cap["iq"], sample_rate)
        nodes.append(Node(cap["node"], cap["lat"], cap["lon"], tdoa_s=tau))
    return nodes


# --------------------------------------------------------------------------- #
# Simulators (for demos + tests, no hardware)
# --------------------------------------------------------------------------- #
def simulate_scenario(emitter: tuple, node_latlons: list[tuple], *,
                      sigma_tdoa_s: float = 0.0, seed: int = 0) -> list[Node]:
    """Build Node objects with true (optionally noisy) TDOAs from a geometry."""
    import random
    rng = random.Random(seed)
    rlat, rlon = node_latlons[0]
    ex, ey = latlon_to_enu(emitter[0], emitter[1], rlat, rlon)
    ranges = []
    for la, lo in node_latlons:
        nx, ny = latlon_to_enu(la, lo, rlat, rlon)
        ranges.append(math.hypot(ex - nx, ey - ny))
    r0 = ranges[0]
    nodes = []
    for i, (la, lo) in enumerate(node_latlons):
        tdoa = (ranges[i] - r0) / SPEED_OF_LIGHT
        if sigma_tdoa_s and i != 0:
            tdoa += rng.gauss(0, sigma_tdoa_s)
        nodes.append(Node(f"node{i}", la, lo, tdoa_s=(0.0 if i == 0 else tdoa)))
    return nodes


def simulate_captures(emitter: tuple, node_latlons: list[tuple], *,
                      sample_rate: int = 20_000_000, n_samples: int = 8192,
                      seed: int = 1) -> list[dict]:
    """Build time-aligned IQ snippets: a common signal delayed per geometry."""
    np = _np()
    rng = np.random.default_rng(seed)
    base = (rng.standard_normal(n_samples) + 1j * rng.standard_normal(n_samples))
    base = base.astype(np.complex64)
    rlat, rlon = node_latlons[0]
    ex, ey = latlon_to_enu(emitter[0], emitter[1], rlat, rlon)
    ranges = []
    for la, lo in node_latlons:
        nx, ny = latlon_to_enu(la, lo, rlat, rlon)
        ranges.append(math.hypot(ex - nx, ey - ny))
    r0 = ranges[0]
    caps = []
    for i, (la, lo) in enumerate(node_latlons):
        delay_samples = int(round((ranges[i] - r0) / SPEED_OF_LIGHT * sample_rate))
        shifted = np.roll(base, delay_samples)
        caps.append({"node": f"node{i}", "lat": la, "lon": lo, "iq": shifted})
    return caps
