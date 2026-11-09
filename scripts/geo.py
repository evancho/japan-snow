"""Prefecture lookup from the GSI Global Map Japan topojson (build time only)."""

from __future__ import annotations

import json
import math
from pathlib import Path

# Japanese prefecture name from the boundary file -> (Traditional Chinese, region id)
PREFECTURES = {
    "北海道": ("北海道", "hokkaido"),
    "青森県": ("青森", "tohoku"),
    "岩手県": ("岩手", "tohoku"),
    "宮城県": ("宮城", "tohoku"),
    "秋田県": ("秋田", "tohoku"),
    "山形県": ("山形", "tohoku"),
    "福島県": ("福島", "tohoku"),
    "茨城県": ("茨城", "kanto"),
    "栃木県": ("栃木", "kanto"),
    "群馬県": ("群馬", "kanto"),
    "埼玉県": ("埼玉", "kanto"),
    "千葉県": ("千葉", "kanto"),
    "東京都": ("東京", "kanto"),
    "神奈川県": ("神奈川", "kanto"),
    "新潟県": ("新潟", "niigata"),
    "富山県": ("富山", "hokuriku"),
    "石川県": ("石川", "hokuriku"),
    "福井県": ("福井", "hokuriku"),
    "山梨県": ("山梨", "kanto"),
    "長野県": ("長野", "kanto"),
    "岐阜県": ("岐阜", "tokai"),
    "静岡県": ("靜岡", "tokai"),
    "愛知県": ("愛知", "tokai"),
    "三重県": ("三重", "tokai"),
    "滋賀県": ("滋賀", "kansai"),
    "京都府": ("京都", "kansai"),
    "大阪府": ("大阪", "kansai"),
    "兵庫県": ("兵庫", "kansai"),
    "奈良県": ("奈良", "kansai"),
    "和歌山県": ("和歌山", "kansai"),
    "鳥取県": ("鳥取", "chugoku"),
    "島根県": ("島根", "chugoku"),
    "岡山県": ("岡山", "chugoku"),
    "広島県": ("廣島", "chugoku"),
    "山口県": ("山口", "chugoku"),
    "徳島県": ("德島", "shikoku"),
    "香川県": ("香川", "shikoku"),
    "愛媛県": ("愛媛", "shikoku"),
    "高知県": ("高知", "shikoku"),
    "福岡県": ("福岡", "kyushu"),
    "佐賀県": ("佐賀", "kyushu"),
    "長崎県": ("長崎", "kyushu"),
    "熊本県": ("熊本", "kyushu"),
    "大分県": ("大分", "kyushu"),
    "宮崎県": ("宮崎", "kyushu"),
    "鹿児島県": ("鹿兒島", "kyushu"),
    "沖縄県": ("沖繩", "kyushu"),
}

REGIONS = [
    ("hokkaido", "北海道"),
    ("tohoku", "東北"),
    ("kanto", "關東甲信"),
    ("niigata", "新潟"),
    ("hokuriku", "北陸"),
    ("tokai", "東海"),
    ("kansai", "關西"),
    ("chugoku", "中國"),
    ("shikoku", "四國"),
    ("kyushu", "九州"),
]


def _decode_arc(index: int, arcs: list, transform: dict) -> list[tuple[float, float]]:
    if index < 0:
        return list(reversed(_decode_arc(~index, arcs, transform)))
    scale = transform["scale"]
    translate = transform["translate"]
    x = y = 0
    points = []
    for dx, dy in arcs[index]:
        x += dx
        y += dy
        points.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
    return points


def _point_in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat):
            denom = yj - yi
            if denom == 0:
                denom = 1e-12
            if lon < (xj - xi) * (lat - yi) / denom + xi:
                inside = not inside
        j = i
    return inside


class PrefectureIndex:
    def __init__(self, topo: dict):
        arcs = topo["arcs"]
        transform = topo["transform"]
        self._areas = []
        for geom in topo["objects"]["japan"]["geometries"]:
            name = geom["properties"]["nam_ja"]
            polygons = []
            all_pts = []
            raw = geom["arcs"]
            # Polygon: [ring, ...]. MultiPolygon: [polygon, ...].
            if geom.get("type") == "Polygon":
                raw = [raw]
            for polygon in raw:
                rings = []
                for ring_idx in polygon:
                    ring = []
                    for arc_i in ring_idx:
                        ring.extend(_decode_arc(arc_i, arcs, transform))
                    if len(ring) >= 3:
                        rings.append(ring)
                        all_pts.extend(ring)
                if rings:
                    polygons.append(rings)
            if not all_pts:
                continue
            xs = [p[0] for p in all_pts]
            ys = [p[1] for p in all_pts]
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            self._areas.append(
                {
                    "name": name,
                    "bbox": (min(xs), min(ys), max(xs), max(ys)),
                    "polygons": polygons,
                    "center": (cx, cy),
                }
            )

    def lookup(self, lat: float, lon: float) -> str | None:
        for area in self._areas:
            minx, miny, maxx, maxy = area["bbox"]
            if lon < minx or lon > maxx or lat < miny or lat > maxy:
                continue
            for rings in area["polygons"]:
                inside = False
                for ring in rings:
                    if _point_in_ring(lon, lat, ring):
                        inside = not inside
                if inside:
                    return area["name"]
        best = None
        best_d = 1e9
        for area in self._areas:
            cx, cy = area["center"]
            d = (cx - lon) ** 2 + (cy - lat) ** 2
            if d < best_d:
                best_d = d
                best = area["name"]
        # ~0.6 degree is roughly 60 km; don't guess across the sea.
        if best is not None and best_d < 0.6 ** 2:
            return best
        return None


def load_index(path: Path) -> PrefectureIndex:
    return PrefectureIndex(json.loads(path.read_text(encoding="utf-8")))


def classify(pref_ja: str | None) -> tuple[str, str]:
    if not pref_ja or pref_ja not in PREFECTURES:
        return ("其他", "other")
    return PREFECTURES[pref_ja]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def self_test(index: PrefectureIndex) -> None:
    samples = [
        (35.0116, 135.7681, "京都府"),
        (42.866, 140.674, "北海道"),
        (36.704, 137.819, "長野県"),
        (36.794, 138.771, "新潟県"),
        (38.161, 140.406, "山形県"),
        (39.987, 140.967, "岩手県"),
        (36.631, 138.575, "群馬県"),
        (43.064, 141.347, "北海道"),
        (36.917, 138.469, "長野県"),
        (35.535, 136.089, "滋賀県"),
        (39.238, 140.897, "岩手県"),
    ]
    bad = []
    for lat, lon, expect in samples:
        got = index.lookup(lat, lon)
        if got != expect:
            bad.append(f"{lat},{lon} -> {got} expected {expect}")
    if bad:
        raise SystemExit("prefecture tests failed:\n" + "\n".join(bad))
