#!/usr/bin/env python3
"""
全市場價格快取更新器

每日模式（正常執行）：
  python update_price_cache.py
  → 拉取今日全市場收盤，append 到 price_cache.parquet

回填模式（初始化，每次執行一個月）：
  python update_price_cache.py --backfill 2025-10
  → 拉取 2025-10 整月資料，合併到 price_cache.parquet

同時維護 stock_list_cache.json（每週一自動更新）
"""

import calendar
import json
import os
import sys
import time

import pandas as pd
import requests

FINMIND_API      = "https://api.finmindtrade.com/api/v4/data"
SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_DIR         = os.path.join(SCRIPT_DIR, "..", "data")
CACHE_PATH       = os.path.join(DATA_DIR, "price_cache.parquet")
STOCK_LIST_PATH  = os.path.join(DATA_DIR, "stock_list_cache.json")
KEEP_DAYS        = 210   # 保留 210 天（200 天需求 + 10 天緩衝）

from datetime import datetime, timedelta, timezone
TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")


# ── 股票清單快取 ───────────────────────────────────────────────

def _should_refresh_stock_list() -> bool:
    """週一或檔案不存在時才更新"""
    if not os.path.exists(STOCK_LIST_PATH):
        return True
    return datetime.now(TW_TZ).weekday() == 0  # 0 = 週一


def _fetch_stock_list(token: str) -> list[dict]:
    """從 FinMind 取得全市場上市/上櫃一般股清單"""
    try:
        r = requests.get(FINMIND_API, params={
            "dataset": "TaiwanStockInfo",
            "token":   token,
        }, timeout=30)
        data = r.json()
        if data.get("status") != 200:
            print(f"  ⚠️  TaiwanStockInfo 回應異常：{data.get('msg')}")
            return []
        stocks = []
        for s in data["data"]:
            sid = s.get("stock_id", "")
            if not sid.isdigit() or len(sid) != 4:
                continue
            if sid.startswith("00"):
                continue
            industry = s.get("industry_category", "")
            if "ETF" in industry:
                continue
            market = s.get("type", "")
            if market not in ("twse", "tpex", "上市", "上櫃", "TWSE", "TPEX"):
                continue
            stocks.append({
                "stock_id": sid,
                "name":     s.get("stock_name", ""),
                "industry": industry,
                "market":   "TWSE" if market in ("twse", "上市", "TWSE") else "TPEX",
            })
        return stocks
    except Exception as e:
        print(f"  ⚠️  取得股票清單失敗：{e}")
        return []


def update_stock_list_cache(token: str):
    if not _should_refresh_stock_list():
        with open(STOCK_LIST_PATH, encoding="utf-8") as f:
            stocks = json.load(f)
        print(f"  📋 stock_list_cache.json 沿用（{len(stocks)} 支，非週一略過更新）")
        return
    print("  🔄 更新股票清單...")
    stocks = _fetch_stock_list(token)
    if not stocks:
        print("  ⚠️  股票清單為空，略過更新")
        return
    with open(STOCK_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False)
    print(f"  ✅ stock_list_cache.json 已更新：{len(stocks)} 支")


# ── 價格快取 ──────────────────────────────────────────────────

