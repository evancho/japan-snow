#!/usr/bin/env python3
"""Attach piste size from OpenStreetMap and curated ticket facts.

Size is the summed length of OSM downhill piste ways, assigned to the nearest
resort within 3 km. It is mapped length, not a resort's published figure.
Prices and extra links are only those read from the resort's own site.
"""

from __future__ import annotations

import json
import math
import ssl
import urllib.request
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
    "furano-ski-resort": (
        9000,
        "2026-27 通常（12/5–3/22）",
        "https://www.princehotels.co.jp/ski/furano/winter/lift/",
        "一般窗口。初滑與春雪是 7,500 円。",
    ),
    "naeba-ski-resort": (
        9800,
        "2026/12/18–2027/4/4 苗場區",
        "https://www.princehotels.co.jp/ski/naeba/winter/lift/",
        "苗場區一日券。含神樂的 Mt.Naeba 共通券是 11,800 円。",
    ),
    "sapporo-kokusai-skiing-resort": (
        7000,
        "2026/11/20–2027/3/31 通常",
        "https://www.sapporo-kokusai.jp/price/",
        "一般窗口。網頁上的線上價是 6,700 円。",
    ),
    "kiroro-resort": (
        9200,
        "2026/12/12–2027/4/11 旺季",
        "https://www.kiroro.co.jp/ja/lift_price/",
        "成人。初滑與春雪是 5,800 円。",
    ),
    "madarao-kogen-mountain-resort": (
        9000,
        "官網マウンテンパス（2026-11-10 查看）",
        "https://www.madarao.jp/ski/price",
        "中學生以上。這張含坦格拉姆全部纜車，不是斑尾單區。",
    ),
    "tangram-madarao-ski-circus": (
        7000,
        "官網專用一日券（2026-11-10 查看）",
        "https://www.tangram.jp/ski/ticket/ticket.php",
        "坦格拉姆專用。與斑尾共通的マウンテンパス是 9,000 円。",
    ),
    "ishiuchi-maruyama-ski-resort": (
        9400,
        "官網整日窗口（2026-11-10 查看）",
        "https://ishiuchi.or.jp/winter/price/",
        "整日窗口。彈性時間一日券窗口是 8,500 円。",
    ),
    "biwako-valley": (
        6800,
        "官網通常價格（2026-11-10 查看）",
        "https://www.biwako-valley.com/w_season/hours_fare_winter/",
        "含纜車往返與雪道。預售有較低的區間價。",
    ),
    "marunuma-kogen-ski-resort": (
        6700,
        "2026/12/19 起 土日祝尖峰",
        "https://www.marunuma.jp/winter/ticket/",
        "平日尖峰是 6,000 円。初滑一日券是 5,200 円。",
    ),
    "inawashiro-snow-paradise": (
        6600,
        "2026-27 訪客一日券",
        "https://www.inawashiro-ski.com/lift/",
        "一般訪客。粉絲俱樂部平日另有優惠。",
    ),
    "hodaigi-ski-resort": (
        7400,
        "土日祝・年末年始",
        "https://hodaigi.jp/lift-price/",
        "平日一日券是 7,100 円。",
    ),
    "maiko-kogen-ski-resort": (
        7300,
        "官網 1 day（2026-11-10 查看）",
        "https://www.maiko-resort.com/winter/lift.html",
        "開場到關場。",
    ),
    "snow-park-yeti": (
        5300,
        "土日祝（2026-11-10 查看）",
        "https://www.yeti-resort.com/service/",
        "平日是 4,300 円。有效到 22:00。",
    ),
    "washigatake-ski-area": (
        5900,
        "官網一日券 8:00–16:30（2026-11-10 查看）",
        "https://ski.washigatake.jp/charge/",
        None,
    ),
    "dynaland-ski-area": (
        6400,
        "全日（2026-11-10 查看）",
        "https://www.dynaland.co.jp/charge/",
        None,
    ),
    "takasu-snow-park": (
        6400,
        "全日（2026-11-10 查看）",
        "https://www.takasu.gr.jp/charge/",
        None,
    ),
    "gala-yuzawa-snow-resort": (
        8000,
        "官網纜車加吊椅券（2026-11-10 查看）",
        "https://gala.co.jp/winter/hours-pricing/",
        "網頁價是 7,500 円。",
    ),
    "kamui-ski-links": (
        5300,
        "2026-27 當日券",
        "https://www.kamui-skilinks.com/guide/",
        "成人欄。另收可退的卡費 500 円。",
    ),
    "appi-kogen-ski-resort": (
        9500,
        "2026/12/19–2027/3/28 通常",
        "https://www.appi.co.jp/snow-mountain-resort/ticket/",
        "BLUE PASS 窗口與線上同價。12/5–12/18 的早季窗口是 4,500 円。",
    ),
    "hakuba-goryu": (
        9500,
        "官網線上新購一日券（2026-11-10 查看）",
        "https://www.hakubagoryu.jp/ski/pricing/lift-tickets/",
        "23–64 歲。春雪一日券是 8,500 円。",
    ),
    "tsugaike-kogen": (
        9800,
        "2026/12/1 起通常",
        "https://www.tsugaike.gr.jp/snow/price",
        "對照早割的通常售價。早割一日券是 6,500 円。",
    ),
    "niseko-annupuri": (
        7800,
        "2026/12/24–2027/2/28 旺季",
        "https://annupuri.info/lift-tickets/",
        "安努普利單區券，不是全山共通券。",
    ),
    "niseko-hirafu": (
        13500,
        "2026-27 旺季（12/24–2/28）全山共通",
        "https://www.niseko.ne.jp/ja/lift/",
        "比羅夫用二世谷全山共通券。通常期 12,600 円。",
    ),
    "niseko-hanazono": (
        13500,
        "2026-27 旺季（12/24–2/28）全山共通",
        "https://www.niseko.ne.jp/ja/lift/",
        "花園用二世谷全山共通券。通常期 12,600 円。",
    ),
    "niseko-village": (
        13500,
        "2026-27 旺季（12/24–2/28）全山共通",
        "https://www.niseko.ne.jp/ja/lift/",
        "二世谷村用全山共通券。通常期 12,600 円。",
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
    "hakuba-goryu": "https://www.hakubagoryu.jp/ski/gelande/lift-and-gondola-status/",
    "maiko-kogen-ski-resort": "https://www.maiko-resort.com/winter/today/",
    "kandatsu-kogen-ski-resort": "https://www.kandatsu.com/today/",
    "marunuma-kogen-ski-resort": "https://www.marunuma.jp/winter/status/",
    "zao-onsen-ski-resort": "https://zaomountainresort.com/ropeway-lift-information/",
    "appi-kogen-ski-resort": "https://www.appi.co.jp/snow-mountain-resort/info/",
    "dynaland-ski-area": "https://www.dynaland.co.jp/condition/",
    "takasu-snow-park": "https://www.takasu.gr.jp/condition/",
    "washigatake-ski-area": "https://ski.washigatake.jp/condition/",
    "niseko-hirafu": "https://www.niseko.ne.jp/ja/niseko-lift-status/",
    "niseko-hanazono": "https://www.niseko.ne.jp/ja/niseko-lift-status/",
    "niseko-village": "https://www.niseko.ne.jp/ja/niseko-lift-status/",
    "niseko-annupuri": "https://www.niseko.ne.jp/ja/niseko-lift-status/",
    "naeba-ski-resort": "https://www.princehotels.co.jp/ski/naeba/winter/coursemap/",
    "shiga-kogen-yakebitaiyama-ski-area": "https://www.princehotels.co.jp/ski/shiga/winter/coursemap/",
}

