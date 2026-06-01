#!/usr/bin/env python3
"""Build the daily stock pool with pattern score as the only score.

The pool keeps only current strategy inputs:
- low-base big-holder pool (chips_big_holder)
- trend big-holder pool (big_holder_trend)
- low-base volume signal (volume_signal)

No legacy context score, source bonus, priority score, AI score, or breakout
tracking score is used here. Rows enter from strategy membership, then receive
one pattern score from pattern_detect.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from finmind_client import get_stock_price_from_cache, load_price_cache
import pattern_detect

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")

CHIPS_PATH = os.path.join(DATA_DIR, "chips_big_holder.json")
BIG_HOLDER_TREND_PATH = os.path.join(DATA_DIR, "big_holder_trend.json")
VOLUME_SIGNAL_PATH = os.path.join(DATA_DIR, "volume_signal.json")
CURRENT_PRICES_PATH = os.path.join(DATA_DIR, "current_prices.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "momentum_candidates.json")

TW_TZ = timezone(timedelta(hours=8))
PRICE_LOOKBACK_DAYS = 220
WATCH_STATE = "值得看圖"


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


def ensure_row(rows: dict[str, dict[str, Any]], stock_id: str, name: str = "") -> dict[str, Any]:
    sid = str(stock_id or "").strip()
    if sid not in rows:
        rows[sid] = {
            "stock_id": sid,
            "name": name,
            "industry": "",
            "market": "",
            "close": None,
            "sources": [],
            "tags": [],
            "metrics": {},
        }
    if name and not rows[sid]["name"]:
        rows[sid]["name"] = name
    return rows[sid]


def add_source(row: dict[str, Any], item: dict[str, Any], source: str) -> None:
    row["name"] = row.get("name") or item.get("name", "")
    row["industry"] = row.get("industry") or item.get("industry", "")
    row["market"] = row.get("market") or item.get("market", "")
    row["close"] = (
        item.get("current_price")
        or item.get("latest_close")
        or item.get("close")
        or row.get("close")
    )
    if source not in row["sources"]:
        row["sources"].append(source)
    for tag in item.get("tags", []) or item.get("source_tags", []) or []:
        if tag not in row["tags"]:
            row["tags"].append(tag)


def merge_metric(row: dict[str, Any], key: str, value: Any, digits: int = 2) -> None:
    value = round_or_none(value, digits)
    if value is not None:
        row["metrics"][key] = value


def add_chips(rows: dict[str, dict[str, Any]]) -> None:
    for item in load_json(CHIPS_PATH).get("results", []) or []:
        sid = str(item.get("stock_id") or "")
        if not sid:
            continue
        row = ensure_row(rows, sid, item.get("name", ""))
        add_source(row, item, "chips")
        for key in (
            "market_cap",
            "bbw",
            "week_chg_pct",
            "big_pct_1000",
            "big_pct_400",
            "deviation",
            "vol_20d_avg",
        ):
            merge_metric(row, key, item.get(key), 1 if key in ("market_cap", "vol_20d_avg") else 2)


def add_big_holder_trend(rows: dict[str, dict[str, Any]]) -> None:
    for item in load_json(BIG_HOLDER_TREND_PATH).get("results", []) or []:
        sid = str(item.get("stock_id") or "")
        if not sid:
            continue
        row = ensure_row(rows, sid, item.get("name", ""))
        add_source(row, item, "big_holder_trend")
        for key in (
            "week_chg_pct",
            "big_pct_1000",
            "big_pct_400",
            "max_gain_60d",
            "pullback_from_60d_high_pct",
            "vol_20d_avg",
            "since_entry_pct",
        ):
            merge_metric(row, key, item.get(key), 1 if key == "vol_20d_avg" else 2)


def add_volume_signal(rows: dict[str, dict[str, Any]]) -> None:
    for item in load_json(VOLUME_SIGNAL_PATH).get("results", []) or []:
        sid = str(item.get("stock_id") or "")
        if not sid:
            continue
        row = ensure_row(rows, sid, item.get("name", ""))
        add_source(row, item, "volume_signal")
        merge_metric(row, "today_vol_ratio", item.get("vol_ratio"))
        merge_metric(row, "vol_today", item.get("vol_today"), 0)
        merge_metric(row, "vol_10d_avg", item.get("vol_10d_avg"), 0)


def apply_pattern(row: dict[str, Any], cache: Any, start_date: str) -> None:
    result = None
    sid = row["stock_id"]
    if cache is not None:
        df = get_stock_price_from_cache(cache, sid, start_date)
        if df is not None:
            tags = set(row.get("tags", []))
            result = pattern_detect.analyze(
                df,
                stock_id=sid,
                big_trend_up=bool({"chips", "big_holder_trend"} & set(row.get("sources", []))),
                inst_buying=any("外資" in str(tag) or "投信" in str(tag) for tag in tags),
                source_count=len(row.get("sources", [])) or 1,
            )

    if result:
        row.update(result.as_dict())
        return

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


def scan() -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    prices = load_json(CURRENT_PRICES_PATH).get("prices", {})

    add_chips(rows)
    add_big_holder_trend(rows)
    add_volume_signal(rows)

    cache = load_price_cache()
    start_date = (date.today() - timedelta(days=PRICE_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    candidates = []
    for sid, row in rows.items():
        row["close"] = row.get("close") or prices.get(sid)
        row["source_count"] = len(row.get("sources", []))
        apply_pattern(row, cache, start_date)
        row["focus_candidate"] = row.get("pattern_state") == WATCH_STATE
        candidates.append(row)

    candidates.sort(key=lambda row: (
        pattern_detect.STATE_ORDER.get(row.get("pattern_state", "先觀察"), 9),
        -num(row.get("pattern_score")),
        -num(row.get("source_count")),
        str(row.get("stock_id") or ""),
    ))
    focus_results = [row for row in candidates if row.get("focus_candidate")]

    return {
        "strategy_id": "momentum_candidates",
        "updated": now_tw(),
        "model": {
            "version": "pattern_score_only_v1",
            "sources": ["chips_big_holder", "big_holder_trend", "volume_signal"],
            "score_field": "pattern_score",
            "focus_rule": "pattern_state == 值得看圖",
        },
        "summary": {
            "total": len(candidates),
            "focus": len(focus_results),
            "pattern_watch": sum(1 for r in candidates if r.get("pattern_state") == "值得看圖"),
            "pattern_observe": sum(1 for r in candidates if r.get("pattern_state") == "先觀察"),
            "pattern_extended": sum(1 for r in candidates if r.get("pattern_state") == "太遠不追"),
            "pattern_broken": sum(1 for r in candidates if r.get("pattern_state") == "型態破壞"),
        },
        "focus_results": focus_results,
        "results": candidates,
    }


def main() -> int:
    output = scan()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")
    summary = output["summary"]
    print(
        "pattern-only stock pool: "
        f"{summary['total']} total / {summary['pattern_watch']} watch"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
