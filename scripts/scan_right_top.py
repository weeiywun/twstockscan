#!/usr/bin/env python3
"""
右上角選股掃描器（週K版）
掃描全市場，篩選同時滿足：
  1. 最新完整週收盤價創近 10 週新高
  2. 最新完整週成交量 >= 20 週均量 * 1.5

【資料抓取策略】
  週批次 bydate（不指定 data_id）搭配本地快取 data/price_weekly_cache.json。
  每週只需 1 次 API 請求（~8,500 筆），vs 原本逐支 ~1,700 次。
  每次執行時補齊缺少的完整週；正常情況下週一~週四不需補齊任何週。
"""

import json, os, time, requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from finmind_client import fetch_price_bydate

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "right_top.json")
CACHE_PATH  = os.path.join(DATA_DIR, "price_weekly_cache.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")

HIGH_PERIOD   = 10   # 週新高基準（週數）
VOL_MA_PERIOD = 20   # 均量週數
VOL_MULT      = 1.5
CACHE_WEEKS   = 25   # 保留週數（> VOL_MA_PERIOD + HIGH_PERIOD + 緩衝）
FINMIND_API   = "https://api.finmindtrade.com/api/v4/data"


# ── 股票清單 ──────────────────────────────────────────────────

def get_all_stocks(token):
    """取得全市場上市/上櫃一般股清單（排除 ETF、特別股）"""
    try:
        r = requests.get(FINMIND_API, params={
            "dataset": "TaiwanStockInfo",
            "token":   token,
        }, timeout=30)
        data = r.json()
        if data.get("status") != 200:
            print(f"⚠️  TaiwanStockInfo 回應異常：{data.get('msg')}")
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
        print(f"⚠️  取得股票清單失敗：{e}")
        return []


# ── 週K快取 ───────────────────────────────────────────────────

def _last_complete_friday() -> str:
    """最近一個已完整收盤的週五（台灣時間）。
    今天是週五（含）之後 → 本週五；否則 → 上週五。
    """
    now = datetime.now(TW_TZ)
    wd = now.weekday()          # Mon=0, Fri=4, Sat=5, Sun=6
    days_back = (wd - 4) if wd >= 4 else (wd + 3)
    return (now - timedelta(days=days_back)).strftime("%Y-%m-%d")


def load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"updated": None, "weeks": {}}


def save_cache(cache: dict):
    cache["updated"] = TODAY
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(',', ':'))
    kb = os.path.getsize(CACHE_PATH) // 1024
    print(f"  快取已儲存（{kb} KB，{len(cache['weeks'])} 週）")


def update_cache(cache: dict, token: str) -> bool:
    """
    補齊快取中缺少的完整週資料。
    - 正常情況（週一~週四）：0 次 API 請求
    - 週五盤後執行：1 次 API 請求（~8,500 筆）
    - 初次建立：最多 CACHE_WEEKS 次請求，每遇 402 自動停止，下次繼續
    回傳 True 代表快取有更新。
    """
    last_fri = _last_complete_friday()
    last_fri_dt = datetime.strptime(last_fri, "%Y-%m-%d")

    # 計算最近 CACHE_WEEKS 週的 Friday 日期（從舊到新）
    needed = [
        (last_fri_dt - timedelta(weeks=i)).strftime("%Y-%m-%d")
        for i in range(CACHE_WEEKS - 1, -1, -1)
    ]
    cached  = set(cache["weeks"].keys())
    missing = [f for f in needed if f not in cached]

    if not missing:
        print("  快取已是最新，跳過抓取")
        return False

    print(f"  缺少 {len(missing)} 週，開始補齊...")
    fetched_any = False

    for idx, fri_str in enumerate(missing):
        fri_dt  = datetime.strptime(fri_str, "%Y-%m-%d")
        mon_str = (fri_dt - timedelta(days=4)).strftime("%Y-%m-%d")
        print(f"  [{idx + 1}/{len(missing)}] 抓取 {mon_str}~{fri_str}...", end="", flush=True)

        df = fetch_price_bydate(mon_str, fri_str, token)
        if df is None:
            # 致命錯誤（401 / 402 / 網路失敗）：停止，下次繼續
            print(" 停止補齊（API 錯誤）")
            break

        if df.empty:
            # 該週無資料（例如農曆新年整週休市）：標記為空週，跳過
            print(" 無資料（休市週）")
            cache["weeks"][fri_str] = {}
            continue

        # 只保留 4 位數字且非 00 開頭（排除 ETF / 指數代號）
        df = df[df["stock_id"].str.match(r"^[1-9]\d{3}$")]

        # 聚合成週K：整週的 open/high/low/close 及總成交量（張）
        wk = (
            df.sort_values("date")
            .groupby("stock_id", sort=False)
            .agg(
                o=("open",        "first"),
                h=("max",         "max"),
                l=("min",         "min"),
                c=("close",       "last"),
                v=("volume_lots", "sum"),
            )
            .dropna()
        )

        week_data = {
            str(sid): [
                round(float(row["o"]), 2),
                round(float(row["h"]), 2),
                round(float(row["l"]), 2),
                round(float(row["c"]), 2),
                int(row["v"]),
            ]
            for sid, row in wk.iterrows()
        }

        cache["weeks"][fri_str] = week_data
        print(f" ✅ {len(week_data)} 支")
        fetched_any = True

        if idx < len(missing) - 1:
            time.sleep(1)   # 週與週之間稍作緩衝

    # 移除超出 CACHE_WEEKS 的舊週，維持滾動視窗
    all_sorted = sorted(cache["weeks"].keys())
    for old_fri in all_sorted[:-CACHE_WEEKS]:
        del cache["weeks"][old_fri]

    return fetched_any


