#!/usr/bin/env python3
"""
投信動能掃描器

用既有 price_cache 取得交易日與價量，再查 TWSE/TPEx 官方盤後投信買賣超。
避免逐檔打 FinMind，降低共享 API 配額壓力。
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from finmind_client import load_price_cache

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "trust_momentum.json")
STOCK_LIST_PATH = os.path.join(DATA_DIR, "stock_list_cache.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")

PRICE_LOOKBACK_DAYS = 80
OFFICIAL_LOOKBACK_TRADING_DAYS = 12
SIGNAL_TRADING_DAYS = 10
MAX_RESULTS = 80
MIN_AVG_VOL_20D = 500
MIN_TRUST_VOL_RATIO_5D = 0.08
MAX_PRICE_CHG_5D = 25.0
MAX_BIAS_MA20 = 18.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,*/*",
}


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _write_output(results: list[dict], industry_stats: list[dict], source_date: str = "") -> None:
    output = {
        "strategy_id": "trust_momentum",
        "updated": now_tw(),
        "source_date": source_date,
        "results": results,
        "industry_stats": industry_stats,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}，投信動能 {len(results)} 檔")


def _preserve_existing_output(source_date: str) -> None:
    if os.path.exists(OUTPUT_PATH):
        print(f"官方法人資料暫時無法取得，保留既有 {OUTPUT_PATH}")
        return
    _write_output([], [], source_date)


def _require_fresh_cache(price_cache: pd.DataFrame) -> str:
    latest = price_cache["date"].max().strftime("%Y-%m-%d")
    if latest != TODAY:
        print(f"price_cache.parquet 最新資料為 {latest}，不是 {TODAY}；停止掃描，避免舊資料產生訊號")
        sys.exit(1)
    return latest


def _stock_map() -> dict[str, dict[str, str]]:
    if not os.path.exists(STOCK_LIST_PATH):
        return {}
    with open(STOCK_LIST_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    stocks: dict[str, dict[str, str]] = {}
    for item in raw:
        sid = str(item.get("stock_id") or "").strip()
        if not sid or sid in stocks:
            continue
        stocks[sid] = {
            "name": item.get("name", ""),
            "industry": item.get("industry", ""),
            "market": item.get("market", ""),
        }
    return stocks


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "").replace("--", "0").strip()
    if text in {"", "-", "X", "x"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _stock_id(value: Any) -> str:
    match = re.search(r"\d{4,6}", str(value or ""))
    return match.group(0) if match else ""


def _roc_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.year - 1911}/{dt.month:02d}/{dt.day:02d}"


def _price_slice(price_cache: pd.DataFrame, sid: str, start_date: str) -> pd.DataFrame:
    df = price_cache[price_cache["stock_id"].astype(str) == sid].copy()
    df = df[df["date"] >= pd.Timestamp(start_date)]
    return df.sort_values("date").reset_index(drop=True)


def _recent_trade_dates(price_cache: pd.DataFrame, limit: int) -> list[str]:
    dates = sorted({d.strftime("%Y-%m-%d") for d in price_cache["date"].dropna()})
    return dates[-limit:]


def fetch_twse_trust(date_str: str) -> dict[str, float]:
    ymd = date_str.replace("-", "")
    url = "https://www.twse.com.tw/fund/TWT44U"
    params = {"date": ymd, "response": "json"}
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=30)
        res.raise_for_status()
        payload = res.json()
    except Exception as exc:
        print(f"  [WARN] TWSE TWT44U {date_str} 取得失敗：{exc}")
        return {}

    rows = payload.get("data") or []
    fields = payload.get("fields") or []
    if not rows or not fields:
        return {}

    code_idx = _find_field(fields, ["證券代號", "代號"])
    net_idx = _find_field(fields, ["買賣超股數"])
    buy_idx = _find_field(fields, ["買進股數"])
    sell_idx = _find_field(fields, ["賣出股數"])
    if code_idx is None or (net_idx is None and (buy_idx is None or sell_idx is None)):
        print(f"  [WARN] TWSE TWT44U {date_str} 欄位格式不符")
        return {}

    result: dict[str, float] = {}
    for row in rows:
        sid = _stock_id(row[code_idx] if code_idx < len(row) else "")
        if not sid:
            continue
        if net_idx is not None and net_idx < len(row):
            net_shares = _num(row[net_idx])
        else:
            buy = _num(row[buy_idx]) if buy_idx is not None and buy_idx < len(row) else 0.0
            sell = _num(row[sell_idx]) if sell_idx is not None and sell_idx < len(row) else 0.0
            net_shares = buy - sell
        result[sid] = net_shares / 1000
    return result


def fetch_tpex_trust(date_str: str) -> dict[str, float]:
    combined: dict[str, float] = {}
    for trade_type in ("buy", "sell"):
        url = "https://www.tpex.org.tw/web/stock/3insti/sitc_trading/sitctr_result.php"
        params = {"d": _roc_date(date_str), "t": "D", "type": trade_type, "l": "zh-tw", "o": "json"}
        try:
            res = requests.get(url, params=params, headers=HEADERS, timeout=30)
            res.raise_for_status()
            payload = res.json()
        except Exception as exc:
            print(f"  [WARN] TPEx 投信 {date_str} {trade_type} 取得失敗：{exc}")
            continue

        for rows, fields in _tpex_tables(payload):
            code_idx = _find_field(fields, ["代號"]) if fields else 1
            net_idx = _find_field(fields, ["買賣超"]) if fields else 5
            if code_idx is None:
                code_idx = 1
            if net_idx is None:
                net_idx = 5

            for raw_row in rows:
                row = _row_values(raw_row)
                if len(row) <= max(code_idx, net_idx):
                    continue
                sid = _stock_id(row[code_idx])
                if not sid:
                    continue
                net_lots = _num(row[net_idx])
                if net_lots:
                    combined[sid] = net_lots
    return combined


def _row_values(row: Any) -> list[Any]:
    if isinstance(row, list):
        return row
    if isinstance(row, dict):
        value = row.get("value")
        if isinstance(value, list):
            return value
    return []


def _tpex_tables(payload: dict[str, Any]) -> list[tuple[list[Any], list[Any]]]:
    tables = payload.get("tables")
    if isinstance(tables, list):
        parsed = []
        for table in tables:
            if not isinstance(table, dict):
                continue
            rows = table.get("data")
            fields = table.get("fields") or []
            if not isinstance(rows, list):
                continue
            parsed.append((rows, fields))
        return parsed

    rows = payload.get("aaData") or payload.get("data")
    fields = payload.get("fields") or payload.get("aaDataTitle") or []
    if isinstance(rows, list):
        return [(rows, fields)]
    return []


def _find_field(fields: list[Any], keywords: list[str]) -> int | None:
    for idx, field in enumerate(fields):
        text = re.sub(r"\s+", "", str(field))
        if all(keyword in text for keyword in keywords):
            return idx
    return None


def fetch_official_trust_map(trade_dates: list[str]) -> dict[str, dict[str, float]]:
    by_stock_date: dict[str, dict[str, float]] = defaultdict(dict)
    for date_str in trade_dates:
        twse = fetch_twse_trust(date_str)
        tpex = fetch_tpex_trust(date_str)
        merged = {**twse, **tpex}
        print(f"官方投信買賣超 {date_str}：TWSE {len(twse):,} 檔 / TPEx {len(tpex):,} 檔")
        for sid, net_lots in merged.items():
            by_stock_date[sid][date_str] = net_lots
    return {sid: dict(date_map) for sid, date_map in by_stock_date.items()}


def _pct(a: float, b: float) -> float | None:
    if b == 0:
        return None
    return (a - b) / b * 100


def _score(row: dict) -> int:
    score = 0
    score += row["trust_buy_days_5d"] * 8
    score += max(row["trust_buy_days_10d"] - 5, 0) * 4
    score += min(max(row["trust_vol_ratio_5d"], 0) * 80, 24)
    score += min(max(row["trust_net_5d"], 0) / max(row["avg_vol_20d"], 1) * 4, 18)
    if row["price_chg_5d"] is not None and 0 <= row["price_chg_5d"] <= 12:
        score += 10
    if row["bias_ma20"] is not None and 0 <= row["bias_ma20"] <= 10:
        score += 8
    if row["is_new_20d_high"]:
        score += 6
    return min(round(score), 100)


def _tags(row: dict) -> list[str]:
    tags = ["投信動能"]
    if row["trust_buy_days_10d"] >= 8:
        tags.append("投信強連買")
    elif row["trust_buy_days_10d"] >= 6:
        tags.append("投信連買")
    if row["trust_vol_ratio_5d"] >= 0.20:
        tags.append("買超占量高")
    elif row["trust_vol_ratio_5d"] >= 0.10:
        tags.append("買超占量增")
    if row["is_new_20d_high"]:
        tags.append("20日新高")
    if row["bias_ma20"] is not None and row["bias_ma20"] <= 10:
        tags.append("低乖離")
    if row["price_chg_5d"] is not None and row["price_chg_5d"] >= 18:
        tags.append("短線偏熱")
    return tags


def build_industry_stats(results: list[dict]) -> list[dict]:
    industry_map: dict[str, dict] = {}
    for row in results:
        industry = row.get("industry") or "其他"
        if industry not in industry_map:
            industry_map[industry] = {"industry": industry, "count": 0, "stocks": []}
        industry_map[industry]["count"] += 1
        industry_map[industry]["stocks"].append({"stock_id": row["stock_id"], "name": row["name"]})
    return sorted(industry_map.values(), key=lambda x: x["count"], reverse=True)


def main() -> None:
    print("=== 投信動能掃描器 ===")
    allow_stale = "--allow-stale" in sys.argv

    stock_map = _stock_map()
    if not stock_map:
        print("stock_list_cache.json 不存在或為空")
        _write_output([], [])
        return

    price_cache = load_price_cache()
    if price_cache is None or price_cache.empty:
        print("price_cache.parquet 不存在或為空")
        _write_output([], [])
        return

    price_cache["date"] = pd.to_datetime(price_cache["date"])
    if allow_stale:
        signal_date = price_cache["date"].max().strftime("%Y-%m-%d")
        print(f"--allow-stale：使用快取最新交易日 {signal_date}")
    else:
        signal_date = _require_fresh_cache(price_cache)

    price_start_dt = price_cache["date"].max() - pd.Timedelta(days=PRICE_LOOKBACK_DAYS)
    price_start = price_start_dt.strftime("%Y-%m-%d")
    official_dates = _recent_trade_dates(price_cache, OFFICIAL_LOOKBACK_TRADING_DAYS)
    signal_dates = official_dates[-SIGNAL_TRADING_DAYS:]
    print(f"使用 price_cache 交易日：{signal_dates[0]} ~ {signal_dates[-1]}")

    trust_map = fetch_official_trust_map(official_dates)
    if not trust_map:
        print("沒有取得官方投信買賣超資料")
        _preserve_existing_output(signal_date)
        return

    results: list[dict] = []
    for sid, date_map in trust_map.items():
        meta = stock_map.get(sid)
        if not meta:
            continue
        daily = _price_slice(price_cache, sid, price_start)
        if len(daily) < 25:
            continue

        daily = daily.copy()
        daily["ma20"] = daily["close"].rolling(20).mean()
        latest = daily.iloc[-1]
        close = float(latest["close"])
        ma20 = None if pd.isna(latest["ma20"]) else float(latest["ma20"])
        avg_vol_20d = float(daily["volume_lots"].tail(20).mean())
        if avg_vol_20d < MIN_AVG_VOL_20D:
            continue

        trade_dates = [d.strftime("%Y-%m-%d") for d in daily["date"].tail(SIGNAL_TRADING_DAYS)]
        vals_10 = [float(date_map.get(d, 0)) for d in trade_dates]
        vals_5 = vals_10[-5:]
        trust_net_5d = sum(vals_5)
        trust_net_10d = sum(vals_10)
        trust_buy_days_5d = sum(1 for v in vals_5 if v > 0)
        trust_buy_days_10d = sum(1 for v in vals_10 if v > 0)
        trust_vol_ratio_5d = trust_net_5d / max(avg_vol_20d * 5, 1)

        price_5d_ago = float(daily.iloc[-6]["close"]) if len(daily) >= 6 else close
        price_chg_5d = _pct(close, price_5d_ago)
        bias_ma20 = _pct(close, ma20) if ma20 else None
        high_20d = float(daily["close"].tail(20).max())
        is_new_20d_high = close >= high_20d

        if trust_buy_days_5d < 3 and trust_buy_days_10d < 6:
            continue
        if trust_net_5d <= 0 or trust_net_10d <= 0:
            continue
        if trust_vol_ratio_5d < MIN_TRUST_VOL_RATIO_5D:
            continue
        if price_chg_5d is not None and price_chg_5d > MAX_PRICE_CHG_5D:
            continue
        if bias_ma20 is not None and bias_ma20 > MAX_BIAS_MA20:
            continue

        row = {
            "stock_id": sid,
            "name": meta.get("name", ""),
            "industry": meta.get("industry", ""),
            "market": meta.get("market", ""),
            "close": round(close, 2),
            "ma20": round(ma20, 2) if ma20 else None,
            "bias_ma20": round(bias_ma20, 2) if bias_ma20 is not None else None,
            "price_chg_5d": round(price_chg_5d, 2) if price_chg_5d is not None else None,
            "avg_vol_20d": round(avg_vol_20d, 1),
            "trust_net_5d": round(trust_net_5d, 1),
            "trust_net_10d": round(trust_net_10d, 1),
            "trust_buy_days_5d": trust_buy_days_5d,
            "trust_buy_days_10d": trust_buy_days_10d,
            "trust_vol_ratio_5d": round(trust_vol_ratio_5d, 3),
            "trust_series_10d": [{"date": d, "net": round(v, 1)} for d, v in zip(trade_dates, vals_10)],
            "is_new_20d_high": is_new_20d_high,
            "signal_date": signal_date,
        }
        row["quality_score"] = _score(row)
        row["tags"] = _tags(row)
        results.append(row)

    results.sort(
        key=lambda r: (
            r.get("quality_score", 0),
            r.get("trust_vol_ratio_5d", 0),
            r.get("trust_net_5d", 0),
        ),
        reverse=True,
    )
    results = results[:MAX_RESULTS]
    industry_stats = build_industry_stats(results)
    print(f"完成：投信動能命中 {len(results)} 檔")
    _write_output(results, industry_stats, signal_date)


if __name__ == "__main__":
    main()
