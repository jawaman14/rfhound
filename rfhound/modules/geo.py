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


def points_geojson(points: list) -> dict:
    """A FeatureCollection from a list of ``{lat, lon, ...props}`` dicts.

    Any keys other than ``lat``/``lon`` become feature properties, so decoded
    contacts (aircraft/vessels) with RSSI drop straight onto a map.
    """
    feats = []
    for pt in points or []:
        if pt.get("lat") is None or pt.get("lon") is None:
            continue
        props = {k: v for k, v in pt.items() if k not in ("lat", "lon")}
        feats.append(_feature(pt["lat"], pt["lon"], props))
    return {"type": "FeatureCollection", "features": feats}


def _xesc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def fix_kml(lat: float, lon: float, props: dict, nodes: list | None = None) -> str:
    """A KML document: the emitter fix plus any receiver nodes (for Google Earth)."""
    def placemark(name, la, lo, desc=""):
        return (f"<Placemark><name>{_xesc(name)}</name>"
                f"<description>{_xesc(desc)}</description>"
                f"<Point><coordinates>{lo:.6f},{la:.6f},0</coordinates></Point></Placemark>")

    desc = "; ".join(f"{k}={v}" for k, v in props.items())
    parts = [placemark("Emitter fix", lat, lon, desc)]
    for n in nodes or []:
        if n.get("lat") is None or n.get("lon") is None:
            continue
        parts.append(placemark(str(n.get("node") or n.get("node_id") or "receiver"),
                               n["lat"], n["lon"], "receiver"))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            + "".join(parts) + "</Document></kml>\n")


def points_kml(points: list, *, name_key: str = "label") -> str:
    """A KML document with one placemark per ``{lat, lon, ...props}`` point."""
    def placemark(nm, la, lo, desc):
        return (f"<Placemark><name>{_xesc(nm)}</name>"
                f"<description>{_xesc(desc)}</description>"
                f"<Point><coordinates>{lo:.6f},{la:.6f},0</coordinates></Point></Placemark>")

    parts = []
    for pt in points or []:
        if pt.get("lat") is None or pt.get("lon") is None:
            continue
        props = {k: v for k, v in pt.items() if k not in ("lat", "lon")}
        nm = props.get(name_key) or props.get("id") or "point"
        desc = "; ".join(f"{k}={v}" for k, v in props.items())
        parts.append(placemark(str(nm), pt["lat"], pt["lon"], desc))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            + "".join(parts) + "</Document></kml>\n")


def write_kml(path: str | Path, kml: str) -> Path:
    p = Path(path)
    p.write_text(kml)
    return p
