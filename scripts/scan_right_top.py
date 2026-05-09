#!/usr/bin/env python3
"""
突破策略掃描器

同一個 right_top.json 內保留兩種突破訊號：
1. 盤整突破：原本「右上角」週線邏輯，要求突破前不要已經大漲。
2. 動能突破：日線多頭排列、整理後突破 60 日高、量能放大且乖離不過熱。
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from finmind_client import get_stock_price_from_cache, load_price_cache

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "right_top.json")
STOCK_LIST_PATH = os.path.join(DATA_DIR, "stock_list_cache.json")
CSV_1000 = os.path.join(DATA_DIR, "big1000.csv")
CSV_400 = os.path.join(DATA_DIR, "big400.csv")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")

LOOKBACK_DAYS = 210

WEEK_HIGH_PERIOD = 10
WEEK_VOL_MA_PERIOD = 20
WEEK_VOL_MULT = 1.5
WEEK_MIN_VOL_LOTS = 500
WEEK_BASE_RANGE_MAX = 0.20
WEEK_MA_SLOPE_MAX = 5.0

MOMENTUM_HIGH_DAYS = 60
MOMENTUM_VOL_DAYS = 5
MOMENTUM_VOL_MULT = 1.5
MOMENTUM_BIAS_MAX = 0.10
CONSOLIDATE_DAYS = 10
CONSOLIDATE_BIAS = 0.03


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    df = df.set_index("date").sort_index()
    weekly = df.resample("W-FRI").agg(
        open=("open", "first"),
        max=("max", "max"),
        min=("min", "min"),
        close=("close", "last"),
        volume_lots=("volume_lots", "sum"),
    ).dropna(subset=["close"])
    return weekly.reset_index()


def _require_fresh_cache(price_cache: pd.DataFrame) -> None:
    latest = price_cache["date"].max().strftime("%Y-%m-%d")
    if latest != TODAY:
        print(f"price_cache.parquet 最新資料為 {latest}，不是 {TODAY}；停止掃描，避免舊資料產生訊號")
        sys.exit(1)


def weekly_metrics(wk: pd.DataFrame) -> dict | None:
    min_weeks = max(WEEK_HIGH_PERIOD, WEEK_VOL_MA_PERIOD) + 1
    if len(wk) < min_weeks:
        return None

    closes = wk["close"].tolist()
    volumes = wk["volume_lots"].tolist()

    close_latest = closes[-1]
    high_prev10 = max(closes[-WEEK_HIGH_PERIOD - 1:-1])
    vol_latest = volumes[-1]
    vol_20w_avg = sum(volumes[-WEEK_VOL_MA_PERIOD - 1:-1]) / WEEK_VOL_MA_PERIOD
    prev_close = closes[-2] if len(closes) >= 2 else close_latest
    change_pct = round((close_latest - prev_close) / prev_close * 100, 2) if prev_close else 0
    latest_week_date = wk.iloc[-1]["date"].strftime("%Y-%m-%d")

    return {
        "close": round(close_latest, 2),
        "high_10w": round(high_prev10, 2),
        "vol_latest_w": int(vol_latest),
        "vol_20w_avg": round(vol_20w_avg, 1),
        "vol_ratio": round(vol_latest / vol_20w_avg, 2) if vol_20w_avg else None,
        "change_pct": change_pct,
        "week_date": latest_week_date,
    }


def check_consolidation_breakout(wk: pd.DataFrame) -> dict | None:
    metrics = weekly_metrics(wk)
    if not metrics:
        return None

    closes = wk["close"].tolist()
    close_latest = closes[-1]
    high_prev10 = metrics["high_10w"]

    if close_latest <= high_prev10:
        return None

    if len(closes) >= 14:
        for i in range(2, 5):
            if closes[-i] > max(closes[-i - WEEK_HIGH_PERIOD:-i]):
                return None

    base_closes = closes[-WEEK_HIGH_PERIOD - 1:-1]
    base_low = min(base_closes)
    base_high = max(base_closes)
    if base_low == 0 or (base_high - base_low) / base_low >= WEEK_BASE_RANGE_MAX:
        return None

    if len(closes) >= 15:
        ma_now = sum(closes[-11:-1]) / 10
        ma_prev = sum(closes[-15:-5]) / 10
        if ma_prev > 0 and (ma_now - ma_prev) / ma_prev * 100 >= WEEK_MA_SLOPE_MAX:
            return None

    if metrics["vol_20w_avg"] < WEEK_MIN_VOL_LOTS:
        return None
    if metrics["vol_latest_w"] < metrics["vol_20w_avg"] * WEEK_VOL_MULT:
        return None

    return metrics


def check_momentum_breakout(daily: pd.DataFrame) -> dict | None:
    if daily is None or len(daily) < MOMENTUM_HIGH_DAYS + 1:
        return None

    df = daily.sort_values("date").reset_index(drop=True).copy()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["bias_ma20"] = (df["close"] - df["ma20"]) / df["ma20"]
    df["prev_60d_high"] = df["close"].shift(1).rolling(MOMENTUM_HIGH_DAYS).max()
    df["prior_bias_abs_avg10"] = df["bias_ma20"].abs().shift(1).rolling(CONSOLIDATE_DAYS).mean()
    df["prior_vol_5d_avg"] = df["volume_lots"].shift(1).rolling(MOMENTUM_VOL_DAYS).mean()

    latest = df.iloc[-1]
    required = ["ma20", "ma60", "bias_ma20", "prev_60d_high", "prior_bias_abs_avg10", "prior_vol_5d_avg"]
    if any(pd.isna(latest[col]) for col in required):
        return None

    close = float(latest["close"])
    ma20 = float(latest["ma20"])
    ma60 = float(latest["ma60"])
    bias = float(latest["bias_ma20"])
    prev_high = float(latest["prev_60d_high"])
    vol_today = float(latest["volume_lots"])
    vol_5d_avg = float(latest["prior_vol_5d_avg"])
    vol_ratio = vol_today / vol_5d_avg if vol_5d_avg else 0

    is_uptrend = close > ma20 > ma60
    is_consolidating = float(latest["prior_bias_abs_avg10"]) < CONSOLIDATE_BIAS
    is_breakout = close > prev_high
    is_volume = vol_ratio >= MOMENTUM_VOL_MULT
    is_low_bias = bias < MOMENTUM_BIAS_MAX

    if not (is_uptrend and is_consolidating and is_breakout and is_volume and is_low_bias):
        return None

    return {
        "daily_uptrend": True,
        "daily_consolidating": True,
        "daily_breakout_60d": True,
        "daily_low_bias": True,
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "bias_ma20": round(bias * 100, 2),
        "high_60d": round(prev_high, 2),
        "daily_vol_today": int(vol_today),
        "daily_vol_5d_avg": round(vol_5d_avg, 1),
        "daily_vol_ratio": round(vol_ratio, 2),
    }


def _parse_whale_csv(path: str) -> tuple[dict[str, dict[str, float]], list[str]]:
    if not os.path.exists(path):
        return {}, []

    stocks: dict[str, dict[str, float]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        date_cols = sorted([h for h in headers if re.fullmatch(r"\d{8}", h)])
        first_header = headers[0] if headers else ""
        for row in reader:
            raw = (row.get("股票") or row.get(first_header, "") or "").strip()
            parts = raw.split(None, 1)
            if len(parts) < 1 or not re.fullmatch(r"\d{4}", parts[0]):
                continue
            pct_map = {}
            for date_col in date_cols:
                try:
                    pct_map[date_col] = float((row.get(date_col) or "").strip())
                except ValueError:
                    pass
            stocks[parts[0]] = pct_map
    return stocks, date_cols


def _last_values(pct_map: dict[str, float], date_cols: list[str], n: int = 4) -> list[float]:
    valid = [date_col for date_col in date_cols if date_col in pct_map]
    return [pct_map[date_col] for date_col in valid[-n:]]


def _is_strictly_up(values: list[float]) -> bool:
    return len(values) >= 4 and all(values[i] > values[i - 1] for i in range(1, len(values)))


def load_whale_map() -> dict[str, dict]:
    stocks_1000, dates_1000 = _parse_whale_csv(CSV_1000)
    stocks_400, dates_400 = _parse_whale_csv(CSV_400)
    whale_map = {}

    for sid in set(stocks_1000) | set(stocks_400):
        v1000 = _last_values(stocks_1000.get(sid, {}), dates_1000)
        v400 = _last_values(stocks_400.get(sid, {}), dates_400)
        whale_map[sid] = {
            "whale_3w_up": _is_strictly_up(v1000),
            "whale_400_3w_up": _is_strictly_up(v400),
            "big_pct_1000": round(v1000[-1], 2) if v1000 else None,
            "big_pct_400": round(v400[-1], 2) if v400 else None,
            "big_1000_chg_3w": round(v1000[-1] - v1000[0], 2) if len(v1000) >= 4 else None,
            "big_400_chg_3w": round(v400[-1] - v400[0], 2) if len(v400) >= 4 else None,
        }
    return whale_map


def build_signal_tags(base_signal: dict | None, momentum_signal: dict | None, whale: dict) -> tuple[list[str], int, list[str]]:
    tags = []
    signal_types = []
    score = 0

    if base_signal:
        tags.append("盤整突破")
        signal_types.append("consolidation")
        score += 50
    if momentum_signal:
        tags.extend(["動能突破", "日線啟動", "低乖離"])
        signal_types.append("momentum")
        score += 45
    if base_signal and momentum_signal:
        tags.append("雙重符合")
        score += 20
    if whale.get("whale_3w_up"):
        tags.append("千張大戶連增")
        score += 12
    if whale.get("whale_400_3w_up"):
        tags.append("400張同步")
        score += 6
    if base_signal and (base_signal.get("vol_ratio") or 0) >= 2:
        tags.append("週量強放大")
        score += 5
    if momentum_signal and (momentum_signal.get("daily_vol_ratio") or 0) >= 2:
        tags.append("日量強放大")
        score += 5

    return list(dict.fromkeys(tags)), min(score, 100), signal_types


def _merge_industries(value: str, industry: str) -> str:
    parts = [p.strip() for p in (value or "").split(" / ") if p.strip()]
    if industry and industry not in parts:
        parts.append(industry)
    return " / ".join(parts)


def _industry_list(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(" / ") if p.strip()]


def dedupe_stocks(stocks: list[dict]) -> list[dict]:
    stock_map = {}
    for stock in stocks:
        sid = stock["stock_id"]
        if sid not in stock_map:
            stock_map[sid] = {**stock}
            continue
        existing = stock_map[sid]
        existing["industry"] = _merge_industries(existing.get("industry", ""), stock.get("industry", ""))
        if not existing.get("market") and stock.get("market"):
            existing["market"] = stock["market"]
        if not existing.get("name") and stock.get("name"):
            existing["name"] = stock["name"]
    return list(stock_map.values())


def _write_output(results: list[dict], industry_stats: list[dict]) -> None:
    output = {
        "strategy_id": "right_top",
        "updated": now_tw(),
        "results": results,
        "industry_stats": industry_stats,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


def build_industry_stats(results: list[dict]) -> list[dict]:
    industry_map = {}
    for row in results:
        for industry in _industry_list(row.get("industry", "")) or ["其他"]:
            if industry not in industry_map:
                industry_map[industry] = {"industry": industry, "count": 0, "stocks": []}
            industry_map[industry]["count"] += 1
            industry_map[industry]["stocks"].append({"stock_id": row["stock_id"], "name": row["name"]})
    return sorted(industry_map.values(), key=lambda x: x["count"], reverse=True)


def main() -> None:
    print("=== 突破策略掃描器：盤整突破 + 動能突破 ===")
    allow_stale = "--allow-stale" in sys.argv

    if not os.path.exists(STOCK_LIST_PATH):
        print("stock_list_cache.json 不存在，請先執行 update_price_cache.py")
        _write_output([], [])
        return

    with open(STOCK_LIST_PATH, encoding="utf-8") as f:
        stocks = dedupe_stocks(json.load(f))
    print(f"股票清單：{len(stocks)} 檔")

    price_cache = load_price_cache()
    if price_cache is None or price_cache.empty:
        print("price_cache.parquet 不存在或為空，請先執行 update_price_cache.py")
        _write_output([], [])
        return

    if allow_stale:
        signal_date = price_cache["date"].max().strftime("%Y-%m-%d")
        print(f"--allow-stale：使用快取最新交易日 {signal_date} 作為訊號日期")
    else:
        _require_fresh_cache(price_cache)
        signal_date = TODAY

    print(f"價格快取：{len(price_cache):,} 筆，{price_cache['stock_id'].nunique()} 檔")

    whale_map = load_whale_map()
    start_date = (datetime.now(TW_TZ) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    results = []
    skipped = 0
    for i, stock in enumerate(stocks, 1):
        sid = stock["stock_id"]
        daily = get_stock_price_from_cache(price_cache, sid, start_date)
        if daily is None or len(daily) < MOMENTUM_HIGH_DAYS + 1:
            skipped += 1
            continue

        weekly = _to_weekly(daily)
        weekly_context = weekly_metrics(weekly)
        base_signal = check_consolidation_breakout(weekly)
        momentum_signal = check_momentum_breakout(daily)

        if base_signal or momentum_signal:
            whale = whale_map.get(sid, {})
            tags, quality_score, signal_types = build_signal_tags(base_signal, momentum_signal, whale)
            signal_payload = {
                **(weekly_context or {}),
                **(base_signal or {}),
                **(momentum_signal or {}),
            }
            results.append({
                "stock_id": sid,
                "name": stock["name"],
                "industry": stock.get("industry", ""),
                "market": stock.get("market", ""),
                "is_consolidation_breakout": bool(base_signal),
                "is_momentum_breakout": bool(momentum_signal),
                "signal_types": signal_types,
                "tags": tags,
                "quality_score": quality_score,
                **whale,
                **signal_payload,
                "signal_date": signal_date,
            })
            print(f"  {sid} {stock['name']} types={'+'.join(signal_types)} score={quality_score}")

        if i % 200 == 0:
            print(f"掃描進度：{i}/{len(stocks)}，命中 {len(results)}，快取缺漏 {skipped}")

    results.sort(key=lambda row: (row.get("quality_score") or 0, row.get("vol_ratio") or 0), reverse=True)
    industry_stats = build_industry_stats(results)

    print(f"完成：命中 {len(results)} 檔，快取缺漏 {skipped} 檔")
    _write_output(results, industry_stats)


if __name__ == "__main__":
    main()
