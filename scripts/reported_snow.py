#!/usr/bin/env python3
"""Scrape resort-reported snow depth from official status pages.

Each parser takes the fetched HTML and returns (summit_cm, base_cm) or None.
Values are what the resort itself measured on the slope, so they beat
AMeDAS valley stations when present. Pages are only populated during the
season; before opening the blocks are empty or missing and we return None,
which keeps the existing AMeDAS/Open-Meteo fallback.
"""

from __future__ import annotations

import re
from html import unescape

STATUS_PAGES = {
    "tomamu-ski-resort": "https://www.snowtomamu.jp/winter/ski/ski-slope/condition/",
    "furano-ski-resort": "https://www.princehotels.co.jp/ski/furano/informations/?tab=operation",
    "kiroro-resort": "https://www.kiroro.co.jp/ja/dashboard/",
    "sapporo-teine": "https://sapporo-teine.com/snow/lang/en/trailstatus",
    "rusutsu-resort-ski-area": "https://rusutsu.com/lift-and-trail-status/",
    "asahidake": "https://asahidake.hokkaido.jp/ja/",
    "kamui-ski-links": "https://www.kamui-skilinks.com/today/",
    "sahoro": "https://sahoro-resort.com/winter/ski/course-info",
}


def _nums(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"(\d{1,4})[\s\S]{0,90}?(?:cm|センチ)", text)]


def _zero_none(pair):
    if pair is None:
        return None
    s, b = pair
    s = None if s in (0, None) else s
    b = None if b in (0, None) else b
    return (s, b) if (s is not None or b is not None) else None


def _parse_tomamu(html: str):
    m = re.search(r"condition-snowfall[\s\S]{0,600}", html)
    if not m:
        return None
    n = _nums(re.sub(r"<[^>]+>", " ", m.group(0)))
    if len(n) >= 2:
        return (n[0], n[1])
    if len(n) == 1:
        return (None, n[0])
    return None


def _parse_kiroro(html: str):
    m = re.search(r"積雪情報</th>\s*<td>\s*(\d{1,4})\s*cm\s*</td>\s*<td>\s*(\d{1,4})\s*cm", html)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))  # 山頂, 山麓


def _parse_teine(html: str):
    # 2026-11 官網改版：積雪區塊變成「標籤在前、數字在後」
    # （山頂積雪 Peak-depth 25cm / 山麓積雪 Base-depth 0cm），
    # 舊寫法抓標籤「前面」的數字，會撈到 24h 降雪當山頂。改在文字層抓標籤後的數字。
    text = re.sub(r"<!--[\s\S]*?-->", " ", html)
    text = re.sub(r"<[^>]+>", " ", unescape(text))
    text = re.sub(r"\s+", " ", text)
    peak = re.search(r"(?:Peak-depth|山頂積雪)[^0-9]{0,40}?(\d{1,4})\s*cm", text)
    base = re.search(r"(?:Base-depth|山麓積雪)[^0-9]{0,40}?(\d{1,4})\s*cm", text)
    if not peak and not base:
        return None
    return (
        int(peak.group(1)) if peak else None,
        int(base.group(1)) if base else None,
    )


def _parse_rusutsu(html: str):
    m = re.search(r"積雪量</dt><dd>\+?(\d{1,4})\s*cm", html)
    if not m:
        return None
    return (None, int(m.group(1)))  # single reported number (mountain)


def _parse_asahidake(html: str):
    m = re.search(r"積雪</th>\s*<td>\s*(\d{1,4})\s*cm", html)
    if not m:
        return None
    return (int(m.group(1)), None)


def _parse_kamui(html: str):
    m = re.search(r"山頂[\s\-]*(\d{1,4})\s*cm[\s\S]{0,30}?山麓[\s\-]*(\d{1,4})\s*cm", html)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


def _parse_generic_snowfall(html: str):
    """Label 積雪（山頂／山麓）or 積雪 followed by up to two cm numbers."""
    text = unescape(html)
    for m in re.finditer(r"積雪(?:（山頂／山麓）|（山麓／山頂）)?[^0-9<]{0,80}?(\d{1,4})\s*(?:cm|センチ)", text):
        start = m.start()
        window = text[m.end():m.end() + 200]
        second = re.search(r"(\d{1,4})\s*(?:cm|センチ)", window)
        order = re.search(r"（山麓／山頂）", text[start:m.end()])
        a, b = int(m.group(1)), int(second.group(1)) if second else None
        if b is not None and order:
            a, b = b, a
        return (a, b)
    return None


PARSERS = {
    "tomamu-ski-resort": _parse_tomamu,
    "kiroro-resort": _parse_kiroro,
    "sapporo-teine": _parse_teine,
    "rusutsu-resort-ski-area": _parse_rusutsu,
    "asahidake": _parse_asahidake,
    "kamui-ski-links": _parse_kamui,
    "furano-ski-resort": _parse_generic_snowfall,
    "sahoro": _parse_generic_snowfall,
}


def fetch_reported(html_by_id: dict[str, str]) -> dict[str, tuple]:
    out = {}
    for rid, html in html_by_id.items():
        parser = PARSERS.get(rid, _parse_generic_snowfall)
        try:
            value = _zero_none(parser(html))
        except Exception:
            value = None
        if value:
            out[rid] = value
    return out


if __name__ == "__main__":
    import sys
    import urllib.request

    ua = {"User-Agent": "Mozilla/5.0 japan-snow/1.0"}
    ids = sys.argv[1:] or list(STATUS_PAGES)
    raw = {}
    for rid in ids:
        url = STATUS_PAGES.get(rid)
        if not url:
            continue
        try:
            raw[rid] = urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=60).read().decode("utf-8", "ignore")
        except Exception as exc:
            print(f"{rid}: FETCH FAIL {exc}")
    for rid, (summit, base) in sorted(fetch_reported(raw).items()):
        print(f"{rid}: summit={summit} base={base}")
