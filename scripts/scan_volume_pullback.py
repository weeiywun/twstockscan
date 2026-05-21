#!/usr/bin/env python3
"""
量增回測模型

目標不是追爆量當天，而是找出：
放量突破 -> 回測原支撐 -> 可能開啟波段

候選來源：
- 籌碼集中 active pool
- 突破策略追蹤 active pool
- 既有量增訊號
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from finmind_client import get_stock_price_from_cache, load_price_cache

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
CHIPS_PATH = os.path.join(DATA_DIR, "chips_big_holder.json")
RIGHT_TOP_TRACK_PATH = os.path.join(DATA_DIR, "right_top_track.json")
VOLUME_SIGNAL_PATH = os.path.join(DATA_DIR, "volume_signal.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "volume_pullback.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")
START_DATE = (datetime.now(TW_TZ) - timedelta(days=180)).strftime("%Y-%m-%d")

IGNITION_LOOKBACK_DAYS = 5
IGNITION_VOL_RATIO_MIN = 2.5
REENTRY_VOL_RATIO_MIN = 1.5
PULLBACK_MAX_FROM_IGNITION_CLOSE = 0.08
FAIL_MAX_FROM_IGNITION_CLOSE = 0.10


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def add_candidate(candidates: dict[str, dict], item: dict, source: str) -> None:
    sid = str(item.get("stock_id") or "").strip()
    if not sid:
        return
    row = candidates.setdefault(sid, {
        "stock_id": sid,
        "name": item.get("name", ""),
        "industry": item.get("industry", ""),
        "market": item.get("market", ""),
        "sources": [],
        "source_tags": [],
    })
    row["name"] = row["name"] or item.get("name", "")
    row["industry"] = row["industry"] or item.get("industry", "")
    row["market"] = row["market"] or item.get("market", "")
    if source not in row["sources"]:
        row["sources"].append(source)
    for tag in item.get("tags", []) or []:
        if tag not in row["source_tags"]:
            row["source_tags"].append(tag)


def load_candidates() -> dict[str, dict]:
    candidates: dict[str, dict] = {}
    for item in load_json(CHIPS_PATH).get("results", []):
        add_candidate(candidates, item, "chips")
    rtt = load_json(RIGHT_TOP_TRACK_PATH)
    for item in rtt.get("active", []):
        add_candidate(candidates, item, "price_breakout_track")
    for item in load_json(VOLUME_SIGNAL_PATH).get("results", []):
        add_candidate(candidates, item, "volume_signal")
    return candidates


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("date").copy()
    out["ema5"] = out["close"].ewm(span=5, adjust=False).mean()
    out["ema20"] = out["close"].ewm(span=20, adjust=False).mean()
    out["vol10"] = out["volume_lots"].shift(1).rolling(10).mean()
    out["vol_ratio10"] = out["volume_lots"] / out["vol10"]
    return out


def classify_pullback(df: pd.DataFrame) -> dict | None:
    if len(df) < 30:
        return None
    df = add_indicators(df)
    recent = df.tail(IGNITION_LOOKBACK_DAYS)
    ignition_rows = recent[
        (recent["vol_ratio10"] >= IGNITION_VOL_RATIO_MIN)
        & ((recent["close"] >= recent["ema5"]) | (recent["close"] >= recent["ema20"]))
    ]
    if ignition_rows.empty:
        return None

    ignition = ignition_rows.iloc[-1]
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest
    days_since = int(len(df[df["date"] > ignition["date"]]))
    pullback_from_close = (latest["close"] / ignition["close"]) - 1 if ignition["close"] else 0

    support_ok = latest["close"] >= ignition["min"] and latest["close"] >= latest["ema20"]
    pullback_ok = pullback_from_close >= -PULLBACK_MAX_FROM_IGNITION_CLOSE
    volume_cools = latest["volume_lots"] < ignition["volume_lots"]
    reentry = days_since >= 1 and support_ok and (
        latest["max"] > prev["max"] or latest["vol_ratio10"] >= REENTRY_VOL_RATIO_MIN
    )
    failed = (
        latest["close"] < ignition["min"]
        or latest["close"] < latest["ema20"]
        or pullback_from_close < -FAIL_MAX_FROM_IGNITION_CLOSE
    )

    if failed:
        status = "failed"
        status_label = "失敗"
    elif days_since == 0:
        status = "ignition"
        status_label = "點火"
    elif reentry:
        status = "reentry"
        status_label = "再啟動"
    elif support_ok and pullback_ok and volume_cools:
        status = "pullback"
        status_label = "回穩觀察"
    else:
        status = "watch"
        status_label = "觀察"

    score = 50
    if status == "reentry":
        score += 35
    elif status == "pullback":
        score += 25
    elif status == "ignition":
        score += 15
    score += min(20, max(0, (float(ignition["vol_ratio10"]) - 2.5) * 6))
    if support_ok:
        score += 10
    if volume_cools and days_since >= 1:
        score += 8
    if failed:
        score -= 60

    return {
        "status": status,
        "status_label": status_label,
        "score": round(score),
        "signal_date": latest["date"].strftime("%Y-%m-%d"),
        "ignition_date": ignition["date"].strftime("%Y-%m-%d"),
        "days_since_ignition": days_since,
        "close": round(float(latest["close"]), 2),
        "high": round(float(latest["max"]), 2),
        "low": round(float(latest["min"]), 2),
        "volume_lots": int(latest["volume_lots"]),
        "vol_10d_avg": round(float(latest["vol10"]), 0) if pd.notna(latest["vol10"]) else None,
        "vol_ratio": round(float(latest["vol_ratio10"]), 2) if pd.notna(latest["vol_ratio10"]) else None,
        "ema5": round(float(latest["ema5"]), 2),
        "ema20": round(float(latest["ema20"]), 2),
        "ignition_close": round(float(ignition["close"]), 2),
        "ignition_high": round(float(ignition["max"]), 2),
        "ignition_low": round(float(ignition["min"]), 2),
        "ignition_volume_lots": int(ignition["volume_lots"]),
        "ignition_vol_ratio": round(float(ignition["vol_ratio10"]), 2),
        "pullback_from_ignition_close_pct": round(pullback_from_close * 100, 2),
        "support_ok": bool(support_ok),
        "volume_cools": bool(volume_cools),
    }


def main() -> int:
    print("=== 量增回測模型 ===")
    candidates = load_candidates()
    print(f"候選來源合併：{len(candidates)} 檔")

    price_cache = load_price_cache()
    if price_cache is None or price_cache.empty:
        print("price_cache.parquet 不存在或為空")
        return 1
    price_cache["date"] = pd.to_datetime(price_cache["date"])

    active, failed = [], []
    for sid, item in candidates.items():
        df = get_stock_price_from_cache(price_cache, sid, START_DATE, TODAY)
        if df is None or df.empty:
            continue
        signal = classify_pullback(df)
        if not signal:
            continue
        row = {**item, **signal}
        if signal["status"] == "failed":
            failed.append(row)
        else:
            active.append(row)

    active.sort(key=lambda r: (r["status"] != "reentry", r["status"] != "pullback", -r["score"]))
    failed.sort(key=lambda r: r["score"], reverse=True)

    output = {
        "strategy_id": "volume_pullback",
        "updated": now_tw(),
        "model": {
            "ignition_vol_ratio_min": IGNITION_VOL_RATIO_MIN,
            "lookback_days": IGNITION_LOOKBACK_DAYS,
            "pullback_max_pct": PULLBACK_MAX_FROM_IGNITION_CLOSE * 100,
            "reentry_vol_ratio_min": REENTRY_VOL_RATIO_MIN,
        },
        "summary": {
            "active": len(active),
            "failed": len(failed),
            "reentry": sum(1 for r in active if r["status"] == "reentry"),
            "pullback": sum(1 for r in active if r["status"] == "pullback"),
            "ignition": sum(1 for r in active if r["status"] == "ignition"),
        },
        "active": active,
        "failed": failed,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"完成：active={len(active)} failed={len(failed)} -> {OUTPUT_PATH}")
    for row in active[:10]:
        print(f"  {row['stock_id']} {row['name']} {row['status_label']} score={row['score']} ignition={row['ignition_vol_ratio']}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
