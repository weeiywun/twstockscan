#!/usr/bin/env python3
"""
股價資料下載模組（FinMind API 版）
供 fetch_holdings_twsthr.py、scan_ema_tangling.py、scan_volume_breakout.py 共用。
"""

import os
import time

import pandas as pd
import requests

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"


def fetch_stock_price(stock_id: str, start_date: str, end_date: str, token: str) -> pd.DataFrame | None:
    """取得單支股票日線資料。回傳 DataFrame 或 None。"""
    try:
        r = requests.get(FINMIND_API, params={
            "dataset":    "TaiwanStockPrice",
            "data_id":    stock_id,
            "start_date": start_date,
            "end_date":   end_date,
            "token":      token,
        }, timeout=20)
        data = r.json()
        if data.get("status") != 200 or not data.get("data"):
            return None
        df = pd.DataFrame(data["data"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df["volume_lots"] = (df["Trading_Volume"] / 1000).round(0).astype(int)
        return df[["date", "open", "max", "min", "close", "volume_lots"]]
    except Exception:
        return None


def fetch_all_stocks(stock_list, start_date, end_date, token=None, sleep=0.35, **_kwargs):
    """
    批次下載全市場歷史 OHLCV 日線資料（FinMind API 版）。

    Parameters
    ----------
    stock_list : list[dict]  每個元素含 stock_id / name / market
    start_date : str  "YYYY-MM-DD"
    end_date   : str  "YYYY-MM-DD"
    token      : str  FinMind API token（優先，否則讀環境變數 FINMIND_TOKEN）

    Returns
    -------
    dict[str, pd.DataFrame]  {stock_id: DataFrame(date, open, max, min, close, volume_lots)}
    """
    if not token:
        token = os.environ.get("FINMIND_TOKEN", "")

    results = {}
    total = len(stock_list)

    for i, s in enumerate(stock_list, 1):
        sid = s["stock_id"]
        df = fetch_stock_price(sid, start_date, end_date, token)
        if df is not None and not df.empty:
            results[sid] = df
        if i % 100 == 0:
            print(f"  進度：{i}/{total}，成功 {len(results)} 支")
        time.sleep(sleep)

    print(f"  完成：{len(results)} / {total} 支")
    return results


def fetch_institutional(stock_id: str, start_date: str, token: str) -> dict | None:
    """
    取得個股三大法人買賣超（外資、投信）。
    回傳 {"foreign": [net_buy, ...], "trust": [net_buy, ...]} 日期升序，或 None。
    """
    try:
        r = requests.get(FINMIND_API, params={
            "dataset":    "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id":    stock_id,
            "start_date": start_date,
            "token":      token,
        }, timeout=20)
        data = r.json()
        if data.get("status") != 200 or not data.get("data"):
            return None
        rows = sorted(data["data"], key=lambda x: x["date"])
        foreign, trust = [], []
        for row in rows:
            name = row.get("name", "")
            net  = float(row.get("buy") or 0) - float(row.get("sell") or 0)
            if name in ("Foreign_Investor", "外資及陸資(不含外資自營商)") or "外資" in name:
                foreign.append(net)
            elif name in ("Investment_Trust", "投信") or "投信" in name:
                trust.append(net)
        return {"foreign": foreign, "trust": trust}
    except Exception:
        return None


def load_price_cache() -> "pd.DataFrame | None":
    """
    載入 price_cache.parquet。
    回傳 DataFrame（欄位：stock_id, date, open, max, min, close, volume_lots）或 None。
    """
    cache_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "price_cache.parquet"
    )
    if not os.path.exists(cache_path):
        return None
    return pd.read_parquet(cache_path)


def get_stock_price_from_cache(
    cache: "pd.DataFrame",
    stock_id: str,
    start_date: str,
    end_date: str | None = None,
) -> "pd.DataFrame | None":
    """
    從快取切出單支股票資料，格式與 fetch_stock_price 完全相同。
    回傳 DataFrame 或 None（快取內無該股）。
    """
    df = cache[cache["stock_id"] == stock_id]
    df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]
    df = df.sort_values("date").reset_index(drop=True)
    if df.empty:
        return None
    return df[["date", "open", "max", "min", "close", "volume_lots"]].copy()


def fetch_month_revenue(stock_id: str, token: str, months: int = 15) -> list[dict] | None:
    """
    取得個股月營收（近 months 個月）。
    回傳 [{"date": "YYYY-MM-01", "revenue": float}, ...] 按日期升序，或 None。
    """
    from datetime import date, timedelta
    start_date = (date.today().replace(day=1) - timedelta(days=months * 31)).strftime("%Y-%m-%d")
    try:
        r = requests.get(FINMIND_API, params={
            "dataset":    "TaiwanStockMonthRevenue",
            "data_id":    stock_id,
            "start_date": start_date,
            "token":      token,
        }, timeout=20)
        data = r.json()
        if data.get("status") != 200 or not data.get("data"):
            return None
        rows = sorted(data["data"], key=lambda x: x["date"])
        return [{"date": row["date"], "revenue": float(row["revenue"])} for row in rows]
    except Exception:
        return None


def fetch_price_bydate(start_date: str, end_date: str, token: str) -> pd.DataFrame | None:
    """
    全市場股價（bydate 模式，不指定 data_id）。
    建議每次日期範圍不超過 1 週（~8,500 筆），避免超出免費方案每日 row 配額。
    回傳 DataFrame(stock_id, date, open, max, min, close, volume_lots) 或 None。
    None 代表致命錯誤（401/402/網路失敗），空 DataFrame 代表該區間無資料。
    """
    for attempt in range(3):
        try:
            r = requests.get(FINMIND_API, params={
                "dataset":    "TaiwanStockPrice",
                "start_date": start_date,
                "end_date":   end_date,
                "token":      token,
            }, timeout=120)
            data = r.json()
            status = data.get("status", 0)
            if status == 401:
                print("[FinMind] Token 無效（401），請確認 FINMIND_TOKEN")
                return None
            if status == 402:
                print("[FinMind] 超出每日 API 配額（402）")
                return None
            if status != 200 or not data.get("data"):
                return pd.DataFrame()
            df = pd.DataFrame(data["data"])
            df["date"] = pd.to_datetime(df["date"])
            for col in ["open", "max", "min", "close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["volume_lots"] = (
                pd.to_numeric(df["Trading_Volume"], errors="coerce") / 1000
            ).round(0).fillna(0).astype(int)
            return df[["stock_id", "date", "open", "max", "min", "close", "volume_lots"]]
        except Exception as e:
            if attempt < 2:
                wait = 10 * (attempt + 1)
                print(f" 重試({attempt + 1}/2，等 {wait}s)...", end="", flush=True)
                time.sleep(wait)
    return None
