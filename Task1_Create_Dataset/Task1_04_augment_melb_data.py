# -*- coding: utf-8 -*-
"""
Created on Wed Oct 22 21:33:19 2025

@author: heidi
"""

#!/usr/bin/env python3
# Augment Melbourne OSM POIs (cafes + restaurants) → CSV/Parquet with derived features.

import json
import pandas as pd
from math import radians, sin, cos, atan2, sqrt
from pathlib import Path
from collections import Counter

# ------------ Paths (Melbourne project) ------------
# Paths are relative to the repository, so the scripts run on any computer
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "Data" / "Raw"
INTERIM_DIR = ROOT / "Data" / "Interim"
DATA_DIR = ROOT / "Data"
IN_PATH  = RAW_DIR / "osm_melb_cafes_restaurants_raw.json"   # expects cafes+restaurants combined RAW
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
OUT_BASE = INTERIM_DIR / "melbourne_cafes_restaurants"           # writes .csv and .parquet

# ------------ CBD reference (Flinders St Station area) ------------
CBD_LAT, CBD_LON = -37.8183, 144.9671

# ------------ Utils ------------
def haversine(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance (km) between two WGS84 points."""
    R = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    c = 2*atan2(sqrt(a), sqrt(1-a))
    return R * c

def flatten_elements(elements):
    """Overpass elements → list of dict rows with derived features."""
    rows = []
    for e in elements:
        tags = e.get("tags") or {}
        # coordinates: nodes have lat/lon; ways/relations use center.lat/lon (we requested 'out center')
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        amenity = tags.get("amenity")
        name = tags.get("name") or ""
        cuisine = tags.get("cuisine")

        # ---- Derived ----
        name_len = len(name.strip()) if name else 0
        cuisine_primary = (cuisine or "").split(";")[0].strip() if cuisine else None
        has_wifi = str(tags.get("internet_access", "")).lower() in {"wlan", "wifi", "yes"}
        has_outdoor = str(tags.get("outdoor_seating", "")).lower() == "yes"
        is_accessible = str(tags.get("wheelchair", "")).lower() == "yes"
        dist_km = round(haversine(CBD_LAT, CBD_LON, lat, lon), 3) if (lat is not None and lon is not None) else None

        # one-line address
        addr_parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:suburb"),
            tags.get("addr:city"),
            tags.get("addr:state"),
            tags.get("addr:postcode"),
        ]
        address_full = " ".join([p for p in addr_parts if p])

        # short text description (handy for Tasks 2–3)
        bits = []
        if name: bits.append(name)
        if cuisine_primary: bits.append(f"cuisine={cuisine_primary}")
        if has_wifi: bits.append("wifi=yes")
        if has_outdoor: bits.append("outdoor=yes")
        if is_accessible: bits.append("wheelchair=yes")
        desc = " — ".join(bits) if bits else "venue"

        rows.append({
            # meta/geom
            "osm_id": e.get("id"),
            "type": e.get("type"),
            "lat": lat, "lon": lon,

            # core tags
            "amenity": amenity,      # 'cafe' or 'restaurant'
            "name": name,
            "brand": tags.get("brand"),
            "website": tags.get("website"),
            "phone": tags.get("phone"),
            "opening_hours": tags.get("opening_hours"),
            "cuisine": cuisine,
            "cuisine_primary": cuisine_primary,

            # address
            "addr_housenumber": tags.get("addr:housenumber"),
            "addr_street": tags.get("addr:street"),
            "addr_suburb": tags.get("addr:suburb"),
            "addr_city": tags.get("addr:city"),
            "addr_state": tags.get("addr:state"),
            "addr_postcode": tags.get("addr:postcode"),
            "address_full": address_full or None,

            # facilities/access
            "internet_access": tags.get("internet_access"),
            "outdoor_seating": tags.get("outdoor_seating"),
            "wheelchair": tags.get("wheelchair"),
            "brand_wikidata": tags.get("brand:wikidata"),

            # derived
            "name_len": name_len,
            "has_wifi": has_wifi,
            "has_outdoor": has_outdoor,
            "is_accessible": is_accessible,
            "distance_to_cbd_km": dist_km,
            "desc": desc,
        })
    return rows

# ------------ Main ------------
def main():
    if not IN_PATH.exists():
        raise SystemExit(f"Raw JSON not found: {IN_PATH}")

    payload = json.load(open(IN_PATH, "r", encoding="utf-8"))
    elements = payload.get("elements") or []
    if not elements:
        raise SystemExit("No elements in RAW. Re-run the request step or adjust area.")

    # de-duplicate by (type,id)
    seen, dedup = set(), []
    for e in elements:
        k = (e.get("type"), e.get("id"))
        if k not in seen:
            seen.add(k); dedup.append(e)

    rows = flatten_elements(dedup)
    df = pd.DataFrame(rows)

    # enforce only cafe/restaurant
    df = df[df["amenity"].isin({"cafe", "restaurant"})].copy()

    # add fixed city label (handy when you later concatenate with Fremantle)
    df.insert(0, "city", "Melbourne")

    # save
    csv_path = OUT_BASE.with_suffix(".csv")
    parquet_path = OUT_BASE.with_suffix(".parquet")
    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False)

    # summary for your report
    total = len(df)
    am_counts = Counter(df["amenity"])
    print("✅ Wrote:", csv_path)
    print("✅ Wrote:", parquet_path)
    print("Rows:", total)
    print("\nAmenity distribution:", am_counts)
    for col in ["name", "cuisine", "opening_hours", "website", "phone",
                "has_wifi", "has_outdoor", "is_accessible"]:
        present = df[col].notna().sum() if col not in {"has_wifi","has_outdoor","is_accessible"} else int(df[col].sum())
        pct = present / total * 100 if total else 0.0
        print(f"{col:<15} {present:>5}  ({pct:>4.1f}%)")

    # helpful warning if cafes are still missing in RAW
    if not am_counts.get("cafe"):
        print("⚠️  No 'cafe' rows detected. Re-check your RAW fetch and ensure it includes amenity='cafe'.")

if __name__ == "__main__":
    main()
