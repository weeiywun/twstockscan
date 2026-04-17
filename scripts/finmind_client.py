#!/usr/bin/env python3
"""
FinMind API 共用工具模組
供 scan_ema_tangling.py 和 scan_volume_breakout.py 共用。

使用前請設定環境變數：
  export FINMIND_API_TOKEN=your_token_here
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"

# 致命錯誤旗標（401 / 402）—— 觸發後中止所有後續請求
_abort_event = threading.Event()


def fetch_stock_prices(stock_id, start_date, end_date, token, max_retries=2):
    """
    從 FinMind TaiwanStockPrice 取得單支股票日線資料。

    回傳 DataFrame(index=DatetimeIndex, columns=[Open, High, Low, Close, Volume])
    無資料或失敗時回傳 None。
    致命錯誤（401 / 402）會設定 _abort_event 並立即回傳 None。
    """
    if _abort_event.is_set():
        return None

    params = {
        "dataset":    "TaiwanStockPrice",
        "data_id":    stock_id,
        "start_date": start_date,
        "end_date":   end_date,
        "token":      token,
    }

    for attempt in range(max_retries + 1):
        try:
            resp    = requests.get(FINMIND_API_URL, params=params, timeout=30)
            payload = resp.json()
            status  = payload.get("status", 0)

            # ── 致命錯誤：中止所有後續請求 ──
            if status == 401:
                _abort_event.set()
                print("\n[FinMind] 致命錯誤：API Token 無效（401），"
                      "請確認 FINMIND_API_TOKEN 環境變數")
                return None

            if status == 402:
                _abort_event.set()
                print("\n[FinMind] 致命錯誤：超出每日 API 請求限制（402），"
                      "請明日再試或升級 FinMind 方案")
                return None

            # ── 無資料（正常，如新上市或休市）──
            if status != 200 or not payload.get("data"):
                return None

            # ── 整理 DataFrame ──
            df = pd.DataFrame(payload["data"])
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            df = df.rename(columns={
                "open":           "Open",
                "max":            "High",
                "min":            "Low",
                "close":          "Close",
                "Trading_Volume": "Volume",
            })
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["Close", "Volume"])
            df.set_index("date", inplace=True)
            return df[["Open", "High", "Low", "Close", "Volume"]]

        except Exception:
            if attempt < max_retries and not _abort_event.is_set():
                time.sleep(3 * (attempt + 1))

    return None


def fetch_all_stocks(stock_list, start_date, end_date, token,
                     max_workers=8, req_interval=0.15):
    """
    並發下載全市場股票的歷史 OHLCV 日線資料。

    Parameters
    ----------
    stock_list   : list[dict]，每個元素包含 stock_id / name / market
    start_date   : str，格式 "YYYY-MM-DD"
    end_date     : str，格式 "YYYY-MM-DD"
    token        : str，FinMind API Token
    max_workers  : int，最大並行請求數（預設 8）
    req_interval : float，每次請求最小間隔秒數，避免打爆 FinMind（預設 0.15s ≈ 6~7 req/s）

    Returns
    -------
    dict[str, pd.DataFrame]：{stock_id: DataFrame}
    """
    _abort_event.clear()

    results   = {}
    lock      = threading.Lock()
    rate_lock = threading.Lock()
    counter   = {"done": 0, "ok": 0}
    last_call = [0.0]
    total     = len(stock_list)

    def fetch_one(s):
        if _abort_event.is_set():
            return

        # ── 速率限制：確保請求間隔 ≥ req_interval ──
        with rate_lock:
            gap = req_interval - (time.time() - last_call[0])
            if gap > 0:
                time.sleep(gap)
            last_call[0] = time.time()

        df = fetch_stock_prices(s["stock_id"], start_date, end_date, token)

        with lock:
            counter["done"] += 1
            if df is not None:
                results[s["stock_id"]] = df
                counter["ok"] += 1
            if counter["done"] % 100 == 0:
                print(f"  進度：{counter['done']:>4} / {total}，"
                      f"成功 {counter['ok']} 支", flush=True)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(fetch_one, stock_list))

    if _abort_event.is_set():
        print(f"  下載中止（致命錯誤），已取得 {counter['ok']} 支資料")
    else:
        print(f"  完成：{counter['ok']} / {total} 支資料下載成功")

    return results
