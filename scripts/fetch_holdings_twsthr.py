#!/usr/bin/env python3
"""
大戶持股抓取器 v1.0
從 norway.twsthr.info/StockBoardTop.aspx 抓取 TDCC 千張大戶持股比例資料，
搭配 yfinance 股價資料，產生 data/chips_big_holder.json。

取代原本 GAS 的 FinMind TaiwanStockHoldingSharesPercentage 查詢。

策略篩選條件：
  1. 千張大戶持股比例 > 30%
  2. 最近 4 週持續增持（每週比前一週高）
  3. 現價對 EMA26 的乖離率 -10% ~ +5%
"""

import json
import os
import re
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH  = os.path.join(SCRIPT_DIR, "..", "data", "chips_big_holder.json")

SOURCE_URL   = "https://norway.twsthr.info/StockBoardTop.aspx"
TW_TZ        = timezone(timedelta(hours=8))

BIG_PCT_MIN  = 30.0   # 千張大戶持股比例最低門檻 (%)
TREND_WEEKS  = 4      # 需要連續幾週增持
EMA_PERIOD   = 26
DEV_MIN      = -10.0  # EMA26 乖離率下限 (%)
DEV_MAX      =   5.0  # EMA26 乖離率上限 (%)
PRICE_DAYS   = 80     # yfinance 抓取天數（確保 EMA26 收斂）


# ─────────────────────────────────────────────────────────────
#  Step 1：從網站抓取持股資料
# ─────────────────────────────────────────────────────────────

