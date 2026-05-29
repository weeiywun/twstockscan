#!/usr/bin/env python3
"""Track strategy-two trend candidates after volume confirmation."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from finmind_client import load_price_cache, get_stock_price_from_cache

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
POOL_PATH = os.path.join(DATA_DIR, "momentum_candidates.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "trend_follow.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")
OBSERVE_TRADING_DAYS = 10
HISTORY_KEEP_TRADING_DAYS = 5


def load_json(path: str) -> dict[str, Any]:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: str, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def add_trading_days(start: date, n: int) -> date:
    d, added = start, 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def trading_days_remaining(expire: date, today: date) -> int:
    if today > expire:
        return 0
    d, count = today, 0
    while d <= expire:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def keep_history_item(item: dict[str, Any], today: date) -> bool:
    if item.get("pinned"):
        return True
    remove_date = item.get("remove_date")
    return bool(remove_date) and date.fromisoformat(remove_date) >= today


def normalize_history_retention(items: list[dict[str, Any]], today: date) -> None:
    keep_until = add_trading_days(today, HISTORY_KEEP_TRADING_DAYS).isoformat()
    for item in items:
        if item.get("pinned"):
            continue
        remove_date = item.get("remove_date")
        if not remove_date or date.fromisoformat(remove_date) > date.fromisoformat(keep_until):
            item["remove_date"] = keep_until


def fetch_close(stock_id: str, price_cache: Any) -> float | None:
    if price_cache is None:
        return None
    start = (datetime.now(TW_TZ) - timedelta(days=7)).strftime("%Y-%m-%d")
    df = get_stock_price_from_cache(price_cache, stock_id, start)
    if df is None or df.empty:
        return None
    return round(float(df.sort_values("date").iloc[-1]["close"]), 2)


def trigger_rows(pool: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in pool.get("trend_results", []) or []:
        if row.get("pool_type") == "trend" and row.get("volume_alert"):
            rows.append(row)
    return rows


def new_entry(row: dict[str, Any], today: date) -> dict[str, Any]:
    expire = add_trading_days(today, OBSERVE_TRADING_DAYS)
    metrics = row.get("metrics") or {}
    return {
        "stock_id": row.get("stock_id"),
        "name": row.get("name", ""),
        "industry": row.get("industry", ""),
        "market": row.get("market", ""),
        "trigger_date": today.isoformat(),
        "expire_date": expire.isoformat(),
        "days_remaining": trading_days_remaining(expire, today),
        "entry_price": row.get("close"),
        "current_price": row.get("close"),
        "pnl_pct": 0.0,
        "volume_alert": True,
        "vol_ratio": metrics.get("today_vol_ratio"),
        "pattern_locked_at": row.get("pattern_locked_at"),
        "pattern_state": row.get("pattern_state"),
        "pattern_score": row.get("pattern_score"),
        "pattern_tags": row.get("pattern_tags", []),
        "patterns": row.get("patterns", []),
        "key_level": row.get("key_level"),
        "invalidation": row.get("invalidation"),
        "pattern_confidence": row.get("pattern_confidence"),
        "pinned": False,
    }


def update_price_fields(item: dict[str, Any], price_cache: Any) -> None:
    price = fetch_close(str(item.get("stock_id") or ""), price_cache)
    if price is None:
        return
    item["current_price"] = price
    entry_price = item.get("entry_price") or price
    item["pnl_pct"] = round((price - entry_price) / entry_price * 100, 2) if entry_price else 0.0


def main() -> int:
    pool = load_json(POOL_PATH)
    data = load_json(OUTPUT_PATH)
    today = date.fromisoformat(TODAY)
    price_cache = load_price_cache()

    active = data.get("active", [])
    expired = data.get("expired", [])
    active_ids = {str(item.get("stock_id")) for item in active}
    tracked_ids = active_ids | {str(item.get("stock_id")) for item in expired if item.get("pinned")}

    new_rows = [row for row in trigger_rows(pool) if str(row.get("stock_id")) not in tracked_ids]
    for row in new_rows:
        active.append(new_entry(row, today))

    still_active: list[dict[str, Any]] = []
    newly_expired: list[dict[str, Any]] = []
    for item in active:
        expire = date.fromisoformat(item["expire_date"])
        item["days_remaining"] = trading_days_remaining(expire, today)
        update_price_fields(item, price_cache)
        if item["days_remaining"] <= 0:
            newly_expired.append({
                **item,
                "entry_date": item.get("trigger_date", item.get("entry_date", "")),
                "remove_date": add_trading_days(today, HISTORY_KEEP_TRADING_DAYS).isoformat(),
                "pinned": bool(item.get("pinned", False)),
            })
        else:
            still_active.append(item)

    expired.extend(newly_expired)
    normalize_history_retention(expired, today)
    expired = [item for item in expired if keep_history_item(item, today)]
    for item in expired:
        update_price_fields(item, price_cache)

    out = {
        "strategy_id": "trend_follow",
        "last_updated": TODAY,
        "model": {
            "source": "momentum_candidates.trend_results",
            "trigger": "pool_type=trend and volume_alert=true",
            "observe_trading_days": OBSERVE_TRADING_DAYS,
            "history_keep_trading_days": HISTORY_KEEP_TRADING_DAYS,
            "pattern_score": "locked from first stock-pool entry",
        },
        "active": still_active,
        "expired": expired,
    }
    save_json(OUTPUT_PATH, out)
    print(f"trend_follow: active={len(still_active)} expired={len(expired)} new={len(new_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
