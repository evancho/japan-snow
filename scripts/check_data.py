#!/usr/bin/env python3
"""Validate resorts.json and conditions.json before publishing."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESORTS = json.loads((ROOT / "data" / "resorts.json").read_text(encoding="utf-8"))
COND = json.loads((ROOT / "data" / "conditions.json").read_text(encoding="utf-8"))
JST = timezone(timedelta(hours=9))
KANA = re.compile(r"[\u3041-\u3096\u30a1-\u30fa]")
REGIONS = {item["id"] for item in RESORTS["regions"]}
errors = []

resorts = RESORTS["resorts"]
if len(resorts) < 300:
    errors.append(f"only {len(resorts)} resorts")
ids = [r["id"] for r in resorts]
if len(ids) != len(set(ids)):
    errors.append("duplicate resort ids")

for resort in resorts:
    for key in ("id", "zh", "ja", "pref", "region", "lat", "lon"):
        if resort.get(key) in (None, ""):
            errors.append(f"{resort.get('id')} missing {key}")
            break
    else:
        if resort["region"] not in REGIONS:
            errors.append(f"{resort['id']} bad region {resort['region']}")
        if not (24 <= resort["lat"] <= 46.5 and 122 <= resort["lon"] <= 154):
            errors.append(f"{resort['id']} outside Japan")
        if KANA.search(resort["zh"]):
            errors.append(f"kana in Chinese name {resort['zh']}")

by_zh = {}
for resort in resorts:
    by_zh.setdefault(resort["zh"], []).append(resort)

for name in ("二世谷", "留壽都", "喜樂樂", "白馬八方尾根", "野澤溫泉", "藏王溫泉", "神樂"):
    if name not in by_zh:
        errors.append(f"missing famous resort {name}")

cond_rows = COND.get("resorts") or {}
if len(cond_rows) < len(resorts) * 0.9:
    errors.append(f"conditions cover {len(cond_rows)}/{len(resorts)}")

try:
    updated = datetime.fromisoformat(COND["updated"])
except Exception:
    errors.append("conditions.updated is not a timestamp")
    updated = None
if updated is not None:
    age = datetime.now(JST) - updated
    if age > timedelta(days=7) or age < timedelta(hours=-1):
        errors.append(f"conditions are stale or in the future: {COND['updated']}")

numeric = 0
for rid, row in cond_rows.items():
    depth = row.get("depth")
    temp = row.get("temp")
    if isinstance(depth, (int, float)) and isinstance(temp, (int, float)):
        numeric += 1
        if not -45 <= temp <= 35 or not 0 <= depth <= 900:
            errors.append(f"{rid} out of range temp={temp} depth={depth}")
    if row.get("depth_kind") not in ("obs", "est"):
        errors.append(f"{rid} bad depth_kind")
if numeric < len(resorts) * 0.9:
    errors.append(f"only {numeric} resorts have depth and temperature")

niseko = next((r for r in resorts if r["zh"] == "二世谷"), None)
if niseko:
    row = cond_rows.get(niseko["id"])
    if not row or not isinstance(row.get("depth"), (int, float)):
        errors.append("二世谷 has no snow depth")
    elif not isinstance(row.get("temp"), (int, float)):
        errors.append("二世谷 has no temperature")

regions_used = {r["region"] for r in resorts}
if len(regions_used) < 8:
    errors.append(f"only regions {regions_used}")

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
try:
    manifest = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
except Exception:
    errors.append("version.json is not valid JSON")
    manifest = {}
version = manifest.get("version")
history = manifest.get("history")
if not isinstance(version, str) or not SEMVER.fullmatch(version):
    errors.append("version.json version must be major.minor.patch")
elif not isinstance(history, list) or not history:
    errors.append("version.json history is empty")
elif history[0].get("version") != version:
    errors.append("version.json history[0] must be the current version")
else:
    seen = set()
    previous = None
    for entry in history:
        item = entry.get("version")
        if item in seen or not isinstance(item, str) or not SEMVER.fullmatch(item):
            errors.append(f"bad history version {item}")
            break
        seen.add(item)
        parts = tuple(int(piece) for piece in item.split("."))
        if previous is not None and parts >= previous:
            errors.append("version history must be newest first")
            break
        previous = parts
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(entry.get("date") or "")):
            errors.append(f"{item} missing date")
        notes = entry.get("notes")
        if not isinstance(notes, list) or not notes or not all(isinstance(note, str) and note.strip() for note in notes):
            errors.append(f"{item} missing notes")
    if "1.0.0" not in seen:
        errors.append("version history is missing 1.0.0")
app_js = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
html = (ROOT / "index.html").read_text(encoding="utf-8")
if isinstance(version, str):
    if f'const APP_VERSION = "{version}";' not in app_js:
        errors.append("APP_VERSION does not match version.json; run scripts/stamp_version.py")
    if f"assets/app.css?v={version}" not in html or f"assets/app.js?v={version}" not in html:
        errors.append("index.html cache-bust does not match version.json; run scripts/stamp_version.py")

if errors:
    print("\n".join(errors))
    sys.exit(1)

positive = sum(1 for row in cond_rows.values() if isinstance(row.get("depth"), (int, float)) and row["depth"] > 0)
observed = sum(1 for row in cond_rows.values() if row.get("depth_kind") == "obs")
print(
    f"ok resorts={len(resorts)} conditions={len(cond_rows)} "
    f"snow>0={positive} observed_depth={observed} updated={COND['updated']}"
)
if niseko:
    row = cond_rows[niseko["id"]]
    print(
        f"二世谷 depth={row['depth']}cm ({row['depth_kind']}) "
        f"24h={row['d24']} temp={row['temp']} ele={row.get('ele')}"
    )
