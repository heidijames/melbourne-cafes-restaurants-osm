# -*- coding: utf-8 -*-
"""
Created on Wed Oct 22 23:11:56 2025

@author: heidi
"""

import json
from pathlib import Path
from collections import Counter

# Paths are relative to the repository, so the scripts run on any computer
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "Data" / "Raw"
INTERIM_DIR = ROOT / "Data" / "Interim"
DATA_DIR = ROOT / "Data"
cafes  = json.load(open(RAW_DIR/"osm_melb_cafes_raw.json","r",encoding="utf-8"))["elements"]
restos = json.load(open(RAW_DIR/"osm_melb_restaurants_raw.json","r",encoding="utf-8"))["elements"]

seen=set(); combo=[]
for e in cafes + restos:
    k=(e.get("type"), e.get("id"))
    if k not in seen:
        seen.add(k); combo.append(e)

out_path = RAW_DIR/"osm_melb_cafes_restaurants_raw.json"
json.dump({"elements": combo}, open(out_path,"w",encoding="utf-8"), indent=2, ensure_ascii=False)

print("Combined elements:", len(combo))
print("Amenity distribution:", Counter((e.get("tags") or {}).get("amenity") for e in combo))
print("Saved:", out_path)
