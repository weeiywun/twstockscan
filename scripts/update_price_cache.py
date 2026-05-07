#!/usr/bin/env python3
"""
全市場價格快取更新器

初始化模式（一次性，用 yfinance，不消耗 FinMind 額度）：
  python update_price_cache.py --init
  → 用 yfinance 批次下載全市場 210 天歷史，建立 price_cache.parquet

每日模式（正常執行）：
  python update_price_cache.py
  → 拉取今日全市場收盤，append 到 price_cache.parquet

回填模式（補漏用，每次執行一個月）：
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
        # FinMind 同一 stock_id 可能回傳多筆（industry 不同），保留第一筆
        seen: set[str] = set()
        stocks = [s for s in stocks if not (s["stock_id"] in seen or seen.add(s["stock_id"]))]
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
    for attempt in range(3):
        try:
            r = requests.get(FINMIND_API, params={
                "dataset":    "TaiwanStockPriceAdj",
                "start_date": start_date,
                "end_date":   end_date,
                "token":      token,
            }, timeout=120)
            data = r.json()
            status = data.get("status", 0)
            if status == 401:
                print("  ❌ Token 無效（401），請確認 FINMIND_TOKEN")
                return None
            if status == 402:
                print("  ❌ 超出每日 API 配額（402）")
                return None
            if status != 200:
                print(f"  ⚠️  API 回應異常（{status}）：{data.get('msg', 'unknown')}")
                if attempt < 2:
                    wait = 15 * (attempt + 1)
                    print(f"  重試({attempt + 1}/2，等 {wait}s)...")
                    time.sleep(wait)
                    continue
                return None
            if not data.get("data"):
                print("  ⚠️  API 回傳空資料（可能為非交易日）")
                return pd.DataFrame()
            return pd.DataFrame(data["data"])
        except Exception as e:
            if attempt < 2:
                wait = 15 * (attempt + 1)
                print(f"  ⚠️  fetch_bydate 失敗：{e}，重試({attempt + 1}/2，等 {wait}s)...")
                time.sleep(wait)
            else:
                print(f"  ❌ fetch_bydate 三次皆失敗：{e}")
    return None


def _num(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "NaN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _official_roc_date(date: str) -> str:
    year, month, day = map(int, date.split("-"))
    return f"{year - 1911:03d}{month:02d}{day:02d}"


def _fetch_official_daily_close(date: str) -> pd.DataFrame:
    """FinMind 延遲時，改用 TWSE/TPEx 官方盤後價量補今日資料。"""
    rows: list[dict] = []
    target = datetime.strptime(date, "%Y-%m-%d")

    print(f"  → 官方盤後資料 fallback {date}")
    try:
        r = requests.get(
            "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
            params={"date": target.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        r.raise_for_status()
        payload = r.json()
        for table in payload.get("tables", []):
            for row in table.get("data", []) or []:
                if not row or len(row) < 9 or not str(row[0]).isdigit() or len(str(row[0])) != 4:
                    continue
                open_, high, low, close = (_num(row[5]), _num(row[6]), _num(row[7]), _num(row[8]))
                volume = _num(row[2])
                if close is None or volume is None:
                    continue
                rows.append({
                    "stock_id": str(row[0]),
                    "date": pd.Timestamp(date),
                    "open": open_,
                    "max": high,
                    "min": low,
                    "close": close,
                    "volume_lots": int(round(volume / 1000)),
                })
    except Exception as exc:
        print(f"  ⚠️  TWSE 官方盤後資料失敗：{exc}")

    try:
        r = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        r.raise_for_status()
        roc_date = _official_roc_date(date)
        for row in r.json():
            sid = str(row.get("SecuritiesCompanyCode", ""))
            if not sid.isdigit() or len(sid) != 4 or str(row.get("Date", "")) != roc_date:
                continue
            open_, high, low, close = (_num(row.get("Open")), _num(row.get("High")), _num(row.get("Low")), _num(row.get("Close")))
            volume = _num(row.get("TradingShares"))
            if close is None or volume is None:
                continue
            rows.append({
                "stock_id": sid,
                "date": pd.Timestamp(date),
                "open": open_,
                "max": high,
                "min": low,
                "close": close,
                "volume_lots": int(round(volume / 1000)),
            })
    except Exception as exc:
        print(f"  ⚠️  TPEx 官方盤後資料失敗：{exc}")

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["stock_id", "date"])
        print(f"  ✅ 官方盤後資料取得 {len(df):,} 筆")
    return df


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


def update_price_cache(start_date: str, end_date: str, token: str) -> bool:
    print(f"\n[2] 拉取全市場股價（{start_date} ～ {end_date}）...")
    raw = _fetch_bydate(start_date, end_date, token)
    if raw is None or raw.empty:
        if start_date == end_date:
            new_df = _fetch_official_daily_close(start_date)
        else:
            print("  ⚠️  無資料，略過")
            return False
    else:
        print(f"  回傳 {len(raw):,} 筆原始資料")
        new_df = _normalize(raw)

    if new_df.empty:
        print("  ⚠️  無有效資料，略過")
        return False
    print(f"  正規化後 {len(new_df):,} 筆")

    print("[3] 合併快取...")
    cache = _load_cache()
    combined = pd.concat([cache, new_df], ignore_index=True)

    print("[4] 儲存快取...")
    _save_cache(combined)
    return True


# ── yfinance 初始化 ───────────────────────────────────────────

def _fetch_init_yfinance(stock_list: list[dict]) -> pd.DataFrame:
    """用 yfinance 批次下載全市場 KEEP_DAYS 天歷史資料（不消耗 FinMind 額度）。"""
    try:
        import yfinance as yf
    except ImportError:
        print("  ❌ yfinance 未安裝"); sys.exit(1)

    # stock_id → yfinance ticker（TWSE: .TW, TPEX: .TWO）
    ticker_map: dict[str, str] = {}
    for s in stock_list:
        suffix = ".TW" if s["market"] == "TWSE" else ".TWO"
        ticker_map[f"{s['stock_id']}{suffix}"] = s["stock_id"]

    symbols = list(ticker_map.keys())
    BATCH   = 100
    total_batches = (len(symbols) + BATCH - 1) // BATCH
    all_frames: list[pd.DataFrame] = []

    for batch_idx, start in enumerate(range(0, len(symbols), BATCH), 1):
        batch = symbols[start:start + BATCH]
        print(f"  批次 {batch_idx}/{total_batches}：下載 {len(batch)} 支...")
        try:
            raw = yf.download(
                batch,
                period=f"{KEEP_DAYS}d",
                auto_adjust=True,
                progress=False,
            )
            if raw.empty:
                print("    ⚠️ 空回應，略過")
                continue

            # 欄位結構：MultiIndex (metric, ticker) 或單層 (單支時)
            if isinstance(raw.columns, pd.MultiIndex):
                for sym in batch:
                    sid = ticker_map[sym]
                    try:
                        close = raw["Close"][sym].dropna()
                        if close.empty:
                            continue
                        idx = close.index
                        frame = pd.DataFrame({
                            "stock_id":    sid,
                            "date":        pd.to_datetime(idx),
                            "open":        raw["Open"][sym].reindex(idx).values,
                            "max":         raw["High"][sym].reindex(idx).values,
                            "min":         raw["Low"][sym].reindex(idx).values,
                            "close":       close.values,
                            "volume_lots": (
                                raw["Volume"][sym].reindex(idx).fillna(0) / 1000
                            ).round(0).astype(int).values,
                        })
                        all_frames.append(frame)
                    except Exception:
                        pass
            else:
                # 單支股票（batch size == 1）
                sym = batch[0]
                sid = ticker_map[sym]
                df  = raw.dropna(subset=["Close"]).reset_index()
                if not df.empty:
                    all_frames.append(pd.DataFrame({
                        "stock_id":    sid,
                        "date":        pd.to_datetime(df["Date"]),
                        "open":        df["Open"].values,
                        "max":         df["High"].values,
                        "min":         df["Low"].values,
                        "close":       df["Close"].values,
                        "volume_lots": (df["Volume"].fillna(0) / 1000).round(0).astype(int).values,
                    }))
        except Exception as e:
            print(f"    ⚠️ 批次失敗：{e}")

    if not all_frames:
        print("  ❌ 未取得任何資料")
        return pd.DataFrame(columns=["stock_id", "date", "open", "max", "min", "close", "volume_lots"])

    result = pd.concat(all_frames, ignore_index=True)
    print(f"  ✅ yfinance 完成：{result['stock_id'].nunique()} 支，{len(result):,} 筆")
    return result


def init_price_cache(token: str):
    """一次性初始化：用 yfinance 建立 210 天全市場快取。"""
    print("=== 初始化模式（yfinance）===\n")
    print("[1] 更新股票清單快取...")
    update_stock_list_cache(token)

    with open(STOCK_LIST_PATH, encoding="utf-8") as f:
        stock_list = json.load(f)
    print(f"  📋 共 {len(stock_list)} 支股票\n")

    print(f"[2] yfinance 批次下載（{KEEP_DAYS} 天）...")
    new_df = _fetch_init_yfinance(stock_list)
    if new_df.empty:
        print("❌ 無資料，中止"); sys.exit(1)

    print("\n[3] 合併並儲存快取...")
    cache   = _load_cache()
    combined = pd.concat([cache, new_df], ignore_index=True)
    _save_cache(combined)


# ── 主程式 ────────────────────────────────────────────────────

def main():
    token = os.environ.get("FINMIND_TOKEN", "")
    if not token:
        print("❌ FINMIND_TOKEN 未設定"); sys.exit(1)

    # --init：yfinance 一次性初始化
    if "--init" in sys.argv:
        init_price_cache(token)
        print("\n✅ 完成")
        return

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

    updated = update_price_cache(start, end, token)
    if not updated and not backfill_month:
        print(f"❌ {TODAY} 尚未取得有效日線資料，停止後續掃描以避免使用舊價量")
        sys.exit(1)
    print("\n✅ 完成")


if __name__ == "__main__":
    main()