HOMEPAGES = {
    "furano-ski-resort": "https://www.princehotels.co.jp/ski/furano/winter/",
    "appi-kogen-ski-resort": "https://www.appi.co.jp/",
    "hakuba-goryu": "https://www.hakubagoryu.jp/?season=winter",
    "tsugaike-kogen": "https://www.tsugaike.gr.jp/",
    "dynaland-ski-area": "https://www.dynaland.co.jp/",
    "takasu-snow-park": "https://www.takasu.gr.jp/",
    "naeba-ski-resort": "https://www.princehotels.co.jp/ski/naeba/winter/",
    "grandeco-snow-resort": "https://grandecoresort.co.jp/",
    "niseko-hirafu": "https://www.niseko.ne.jp/ja/",
    "niseko-hanazono": "https://hanazononiseko.com/ja",
    "niseko-village": "https://www.niseko-village.com/",
    "niseko-annupuri": "https://annupuri.info/",
}

# Official course counts seen on the resort site, kept as a note. The km figure stays OSM.
SIZE_NOTES = {
    "niseko-united": "比羅夫、花園、二世谷村、安努普利已分開計算，這筆是中間剩下、較靠近全山中心的雪道。",
    "furano-ski-resort": "官網介紹寫約 28 條雪道。這裡的條數是地圖上有名稱的段，可能對不上。",
    "hoshino-resorts-nekoma-mountain": "官網寫全山 33 條雪道，含舊阿爾茨磐梯與貓魔。",
    "gala-yuzawa-snow-resort": "官網介紹寫 16 條雪道。地圖上的有名段數可能更多，因為一段雪道被拆開畫。",
}

