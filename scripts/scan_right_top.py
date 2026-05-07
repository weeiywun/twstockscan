#!/usr/bin/env python3
"""
右上角選股掃描器（週K版）
掃描全市場，篩選同時滿足：
  1. 最新週收盤價創近 10 週新高（含當週未完整週）
  2. 最新週成交量 >= 20 週均量 * 1.5
  3. 突破前橫盤整理（10 週波動 < 20%，均線斜率 < 5%）
  4. 首次突破（前 3 週未曾突破）

資料來源：price_cache.parquet（由 update_price_cache.py 每日維護）
日K → 週K：df.resample("W-FRI") 動態聚合，含當週未完整週
"""

import json, os, sys
import pandas as pd
from datetime import datetime, timedelta, timezone
from finmind_client import load_price_cache, get_stock_price_from_cache

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
DATA_DIR        = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH     = os.path.join(DATA_DIR, "right_top.json")
STOCK_LIST_PATH = os.path.join(DATA_DIR, "stock_list_cache.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")

HIGH_PERIOD   = 10
VOL_MA_PERIOD = 20
VOL_MULT      = 1.5
LOOKBACK_DAYS = 210   # 對應 price_cache.parquet 保留天數


def _to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """日K → 週K（週五為週末基準，含當週未完整週）"""
    df = df.set_index("date").sort_index()
    weekly = df.resample("W-FRI").agg(
        open=("open",        "first"),
        max=("max",          "max"),
        min=("min",          "min"),
        close=("close",      "last"),
        volume_lots=("volume_lots", "sum"),
    ).dropna(subset=["close"])
    return weekly.reset_index()


def _require_fresh_cache(price_cache: pd.DataFrame) -> None:
    latest = price_cache["date"].max().strftime("%Y-%m-%d")
    if latest != TODAY:
        print(f"❌ price_cache.parquet 最新資料為 {latest}，不是 {TODAY}；停止右上角掃描，避免用舊價量產生今日訊號")
        sys.exit(1)


def check_signal(wk: pd.DataFrame) -> dict | None:
    min_weeks = max(HIGH_PERIOD, VOL_MA_PERIOD) + 1
    if len(wk) < min_weeks:
        return None

    closes  = wk["close"].tolist()
    volumes = wk["volume_lots"].tolist()

    close_latest = closes[-1]
    high_prev10  = max(closes[-HIGH_PERIOD - 1:-1])  # 前 10 週最高收盤

    if close_latest <= high_prev10:
        return None

    # 前 3 週皆未突破（確保為第一根突破）
    if len(closes) >= 14:
        for i in range(2, 5):
            if closes[-i] > max(closes[-i - 10:-i]):
                return None

    # 突破前 10 週波動 < 20%（橫盤打底）
    base_closes = closes[-11:-1]
    base_low    = min(base_closes)
    base_high   = max(base_closes)
    if base_low == 0 or (base_high - base_low) / base_low >= 0.20:
        return None

    # 突破前 10 週均線斜率 < 5%（排除已走揚趨勢股）
    if len(closes) >= 15:
        ma_now  = sum(closes[-11:-1]) / 10
        ma_prev = sum(closes[-15:-5]) / 10
        if ma_prev > 0 and (ma_now - ma_prev) / ma_prev * 100 >= 5.0:
            return None

    vol_latest  = volumes[-1]
    vol_20w_avg = sum(volumes[-VOL_MA_PERIOD - 1:-1]) / VOL_MA_PERIOD
    if vol_20w_avg < 500:
        return None
    if vol_latest < vol_20w_avg * VOL_MULT:
        return None

    prev_close = closes[-2] if len(closes) >= 2 else close_latest
    change_pct = round((close_latest - prev_close) / prev_close * 100, 2) if prev_close else 0
    latest_week_date = wk.iloc[-1]["date"].strftime("%Y-%m-%d")

    return {
        "close":        round(close_latest, 2),
        "high_10w":     round(high_prev10, 2),
        "vol_latest_w": int(vol_latest),
        "vol_20w_avg":  round(vol_20w_avg, 1),
        "vol_ratio":    round(vol_latest / vol_20w_avg, 2),
        "change_pct":   change_pct,
        "week_date":    latest_week_date,
    }


def now_tw():
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


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


def _write_output(results, industry_stats):
    output = {
        "strategy_id":    "right_top",
        "updated":        now_tw(),
        "results":        results,
        "industry_stats": industry_stats,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 已寫入 {OUTPUT_PATH}")


def main():
    print("=== 右上角選股掃描器（週K版）===")

    # ── 步驟 1：載入股票清單 ──
    print("\n[1] 載入股票清單...")
    if not os.path.exists(STOCK_LIST_PATH):
        print("⚠️  stock_list_cache.json 不存在，請先執行 update_price_cache.py")
        _write_output([], [])
        return
    with open(STOCK_LIST_PATH, encoding="utf-8") as f:
        stocks = json.load(f)
    raw_count = len(stocks)
    stocks = dedupe_stocks(stocks)
    print(f"  共 {raw_count} 筆 / 去重後 {len(stocks)} 支")

    # ── 步驟 2：載入價格快取 ──
    print("\n[2] 載入 price_cache.parquet...")
    price_cache = load_price_cache()
    if price_cache is None or price_cache.empty:
        print("⚠️  price_cache.parquet 不存在或為空，請先執行 update_price_cache.py")
        _write_output([], [])
        return
    latest_date = price_cache["date"].max().date()
    print(f"  {len(price_cache):,} 筆 | {price_cache['stock_id'].nunique()} 支 | 最新 {latest_date}")
    _require_fresh_cache(price_cache)

    start_date = (datetime.now(TW_TZ) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    # ── 步驟 3：掃描訊號（日K → 週K，無 API 請求）──
    print("\n[3] 掃描訊號...")
    results = []
    skipped = 0

    for i, s in enumerate(stocks, 1):
        sid   = s["stock_id"]
        daily = get_stock_price_from_cache(price_cache, sid, start_date)
        if daily is None or len(daily) < 20:
            skipped += 1
            continue

        wk     = _to_weekly(daily)
        signal = check_signal(wk)
        if signal:
            results.append({
                "stock_id":    sid,
                "name":        s["name"],
                "industry":    s["industry"],
                "market":      s["market"],
                **signal,
                "signal_date": TODAY,
            })
            print(f"  ✅ {sid} {s['name']}  量比={signal['vol_ratio']}x  漲幅={signal['change_pct']}%  週={signal['week_date']}")

        if i % 200 == 0:
            print(f"  掃描進度：{i}/{len(stocks)}，已觸發 {len(results)} 支，快取缺失 {skipped} 支")

    results.sort(key=lambda r: r.get("vol_ratio") or 0, reverse=True)
    print(f"\n觸發訊號：{len(results)} 支（快取缺失 {skipped} 支）")

    # ── 產業統計 ──
    industry_map = {}
    for r in results:
        for ind in _industry_list(r["industry"]) or ["其他"]:
            if ind not in industry_map:
                industry_map[ind] = {"industry": ind, "count": 0, "stocks": []}
            industry_map[ind]["count"] += 1
            industry_map[ind]["stocks"].append({"stock_id": r["stock_id"], "name": r["name"]})
    industry_stats = sorted(industry_map.values(), key=lambda x: x["count"], reverse=True)

    _write_output(results, industry_stats)


if __name__ == "__main__":
    main()
