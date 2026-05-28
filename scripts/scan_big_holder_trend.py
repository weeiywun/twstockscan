#!/usr/bin/env python3
"""Scan the big-holder trend pool.

This model is intentionally looser than chips_big_holder:
- no EMA120 deviation cap
- no BBW cap
- only keeps liquid names with short-term price strength
- excludes stocks that already doubled within the latest 60 trading days
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

import fetch_holdings_twsthr as holdings

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
CSV_1000 = os.path.join(DATA_DIR, "big1000.csv")
CSV_400 = os.path.join(DATA_DIR, "big400.csv")
PRICE_CACHE_PATH = os.path.join(DATA_DIR, "price_cache.parquet")
OUTPUT_PATH = os.path.join(DATA_DIR, "big_holder_trend.json")

TW_TZ = timezone(timedelta(hours=8))

BIG_PCT_MIN = 30.0
VOL20_MIN_LOTS = 500
MAX_GAIN_60D = 100.0


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def ema(series: pd.Series, span: int) -> pd.Series:
    return pd.Series(series, dtype="float64").ewm(span=span, adjust=False).mean()


def recent_values(pct_map: dict[str, float], date_cols: list[str], n: int) -> list[tuple[str, float]]:
    values = [(d, pct_map[d]) for d in date_cols if d in pct_map]
    return values[-n:]


def four_week_up(pct_map: dict[str, float], date_cols: list[str]) -> bool:
    values = recent_values(pct_map, date_cols, 5)
    if len(values) < 5:
        return False
    nums = [value for _, value in values]
    return all(nums[i] > nums[i - 1] for i in range(1, len(nums)))


def single_week_surge(pct_map: dict[str, float], date_cols: list[str]) -> bool:
    ratio = holdings.calc_r(pct_map, date_cols, 0)
    return ratio is not None and ratio > 3.0


def trend_labels(
    up4_1000: bool,
    up4_400: bool,
    surge_1000: bool,
    surge_400: bool,
) -> list[str]:
    labels: list[str] = []
    if up4_1000:
        labels.append("千張4週連增")
    if up4_400:
        labels.append("400張4週連增")
    if surge_1000:
        labels.append("千張單週激增")
    if surge_400:
        labels.append("400張單週激增")
    return labels


def price_features(price_df: pd.DataFrame, stock_id: str) -> dict[str, Any] | None:
    hist = price_df[price_df["stock_id_norm"] == stock_id].sort_values("date").reset_index(drop=True)
    if len(hist) < 80:
        return None

    close = hist["close"].astype(float)
    volume = hist["volume_lots"].astype(float)
    ema5 = ema(close, 5)
    ema60 = ema(close, 60)
    ema120 = ema(close, 120)
    ema200 = ema(close, 200)

    close_now = float(close.iloc[-1])
    high60 = float(close.tail(60).max())
    low60 = float(close.tail(60).min())
    vol20 = float(volume.tail(20).mean())

    if low60 <= 0 or high60 <= 0:
        return None

    slope_ok = (
        ema60.iloc[-1] > ema60.iloc[-6]
        and ema120.iloc[-1] > ema120.iloc[-6]
        and ema200.iloc[-1] > ema200.iloc[-6]
    )
    max_gain_60d = (high60 - low60) / low60 * 100.0
    week_ago = float(close.iloc[-6]) if len(close) >= 6 else float(close.iloc[0])

    return {
        "price_date": str(hist["date"].iloc[-1])[:10],
        "close": round(close_now, 2),
        "ema5": round(float(ema5.iloc[-1]), 2),
        "ema60": round(float(ema60.iloc[-1]), 2),
        "ema120": round(float(ema120.iloc[-1]), 2),
        "ema200": round(float(ema200.iloc[-1]), 2),
        "ema60_slope_5d": round((float(ema60.iloc[-1]) - float(ema60.iloc[-6])) / float(ema60.iloc[-6]) * 100, 2),
        "ema120_slope_5d": round((float(ema120.iloc[-1]) - float(ema120.iloc[-6])) / float(ema120.iloc[-6]) * 100, 2),
        "ema200_slope_5d": round((float(ema200.iloc[-1]) - float(ema200.iloc[-6])) / float(ema200.iloc[-6]) * 100, 2),
        "high_60d": round(high60, 2),
        "low_60d": round(low60, 2),
        "max_gain_60d": round(max_gain_60d, 2),
        "pullback_from_60d_high_pct": round((close_now - high60) / high60 * 100.0, 2),
        "vol_20d_avg": int(round(vol20, 0)),
        "week_chg_pct": round((close_now - week_ago) / week_ago * 100.0, 2) if week_ago else None,
        "price_filter_pass": (
            vol20 > VOL20_MIN_LOTS
            and close_now > float(ema5.iloc[-1])
            and slope_ok
            and max_gain_60d <= MAX_GAIN_60D
        ),
    }


def build_results() -> dict[str, Any]:
    if not os.path.exists(PRICE_CACHE_PATH):
        raise FileNotFoundError(f"Missing price cache: {PRICE_CACHE_PATH}")

    stocks_1000, dates_1000 = holdings.parse_csv(CSV_1000, "utf-8-sig")
    stocks_400, dates_400 = holdings.parse_csv(CSV_400, "utf-8-sig")
    price_df = pd.read_parquet(PRICE_CACHE_PATH)
    price_df["stock_id_norm"] = price_df["stock_id"].astype(str).str.zfill(4)

    results: list[dict[str, Any]] = []
    counts = {
        "big_pct_gt_30": 0,
        "chip_signal": 0,
        "trend_pool_before_gain_cap": 0,
        "results": 0,
    }

    for stock_id, stock_1000 in stocks_1000.items():
        pct_map_1000 = stock_1000.get("pct_map") or {}
        if not pct_map_1000:
            continue
        latest_pct = pct_map_1000.get(max(pct_map_1000))
        if latest_pct is None or latest_pct <= BIG_PCT_MIN:
            continue
        counts["big_pct_gt_30"] += 1

        stock_400 = stocks_400.get(stock_id)
        pct_map_400 = stock_400.get("pct_map") if stock_400 else None
        up4_1000 = four_week_up(pct_map_1000, dates_1000)
        up4_400 = four_week_up(pct_map_400, dates_400) if pct_map_400 else False
        surge_1000 = single_week_surge(pct_map_1000, dates_1000)
        surge_400 = single_week_surge(pct_map_400, dates_400) if pct_map_400 else False

        if not (up4_1000 or up4_400 or surge_1000 or surge_400):
            continue
        counts["chip_signal"] += 1

        price = price_features(price_df, stock_id)
        if price is None:
            continue
        if (
            price["vol_20d_avg"] > VOL20_MIN_LOTS
            and price["close"] > price["ema5"]
            and price["ema60_slope_5d"] > 0
            and price["ema120_slope_5d"] > 0
            and price["ema200_slope_5d"] > 0
        ):
            counts["trend_pool_before_gain_cap"] += 1
        if not price["price_filter_pass"]:
            continue

        recent_1000 = recent_values(pct_map_1000, dates_1000, 4)
        recent_400 = recent_values(pct_map_400, dates_400, 4) if pct_map_400 else []
        labels = trend_labels(up4_1000, up4_400, surge_1000, surge_400)
        r1w_1000 = holdings.calc_r(pct_map_1000, dates_1000, 0)
        r1w_400 = holdings.calc_r(pct_map_400, dates_400, 0) if pct_map_400 else None

        results.append({
            "stock_id": stock_id,
            "name": stock_1000.get("name"),
            "industry": stock_1000.get("industry"),
            "market_cap": stock_1000.get("market_cap"),
            "big_pct_1000": round(float(latest_pct), 2),
            "big_pct_400": round(float(pct_map_400.get(max(pct_map_400))), 2) if pct_map_400 else None,
            "chg_1w_1000": round(float(r1w_1000), 2) if r1w_1000 is not None else None,
            "chg_1w_400": round(float(r1w_400), 2) if r1w_400 is not None else None,
            "big_trend_1000": [round(v, 2) for _, v in recent_1000],
            "big_trend_400": [round(v, 2) for _, v in recent_400],
            "date_labels": [f"{d[4:6]}/{d[6:8]}" for d, _ in recent_1000],
            "tags": labels,
            "sources": ["big_holder_trend"],
            **price,
        })

    results.sort(
        key=lambda row: (
            max(row.get("chg_1w_1000") or -999, row.get("chg_1w_400") or -999),
            row.get("max_gain_60d") or 0,
            row.get("big_pct_1000") or 0,
        ),
        reverse=True,
    )
    counts["results"] = len(results)

    return {
        "strategy_id": "big_holder_trend",
        "updated": now_tw(),
        "source_date": results[0]["price_date"] if results else None,
        "criteria": {
            "big_pct_1000_gt": BIG_PCT_MIN,
            "chip_signal": "千張或400張連續4週增加，或千張/400張本週增加超過3%",
            "vol_20d_avg_gt": VOL20_MIN_LOTS,
            "close_gt": "EMA5",
            "long_ema_slope": "EMA60/EMA120/EMA200 最近5日上揚",
            "max_gain_60d_lte": MAX_GAIN_60D,
        },
        "counts": counts,
        "results": results,
    }


def main() -> int:
    data = build_results()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[big-holder-trend] wrote {len(data['results'])} rows -> {OUTPUT_PATH}")
    print(f"[big-holder-trend] counts: {data['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
