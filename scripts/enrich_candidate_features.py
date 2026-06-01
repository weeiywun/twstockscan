#!/usr/bin/env python3
"""Build a shared feature layer for every candidate stock.

This script does not select stocks. It collects stock ids already surfaced by
strategy outputs, then enriches them from local data/cache files so the scoring
model can evaluate every candidate with a comparable feature set.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "candidate_features.json")
PRICE_CACHE_PATH = os.path.join(DATA_DIR, "price_cache.parquet")
TW_TZ = timezone(timedelta(hours=8))

SOURCE_FILES: list[tuple[str, list[str], str]] = [
    ("ai_analysis.json", ["active", "expired"], "stock_analysis"),
    ("chips_big_holder.json", ["results"], "chips"),
    ("big_holder_trend.json", ["results"], "big_holder_trend"),
    ("right_top.json", ["results"], "right_top"),
    ("right_top_track.json", ["active", "expired"], "right_top_track"),
    ("volume_signal.json", ["results"], "volume_signal"),
    ("volume_pullback.json", ["active", "failed", "history"], "volume_pullback"),
    ("momentum_candidates.json", ["focus_results", "results"], "momentum_candidates"),
    ("performance.json", ["positions"], "holding"),
]

FIELD_PRIORITY = {
    "name",
    "industry",
    "market",
    "close",
    "entry_date",
    "entry_close",
    "latest_price_date",
    "latest_close",
    "since_entry_pct",
    "current_price",
    "ema5",
    "ema20",
    "ema60",
    "ema120",
    "big_pct_1000",
    "big_pct_400",
    "chg_1w_1000",
    "chg_1w_400",
    "chg_4w_1000",
    "chg_4w_400",
    "cumulative_3w",
    "cumulative_3w_400",
    "tag_score",
    "consecutive_weeks",
    "market_cap",
    "bbw",
    "week_chg_pct",
    "vol_5d_avg",
    "vol_10d_avg",
    "vol_20d_avg",
    "vol_today",
    "volume_lots",
    "vol_ratio",
    "today_vol_ratio",
    "ignition_vol_ratio",
    "track_vol_ratio",
    "price_vol_ratio",
    "daily_vol_ratio",
    "price_bias_ema20",
    "price_bias_ema120",
    "ma_distance_pct",
    "risk_to_support_pct",
    "pullback_from_high_pct",
    "pullback_from_ignition_close_pct",
    "fib_zone",
    "support_ok",
    "volume_cools",
    "volume_cooldown_pct",
    "max_gain_60d",
    "pullback_from_60d_high_pct",
    "ema60_slope_5d",
    "ema120_slope_5d",
    "ema200_slope_5d",
    "status",
    "status_label",
    "pnl_pct",
    "track_pnl_pct",
    "entry_price",
    "days_remaining",
    "is_consolidation_breakout",
    "is_momentum_breakout",
    "is_price_breakout",
    "daily_breakout_60d",
    "price_breakout_60d",
}


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def load_json(filename: str) -> dict[str, Any]:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict[str, Any]) -> None:
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sid_of(row: dict[str, Any]) -> str:
    return str(row.get("stock_id") or row.get("ticker") or "").strip()


def num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def round_or_none(value: Any, digits: int = 2) -> float | None:
    n = num(value)
    return None if n is None else round(n, digits)


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def ensure(features: dict[str, dict[str, Any]], sid: str) -> dict[str, Any]:
    if sid not in features:
        features[sid] = {
            "stock_id": sid,
            "name": "",
            "industry": "",
            "market": "",
            "sources": [],
            "tags": [],
            "source_rows": [],
        }
    return features[sid]


def merge_feature(base: dict[str, Any], row: dict[str, Any], source: str) -> None:
    if source not in base["sources"]:
        base["sources"].append(source)
    base["source_rows"].append(source)

    metrics = row.get("metrics") or {}
    merged = {**metrics, **row}
    for key in FIELD_PRIORITY:
        value = merged.get(key)
        if value in (None, ""):
            continue
        if key in ("name", "industry", "market"):
            if not base.get(key):
                base[key] = value
        else:
            base[key] = value

    for tag in (row.get("tags") or []) + (row.get("source_tags") or []):
        if tag and tag not in base["tags"]:
            base["tags"].append(tag)


def collect_candidates() -> dict[str, dict[str, Any]]:
    features: dict[str, dict[str, Any]] = {}
    for filename, keys, source in SOURCE_FILES:
        data = load_json(filename)
        for key in keys:
            rows = data.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sid = sid_of(row)
                if not sid:
                    continue
                merge_feature(ensure(features, sid), row, source)
    for row in features.values():
        row["sources"] = sorted(set(row["sources"]))
        row["source_rows"] = sorted(set(row["source_rows"]))
    return features


def add_price_features(features: dict[str, dict[str, Any]]) -> str | None:
    if not os.path.exists(PRICE_CACHE_PATH) or not features:
        return None

    df = pd.read_parquet(PRICE_CACHE_PATH)
    if df.empty:
        return None
    df["stock_id"] = df["stock_id"].astype(str)
    df = df[df["stock_id"].isin(features.keys())].sort_values(["stock_id", "date"])
    latest_date = None

    for sid, hist in df.groupby("stock_id"):
        hist = hist.tail(140).copy()
        if hist.empty:
            continue
        close = hist["close"]
        volume = hist["volume_lots"]
        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else None

        f = features[sid]
        latest_date = max(str(last["date"])[:10], latest_date or str(last["date"])[:10])
        f["price_date"] = str(last["date"])[:10]
        f["close"] = round_or_none(last["close"], 2)
        f["current_price"] = f["close"]
        f["prev_close"] = round_or_none(prev["close"], 2) if prev is not None else None
        if f["prev_close"]:
            f["change_pct"] = round((f["close"] - f["prev_close"]) / f["prev_close"] * 100, 2)
        for span in (5, 20, 60, 120):
            if len(hist) >= min(span, 5):
                f[f"ema{span}"] = round_or_none(close.ewm(span=span, adjust=False).mean().iloc[-1], 2)
        for window in (5, 10, 20):
            if len(hist) >= window:
                f[f"vol_{window}d_avg"] = round_or_none(volume.tail(window).mean(), 0)
        f["vol_today"] = int(last["volume_lots"])
        f["volume_lots"] = int(last["volume_lots"])
        if f.get("vol_20d_avg"):
            f["vol_ratio"] = round(f["volume_lots"] / f["vol_20d_avg"], 2)
            f["today_vol_ratio"] = f["vol_ratio"]
            f["daily_vol_ratio"] = f["vol_ratio"]
        if f.get("vol_5d_avg") and f.get("vol_20d_avg"):
            f["price_vol_ratio"] = round(f["vol_5d_avg"] / f["vol_20d_avg"], 2)
        if f.get("ema20"):
            f["price_bias_ema20"] = round((f["close"] - f["ema20"]) / f["ema20"] * 100, 2)
        if f.get("ema120"):
            f["price_bias_ema120"] = round((f["close"] - f["ema120"]) / f["ema120"] * 100, 2)
        if len(hist) >= 60:
            f["high_60d"] = round_or_none(hist["max"].tail(60).max(), 2)
            f["price_breakout_60d"] = bool(f["close"] >= f["high_60d"])
            f["daily_breakout_60d"] = f["price_breakout_60d"]
        if len(hist) >= 20:
            base = float(close.iloc[-20])
            if base:
                f["week_chg_pct"] = round((f["close"] - base) / base * 100, 2)
    return latest_date


def main() -> int:
    features = collect_candidates()
    price_date = add_price_features(features)
    rows = sorted(features.values(), key=lambda row: row["stock_id"])
    output = {
        "strategy_id": "candidate_features",
        "updated": now_tw(),
        "source": "local_json_and_price_cache",
        "price_date": price_date,
        "summary": {
            "total": len(rows),
            "with_price": sum(1 for row in rows if row.get("close") is not None),
            "with_chips": sum(1 for row in rows if row.get("big_pct_1000") is not None),
        },
        "results": rows,
    }
    save_json(output)
    print(f"[candidate-features] {len(rows)} stocks / price_date={price_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
