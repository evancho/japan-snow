#!/usr/bin/env python3
"""Write data/conditions.json from Open-Meteo and JMA AMeDAS.

Snow depth and 24h snowfall are observed when a nearby AMeDAS snow station
is reporting a normal value. Otherwise they are Open-Meteo model estimates.
48h snowfall and the daily forecast are model estimates. Temperature on the
card is the model value at the resort grid elevation, because valley stations
are often much warmer than the slope.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESORTS = ROOT / "data" / "resorts.json"
OUT = ROOT / "data" / "conditions.json"
JST = timezone(timedelta(hours=9))
UA = "japan-snow/1.0 (+https://github.com/evancho/japan-snow)"
BATCH = 25
METEO = "https://api.open-meteo.com/v1/forecast"


def get_bytes(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/plain"})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed {url[:80]}: {last}")


def valid_pair(pair) -> float | None:
    if not isinstance(pair, list) or len(pair) < 2:
        return None
    value, quality = pair[0], pair[1]
    if quality in (0, 1) and isinstance(value, (int, float)):
        return float(value)
    return None


def round1(value) -> float | None:
    if value is None:
        return None
    number = round(float(value), 1)
    if number == 0:
        return 0
    return number


def round0(value) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))


def parse_local(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp).replace(tzinfo=JST)


def load_amedas_map() -> tuple[str, dict]:
    latest = get_bytes("https://www.jma.go.jp/bosai/amedas/data/latest_time.txt", timeout=30).decode().strip()
    stamp = datetime.fromisoformat(latest).strftime("%Y%m%d%H%M%S")
    url = f"https://www.jma.go.jp/bosai/amedas/data/map/{stamp}.json"
    try:
        payload = json.loads(get_bytes(url, timeout=60))
    except Exception:
        # The map file can lag the timestamp by a minute.
        previous = datetime.fromisoformat(latest) - timedelta(minutes=10)
        stamp = previous.strftime("%Y%m%d%H%M%S")
        url = f"https://www.jma.go.jp/bosai/amedas/data/map/{stamp}.json"
        payload = json.loads(get_bytes(url, timeout=60))
        latest = previous.isoformat()
    return latest, payload


def fetch_batch(rows: list[dict]) -> list[dict]:
    params = {
        "latitude": ",".join(f"{r['lat']:.5f}" for r in rows),
        "longitude": ",".join(f"{r['lon']:.5f}" for r in rows),
        "current": "temperature_2m,snowfall,snow_depth,weather_code",
        "hourly": "temperature_2m,snowfall,snow_depth",
        "daily": "snowfall_sum,temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": "Asia/Tokyo",
        "past_days": "2",
        "forecast_days": "5",
        "wind_speed_unit": "ms",
    }
    url = METEO + "?" + urllib.parse.urlencode(params)
    data = json.loads(get_bytes(url, timeout=120))
    if isinstance(data, dict):
        data = [data]
    if len(data) != len(rows):
        raise RuntimeError(f"Open-Meteo returned {len(data)} rows for {len(rows)}")
    return data


def summarize(row: dict, block: dict, obs_time: str, obs_row: dict | None) -> dict | None:
    current = block.get("current") or {}
    hourly = block.get("hourly") or {}
    daily = block.get("daily") or {}
    if not current and not daily:
        return None
    try:
        now = parse_local(current.get("time") or hourly.get("time", [None])[-1])
    except Exception:
        now = datetime.now(JST)

    times = hourly.get("time") or []
    snows = hourly.get("snowfall") or []
    d24 = 0.0
    d48 = 0.0
    seen = 0
    for stamp, amount in zip(times, snows):
        if amount is None:
            continue
        seen += 1
        ts = parse_local(stamp)
        if now - timedelta(hours=48) < ts <= now:
            d48 += float(amount)
        if now - timedelta(hours=24) < ts <= now:
            d24 += float(amount)
    if seen == 0:
        d24 = d48 = None

    depth_m = current.get("snow_depth")
    model_depth = None if depth_m is None else round0(float(depth_m) * 100)
    model_temp = round1(current.get("temperature_2m"))
    model_ele = block.get("elevation")
    model_ele = None if model_ele is None else int(round(float(model_ele)))

    dates = daily.get("time") or []
    snow_sum = daily.get("snowfall_sum") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []
    today = now.date().isoformat()
    forecast = []
    for i, day in enumerate(dates):
        if day < today:
            continue
        forecast.append(
            [
                day,
                round1(snow_sum[i] if i < len(snow_sum) else None),
                round1(tmax[i] if i < len(tmax) else None),
                round1(tmin[i] if i < len(tmin) else None),
                None if i >= len(codes) or codes[i] is None else int(codes[i]),
            ]
        )
        if len(forecast) == 5:
            break
    fc3_vals = [item[1] for item in forecast[:3] if item[1] is not None]
    fc3 = round1(sum(fc3_vals)) if fc3_vals else None

    obs = None
    obs_depth = None
    obs_d24 = None
    obs_temp = None
    station = row.get("amedas")
    if station and obs_row:
        obs_depth = valid_pair(obs_row.get("snow"))
        obs_d24 = valid_pair(obs_row.get("snow24h"))
        obs_temp = valid_pair(obs_row.get("temp"))
        # Some hours only publish snow1h / snow6h / snow12h.
        if obs_d24 is None:
            for key, hours in (("snow12h", 12), ("snow6h", 6), ("snow1h", 1)):
                piece = valid_pair(obs_row.get(key))
                if piece is not None and hours >= 12:
                    obs_d24 = piece
                    break
        ele_diff = None
        if station.get("ele") is not None and model_ele is not None:
            ele_diff = abs(float(station["ele"]) - model_ele)
        obs = {
            "id": station["id"],
            "zh": station.get("zh") or station.get("ja"),
            "ja": station.get("ja"),
            "dist": station.get("dist"),
            "ele": station.get("ele"),
            "time": obs_time,
        }
        if obs_temp is not None:
            obs["temp"] = round1(obs_temp)
        if obs_depth is not None:
            obs["depth"] = round0(obs_depth)
        if obs_d24 is not None:
            obs["d24"] = round1(obs_d24)
        if ele_diff is not None:
            obs["ele_diff"] = int(round(ele_diff))
        close = (station.get("dist") or 99) <= 12 and (ele_diff is None or ele_diff <= 500)
    else:
        close = False

    if obs and obs.get("depth") is not None and close:
        depth, depth_kind = obs["depth"], "obs"
    else:
        depth, depth_kind = model_depth, "est"
    if obs and obs.get("d24") is not None and close:
        snow24, snow24_kind = obs["d24"], "obs"
    else:
        snow24, snow24_kind = (None if d24 is None else round1(d24)), "est"

    item = {
        "temp": model_temp,
        "temp_kind": "est",
        "depth": depth,
        "depth_kind": depth_kind,
        "d24": snow24,
        "d24_kind": snow24_kind,
        "d48": None if d48 is None else round1(d48),
        "d48_kind": "est",
        "wx": None if current.get("weather_code") is None else int(current["weather_code"]),
        "ele": model_ele,
        "fc": forecast,
        "fc3": fc3,
        "model_depth": model_depth,
    }
    if obs:
        item["obs"] = obs
    if depth is None and model_temp is None and not forecast:
        return None
    return item


def main() -> None:
    resorts = json.loads(RESORTS.read_text(encoding="utf-8"))["resorts"]
    print(f"resorts {len(resorts)}", flush=True)
    obs_time, obs_map = load_amedas_map()
    snow_reports = 0
    for row in obs_map.values():
        if valid_pair(row.get("snow")) is not None:
            snow_reports += 1
    print(f"AMeDAS {obs_time} snow values {snow_reports}", flush=True)

    by_id = {}
    failures = []
    for start in range(0, len(resorts), BATCH):
        chunk = resorts[start : start + BATCH]
        try:
            blocks = fetch_batch(chunk)
        except Exception as exc:  # noqa: BLE001
            print(f"batch {start} failed: {exc}", flush=True)
            # Split once so one bad coordinate doesn't drop the whole batch.
            blocks = []
            for row in chunk:
                try:
                    blocks.append(fetch_batch([row])[0])
                    time.sleep(0.4)
                except Exception as inner:  # noqa: BLE001
                    blocks.append(None)
                    failures.append(row["id"] + ": " + str(inner))
        for row, block in zip(chunk, blocks):
            if not block:
                failures.append(row["id"])
                continue
            got_lat = block.get("latitude")
            if got_lat is not None and abs(float(got_lat) - row["lat"]) > 0.2:
                failures.append(row["id"] + ": lat mismatch")
                continue
            obs_row = None
            station = row.get("amedas")
            if station:
                obs_row = obs_map.get(station["id"])
            item = summarize(row, block, obs_time, obs_row)
            if item:
                by_id[row["id"]] = item
            else:
                failures.append(row["id"] + ": empty")
        print(f"  {min(start + BATCH, len(resorts))}/{len(resorts)}", flush=True)
        time.sleep(0.8)

    coverage = len(by_id) / max(len(resorts), 1)
    print(f"coverage {len(by_id)}/{len(resorts)} ({coverage:.1%}) failures {len(failures)}", flush=True)
    if failures[:8]:
        print("failures:", "; ".join(failures[:8]), flush=True)
    if coverage < 0.9:
        raise SystemExit("not enough resorts updated; leaving the previous file in place")

    payload = {
        "updated": datetime.now(JST).isoformat(timespec="seconds"),
        "timezone": "Asia/Tokyo",
        "obs_time": obs_time,
        "sources": {
            "model": "Open-Meteo",
            "obs": "JMA AMeDAS",
        },
        "resorts": by_id,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    depths = [v["depth"] for v in by_id.values() if isinstance(v.get("depth"), (int, float))]
    positive = sum(1 for n in depths if n > 0)
    print(f"wrote {OUT} positive snow {positive} max {max(depths) if depths else 0}", flush=True)


if __name__ == "__main__":
    main()
