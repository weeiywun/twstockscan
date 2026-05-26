#!/usr/bin/env python3
"""
動能回測模型

尋找已經被市場資金推升、但目前回測到 Fib / 均線共振區的標的。
這不是追高策略，而是提供「強者回頭」的人工複查清單。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from finmind_client import load_price_cache

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
STOCK_LIST_PATH = os.path.join(DATA_DIR, "stock_list_cache.json")
CHIPS_PATH = os.path.join(DATA_DIR, "chips_big_holder.json")
RIGHT_TOP_PATH = os.path.join(DATA_DIR, "right_top.json")
RIGHT_TOP_TRACK_PATH = os.path.join(DATA_DIR, "right_top_track.json")
VOLUME_SIGNAL_PATH = os.path.join(DATA_DIR, "volume_signal.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "momentum_pullback.json")

TW_TZ = timezone(timedelta(hours=8))

MIN_DAYS = 100
HIGH_LOOKBACK_DAYS = 60
LOW_LOOKBACK_BEFORE_HIGH = 50
RECENT_HIGH_MAX_AGE = 25
MIN_ADVANCE_PCT = 18.0
MIN_VOL20_LOTS = 300
MIN_PULLBACK_FROM_HIGH_PCT = 3.0
MAX_PULLBACK_FROM_HIGH_PCT = 28.0
FIB_MIN = 0.236
FIB_MAX = 0.618
NEAR_MA_PCT = 3.0
MAX_RESULTS = 40


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def load_json(path: str, fallback: Any) -> Any:
    if not os.path.exists(path):
        return fallback
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def round_or_none(value: Any, digits: int = 2) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def stock_meta() -> dict[str, dict[str, Any]]:
    rows = load_json(STOCK_LIST_PATH, [])
    return {
        str(row.get("stock_id")): {
            "name": row.get("name", ""),
            "industry": row.get("industry", ""),
            "market": row.get("market", ""),
        }
        for row in rows
        if row.get("stock_id")
    }


def source_maps() -> dict[str, dict[str, dict[str, Any]]]:
    chips = {
        str(row.get("stock_id")): row
        for row in load_json(CHIPS_PATH, {}).get("results", [])
        if row.get("stock_id")
    }
    right_top = {
        str(row.get("stock_id")): row
        for row in load_json(RIGHT_TOP_PATH, {}).get("results", [])
        if row.get("stock_id")
    }
    rtt = {
        str(row.get("stock_id")): row
        for row in load_json(RIGHT_TOP_TRACK_PATH, {}).get("active", [])
        if row.get("stock_id")
    }
    volume_signal = {
        str(row.get("stock_id")): row
        for row in load_json(VOLUME_SIGNAL_PATH, {}).get("results", [])
        if row.get("stock_id")
    }
    return {
        "chips": chips,
        "right_top": right_top,
        "right_top_track": rtt,
        "volume_signal": volume_signal,
    }


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("date").reset_index(drop=True).copy()
    out["ema5"] = out["close"].ewm(span=5, adjust=False).mean()
    out["ema10"] = out["close"].ewm(span=10, adjust=False).mean()
    out["ema20"] = out["close"].ewm(span=20, adjust=False).mean()
    out["ema60"] = out["close"].ewm(span=60, adjust=False).mean()
    out["ema120"] = out["close"].ewm(span=120, adjust=False).mean()
    out["vol20"] = out["volume_lots"].shift(1).rolling(20).mean()
    out["vol60"] = out["volume_lots"].shift(1).rolling(60).mean()
    return out


def fib_zone(depth: float) -> tuple[str, int]:
    if depth < 0.236:
        return "0-23.6%", 3
    if depth < 0.382:
        return "23.6%-38.2%", 1
    if depth < 0.5:
        return "38.2%-50%", 2
    if depth <= 0.618:
        return "50%-61.8%", 4
    return ">61.8%", 9


def nearest_ma(latest: pd.Series) -> tuple[str, float | None, float | None]:
    candidates: list[tuple[str, float, float]] = []
    close = float(latest["close"])
    for key, label in [("ema5", "EMA5"), ("ema10", "EMA10"), ("ema20", "EMA20"), ("ema60", "EMA60")]:
        value = float(latest[key])
        dist = (close / value - 1) * 100 if value else 999
        candidates.append((label, value, dist))
    label, value, dist = min(candidates, key=lambda x: abs(x[2]))
    return label, round(value, 2), round(dist, 2)


def support_label_and_price(latest: pd.Series, fib_levels: dict[str, float]) -> tuple[str, float]:
    close = float(latest["close"])
    supports = [
        ("EMA20", float(latest["ema20"])),
        ("EMA60", float(latest["ema60"])),
        ("Fib 38.2%", fib_levels["38.2"]),
        ("Fib 50%", fib_levels["50"]),
        ("Fib 61.8%", fib_levels["61.8"]),
    ]
    below = [(label, price) for label, price in supports if price <= close]
    if not below:
        label, price = min(supports, key=lambda x: abs(close - x[1]))
        return label, round(price, 2)
    label, price = max(below, key=lambda x: x[1])
    return label, round(price, 2)


def classify_reversal(df: pd.DataFrame) -> str:
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []
    if latest["close"] > latest["open"]:
        signals.append("收紅K")
    if latest["close"] > latest["ema5"]:
        signals.append("站回EMA5")
    if latest["close"] > prev["max"]:
        signals.append("突破昨日高")
    if not signals:
        return "等待轉強"
    return " / ".join(signals[:2])


def classify_stock(df: pd.DataFrame, sid: str, meta: dict[str, Any], maps: dict[str, dict[str, dict[str, Any]]]) -> dict | None:
    if df is None or len(df) < MIN_DAYS:
        return None
    df = add_indicators(df)
    latest = df.iloc[-1]
    if pd.isna(latest["ema120"]) or pd.isna(latest["vol20"]):
        return None

    close = float(latest["close"])
    ema20 = float(latest["ema20"])
    ema60 = float(latest["ema60"])
    ema120 = float(latest["ema120"])
    vol20 = float(latest["vol20"])
    if vol20 < MIN_VOL20_LOTS:
        return None
    if not (close > ema60 and ema20 > ema60 > ema120):
        return None

    recent = df.tail(HIGH_LOOKBACK_DAYS)
    high_idx = recent["max"].idxmax()
    high_row = df.loc[high_idx]
    high_age = int(len(df) - 1 - high_idx)
    if high_age > RECENT_HIGH_MAX_AGE:
        return None

    low_start = max(0, high_idx - LOW_LOOKBACK_BEFORE_HIGH)
    before_high = df.iloc[low_start:high_idx + 1]
    if before_high.empty:
        return None
    low_idx = before_high["min"].idxmin()
    low_row = df.loc[low_idx]
    swing_high = float(high_row["max"])
    swing_low = float(low_row["min"])
    if swing_low <= 0 or swing_high <= swing_low:
        return None

    advance_pct = (swing_high / swing_low - 1) * 100
    if advance_pct < MIN_ADVANCE_PCT:
        return None

    pullback_from_high_pct = (swing_high / close - 1) * 100
    if pullback_from_high_pct < MIN_PULLBACK_FROM_HIGH_PCT or pullback_from_high_pct > MAX_PULLBACK_FROM_HIGH_PCT:
        return None

    depth = (swing_high - close) / (swing_high - swing_low)
    if depth < FIB_MIN or depth > FIB_MAX:
        return None

    fib_levels = {
        "23.6": swing_high - (swing_high - swing_low) * 0.236,
        "38.2": swing_high - (swing_high - swing_low) * 0.382,
        "50": swing_high - (swing_high - swing_low) * 0.5,
        "61.8": swing_high - (swing_high - swing_low) * 0.618,
    }
    zone, zone_rank = fib_zone(depth)
    ma_label, ma_value, ma_distance_pct = nearest_ma(latest)
    if ma_distance_pct is None or abs(ma_distance_pct) > 8.0:
        return None

    attack_slice = df.iloc[int(low_idx):int(high_idx) + 1]
    attack_volume = float(attack_slice["volume_lots"].max()) if not attack_slice.empty else float(latest["volume_lots"])
    recent_vol3 = float(df.tail(3)["volume_lots"].mean())
    volume_cooldown_pct = max(0.0, (1 - recent_vol3 / attack_volume) * 100) if attack_volume else 0
    if volume_cooldown_pct < 20:
        return None

    support_label, support_price = support_label_and_price(latest, fib_levels)
    risk_to_support_pct = (close / support_price - 1) * 100 if support_price else None
    upside_to_high_pct = (swing_high / close - 1) * 100 if close else None
    if risk_to_support_pct is None or risk_to_support_pct > 12:
        return None

    sources = []
    tags = []
    for key, label in [
        ("chips", "籌碼集中"),
        ("right_top", "突破策略"),
        ("right_top_track", "標的追蹤"),
        ("volume_signal", "量增訊號"),
    ]:
        src = maps[key].get(sid)
        if src:
            sources.append(label)
            for tag in src.get("tags", []) or []:
                if tag not in tags:
                    tags.append(tag)

    score = 50
    score += {1: 18, 2: 14, 4: 6}.get(zone_rank, 0)
    if abs(ma_distance_pct) <= NEAR_MA_PCT:
        score += 14
    elif abs(ma_distance_pct) <= 5:
        score += 7
    score += min(12, volume_cooldown_pct / 5)
    score += min(10, max(0, upside_to_high_pct or 0) / 1.5)
    score -= min(18, max(0, risk_to_support_pct or 0) * 1.2)
    score += min(8, len(sources) * 2)
    if "籌碼集中" in sources:
        score += 4
    if "突破策略" in sources or "標的追蹤" in sources:
        score += 4

    return {
        "stock_id": sid,
        "name": meta.get("name", ""),
        "industry": meta.get("industry", ""),
        "market": meta.get("market", ""),
        "signal_date": latest["date"].strftime("%Y-%m-%d"),
        "score": round(score),
        "close": round(close, 2),
        "volume_lots": int(latest["volume_lots"]),
        "vol20": round(vol20, 0),
        "swing_low": round(swing_low, 2),
        "swing_low_date": low_row["date"].strftime("%Y-%m-%d"),
        "swing_high": round(swing_high, 2),
        "swing_high_date": high_row["date"].strftime("%Y-%m-%d"),
        "high_age_days": high_age,
        "advance_pct": round(advance_pct, 2),
        "pullback_from_high_pct": round(pullback_from_high_pct, 2),
        "fib_depth_pct": round(depth * 100, 1),
        "fib_zone": zone,
        "fib_levels": {k: round(v, 2) for k, v in fib_levels.items()},
        "ma_confluence": ma_label,
        "ma_value": ma_value,
        "ma_distance_pct": ma_distance_pct,
        "ema5": round(float(latest["ema5"]), 2),
        "ema10": round(float(latest["ema10"]), 2),
        "ema20": round(ema20, 2),
        "ema60": round(ema60, 2),
        "ema120": round(ema120, 2),
        "volume_cooldown_pct": round(volume_cooldown_pct, 1),
        "attack_volume_lots": int(attack_volume),
        "reversal_signal": classify_reversal(df),
        "defense_label": support_label,
        "defense_price": support_price,
        "risk_to_support_pct": round(risk_to_support_pct, 2),
        "upside_to_high_pct": round(upside_to_high_pct, 2),
        "sources": sources,
        "tags": tags[:6],
    }


def main() -> int:
    print("=== 動能回測模型 ===")
    price_cache = load_price_cache()
    if price_cache is None or price_cache.empty:
        print("price_cache.parquet 不存在或為空")
        return 1
    price_cache["date"] = pd.to_datetime(price_cache["date"])
    latest_date = price_cache["date"].max().strftime("%Y-%m-%d")
    meta_map = stock_meta()
    maps = source_maps()

    rows = []
    for sid, df in price_cache.groupby("stock_id"):
        sid = str(sid)
        row = classify_stock(df, sid, meta_map.get(sid, {}), maps)
        if row:
            rows.append(row)

    rows.sort(key=lambda r: (-r["score"], r["risk_to_support_pct"], -r["upside_to_high_pct"]))
    rows = rows[:MAX_RESULTS]
    output = {
        "strategy_id": "momentum_pullback",
        "updated": now_tw(),
        "source_date": latest_date,
        "model": {
            "high_lookback_days": HIGH_LOOKBACK_DAYS,
            "recent_high_max_age": RECENT_HIGH_MAX_AGE,
            "min_advance_pct": MIN_ADVANCE_PCT,
            "fib_range": "23.6%-61.8%",
            "min_vol20_lots": MIN_VOL20_LOTS,
            "near_ma_pct": NEAR_MA_PCT,
        },
        "summary": {
            "total": len(rows),
            "strong_zone": sum(1 for r in rows if r["fib_zone"] == "23.6%-38.2%"),
            "healthy_zone": sum(1 for r in rows if r["fib_zone"] == "38.2%-50%"),
            "deep_zone": sum(1 for r in rows if r["fib_zone"] == "50%-61.8%"),
        },
        "results": rows,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"完成：{len(rows)} 檔 -> {OUTPUT_PATH}")
    for row in rows[:12]:
        print(
            f"  {row['stock_id']} {row['name']} score={row['score']} "
            f"{row['fib_zone']} {row['ma_confluence']} {row['ma_distance_pct']}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