def _fetch_bydate(start_date: str, end_date: str, token: str) -> pd.DataFrame | None:
    """一次取得全市場指定日期範圍的調整後股價（不帶 data_id）"""
    print(f"  → GET TaiwanStockPriceAdj  {start_date} ～ {end_date}")
    try:
        r = requests.get(FINMIND_API, params={
            "dataset":    "TaiwanStockPriceAdj",
            "start_date": start_date,
            "end_date":   end_date,
            "token":      token,
        }, timeout=120)
        data = r.json()
        if data.get("status") != 200:
            print(f"  ⚠️  API 回應異常：{data.get('msg', 'unknown')}")
            return None
        if not data.get("data"):
            print("  ⚠️  API 回傳空資料")
            return None
        return pd.DataFrame(data["data"])
    except Exception as e:
        print(f"  ⚠️  fetch_bydate 失敗：{e}")
        return None


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """統一欄位名稱、型別，過濾非普通股"""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # volume 欄位名稱依 FinMind 版本可能不同
    if "Trading_Volume" in df.columns:
        vol_col = "Trading_Volume"
    elif "volume" in df.columns:
        vol_col = "volume"
    else:
        vol_col = df.columns[-1]   # fallback
    df["volume_lots"] = (
        pd.to_numeric(df[vol_col], errors="coerce") / 1000
    ).round(0).fillna(0).astype(int)

    # 只保留 4 位純數字代號（一般股）
    df = df[df["stock_id"].str.match(r"^\d{4}$", na=False)].copy()

    for col in ["open", "max", "min", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])

    return df[["stock_id", "date", "open", "max", "min", "close", "volume_lots"]]


def _load_cache() -> pd.DataFrame:
    if os.path.exists(CACHE_PATH):
        return pd.read_parquet(CACHE_PATH)
    return pd.DataFrame(
        columns=["stock_id", "date", "open", "max", "min", "close", "volume_lots"]
    )


def _save_cache(df: pd.DataFrame):
    """去重、排序、裁剪至 KEEP_DAYS，存回 parquet"""
    df = df.drop_duplicates(subset=["stock_id", "date"])
    df = df.sort_values(["stock_id", "date"]).reset_index(drop=True)
    cutoff = pd.Timestamp(datetime.now(TW_TZ).date()) - pd.Timedelta(days=KEEP_DAYS)
    df = df[df["date"] >= cutoff]
    df.to_parquet(CACHE_PATH, index=False)
    stocks = df["stock_id"].nunique()
    latest = df["date"].max().date() if not df.empty else "—"
    size_mb = os.path.getsize(CACHE_PATH) / 1024 / 1024
    print(f"  ✅ price_cache.parquet 已更新")
    print(f"     {len(df):,} 筆 | {stocks} 支 | 最新 {latest} | {size_mb:.1f} MB")


def update_price_cache(start_date: str, end_date: str, token: str):
    print(f"\n[2] 拉取全市場股價（{start_date} ～ {end_date}）...")
    raw = _fetch_bydate(start_date, end_date, token)
    if raw is None or raw.empty:
        print("  ⚠️  無資料，略過"); return

    print(f"  回傳 {len(raw):,} 筆原始資料")
    new_df = _normalize(raw)
    print(f"  正規化後 {len(new_df):,} 筆")

    print("[3] 合併快取...")
    cache = _load_cache()
    combined = pd.concat([cache, new_df], ignore_index=True)

    print("[4] 儲存快取...")
    _save_cache(combined)


# ── 主程式 ────────────────────────────────────────────────────

def main():
    token = os.environ.get("FINMIND_TOKEN", "")
    if not token:
        print("❌ FINMIND_TOKEN 未設定"); sys.exit(1)

    # 解析 --backfill YYYY-MM
    backfill_month: str | None = None
    if "--backfill" in sys.argv:
        idx = sys.argv.index("--backfill")
        if idx + 1 < len(sys.argv):
            backfill_month = sys.argv[idx + 1]

    if backfill_month:
        print(f"=== 回填模式：{backfill_month} ===")
        try:
            year, month = map(int, backfill_month.split("-"))
        except ValueError:
            print("❌ 格式錯誤，請用 YYYY-MM，例如 2025-10"); sys.exit(1)
        _, last_day = calendar.monthrange(year, month)
        start = f"{year:04d}-{month:02d}-01"
        end   = f"{year:04d}-{month:02d}-{last_day:02d}"
    else:
        print(f"=== 每日更新模式：{TODAY} ===")
        start = TODAY
        end   = TODAY

    print("\n[1] 更新股票清單快取...")
    update_stock_list_cache(token)

    update_price_cache(start, end, token)
    print("\n✅ 完成")


if __name__ == "__main__":
    main()
