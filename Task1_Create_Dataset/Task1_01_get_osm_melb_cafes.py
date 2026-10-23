# -*- coding: utf-8 -*-
"""
Created on Wed Oct 22 22:40:51 2025

@author: heidi
"""

import requests, json
from pathlib import Path

# Paths are relative to the repository, so the scripts run on any computer
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "Data" / "Raw"
INTERIM_DIR = ROOT / "Data" / "Interim"
DATA_DIR = ROOT / "Data"
RAW_DIR.mkdir(parents=True, exist_ok=True)

OUT_CAFES = RAW_DIR / "osm_melb_cafes_raw.json"

# CBD point + radius covers CBD + Fitzroy nicely
CBD_LAT, CBD_LON = -37.8183, 144.9671
RADIUS_METERS = 3500

# Try a different Overpass mirror (the default sometimes behaves oddly)
OVERPASS = "https://overpass.kumi.systems/api/interpreter"

ql = f"""[out:json][timeout:90];
nwr(around:{RADIUS_METERS},{CBD_LAT},{CBD_LON})["amenity"="cafe"];
out center tags;"""

resp = requests.get(OVERPASS, params={"data": ql}, timeout=180)
resp.raise_for_status()
payload = resp.json()

# de-dup
seen=set(); elements=[]
for e in payload.get("elements", []):
    k=(e.get("type"), e.get("id"))
    if k not in seen:
        seen.add(k); elements.append(e)

json.dump({"elements": elements}, open(OUT_CAFES, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("Cafes fetched:", len(elements), "->", OUT_CAFES)