def build_stock_weekly(cache: dict, stock_id: str) -> pd.DataFrame | None:
    """從快取重建單支股票的週K DataFrame（date, open, max, min, close, volume_lots）。"""
    rows = []
    for fri_str in sorted(cache["weeks"].keys()):
        entry = cache["weeks"][fri_str].get(stock_id)
        if entry is None:
            continue
        o, h, l, c, v = entry
        rows.append({
            "date":        pd.Timestamp(fri_str),
            "open":        o,
            "max":         h,
            "min":         l,
            "close":       c,
            "volume_lots": v,
        })
    if not rows:
        return None
    return pd.DataFrame(rows).reset_index(drop=True)


# ── 訊號判斷 ──────────────────────────────────────────────────

def check_signal(wk: pd.DataFrame) -> dict | None:
    """對週K DataFrame 執行訊號判斷，邏輯與原版完全相同。"""
    min_weeks = max(HIGH_PERIOD, VOL_MA_PERIOD) + 1
    if len(wk) < min_weeks:
        return None

    closes  = wk["close"].tolist()
    volumes = wk["volume_lots"].tolist()

    close_latest = closes[-1]
    high_prev10  = max(closes[-HIGH_PERIOD - 1:-1])  # 前 10 週最高收盤

    # 條件一：最新週收盤突破前 10 週最高價
    if close_latest <= high_prev10:
        return None

    # 條件一b：前 3 週皆未突破（確保為第一根突破，非強勢延續）
    if len(closes) >= 14:
        for i in range(2, 5):
            if closes[-i] > max(closes[-i - 10:-i]):
                return None

    # 條件一c：突破前 10 週價格波動 < 20%（確認橫盤打底）
    base_closes = closes[-11:-1]
    base_low    = min(base_closes)
    base_high   = max(base_closes)
    if base_low == 0 or (base_high - base_low) / base_low >= 0.20:
        return None

    # 條件一d：突破前 10 週均線斜率 < 5%（排除均線已走揚的趨勢股）
    if len(closes) >= 15:
        ma_now  = sum(closes[-11:-1]) / 10
        ma_prev = sum(closes[-15:-5]) / 10
        if ma_prev > 0 and (ma_now - ma_prev) / ma_prev * 100 >= 5.0:
            return None

    # 條件二：最新週量能 >= 20 週均量 * 1.5，且週均量 >= 500 張
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


# ── 主程式 ────────────────────────────────────────────────────

def now_tw():
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def main():
    print("=== 右上角選股掃描器（週K版）===")
    token = os.environ.get("FINMIND_TOKEN", "")
    if not token:
        print("⚠️  FINMIND_TOKEN 未設定")

    # ── 步驟 1：更新週K快取 ──
    print("\n[1] 更新週K快取...")
    cache = load_cache()
    updated = update_cache(cache, token)
    if updated:
        save_cache(cache)

    # ── 步驟 2：取得股票清單 ──
    print("\n[2] 取得全市場股票清單...")
    stocks = get_all_stocks(token)
    print(f"  全市場股票：{len(stocks)} 支")
    if not stocks:
        _write_output([], [])
        return

    # ── 步驟 3：掃描訊號（全從快取讀取，無 API 請求）──
    print("\n[3] 掃描訊號...")
    results  = []
    skipped  = 0
    for i, s in enumerate(stocks, 1):
        sid = s["stock_id"]
        wk  = build_stock_weekly(cache, sid)
        if wk is None:
            skipped += 1
            continue
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
        ind = r["industry"] or "其他"
        if ind not in industry_map:
            industry_map[ind] = {"industry": ind, "count": 0, "stocks": []}
        industry_map[ind]["count"] += 1
        industry_map[ind]["stocks"].append({"stock_id": r["stock_id"], "name": r["name"]})
    industry_stats = sorted(industry_map.values(), key=lambda x: x["count"], reverse=True)

    _write_output(results, industry_stats)


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


if __name__ == "__main__":
    main()
