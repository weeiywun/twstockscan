#!/usr/bin/env python3
"""Update latest close and performance for the fixed big-holder trend pool."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
POOL_PATH = os.path.join(DATA_DIR, "big_holder_trend.json")
PRICE_CACHE_PATH = os.path.join(DATA_DIR, "price_cache.parquet")
TW_TZ = timezone(timedelta(hours=8))


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def load_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def close_on_or_before(hist: pd.DataFrame, date_text: str | None) -> tuple[str, float] | None:
    if hist.empty:
        return None
    if date_text:
        target = pd.to_datetime(date_text)
        subset = hist[hist["date"] <= target]
        if subset.empty:
            return None
        row = subset.iloc[-1]
    else:
        row = hist.iloc[-1]
    return str(row["date"])[:10], float(row["close"])


def update_pool(entry_date: str | None = None) -> dict[str, Any]:
    data = load_json(POOL_PATH)
    rows = data.get("results") or []
    if not rows:
        return data
    if not os.path.exists(PRICE_CACHE_PATH):
        raise FileNotFoundError(f"Missing price cache: {PRICE_CACHE_PATH}")

    price_df = pd.read_parquet(PRICE_CACHE_PATH)
    price_df["stock_id_norm"] = price_df["stock_id"].astype(str).str.zfill(4)
    price_df["date"] = pd.to_datetime(price_df["date"])

    updated = 0
    latest_dates: list[str] = []
    for row in rows:
        stock_id = str(row.get("stock_id") or "").zfill(4)
        hist = price_df[price_df["stock_id_norm"] == stock_id].sort_values("date")
        if hist.empty:
            continue

        if entry_date:
            entry = close_on_or_before(hist, entry_date)
            if entry:
                row["entry_date"], row["entry_close"] = entry[0], round(entry[1], 2)
        elif row.get("entry_close") is None:
            row["entry_date"] = row.get("price_date") or row.get("source_date") or data.get("source_date")
            row["entry_close"] = row.get("close")

        latest = close_on_or_before(hist, None)
        if not latest:
            continue
        latest_date, latest_close = latest
        row["latest_price_date"] = latest_date
        row["latest_close"] = round(latest_close, 2)
        row["close"] = round(latest_close, 2)
        entry_close = row.get("entry_close")
        if entry_close:
            row["since_entry_pct"] = round((latest_close - float(entry_close)) / float(entry_close) * 100.0, 2)
        latest_dates.append(latest_date)
        updated += 1

    data["price_updated"] = max(latest_dates) if latest_dates else data.get("price_updated")
    data["performance_updated"] = now_tw()
    data["updated_rows"] = updated
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry-date", help="Set/rebuild entry_close from the close on or before this date.")
    args = parser.parse_args()
    data = update_pool(args.entry_date)
    save_json(POOL_PATH, data)
    print(f"[big-holder-trend-prices] updated {data.get('updated_rows', 0)} rows")
    if args.entry_date:
        print(f"[big-holder-trend-prices] entry date rebuilt from {args.entry_date}")
    print(f"[big-holder-trend-prices] latest price date: {data.get('price_updated')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
