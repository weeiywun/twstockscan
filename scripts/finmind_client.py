#!/usr/bin/env python3
"""
FinMind API 共用工具模組
供 scan_ema_tangling.py 和 scan_volume_breakout.py 共用。

使用前請設定環境變數：
  export FINMIND_API_TOKEN=your_token_here

【資料抓取策略】
  使用「月份批次 + 全市場」方式：不指定 data_id，一次抓取該月份所有股票。
  ~7 次 API 呼叫取得 6~7 個月全市場資料，vs 逐支抓取需要 ~1900 次。
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import requests

FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"


def _next_month_start(dt):
    """回傳下個月 1 日的 datetime。"""
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1, day=1)
    return dt.replace(month=dt.month + 1, day=1)


def fetch_all_stocks(stock_list, start_date, end_date, token, **_kwargs):
    """
    下載全市場歷史 OHLCV 日線資料。

    內部以「月份批次、不指定 data_id」方式呼叫 FinMind，
    將原本 ~1900 次 per-stock 請求降至 ~7 次，大幅節省每日 API 配額。

    Parameters
    ----------
    stock_list : list[dict]，每個元素包含 stock_id / name / market
    start_date : str，格式 "YYYY-MM-DD"
    end_date   : str，格式 "YYYY-MM-DD"
    token      : str，FinMind API Token
    **_kwargs  : 舊介面相容參數（max_workers / req_interval），忽略

    Returns
    -------
    dict[str, pd.DataFrame]：{stock_id: DataFrame(index=date, cols=[Open,High,Low,Close,Volume])}
    """
    # 僅保留需要的 stock_id 集合，用於最後過濾
    needed_ids = {s["stock_id"] for s in stock_list}

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")

    all_rows = []

    # ── 按月份逐批下載 ──
    current = start_dt.replace(day=1)   # 從該月 1 日起
    total_months = 0
    while current <= end_dt:
        total_months += 1
        current = _next_month_start(current)
    current = start_dt.replace(day=1)
    month_idx = 0

    while current <= end_dt:
        period_end = min(_next_month_start(current) - timedelta(days=1), end_dt)
        month_idx += 1
        label = current.strftime("%Y-%m")
        print(f"  [{month_idx}/{total_months}] 下載 {label} 全市場資料...",
              end="", flush=True)

        success = False
        for attempt in range(3):
            try:
                resp = requests.get(
                    FINMIND_API_URL,
                    params={
                        "dataset":    "TaiwanStockPrice",
                        "start_date": current.strftime("%Y-%m-%d"),
                        "end_date":   period_end.strftime("%Y-%m-%d"),
                        "token":      token,
                    },
                    timeout=120,
                )
                payload = resp.json()
                status  = payload.get("status", 0)

                if status == 401:
                    print(f"\n[FinMind] 致命錯誤：API Token 無效（401），"
                          "請確認 FINMIND_API_TOKEN")
                    return {}

                if status == 402:
                    print(f"\n[FinMind] 致命錯誤：超出每日 API 請求限制（402），"
                          "請明日再試或升級 FinMind 方案")
                    return {}

                if status == 200:
                    rows = payload.get("data") or []
                    all_rows.extend(rows)
                    print(f" {len(rows):,} 筆")
                    success = True
                    break

                # 其他非 200 狀態
                print(f" status={status}，跳過")
                success = True   # 非致命，繼續下一個月
                break

            except Exception as e:
                if attempt < 2:
                    wait = 10 * (attempt + 1)
                    print(f" 重試({attempt+1}/2，等 {wait}s)...", end="", flush=True)
                    time.sleep(wait)
                else:
                    print(f" 失敗：{e}")

        if not success:
            print(f"  {label} 下載最終失敗，跳過該月")

        current = _next_month_start(current)

    if not all_rows:
        print("  未取得任何資料")
        return {}

    print(f"  共 {len(all_rows):,} 筆原始資料，整理中...", flush=True)

    # ── 整理成 per-stock DataFrame ──
    df_all = pd.DataFrame(all_rows)

    # 確保必要欄位存在
    required_cols = {"stock_id", "date", "open", "max", "min", "close", "Trading_Volume"}
    if not required_cols.issubset(df_all.columns):
        missing = required_cols - set(df_all.columns)
        print(f"  FinMind 回傳欄位缺失：{missing}")
        return {}

    df_all["date"] = pd.to_datetime(df_all["date"])
    df_all = df_all.rename(columns={
        "open":           "Open",
        "max":            "High",
        "min":            "Low",
        "close":          "Close",
        "Trading_Volume": "Volume",
    })
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df_all[col] = pd.to_numeric(df_all[col], errors="coerce")
    df_all = df_all.dropna(subset=["Close", "Volume"])

    # 只保留股票清單中需要的 stock_id
    df_all = df_all[df_all["stock_id"].isin(needed_ids)]

    results = {}
    for sid, group in df_all.groupby("stock_id"):
        df = (group
              .sort_values("date")
              .set_index("date")[["Open", "High", "Low", "Close", "Volume"]]
              .copy())
        results[str(sid)] = df

    print(f"  完成：{len(results)} / {len(needed_ids)} 支股票資料整理完成")
    return results