def fetch_page() -> bytes:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://norway.twsthr.info/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    for attempt in range(3):
        try:
            resp = requests.get(SOURCE_URL, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            if attempt < 2:
                wait = 2 ** attempt
                print(f"  抓取失敗（{e}），{wait}s 後重試...")
                time.sleep(wait)
            else:
                raise


def _mmdd_to_label(mmdd: str, ref_year: int, today: datetime) -> str:
    """'0410' → '04-10'，並處理跨年邊界。"""
    mm, dd = int(mmdd[:2]), int(mmdd[2:])
    for year in (ref_year, ref_year - 1):
        try:
            d = datetime(year, mm, dd, tzinfo=TW_TZ)
            if d <= today + timedelta(days=8):
                return d.strftime("%m-%d")
        except ValueError:
            continue
    return f"{mmdd[:2]}-{mmdd[2:]}"


def parse_holdings(html: bytes):
    """
    解析持股表格。
    回傳 (stocks, date_labels)
      stocks: list of {stock_id, name, industry, weekly_pct}
              weekly_pct 由新到舊排列（index 0 = 最新週）
      date_labels: list of "MM-DD" 由新到舊
    """
    soup = BeautifulSoup(html, "lxml")
    today = datetime.now(TW_TZ)
    ref_year = today.year

    # ── 找主要資料表格 ──
    main_table = None
    best_count = 0
    for t in soup.find_all("table"):
        cnt = len(t.find_all("a", href=re.compile(r'[Ss]=\d{4}')))
        if cnt > best_count:
            best_count = cnt
            main_table = t

    if main_table is None or best_count < 5:
        raise ValueError("找不到股票資料表格（可能被 403 擋住）")

    rows = main_table.find_all("tr")

    # ── 從表頭取得日期欄位 ──
    date_labels = []
    for row in rows[:8]:
        for cell in row.find_all(["th", "td"]):
            txt = cell.get_text(strip=True)
            # 年份標記
            if re.fullmatch(r'20\d{2}', txt):
                ref_year = int(txt)
            # MMDD 格式
            elif re.fullmatch(r'\d{4}', txt):
                mm = int(txt[:2])
                dd = int(txt[2:])
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    date_labels.append(_mmdd_to_label(txt, ref_year, today))
        if len(date_labels) >= 4:
            break

    if len(date_labels) < 4:
        raise ValueError(f"日期欄位不足（只找到 {len(date_labels)} 個）")

    n_dates = len(date_labels)
    print(f"  日期欄：{date_labels}（共 {n_dates} 週）")

    # ── 解析股票列 ──
    stocks = []
    seen = set()

    for row in rows:
        link = row.find("a", href=re.compile(r'[Ss]=\d{4}'))
        if not link:
            continue

        href = link.get("href", "")
        m = re.search(r'[Ss]=(\d{4})', href)
        if not m:
            continue
        sid = m.group(1)
        if sid in seen:
            continue

        # 股票名稱（去除代號）
        raw_name = link.get_text(strip=True)
        name = re.sub(r'^\d{4}\s*', '', raw_name).strip() or raw_name

        # 產業類別
        industry = ""
        for cell in row.find_all("td"):
            if cell.find("a"):
                continue
            txt = cell.get_text(strip=True)
            # 純中文（可含破折號、英文字母）、長度 1-8
            if re.fullmatch(r'[\u4e00-\u9fff\w－\-]{1,8}', txt) and not txt.isdigit():
                industry = txt
                break

        # 從所有 td 抽取數字
        all_nums = []
        for cell in row.find_all("td"):
            for s in cell.stripped_strings:
                clean = s.replace(',', '').replace('+', '').strip()
                try:
                    all_nums.append(float(clean))
                except ValueError:
                    pass

        # 持股比例 > 5%（大戶通常 > 10%），差異值絕對值通常 < 5
        pct_vals = [v for v in all_nums if v > 5.0]

        if len(pct_vals) < n_dates:
            continue

        # 取最前面 n_dates 個（表格由新到舊排列）
        weekly_pct = pct_vals[:n_dates]

        seen.add(sid)
        stocks.append({
            "stock_id":   sid,
            "name":       name,
            "industry":   industry,
            "weekly_pct": weekly_pct,   # index 0 = 最新週
        })

    print(f"  解析到 {len(stocks)} 支股票")
    return stocks, date_labels


# ─────────────────────────────────────────────────────────────
#  Step 2：策略篩選
# ─────────────────────────────────────────────────────────────

def passes_holding_filter(weekly_pct: list) -> bool:
    """
    篩選條件：
      - 最新週持股比例 > BIG_PCT_MIN
      - 最近 TREND_WEEKS 週連續增持（每週高於前一週）
    """
    if len(weekly_pct) < TREND_WEEKS:
        return False
    if weekly_pct[0] < BIG_PCT_MIN:
        return False
    # weekly_pct[0] 最新，weekly_pct[1] 前一週，以此類推
    for i in range(TREND_WEEKS - 1):
        if weekly_pct[i] <= weekly_pct[i + 1]:
            return False
    return True


# ─────────────────────────────────────────────────────────────
#  Step 3：取得股價與 EMA26
# ─────────────────────────────────────────────────────────────

def get_market_map() -> dict:
    """回傳 {stock_id: 'TWSE'|'TPEX'} 對照表。"""
    mmap = {}
    for url, market in [
        ("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "TWSE"),
        ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", "TPEX"),
    ]:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            for item in r.json():
                sid = (
                    item.get("Code") or item.get("SecuritiesCompanyCode") or ""
                ).strip()
                if re.fullmatch(r'\d{4}', sid):
                    mmap[sid] = market
        except Exception as e:
            print(f"  市場清單取得失敗（{market}）：{e}")
    return mmap


def fetch_price_ema(stock_id: str, suffix: str) -> dict | None:
    """
    用 yfinance 取得最新收盤價與 EMA26。
    回傳 {close, ema26, deviation, vol_lots} 或 None。
    """
    ticker = f"{stock_id}{suffix}"
    end   = datetime.now(TW_TZ)
    start = end - timedelta(days=PRICE_DAYS)

    try:
        df = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if df is None or df.empty or len(df) < 10:
            return None

        close_arr = df["Close"].dropna().values.astype(float)
        vol_arr   = df["Volume"].dropna().values.astype(float)

        if len(close_arr) < 10:
            return None

        ema26 = float(
            pd.Series(close_arr).ewm(span=EMA_PERIOD, adjust=False).mean().iloc[-1]
        )
        close = float(close_arr[-1])
        deviation = round((close - ema26) / ema26 * 100, 2)

        avg_vol = float(np.mean(vol_arr[-20:])) if len(vol_arr) >= 20 else float(np.mean(vol_arr))
        vol_lots = round(avg_vol / 1000, 0)

        return {
            "close":     round(close, 2),
            "ema26":     round(ema26, 2),
            "deviation": deviation,
            "vol_lots":  int(vol_lots),
        }
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
#  Step 4：組合輸出
# ─────────────────────────────────────────────────────────────

def now_tw_str() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def main():
    print("=== 大戶持股抓取器 v1.0 ===")

    # Step 1：抓網頁
    print("\nStep 1：抓取 norway.twsthr.info...")
    html = fetch_page()
    stocks_raw, date_labels = parse_holdings(html)

    # Step 2：持股篩選
    print(f"\nStep 2：策略篩選（大戶>{BIG_PCT_MIN}%、連續{TREND_WEEKS}週增持）...")
    candidates = [s for s in stocks_raw if passes_holding_filter(s["weekly_pct"])]
    print(f"  通過：{len(candidates)} / {len(stocks_raw)} 支")

    if not candidates:
        print("⚠️  無符合條件股票，輸出空結果")
        _write_output([], date_labels)
        return

    # Step 3：取得市場對照表
    print("\nStep 3：取得市場清單...")
    mmap = get_market_map()
    print(f"  上市+上櫃：{len(mmap)} 支")

    # Step 4：逐批抓 yfinance 股價
    print(f"\nStep 4：取得股價與 EMA26（共 {len(candidates)} 支）...")
    results = []
    batch_size = 20

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        for s in batch:
            sid    = s["stock_id"]
            market = mmap.get(sid, "TWSE")
            suffix = ".TW" if market == "TWSE" else ".TWO"
            price_data = fetch_price_ema(sid, suffix)
            if price_data is None:
                continue

            dev = price_data["deviation"]
            if not (DEV_MIN <= dev <= DEV_MAX):
                continue

            pcts = s["weekly_pct"]
            # date_labels[0] = 最新；trend 由舊到新（for chart）
            trend_labels = list(reversed(date_labels[:TREND_WEEKS]))
            trend_pcts   = list(reversed(pcts[:TREND_WEEKS]))

            results.append({
                "stock_id":       sid,
                "name":           s["name"],
                "industry":       s["industry"],
                "close":          price_data["close"],
                "ema26":          price_data["ema26"],
                "deviation":      dev,
                "vol_lots":       price_data["vol_lots"],
                "big_pct_latest": round(pcts[0], 2),
                "big_4w_chg":     round(pcts[0] - pcts[TREND_WEEKS - 1], 2),
                "big_trend":      [round(v, 2) for v in trend_pcts],
                "date_labels":    trend_labels,
            })
            sys.stdout.write(".")
            sys.stdout.flush()

        time.sleep(0.5)

    print(f"\n  最終結果：{len(results)} 支通過乖離率篩選")

    # 依 big_4w_chg 降冪排列
    results.sort(key=lambda r: r["big_4w_chg"], reverse=True)

    _write_output(results, date_labels)


def _write_output(results, date_labels):
    output = {
        "strategy_id": "chips_big_holder",
        "updated":     now_tw_str(),
        "source":      SOURCE_URL,
        "date_labels": date_labels,
        "results":     results,
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已寫入 {OUTPUT_PATH}（{len(results)} 支）")


if __name__ == "__main__":
    main()
