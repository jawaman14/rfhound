"""GeoJSON export for geolocation fixes (dissemination).

Turns a `sigint locate` fix (RSSI centroid or TDOA multilateration) into a
GeoJSON FeatureCollection — an emitter point plus the receiver nodes — so a fix
drops straight into a map (Leaflet, QGIS, geojson.io) or a GIS pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path


def _feature(lat: float, lon: float, props: dict) -> dict:
    return {"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": props}


def fix_geojson(lat: float, lon: float, props: dict, nodes: list | None = None) -> dict:
    """A FeatureCollection: the emitter fix plus any contributing receivers."""
    feats = [_feature(lat, lon, {**props, "role": "emitter"})]
    for n in nodes or []:
        if n.get("lat") is None or n.get("lon") is None:
            continue
        feats.append(_feature(n["lat"], n["lon"],
                              {"role": "receiver", "node": n.get("node") or n.get("node_id")}))
    return {"type": "FeatureCollection", "features": feats}


def write_geojson(path: str | Path, fc: dict) -> Path:
    p = Path(path)
    p.write_text(json.dumps(fc, indent=2))
    return p
