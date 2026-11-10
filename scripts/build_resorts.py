#!/usr/bin/env python3
"""Build data/resorts.json from OpenStreetMap, with Chinese names and AMeDAS links.

Run from the repo root:
  python3 scripts/build_resorts.py
  python3 scripts/build_resorts.py --osm /path/to/overpass.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo import REGIONS, classify, haversine_km, load_index, self_test as geo_test  # noqa: E402
from zhname import (  # noqa: E402
    CACHE,
    OPENCC_URL,
    apply_kanji,
    has_kana,
    load_kanji_map,
    norm_key,
    override_meta,
    romaji,
    self_test as name_test,
    to_zh,
)

JST = timezone(timedelta(hours=9))
UA = "japan-snow/1.0 (+https://github.com/evancho/japan-snow)"
TOPO_URL = "https://raw.githubusercontent.com/dataofjapan/land/master/japan.topojson"
AMEDAS_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
OVERPASS_URLS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
OVERPASS_QUERY = """
[out:json][timeout:180];
area(3600382313)->.jp;
(
  nwr["landuse"="winter_sports"]["name"](area.jp);
  nwr["leisure"="ski_resort"](area.jp);
  nwr["site"="piste"]["name"](area.jp);
);
out tags center;
""".strip()

DROP_PARTS = ("シャンツェ", "ジャンプ台", "スキージャンプ", "ウォータージャンプ", "スキージャンプ台")
DROP_EXACT = {
    norm_key("Hakuba Valley"),
    norm_key("かぐらエリア"),
    norm_key("みつまたエリア"),
    norm_key("田代エリア"),
    norm_key("かぐらスキー場 田代ステーション"),
    norm_key("大鰐温泉スキー場 国際エリア"),
    norm_key("八甲田ロープウェー"),
    norm_key("八甲田ロープウェイ"),
}
CORE_SUFFIXES = (
    "スキーフィールド",
    "スキーリゾート",
    "スノーリゾート",
    "スノーパーク",
    "スキーガーデン",
    "スキーエリア",
    "スノーエリア",
    "スノーワールド",
    "スノーランド",
    "スキーパーク",
    "スキー場",
    "ゲレンデ",
    "リゾート",
    "スキー",
)


def fetch(url: str, data: bytes | None = None, timeout: int = 180) -> bytes:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def cached(name: str, url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if path.exists() and path.stat().st_size > 0:
        return path
    path.write_bytes(fetch(url))
    return path


def download_osm() -> dict:
    payload = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode()
    last = None
    for url in OVERPASS_URLS:
        try:
            body = fetch(url, data=payload, timeout=180)
            data = json.loads(body)
            if data.get("elements"):
                return data
            last = "empty response"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
    raise SystemExit(f"Overpass query failed: {last}")


def dms_to_deg(pair: list) -> float:
    deg = float(pair[0])
    minutes = float(pair[1]) if len(pair) > 1 else 0.0
    sign = -1 if deg < 0 else 1
    return sign * (abs(deg) + minutes / 60.0)


def center_of(element: dict) -> tuple[float, float] | None:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def core_name(value: str) -> str:
    text = norm_key(value)
    changed = True
    while changed:
        changed = False
        for suffix in CORE_SUFFIXES:
            suf = norm_key(suffix)
            if text.endswith(suf) and len(text) - len(suf) >= 2:
                text = text[: -len(suf)]
                changed = True
                break
    return text


def japanese_source(tags: dict) -> str:
    ja = tags.get("name:ja") or ""
    name = tags.get("name") or ""
    if ja:
        return ja
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", name):
        return name
    return name


def display_ja(tags: dict) -> str:
    return tags.get("name:ja") or tags.get("name") or tags.get("name:en") or ""


def display_en(tags: dict) -> str:
    en = tags.get("name:en") or ""
    name = tags.get("name") or ""
    if en:
        return en
    if name and not re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", name):
        return name
    return ""


def website(tags: dict) -> str:
    for key in ("website", "contact:website", "url"):
        value = (tags.get(key) or "").strip()
        if value.startswith("http://") or value.startswith("https://"):
            return value
    return ""


def should_drop(tags: dict) -> bool:
    if tags.get("abandoned") == "yes" or tags.get("disused") == "yes":
        return True
    blob = " ".join(
        tags.get(key) or ""
        for key in ("name", "name:ja", "name:en", "official_name")
    )
    if any(part in blob for part in DROP_PARTS):
        return True
    if norm_key(tags.get("name") or "") in DROP_EXACT:
        return True
    if norm_key(tags.get("name:ja") or "") in DROP_EXACT:
        return True
    if norm_key(blob) in DROP_EXACT:
        return True
    ja = tags.get("name:ja") or ""
    en = tags.get("name:en") or ""
    if ja == "白馬村" and "Valley" in en:
        return True
    name = tags.get("name") or ja
    if name.endswith(("ロープウェー", "ロープウェイ")) and "スキー" not in blob:
        return True
    return False


def slugify(en: str, ja: str, osm_type: str, osm_id: int) -> str:
    raw = unicodedata.normalize("NFKD", en or "")
    raw = raw.encode("ascii", "ignore").decode().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if len(raw) < 3:
        raw = f"{osm_type}-{osm_id}"
    return raw[:52].strip("-")


def score(tags: dict) -> int:
    value = 0
    if tags.get("name:ja"):
        value += 5
    if tags.get("name:en"):
        value += 2
    if website(tags):
        value += 2
    blob = (tags.get("name:ja") or "") + (tags.get("name") or "")
    if "スキー場" in blob:
        value += 2
    value += min(len(blob), 40)
    return value


def similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return True
    return False


def load_amedas(path: Path) -> list[dict]:
    table = json.loads(path.read_text(encoding="utf-8"))
    kanji = load_kanji_map()
    stations = []
    for sid, row in table.items():
        elems = row.get("elems") or ""
        if len(elems) < 6 or elems[5] not in "12":
            continue
        lat = dms_to_deg(row.get("lat") or [0, 0])
        lon = dms_to_deg(row.get("lon") or [0, 0])
        ja = row.get("kjName") or ""
        stations.append(
            {
                "id": str(sid),
                "ja": ja,
                "zh": apply_kanji(ja, kanji),
                "lat": lat,
                "lon": lon,
                "ele": row.get("alt"),
            }
        )
    return stations


def nearest_station(lat: float, lon: float, stations: list[dict]) -> dict | None:
    best = None
    best_d = 30.0
    for station in stations:
        if abs(station["lat"] - lat) > 0.45 or abs(station["lon"] - lon) > 0.55:
            continue
        dist = haversine_km(lat, lon, station["lat"], station["lon"])
        if dist < best_d:
            best_d = dist
            best = station
    if not best:
        return None
    return {
        "id": best["id"],
        "ja": best["ja"],
        "zh": best["zh"],
        "dist": round(best_d, 1),
        "ele": best["ele"],
    }


def build(osm: dict, index, stations: list[dict]) -> dict:
    drafts = []
    for element in osm.get("elements") or []:
        tags = element.get("tags") or {}
        if not (tags.get("name") or tags.get("name:ja")):
            continue
        if should_drop(tags):
            continue
        coords = center_of(element)
        if not coords:
            continue
        lat, lon = coords
        if not (24 <= lat <= 46.5 and 122 <= lon <= 154):
            continue
        src = japanese_source(tags)
        en = display_en(tags)
        ja = display_ja(tags)
        meta = override_meta(src) or override_meta(ja) or override_meta(tags.get("name") or "") or override_meta(en)
        if meta:
            zh, aliases, note = meta
        else:
            zh = to_zh(src)
            aliases, note = [], None
        ja_fix = {
            "Yogoshiyama Ski Area": "夜越山スキー場",
            "Geto Kogen": "夏油高原スキー場",
            "Ohana Resort": "オハナリゾート",
        }
        raw_name = tags.get("name") or ""
        if raw_name in ja_fix:
            ja = ja_fix[raw_name]
            if not en:
                en = raw_name
        pref_ja = index.lookup(lat, lon)
        pref_fix = {
            norm_key("かぐらスキー場"): "群馬県",
            norm_key("斑尾高原スキー場"): "長野県",
        }
        fixed = pref_fix.get(norm_key(src)) or pref_fix.get(norm_key(ja)) or pref_fix.get(norm_key(tags.get("name") or ""))
        if fixed:
            pref_ja = fixed
        pref_zh, region = classify(pref_ja)
        extra_aliases = [a for a in aliases if a and a != zh]
        roma = " ".join(
            bit
            for bit in {
                romaji(ja),
                romaji(src),
                romaji(" ".join(extra_aliases)),
            }
            if bit
        )
        drafts.append(
            {
                "tags": tags,
                "osm": f"{element.get('type')}/{element.get('id')}",
                "osm_type": element.get("type") or "way",
                "osm_id": int(element.get("id") or 0),
                "zh": zh,
                "ja": ja,
                "en": en,
                "pref": pref_zh,
                "pref_ja": pref_ja or "",
                "region": region,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "aliases": extra_aliases,
                "note": note,
                "web": website(tags),
                "roma": roma,
                "core": core_name(src or ja),
                "score": score(tags),
            }
        )

    drafts.sort(key=lambda item: item["score"], reverse=True)
    kept: list[dict] = []
    for item in drafts:
        merged = False
        for prev in kept:
            dist = haversine_km(item["lat"], item["lon"], prev["lat"], prev["lon"])
            same = item["core"] and item["core"] == prev["core"]
            close = dist <= (4.0 if same else 1.5)
            if close and similar(item["core"], prev["core"]):
                merged = True
                break
        if not merged:
            kept.append(item)

    used: dict[str, int] = {}
    resorts = []
    for item in sorted(kept, key=lambda row: (row["region"], row["pref"], row["zh"])):
        base = slugify(item["en"], item["ja"], item["osm_type"], item["osm_id"])
        pref_bit = re.sub(r"[^a-z]+", "", item["pref_ja"].lower())[:8]
        candidate = base
        if candidate in used:
            candidate = f"{base}-{pref_bit or item['region']}"
        n = 2
        while candidate in used:
            candidate = f"{base}-{n}"
            n += 1
        used[candidate] = 1
        amedas = nearest_station(item["lat"], item["lon"], stations)
        resort = {
            "id": candidate,
            "zh": item["zh"],
            "ja": item["ja"],
            "en": item["en"],
            "pref": item["pref"],
            "region": item["region"],
            "lat": item["lat"],
            "lon": item["lon"],
            "aliases": item["aliases"],
            "roma": item["roma"],
            "osm": item["osm"],
        }
        if item["note"]:
            resort["note"] = item["note"]
        if item["web"]:
            resort["web"] = item["web"]
        if amedas:
            resort["amedas"] = amedas
        resorts.append(resort)

    resorts.sort(key=lambda row: row["id"])
    return {
        "version": 1,
        "generated": datetime.now(JST).isoformat(timespec="seconds"),
        "count": len(resorts),
        "regions": [{"id": rid, "zh": label} for rid, label in REGIONS],
        "resorts": resorts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osm", type=Path, help="Existing Overpass JSON")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "resorts.json")
    args = parser.parse_args()

    opencc = cached("JPShinjitaiCharacters.txt", OPENCC_URL)
    load_kanji_map(opencc)
    name_test()

    topo = cached("japan.topojson", TOPO_URL)
    index = load_index(topo)
    geo_test(index)

    amedas_path = cached("amedastable.json", AMEDAS_URL)
    stations = load_amedas(amedas_path)
    print(f"AMeDAS snow stations: {len(stations)}")

    if args.osm:
        osm = json.loads(args.osm.read_text(encoding="utf-8"))
    else:
        osm = download_osm()
    print(f"OSM elements: {len(osm.get('elements') or [])}")

    payload = build(osm, index, stations)
    if args.out.exists():
        try:
            old_rows = json.loads(args.out.read_text(encoding="utf-8")).get("resorts") or []
            previous = {row["id"]: row for row in old_rows}
        except json.JSONDecodeError:
            previous = {}
        for resort in payload["resorts"]:
            old = previous.get(resort["id"]) or {}
            for key in ("size", "ticket", "links"):
                if old.get(key):
                    resort[key] = old[key]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    resorts = payload["resorts"]
    kana_left = [r for r in resorts if has_kana(r["zh"])]
    regions: dict[str, int] = {}
    for resort in resorts:
        regions[resort["region"]] = regions.get(resort["region"], 0) + 1
    linked = sum(1 for r in resorts if r.get("amedas"))
    print(f"resorts: {len(resorts)} amedas<=30km: {linked}")
    print("regions:", regions)
    if kana_left:
        print("KANA IN ZH:")
        for resort in kana_left[:30]:
            print(" ", resort["zh"], resort["ja"])
        raise SystemExit(f"{len(kana_left)} Chinese names still contain kana")
    other = regions.get("other", 0)
    if other:
        print(f"warning: {other} resorts without a prefecture")
    print("sample:")
    wanted = ("二世谷", "留壽都", "白馬八方尾根", "野澤溫泉", "藏王溫泉", "神樂", "喜樂樂")
    for resort in resorts:
        if resort["zh"] in wanted:
            station = resort.get("amedas")
            dist = f"{station['zh']} {station['dist']}km" if station else "-"
            print(f"  {resort['id']:28} {resort['zh']:10} {resort['pref']:4} {resort['ja']} | {dist}")


if __name__ == "__main__":
    main()