EXTRA_RESORTS = [
    {
        "id": "niseko-hirafu",
        "zh": "二世谷比羅夫",
        "ja": "ニセコ東急グラン・ヒラフ",
        "en": "Niseko Grand Hirafu",
        "pref": "北海道",
        "region": "hokkaido",
        "lat": 42.8619,
        "lon": 140.69854,
        "aliases": ["比羅夫", "グランヒラフ", "Hirafu", "Grand Hirafu"],
        "roma": "niseko tokyu grand hirafu",
        "note": "二世谷全山的比羅夫區。座標是 OpenStreetMap 的售票處。",
    },
    {
        "id": "niseko-hanazono",
        "zh": "二世谷花園",
        "ja": "ニセコHANAZONOリゾート",
        "en": "Niseko Hanazono",
        "pref": "北海道",
        "region": "hokkaido",
        "lat": 42.88117,
        "lon": 140.68152,
        "aliases": ["花園", "ハナゾノ", "Hanazono"],
        "roma": "niseko hanazono",
        "note": "座標是 OpenStreetMap 上花園纜車的中心。",
    },
    {
        "id": "niseko-village",
        "zh": "二世谷村",
        "ja": "ニセコビレッジ",
        "en": "Niseko Village",
        "pref": "北海道",
        "region": "hokkaido",
        "lat": 42.84642,
        "lon": 140.68044,
        "aliases": ["二世谷村", "ビレッジ", "Village"],
        "roma": "niseko village",
        "note": "座標是 OpenStreetMap 的比羅夫村快速纜車。",
    },
    {
        "id": "niseko-annupuri",
        "zh": "二世谷安努普利",
        "ja": "ニセコアンヌプリ",
        "en": "Niseko Annupuri",
        "pref": "北海道",
        "region": "hokkaido",
        "lat": 42.85005,
        "lon": 140.64945,
        "aliases": ["安努普利", "アンヌプリ", "Annupuri"],
        "roma": "niseko annupuri",
        "note": "座標是 OpenStreetMap 的安努普利滑雪場節點。單區券和全山券不同。",
    },
]

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


def url_ok(url: str) -> bool:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "japan-snow/1.0 (+https://github.com/evancho/japan-snow)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12, context=ssl.create_default_context()) as res:
            return 200 <= res.status < 400
    except Exception as exc:  # noqa: BLE001
        print("drop", url, type(exc).__name__, str(exc)[:80])
        return False


def main():
    payload = json.loads(RESORTS.read_text(encoding="utf-8"))
    resorts = payload["resorts"]
    have = {r["id"] for r in resorts}
    for extra in EXTRA_RESORTS:
        if extra["id"] not in have:
            resorts.append(dict(extra))
    for resort in resorts:
        if resort["id"] == "niseko-united":
            aliases = set(resort.get("aliases") or [])
            aliases.update(["比羅夫", "花園", "安努普利", "二世谷村", "Hirafu", "Hanazono", "Annupuri"])
            resort["aliases"] = sorted(aliases)
        if resort["id"] == "hoshino-resorts-nekoma-mountain":
            aliases = set(resort.get("aliases") or [])
            aliases.update(["阿爾茨磐梯", "アルツ磐梯", "Alts Bandai", "貓魔"])
            resort["aliases"] = sorted(aliases)
        home = HOMEPAGES.get(resort["id"])
        if home:
            resort["web"] = home
    size_map = sizes(resorts) if any(PISTES.glob("*.json")) else {r["id"]: r["size"] for r in resorts if r.get("size")}
    link_map = discovered_links(resorts)
    # Correct a few ticket pages the crawler pointed at a subpage.
    link_map.update(TICKET_URL)
    for resort in resorts:
        resort.pop("size", None)
        resort.pop("ticket", None)
        resort.pop("links", None)
        size = size_map.get(resort["id"])
        if size:
            extra_note = SIZE_NOTES.get(resort["id"])
            if extra_note and extra_note not in size["note"]:
                size["note"] = size["note"] + extra_note
            resort["size"] = size
        price = PRICES.get(resort["id"])
        links = {}
        if price:
            jpy, season, source, note = price
            if url_ok(source):
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
        elif resort["id"] in link_map and url_ok(link_map[resort["id"]]):
            links["ticket"] = link_map[resort["id"]]
        status = STATUS.get(resort["id"])
        if status and url_ok(status):
            links["status"] = status
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
