#!/usr/bin/env python3
"""
股價資料下載模組（yfinance 批次版）
供 scan_ema_tangling.py 和 scan_volume_breakout.py 共用。
"""

import time

import pandas as pd
import yfinance as yf


def fetch_all_stocks(stock_list, start_date, end_date, token=None, **_kwargs):
    """
    下載全市場歷史 OHLCV 日線資料（yfinance 批次版）。

    Parameters
    ----------
    stock_list : list[dict]，每個元素包含 stock_id / name / market
    start_date : str，格式 "YYYY-MM-DD"
    end_date   : str，格式 "YYYY-MM-DD"
    token      : 忽略（相容舊介面）

    Returns
    -------
    dict[str, pd.DataFrame]：{stock_id: DataFrame(index=date, cols=[Open,High,Low,Close,Volume])}
    """
    BATCH = 100

    # 建立 ticker → stock_id 對照表
    ticker_map = {}
    for s in stock_list:
        suffix = ".TW" if s["market"] == "TWSE" else ".TWO"
        ticker_map[s["stock_id"] + suffix] = s["stock_id"]

    tickers = list(ticker_map.keys())
    total   = len(tickers)
    n_batches = (total + BATCH - 1) // BATCH
    results = {}

    for b_idx in range(n_batches):
        batch   = tickers[b_idx * BATCH:(b_idx + 1) * BATCH]
        ticker_str = " ".join(batch)
        print(f"  [{b_idx+1}/{n_batches}] 下載 {len(batch)} 支...", end="", flush=True)

        try:
            raw = yf.download(
                ticker_str,
                start=start_date,
                end=end_date,
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if raw is None or raw.empty:
                print(" 無資料")
                continue

            hits = 0
            for ticker in batch:
                sid = ticker_map[ticker]
                try:
                    if len(batch) == 1:
                        df = raw.dropna(how="all")
                    else:
                        lvl0 = raw.columns.get_level_values(0)
                        if ticker not in lvl0:
                            continue
                        df = raw[ticker].dropna(how="all")

                    if df is None or df.empty:
                        continue

                    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
                    for col in ["Open", "High", "Low", "Close", "Volume"]:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    df = df.dropna(subset=["Close", "Volume"])

                    if not df.empty:
                        results[sid] = df
                        hits += 1
                except Exception:
                    pass

            print(f" {hits} 支有效")

        except Exception as e:
            print(f" 失敗：{e}")

        time.sleep(1.2)

    print(f"  完成：{len(results)} / {len(stock_list)} 支股票資料整理完成")
    return results
