# -*- coding: utf-8 -*-
"""
Created on Wed Oct 22 23:54:07 2025

@author: heidi
"""

#!/usr/bin/env python3
# Validate + light-clean Melbourne cafes & restaurants CSV

import os
import re
import math
import pandas as pd
from pathlib import Path
from collections import Counter

# ---- Paths ----
# Paths are relative to the repository, so the scripts run on any computer
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "Data" / "Raw"
INTERIM_DIR = ROOT / "Data" / "Interim"
DATA_DIR = ROOT / "Data"
IN_CSV   = INTERIM_DIR / "melbourne_cafes_restaurants.csv"

OUT_CLEAN     = DATA_DIR / "melbourne_cafes_restaurants_clean.csv"
OUT_SLIM      = INTERIM_DIR / "melbourne_cafes_restaurants_slim.csv"
OUT_EXPLODED  = INTERIM_DIR / "melbourne_cafes_restaurants_exploded_cuisine.csv"
OUT_PROFILE   = INTERIM_DIR / "melbourne_profile.txt"

# ---- Helper funcs ----
def coerce_bool(x):
    """Convert common truthy/falsey strings to bool; keep NaN as NaN."""
    if pd.isna(x):
        return pd.NA
    s = str(x).strip().lower()
    if s in {"y", "yes", "true", "1"}:
        return True
    if s in {"n", "no", "false", "0"}:
        return False
    return pd.NA

def normalize_url(u: str) -> str | None:
    if not isinstance(u, str) or not u.strip():
        return None
    u = u.strip()
    # If looks like domain only, add https://
    if not re.match(r"^https?://", u):
        u = "https://" + u
    return u

def within_bbox(lat, lon, bbox):
    s, w, n, e = bbox
    return (s <= lat <= n) and (w <= lon <= e)

# Approx analysis area (CBD + Fitzroy + surrounds) for sanity checks
MELB_BBOX = (-37.86, 144.90, -37.76, 145.05)

