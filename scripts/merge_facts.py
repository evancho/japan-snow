#!/usr/bin/env python3
"""Attach piste size from OpenStreetMap and curated ticket facts.

Size is the summed length of OSM downhill piste ways, assigned to the nearest
resort within 3 km. It is mapped length, not a resort's published figure.
Prices and extra links are only those read from the resort's own site.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RESORTS = ROOT / "data" / "resorts.json"
PISTES = Path("/tmp/pistes")
LIFTS = Path("/tmp/lifts")
LINKS = Path("/tmp/ticket_clean.json")

# Adult one-day prices read from the resort's own page on 2026-11-10.
# jpy, season label, source url, note
PRICES = {
    "niseko-united": (
        13500,
        "2026-27 旺季（12/24–2/28）",
        "https://www.niseko.ne.jp/ja/lift/",
        "窗口價。通常期 12,600 円，季初與春季 8,800 円。",
    ),
    "hakuba-happo-one": (
        9800,
        "2026-27 旺季（12/19–3/22）",
        "https://www.happo-one.jp/ticket/",
        "窗口成人一日券。季初與春季是 6,400 円。",
    ),
    "nozawa-onsen": (
        7800,
        "2026-27 通常（12/19–3/28）",
        "https://nozawaski.com/winter/lift_price/",
        "初滑期間另有 5,600 円。",
    ),
    "rusutsu-resort-ski-area": (
        16700,
        "官網現行窗口價（2026-11-10 查看）",
        "https://rusutsu.com/winter-lift-tickets/",
        "成人 19–64 歲。線上價是 13,200 円。",
    ),
    "hakuba-47": (
        9500,
        "2026-27 一日券",
        "https://hakuba47.co.jp/ja/lift-tickets/",
        "這筆含可退的 IC 卡保證金 500 円。早割與春雪是 8,500 円。",
    ),
    "geto-kogen": (
        6900,
        "官網一日券（初滑・春雪另計）",
        "https://www.getokogen.com/winter/02service/index.html",
        "成人欄。從閘門起連續 8 小時。初滑・春雪是 5,300 円。",
    ),
    "hoshino-resorts-nekoma-mountain": (
        6500,
        "2026-27 通常",
        "https://www.nekoma.co.jp/price/",
        None,
    ),
    "pilatus-tateshina-snow-resort": (
        6500,
        "2026-27",
        "https://www.pilatus.jp/price/",
        "中學生以上。",
    ),
    "yuzawa-nakazato-ski-resort": (
        6700,
        "2026/12/19–2027/3/28",
        "https://www.yuzawa-nakazato.com/winter/fee/",
        None,
    ),
    "shizukuishi-ski-resort": (
        6800,
        "官網冬季頁（2026-11-10 查看）",
        "https://www.princehotels.co.jp/ski/shizukuishi/winter/lift/",
        "一般成人一日券。",
    ),
    "myoko-suginohara-ski-resort": (
        9000,
        "官網冬季頁（2026-11-10 查看）",
        "https://www.princehotels.co.jp/ski/myoko/winter/lift/",
        "一般價。會員價較低。",
    ),
    "prince-hotels-and-resorts-karuizawa": (
        13000,
        "官網現地購買一日券（2026-11-10 查看）",
        "https://www.princehotels.co.jp/ski/karuizawa/winter/lift/",
        "頁面上的成人現地價。",
    ),
    "kagura-ski-resort": (
        11800,
        "2026/12/26–2027/3/22",
        "https://www.princehotels.co.jp/ski/kagura/winter/lift/",
        "苗場、神樂、三俣、田代共通一日券。",
    ),
    "ryuoo-ski-park": (
        6000,
        "2026/12/19–2027/3/22 平日",
        "https://ryuoo.com/winter/price_w/",
        "平日一日券。",
    ),
    "fujiten-snow-resort": (
        5800,
        "平日窗口（2026-11-10 查看）",
        "https://www.fujiten.net/charges/",
        "平日 9:00–16:30 的窗口一日券。",
    ),
    "white-world-oze-iwakura": (
        7200,
        "特定日（2026-11-10 查看）",
        "https://www.oze-iwakura.co.jp/ski/price/",
        "特定日的成人一日券。",
    ),
    "kawaba-ski-resort": (
        7600,
        "平日（2026-11-10 查看）",
        "https://www.kawaba.co.jp/lift-prices/",
        "平日一日券。",
    ),
    "akakura-kanko-ski-resort": (
        10000,
        "官網共通一日券（2026-11-10 查看）",
        "https://akr-ski.com/slope/",
        "赤倉觀光與赤倉溫泉共通，成人與中學生。",
    ),
    "rokkosan-snow-park": (
        3300,
        "土日祝",
        "https://www.rokkosan.com/ski/fee/",
        "平日是 1,600 円。大人與小孩同價。",
    ),
    "okutadami-maruyama-ski-resort": (
        5500,
        "官網一日券（2026-11-10 查看）",
        "http://www.okutadami.co.jp/ski/price.html",
        "成人一日券。兩日券是 9,400 円。",
    ),
    "kuzuryu-ski-resort": (
        4000,
        "土日祝一日券",
        "https://kuzuryu-skiland.com/price/",
        "平日是 3,000 円。中學生以上。",
    ),
}

# Lift-operation pages that returned HTTP 200 and are status pages, not cameras.
STATUS = {
    "niseko-united": "https://www.niseko.ne.jp/ja/niseko-lift-status/",
    "hakuba-happo-one": "https://www.happo-one.jp/en/gelande/lift-report/",
    "kiroro-resort": "https://www.kiroro.co.jp/ja/dashboard/",
    "kagura-ski-resort": "https://www.princehotels.co.jp/ski/kagura/informations/?tab=operation",
    "prince-hotels-and-resorts-karuizawa": "https://www.princehotels.co.jp/ski/karuizawa/informations/?tab=operation",
    "shizukuishi-ski-resort": "https://www.princehotels.co.jp/ski/shizukuishi/informations/?tab=operation",
    "sapporo-teine": "https://sapporo-teine.com/snow/lang/en/trailstatus",
    "geto-kogen": "https://www.getokogen.com/winter/01trail/operation.cgi",
    "osorakan-snow-park": "https://osorakan.co.jp/winter/lift-status-map/",
    "white-world-oze-iwakura": "https://www.oze-iwakura.co.jp/ski/slopeguide/today/",
    "fujiten-snow-resort": "https://www.fujiten.net/slopeguide/condition/",
    "spring-valley-izumi-kogen": "https://www.springvalley.co.jp/winter/gelande/lift",
}

TICKET_URL = {rid: item[2] for rid, item in PRICES.items()}

SKIP_URL = ("rss", "feed", "/summer/", "/green/", "tourpack", "webstores", "file.jsp", "playland", "rental")


def hav(lat1, lon1, lat2, lon2):
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, a)))


def host(url: str) -> str:
    name = urlparse(url).netloc.lower()
    return name[4:] if name.startswith("www.") else name


def same_site(a: str, b: str) -> bool:
    ha, hb = host(a), host(b)
    return bool(ha and hb) and (ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha))


def length_km(geom):
    total = 0.0
    for a, b in zip(geom, geom[1:]):
        total += hav(a["lat"], a["lon"], b["lat"], b["lon"])
    return total


def load_elements(folder: Path):
    found = {}
    if not folder.exists():
        return found
    for path in folder.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for el in data.get("elements") or []:
            found[el["id"]] = el
    return found


def nearest(resorts, lat, lon, limit):
    best = None
    best_d = limit
    for resort in resorts:
        if abs(resort["lat"] - lat) > 0.05 or abs(resort["lon"] - lon) > 0.06:
            continue
        dist = hav(resort["lat"], resort["lon"], lat, lon)
        if dist < best_d:
            best_d = dist
            best = resort
    return best


def sizes(resorts):
    buckets = {r["id"]: {"km": 0.0, "named": set(), "lifts": 0} for r in resorts}
    pistes = load_elements(PISTES)
    for el in pistes.values():
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        sample = geom[::4] or geom[:1]
        best = None
        best_d = 3.0
        for point in sample:
            hit = nearest(resorts, point["lat"], point["lon"], best_d)
            if not hit:
                continue
            dist = hav(hit["lat"], hit["lon"], point["lat"], point["lon"])
            if dist < best_d:
                best_d = dist
                best = hit
        if not best:
            continue
        bucket = buckets[best["id"]]
        bucket["km"] += length_km(geom)
        name = (el.get("tags") or {}).get("name")
        if name:
            bucket["named"].add(name)
    skip_lift = {"station", "pylon", "goods", "zip_line"}
    for el in load_elements(LIFTS).values():
        kind = (el.get("tags") or {}).get("aerialway")
        if kind in skip_lift:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None:
            continue
        hit = nearest(resorts, lat, lon, 2.5)
        if hit:
            buckets[hit["id"]]["lifts"] += 1
    out = {}
    for rid, bucket in buckets.items():
        km = round(bucket["km"], 1)
        if km < 1:
            continue
        item = {
            "piste_km": km,
            "source": "OpenStreetMap",
            "as_of": "2026-11-10",
            "note": "OpenStreetMap 已繪製的 downhill 雪道長度，不是雪場公布的數字，沒畫到的不算。",
        }
        if bucket["named"]:
            item["courses"] = len(bucket["named"])
        if bucket["lifts"]:
            item["lifts"] = bucket["lifts"]
        out[rid] = item
    return out


def discovered_links(resorts):
    if not LINKS.exists():
        return {}
    rows = json.loads(LINKS.read_text(encoding="utf-8"))
    by_web = {r["id"]: r.get("web") or "" for r in resorts}
    found = {}
    for row in rows:
        web = by_web.get(row["id"]) or ""
        url = row.get("ticket_url") or ""
        if not url or not web or not same_site(web, url):
            continue
        low = url.lower()
        if any(part in low for part in SKIP_URL):
            continue
        found[row["id"]] = url
    return found


def main():
    payload = json.loads(RESORTS.read_text(encoding="utf-8"))
    resorts = payload["resorts"]
    size_map = sizes(resorts)
    link_map = discovered_links(resorts)
    # Correct a few ticket pages the crawler pointed at a subpage.
    link_map.update(TICKET_URL)
    for resort in resorts:
        resort.pop("size", None)
        resort.pop("ticket", None)
        resort.pop("links", None)
        size = size_map.get(resort["id"])
        if size:
            resort["size"] = size
        price = PRICES.get(resort["id"])
        links = {}
        if price:
            jpy, season, source, note = price
            ticket = {
                "jpy": jpy,
                "season": season,
                "label": "成人一日券",
                "source": source,
                "as_of": "2026-11-10",
            }
            if note:
                ticket["note"] = note
            resort["ticket"] = ticket
            links["ticket"] = source
        elif resort["id"] in link_map:
            links["ticket"] = link_map[resort["id"]]
        if resort["id"] in STATUS:
            links["status"] = STATUS[resort["id"]]
        if links:
            resort["links"] = links
    RESORTS.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = len(resorts)
    print(f"resorts {n}")
    print(f"size {sum(1 for r in resorts if r.get('size'))}")
    print(f"price {sum(1 for r in resorts if r.get('ticket'))}")
    print(f"status link {sum(1 for r in resorts if (r.get('links') or {}).get('status'))}")
    print(f"ticket link {sum(1 for r in resorts if (r.get('links') or {}).get('ticket'))}")


if __name__ == "__main__":
    main()
