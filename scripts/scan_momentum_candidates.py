#!/usr/bin/env python3
"""Build the daily stock pool from chip accumulation, then rank by pattern only."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from finmind_client import load_price_cache, get_stock_price_from_cache
import pattern_detect

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")

CHIPS_PATH = os.path.join(DATA_DIR, "chips_big_holder.json")
VOLUME_SIGNAL_PATH = os.path.join(DATA_DIR, "volume_signal.json")
CURRENT_PRICES_PATH = os.path.join(DATA_DIR, "current_prices.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "momentum_candidates.json")

TW_TZ = timezone(timedelta(hours=8))
PRICE_LOOKBACK_DAYS = 200
LOW_BASE_DEVIATION_MIN = 0.0
LOW_BASE_DEVIATION_MAX = 10.0


def load_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def round_or_none(value: Any, digits: int = 2) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def latest_ema_state(cache: Any, stock_id: str, start_date: str) -> dict[str, Any]:
    if cache is None:
        return {}
    df = get_stock_price_from_cache(cache, stock_id, start_date)
    if df is None or df.empty:
        return {}
    df = df.sort_values("date")
    close = df["close"]
    if len(close) < 60:
        return {}
    ema5 = close.ewm(span=5, adjust=False).mean().iloc[-1]
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema60 = close.ewm(span=60, adjust=False).mean().iloc[-1]
    return {
        "ema5": round_or_none(ema5, 2),
        "ema20": round_or_none(ema20, 2),
        "ema60": round_or_none(ema60, 2),
        "ema_bull": bool(ema5 > ema20 > ema60),
        "price_df": df,
    }


def volume_signal_map() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in load_json(VOLUME_SIGNAL_PATH).get("results", []):
        sid = str(item.get("stock_id") or "").strip()
        if sid:
            out[sid] = item
    return out


def load_pattern_registry() -> dict[str, dict[str, Any]]:
    data = load_json(OUTPUT_PATH)
    registry = data.get("pattern_registry")
    if isinstance(registry, dict):
        return registry
    out: dict[str, dict[str, Any]] = {}
    for row in data.get("results", []) or []:
        sid = str(row.get("stock_id") or "").strip()
        if sid and row.get("pattern_score") is not None:
            out[sid] = pattern_snapshot(row, row.get("pattern_locked_at") or row.get("updated"))
    return out


def pattern_snapshot(row: dict[str, Any], locked_at: str | None = None) -> dict[str, Any]:
    return {
        "pattern_locked_at": locked_at or now_tw(),
        "pattern_state": row.get("pattern_state", "先觀察"),
        "pattern_score": row.get("pattern_score", 0.0),
        "pattern_subs": row.get("pattern_subs", {}),
        "pattern_tags": row.get("pattern_tags", []),
        "patterns": row.get("patterns", []),
        "key_level": row.get("key_level"),
        "invalidation": row.get("invalidation"),
        "pattern_confidence": row.get("pattern_confidence", 1.0),
    }


def apply_locked_pattern(row: dict[str, Any], registry: dict[str, dict[str, Any]]) -> None:
    sid = row["stock_id"]
    latest = pattern_snapshot(row)
    row.update({f"latest_{k}": v for k, v in latest.items() if k != "pattern_locked_at"})
    if sid not in registry:
        registry[sid] = latest
    locked = registry[sid]
    row.update({
        "pattern_locked": True,
        "pattern_locked_at": locked.get("pattern_locked_at"),
        "pattern_state": locked.get("pattern_state", "先觀察"),
        "pattern_score": locked.get("pattern_score", 0.0),
        "pattern_subs": locked.get("pattern_subs", {}),
        "pattern_tags": locked.get("pattern_tags", []),
        "patterns": locked.get("patterns", []),
        "key_level": locked.get("key_level"),
        "invalidation": locked.get("invalidation"),
        "pattern_confidence": locked.get("pattern_confidence", 1.0),
    })


def base_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "stock_id": str(item.get("stock_id") or "").strip(),
        "name": item.get("name", ""),
        "industry": item.get("industry", ""),
        "market": item.get("market", ""),
        "close": item.get("current_price") or item.get("close"),
        "sources": ["chips"],
        "tags": item.get("tags", []) or [],
        "metrics": {
            "market_cap": round_or_none(item.get("market_cap"), 1),
            "deviation": round_or_none(item.get("deviation"), 2),
            "ema120": round_or_none(item.get("ema120"), 2),
            "bbw": round_or_none(item.get("bbw"), 2),
            "week_chg_pct": round_or_none(item.get("week_chg_pct"), 2),
            "big_pct_1000": round_or_none(item.get("big_pct_1000"), 2),
            "big_pct_400": round_or_none(item.get("big_pct_400"), 2),
        },
    }


def attach_volume_signal(row: dict[str, Any], signal: dict[str, Any] | None) -> None:
    if not signal:
        row["volume_alert"] = False
        return
    row["volume_alert"] = True
    if "volume_signal" not in row["sources"]:
        row["sources"].append("volume_signal")
    metrics = row["metrics"]
    metrics["today_vol_ratio"] = round_or_none(signal.get("vol_ratio"), 2)
    metrics["vol_today"] = signal.get("vol_today")
    metrics["vol_10d_avg"] = round_or_none(signal.get("vol_10d_avg"), 0)


def classify_pool(row: dict[str, Any], ema_state: dict[str, Any]) -> str | None:
    deviation = row.get("metrics", {}).get("deviation")
    if deviation is not None and LOW_BASE_DEVIATION_MIN <= deviation <= LOW_BASE_DEVIATION_MAX:
        return "low_base"
    if ema_state.get("ema_bull"):
        return "trend"
    return None


def apply_pattern(row: dict[str, Any], ema_state: dict[str, Any]) -> None:
    df = ema_state.get("price_df")
    if df is None:
        row.update({
            "pattern_state": "先觀察",
            "pattern_score": 0.0,
            "pattern_subs": {},
            "pattern_tags": [],
            "patterns": [],
            "key_level": None,
            "invalidation": None,
            "pattern_confidence": 1.0,
        })
        return
    result = pattern_detect.analyze(
        df,
        stock_id=row["stock_id"],
        track_pnl_pct=0,
        big_trend_up=False,
        inst_buying=False,
        source_count=1,
    )
    if result:
        row.update(result.as_dict())
    else:
        row.update({
            "pattern_state": "先觀察",
            "pattern_score": 0.0,
            "pattern_subs": {},
            "pattern_tags": [],
            "patterns": [],
            "key_level": None,
            "invalidation": None,
            "pattern_confidence": 1.0,
        })


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (
        pattern_detect.STATE_ORDER.get(r.get("pattern_state", "先觀察"), 9),
        -num(r.get("pattern_score")),
        0 if r.get("pool_type") == "low_base" else 1,
        0 if r.get("volume_alert") else 1,
        r.get("stock_id", ""),
    ))


def scan() -> dict[str, Any]:
    current_prices = load_json(CURRENT_PRICES_PATH).get("prices", {})
    signals = volume_signal_map()
    pattern_registry = load_pattern_registry()
    cache = load_price_cache()
    start_date = (date.today() - timedelta(days=PRICE_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    rows: list[dict[str, Any]] = []
    for item in load_json(CHIPS_PATH).get("results", []):
        sid = str(item.get("stock_id") or "").strip()
        if not sid:
            continue

        row = base_row(item)
        row["close"] = row.get("close") or current_prices.get(sid)
        ema_state = latest_ema_state(cache, sid, start_date)
        row["metrics"].update({
            "ema5": ema_state.get("ema5"),
            "ema20": ema_state.get("ema20"),
            "ema60": ema_state.get("ema60"),
            "ema_bull": ema_state.get("ema_bull", False),
        })

        pool_type = classify_pool(row, ema_state)
        if not pool_type:
            continue

        row["pool_type"] = pool_type
        row["pool_label"] = "低基期" if pool_type == "low_base" else "趨勢"
        attach_volume_signal(row, signals.get(sid))
        apply_pattern(row, ema_state)
        apply_locked_pattern(row, pattern_registry)
        row["focus_candidate"] = row.get("pattern_state") == "值得看圖"
        rows.append(row)

    rows = sort_rows(rows)
    focus_results = [row for row in rows if row.get("pattern_state") == "值得看圖"]
    low_base_results = [row for row in rows if row.get("pool_type") == "low_base"]
    trend_results = [row for row in rows if row.get("pool_type") == "trend"]

    return {
        "strategy_id": "momentum_candidates",
        "updated": now_tw(),
        "model": {
            "version": "pattern_only_chip_pool_v1",
            "ranking": ["pattern_state", "pattern_score"],
            "sources": ["chips_big_holder", "volume_signal"],
            "volume_signal_role": "alert_only",
            "low_base_rules": {
                "source": "chips_big_holder",
                "deviation_ema120_pct": [LOW_BASE_DEVIATION_MIN, LOW_BASE_DEVIATION_MAX],
            },
            "trend_rules": {
                "source": "chips_big_holder",
                "ema_bull": "EMA5 > EMA20 > EMA60",
            },
            "focus_rules": {
                "pattern_state": "值得看圖",
            },
        },
        "summary": {
            "total": len(rows),
            "focus": len(focus_results),
            "low_base": len(low_base_results),
            "trend": len(trend_results),
            "volume_alert": sum(1 for row in rows if row.get("volume_alert")),
            "pattern_watch": len(focus_results),
            "pattern_observe": sum(1 for row in rows if row.get("pattern_state") == "先觀察"),
            "pattern_extended": sum(1 for row in rows if row.get("pattern_state") == "太遠不追"),
            "pattern_broken": sum(1 for row in rows if row.get("pattern_state") == "型態破壞"),
        },
        "focus_results": focus_results,
        "low_base_results": low_base_results,
        "trend_results": trend_results,
        "pattern_registry": pattern_registry,
        "results": rows,
    }


def main() -> int:
    output = scan()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")
    s = output["summary"]
    print(
        "每日標的池："
        f"{s['total']} 檔 / 值得看圖 {s['focus']} / "
        f"低基期 {s['low_base']} / 趨勢 {s['trend']} / 量增提醒 {s['volume_alert']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