def profile_missing(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = []
    total = len(df)
    for c in cols:
        miss = df[c].isna().sum()
        out.append({"column": c, "missing": miss, "missing_pct": round(100*miss/total, 1)})
    return pd.DataFrame(out).sort_values("missing_pct", ascending=False)

def vc(df, col, n=15):
    counts = df[col].value_counts(dropna=False).head(n)
    return counts

# ---- Load ----
assert IN_CSV.exists(), f"CSV not found: {IN_CSV}"
df = pd.read_csv(IN_CSV)
print(f"Loaded: {IN_CSV}  rows={len(df)}  cols={df.shape[1]}")

# ---- VALIDATION ----
# 1) Basic expectations
assert set(df["amenity"].unique()) <= {"cafe", "restaurant"}, "Unexpected amenity values found."
assert df["city"].eq("Melbourne").all(), "City column not uniformly 'Melbourne'."
assert df["lat"].between(-90, 90).all() and df["lon"].between(-180, 180).all(), "Invalid lat/lon ranges."
null_coords = int(df["lat"].isna().sum() + df["lon"].isna().sum())
print("Null coords:", null_coords)

# 2) Duplicates by (type, osm_id)
before = len(df)
df = df.drop_duplicates(subset=["type", "osm_id"])
dups = before - len(df)
print("Dropped duplicates:", dups)

# 3) Coordinates plausibility vs Melbourne bbox
out_of_bbox = ~df.apply(lambda r: within_bbox(r["lat"], r["lon"], MELB_BBOX), axis=1)
n_oob = int(out_of_bbox.sum())
if n_oob:
    print(f"⚠️  {n_oob} rows outside expected Melbourne bbox — keeping them (they may be fringe suburbs).")

# 4) Amenity distribution
am_counts = Counter(df["amenity"])
print("Amenity distribution:", am_counts)

# ---- LIGHT CLEANUPS (optional but helpful) ----
# A) Normalize cuisine_primary (lowercase, trimmed)
if "cuisine_primary" in df.columns:
    df["cuisine_primary"] = df["cuisine_primary"].astype("string").str.lower().str.strip()

# B) Normalize website field to include scheme
df["website"] = df["website"].apply(normalize_url)

# C) Coerce booleans to proper boolean dtype with NA support
for b in ["has_wifi", "has_outdoor", "is_accessible"]:
    if b in df.columns:
        df[b] = df[b].apply(coerce_bool).astype("boolean")

# D) Strip whitespace from common text cols
for c in ["name", "addr_street", "addr_suburb", "addr_city", "addr_state", "address_full", "cuisine", "opening_hours", "phone"]:
    if c in df.columns:
        df[c] = df[c].astype("string").str.strip()

# E) Drop rows with completely missing name (should be none, but just in case)
missing_name = df["name"].isna() | (df["name"].str.len() == 0)
n_missing_name = int(missing_name.sum())
if n_missing_name:
    print(f"⚠️  Dropping {n_missing_name} rows with empty 'name'.")
    df = df[~missing_name].copy()

# F) Round distance to 3 decimals for readability
if "distance_to_cbd_km" in df.columns:
    df["distance_to_cbd_km"] = df["distance_to_cbd_km"].round(3)

# G) (Optional) Build an NLP-friendly text field (keep if not present)
if "text" not in df.columns:
    base_bits = ["name"]
    opt_bits = ["cuisine_primary", "addr_suburb"]
    def make_text(row):
        parts = [str(row[b]) for b in base_bits if pd.notna(row.get(b))]
        for b in opt_bits:
            v = row.get(b)
            if pd.notna(v) and str(v):
                parts.append(str(v))
        return " — ".join(parts)
    df["text"] = df.apply(make_text, axis=1)

# ---- EXPORTS ----
# Main clean file
df.to_csv(OUT_CLEAN, index=False)
print("✅ Wrote clean CSV:", OUT_CLEAN)

# Slim columns (handy for models / FAISS later)
slim_cols = [
    "city", "amenity", "name", "cuisine_primary",
    "has_wifi", "has_outdoor", "is_accessible",
    "distance_to_cbd_km", "lat", "lon", "text"
]
slim = df[[c for c in slim_cols if c in df.columns]].copy()
slim.to_csv(OUT_SLIM, index=False)
print("✅ Wrote slim CSV:", OUT_SLIM)

# Exploded cuisine (one row per cuisine token) — optional analytic view
def split_cuisine_list(x):
    if not isinstance(x, str) or not x.strip():
        return []
    return [t.strip().lower() for t in x.split(";") if t.strip()]

tmp = df.copy()
tmp["cuisine_list"] = df["cuisine"].apply(split_cuisine_list)
exploded = tmp.explode("cuisine_list").dropna(subset=["cuisine_list"])
exploded.to_csv(OUT_EXPLODED, index=False)
print("✅ Wrote exploded-cuisine CSV:", OUT_EXPLODED)

# ---- PROFILE / SUMMARY (to a text file) ----
lines = []
lines.append(f"Rows (clean): {len(df)}")
lines.append(f"Amenity distribution: {dict(am_counts)}")
miss_tbl = profile_missing(df, ["name","cuisine","cuisine_primary","opening_hours","website","phone","addr_suburb","has_wifi","has_outdoor","is_accessible","distance_to_cbd_km"])
lines.append("\nMissingness (% top 12):\n" + miss_tbl.head(12).to_string(index=False))
lines.append("\nTop cuisines (primary):\n" + vc(df, "cuisine_primary", 15).to_string())
lines.append("\nTop suburbs:\n" + vc(df, "addr_suburb", 15).to_string())

with open(OUT_PROFILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("📝 Wrote profile:", OUT_PROFILE)

# Final console recap
print("\n--- Recap ---")
print("Clean rows:", len(df))
print("Cafes:", am_counts.get("cafe", 0), "Restaurants:", am_counts.get("restaurant", 0))
print("Sample columns:", df.columns.tolist()[:12])
