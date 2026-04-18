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
