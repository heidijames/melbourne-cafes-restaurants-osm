# -*- coding: utf-8 -*-
"""
Created on Wed Oct 22 21:23:33 2025

@author: heidi
"""

# Robust Overpass fetch: Melbourne restaurants (CBD + Fitzroy) with mirrors, retries, and fallback tiling
import requests, json, time, math
from pathlib import Path
from typing import List, Tuple

# Paths are relative to the repository, so the scripts run on any computer
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "Data" / "Raw"
INTERIM_DIR = ROOT / "Data" / "Interim"
DATA_DIR = ROOT / "Data"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_RESTOS = RAW_DIR / "osm_melb_restaurants_raw.json"

# Primary area: CBD + Fitzroy + Collingwood + Carlton + Richmond West
# south, west, north, east
BBOX = (-37.840, 144.930, -37.770, 145.020)

# Mirrors to try in order
MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]

HEADERS = {"User-Agent": "TAFE-Assessment-Heidi/1.0 (mailto:example@example.com)"}

def build_ql_bbox(bbox: Tuple[float,float,float,float]) -> str:
    s,w,n,e = bbox
    return f"""[out:json][timeout:90];
nwr["amenity"="restaurant"]({s},{w},{n},{e});
out center tags;"""

def build_ql_radius(lat: float, lon: float, radius_m: int) -> str:
    return f"""[out:json][timeout:90];
nwr(around:{radius_m},{lat},{lon})["amenity"="restaurant"];
out center tags;"""

def fetch_overpass(ql: str) -> dict:
    # Try POST first (more reliable with larger queries), then GET
    errors = []
    for url in MIRRORS:
        for method in ("post", "get"):
            try:
                if method == "post":
                    resp = requests.post(url, data={"data": ql}, headers=HEADERS, timeout=180)
                else:
                    resp = requests.get(url, params={"data": ql}, headers=HEADERS, timeout=180)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                errors.append((url, method, repr(e)))
                # brief pause before next attempt
                time.sleep(2)
    raise RuntimeError(f"All mirrors failed. Examples: {errors[:2]}")

def dedup_elements(elements: List[dict]) -> List[dict]:
    seen = set(); out=[]
    for e in elements:
        k = (e.get("type"), e.get("id"))
        if k not in seen:
            seen.add(k); out.append(e)
    return out

def split_bbox(bbox: Tuple[float,float,float,float], grid: int = 2) -> List[Tuple[float,float,float,float]]:
    s,w,n,e = bbox
    lats = [s + (n-s)*i/grid for i in range(grid+1)]
    lons = [w + (e-w)*j/grid for j in range(grid+1)]
    tiles=[]
    for i in range(grid):
        for j in range(grid):
            tiles.append((lats[i], lons[j], lats[i+1], lons[j+1]))
    return tiles

def robust_fetch_restaurants() -> List[dict]:
    elements = []

    # Strategy A: radius around Flinders St (covers Fitzroy with 3500m)
    center_lat, center_lon, radius_m = -37.8183, 144.9671, 3500
    ql = build_ql_radius(center_lat, center_lon, radius_m)

    # Retry with exponential backoff across mirrors/methods
    for attempt in range(4):  # 4 attempts: 0,1,2,3
        try:
            payload = fetch_overpass(ql)
            elements = payload.get("elements", [])
            if elements:
                return dedup_elements(elements)
        except Exception as e:
            pass
        time.sleep(2 * (attempt + 1))  # backoff: 2s, 4s, 6s, 8s

    # Strategy B: bbox, split into tiles if needed
    # Try full bbox first
    try:
        payload = fetch_overpass(build_ql_bbox(BBOX))
        got = payload.get("elements", [])
        if got:
            return dedup_elements(got)
    except Exception:
        pass

    # Split bbox into 4 tiles and fetch each
    all_e = []
    for tile in split_bbox(BBOX, grid=2):
        ql_tile = build_ql_bbox(tile)
        for attempt in range(3):
            try:
                payload = fetch_overpass(ql_tile)
                all_e.extend(payload.get("elements", []))
                break
            except Exception:
                time.sleep(2 * (attempt + 1))
                continue
    return dedup_elements(all_e)

def main():
    try:
        elems = robust_fetch_restaurants()
        json.dump({"elements": elems}, open(OUT_RESTOS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Restaurants fetched: {len(elems)} -> {OUT_RESTOS}")
    except Exception as e:
        print("Failed to fetch restaurants:", e)

if __name__ == "__main__":
    main()
