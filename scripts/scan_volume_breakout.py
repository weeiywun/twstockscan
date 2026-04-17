#!/usr/bin/env python3
"""
爆量追蹤選股策略 (Volume Breakout Scanner)
盤後自動執行，篩選符合「爆量突破 → 縮量洗盤 → 等待二次啟動」型態的台股。

策略模組：
  模組一：季線（60MA）趨勢走平或向上，收盤 > 60MA
  模組二：T日 = 3~8 個交易日內存在：量>20MA量×3、收盤漲>4%、實體紅K
  模組三：T+1 到今日：每日量 < T日量×35%、每日收盤 ≥ T日最低
  模組四：今日量 > 前5日均量×1.5（溫和放量），今日收 > T日以來最高（突破洗盤區）

執行方式：
  python scan_volume_breakout.py          # 全市場掃描
  python scan_volume_breakout.py --quick  # 快速測試（前200支）
"""

import json
import time
import warnings
import sys
import os
from datetime import datetime, timedelta

import requests
import pandas as pd
import numpy as np
from finmind_client import fetch_all_stocks

warnings.filterwarnings("ignore")

TODAY = datetime.now().strftime("%Y-%m-%d")

# 輸出路徑：scripts/ 的上一層是 repo root，再進 data/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "..", "data", "volume_breakout.json")

# ─────────────────────────────────────────────────────────────
#  台灣股市休市日（國定假日 + 彈性放假）
#  注意：此列表需每年初依行政院公告手動更新！
#  格式：{"MM-DD": "假日名稱"}，僅列平日休市（六日已由 cron 排除）
# ─────────────────────────────────────────────────────────────
TW_MARKET_HOLIDAYS = {
    # ── 2026 年台灣股市休市日 ──
    "01-01": "元旦",
    "01-26": "農曆除夕",
    "01-27": "農曆春節",
    "01-28": "農曆春節",
    "01-29": "農曆春節",
    "01-30": "農曆春節",
    "02-02": "春節補假",
    "02-28": "和平紀念日",
    "04-03": "清明節",
    "06-19": "端午節",
    "09-25": "中秋節",
    "10-09": "國慶日補假",
    "10-10": "國慶日",
}


# ─────────────────────────────────────────────────────────────
#  Step 1：取得股票清單
# ─────────────────────────────────────────────────────────────

def get_stock_list():
    """取得上市 + 上櫃普通股清單"""
    stocks = []

    # ── 上市 (TWSE) ──
    for attempt in range(2):
        try:
            url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            for item in r.json():
                sid = item.get("Code", "").strip()
                name = item.get("Name", "").strip()
                if len(sid) == 4 and sid.isdigit():
                    stocks.append({"stock_id": sid, "name": name, "market": "TWSE"})
            twse_count = sum(1 for s in stocks if s["market"] == "TWSE")
            print(f"  上市股票：{twse_count} 支")
            break
        except Exception as e:
            if attempt == 0:
                print(f"  上市清單取得失敗，3秒後重試：{e}")
                time.sleep(3)
            else:
                print(f"  上市清單取得失敗（已重試）：{e}")

    # ── 上櫃 (TPEx) ──
    for attempt in range(2):
        try:
            url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            for item in r.json():
                sid = (item.get("SecuritiesCompanyCode") or item.get("Code") or "").strip()
                name = (item.get("CompanyName") or item.get("Name") or "").strip()
                if len(sid) == 4 and sid.isdigit():
                    stocks.append({"stock_id": sid, "name": name, "market": "TPEX"})
            tpex_count = sum(1 for s in stocks if s["market"] == "TPEX")
            print(f"  上櫃股票：{tpex_count} 支")
            break
        except Exception as e:
            if attempt == 0:
                print(f"  上櫃清單取得失敗，3秒後重試：{e}")
                time.sleep(3)
            else:
                print(f"  上櫃清單取得失敗（已重試）：{e}")

    return stocks


# ─────────────────────────────────────────────────────────────
#  Step 2：策略核心運算
# ─────────────────────────────────────────────────────────────

def check_strategy(close, open_, high, low, volume, dates):
    """
    套用四個模組篩選條件。

    參數：
        close, open_, high, low, volume：np.ndarray，按時間升序排列
        dates：DatetimeIndex，與上述陣列對齊

    回傳：
        (True, result_dict)  符合全部基礎條件（模組一~三）
        (False, None)        不符合
    """
    n = len(close)
    if n < 70:  # 60(MA) + 10(緩衝)
        return False, None

    # ────── 模組一：基礎位階濾網 ──────
    today_ma60 = float(np.mean(close[-60:]))

    # 條件 1：60MA 走平或翻揚（比較今日 MA60 與 5 個交易日前的 MA60）
    if n < 65:
        return False, None
    ma60_5d_ago = float(np.mean(close[-65:-5]))
    cond1 = today_ma60 >= ma60_5d_ago * 0.999   # 允許 0.1% 的走平誤差

    # 條件 2：今日收盤 > 60MA
    cond2 = float(close[-1]) > today_ma60

    if not (cond1 and cond2):
        return False, None

    # ────── 模組二：尋找爆量突破日（T日）──────
    # T日距今 i 個交易日 → 陣列負索引 -(i+1)
    #   i=3 → 今日=-1, 昨日=-2, 前天=-3, T日=-4
    #   i=8 → T日=-9
    t_idx = None
    t_i = None

    for i in range(3, 9):
        idx = -(i + 1)
        abs_idx = n + idx   # 轉為正索引

        # 確保 T日前有足夠的 20 日資料
        if abs_idx < 22:
            continue

        vol_20ma = float(np.mean(volume[idx - 20:idx]))
        if vol_20ma <= 0:
            continue

        # 條件 3：T日量 > 20日均量 × 3
        cond3 = float(volume[idx]) > vol_20ma * 3.0

        # 條件 4：T日收盤漲幅 > 4%
        prev_close = float(close[idx - 1])
        if prev_close <= 0:
            continue
        cond4 = (float(close[idx]) - prev_close) / prev_close > 0.04

        # 條件 5：T日收盤 > T日開盤（實體紅K）
        cond5 = float(close[idx]) > float(open_[idx])

        if cond3 and cond4 and cond5:
            t_idx = idx
            t_i = i
            break

    if t_idx is None:
        return False, None

    # ────── 模組三：洗盤期驗證（T+1 到今日）──────
    t_vol = float(volume[t_idx])
    t_low = float(low[t_idx])
    t_close_price = float(close[t_idx])

    washout_vol = volume[t_idx + 1:]    # T+1 到今日（含今日）
    washout_close = close[t_idx + 1:]

    if len(washout_vol) == 0:
        return False, None

    # 條件 7：洗盤期每日量 < T日量 × 35%
    cond7 = bool(np.all(washout_vol < t_vol * 0.35))

    # 條件 8：洗盤期每日收盤 ≥ T日最低價
    cond8 = bool(np.all(washout_close >= t_low))

    if not (cond7 and cond8):
        return False, None

    # ────── 模組四：發動確認（資訊性，不作為通過條件）──────
    today_vol = float(volume[-1])
    vol_5ma_prev = float(np.mean(volume[-6:-1]))  # 今日前5日均量

    # 條件 9：今日量 > 前5日均量 × 1.5
    cond9 = (today_vol > vol_5ma_prev * 1.5) if vol_5ma_prev > 0 else False

    # 條件 10：今日收盤 > T日以來（含T日）最高價
    since_t_high = float(np.max(high[t_idx:]))
    cond10 = float(close[-1]) > since_t_high

    # ────── 整理輸出資料 ──────
    t_vol_20ma = float(np.mean(volume[t_idx - 20:t_idx]))
    t_change_pct = (float(close[t_idx]) / float(close[t_idx - 1]) - 1) * 100

    abs_t_idx = n + t_idx
    t_date_str = str(dates[abs_t_idx])[:10]   # YYYY-MM-DD

    result = {
        # 今日資料
        "close":           round(float(close[-1]), 2),
        "ma60":            round(today_ma60, 2),
        "deviation_ma60":  round((float(close[-1]) - today_ma60) / today_ma60 * 100, 2),
        # T日資料
        "t_date":          t_date_str,
        "t_change_pct":    round(t_change_pct, 2),
        "t_vol_ratio":     round(t_vol / t_vol_20ma, 1) if t_vol_20ma > 0 else 0,
        "t_low":           round(t_low, 2),
        "t_close":         round(t_close_price, 2),
        # 洗盤期資料
        "days_since_t":    int(len(washout_vol)),   # T+1 到今日共幾天
        # 模組四
        "phase4_activated": bool(cond9 and cond10),
        "cond9_vol_ratio":  round(today_vol / vol_5ma_prev, 2) if vol_5ma_prev > 0 else 0,
    }

    return True, result


# ─────────────────────────────────────────────────────────────
#  Step 3：下載資料（FinMind）+ 主流程
# ─────────────────────────────────────────────────────────────

def main(quick_test=False):
    print("=" * 55)
    print(f"  爆量追蹤選股  {TODAY}")
    print("=" * 55)

    # ── 判斷是否為休市日 ──
    today_mmdd = datetime.now().strftime("%m-%d")
    if today_mmdd in TW_MARKET_HOLIDAYS:
        holiday_name = TW_MARKET_HOLIDAYS[today_mmdd]
        print(f"今日為休市日 ({TODAY} {holiday_name})，跳過掃描")
        sys.exit(0)

    # ── 取得股票清單 ──
    print("\n[1] 取得股票清單...")
    stocks = get_stock_list()
    if not stocks:
        print("無法取得股票清單，結束執行")
        sys.exit(1)

    if quick_test:
        stocks = stocks[:200]
        print(f"    ⚡ 快速測試模式：僅掃描前 {len(stocks)} 支")

    print(f"    合計：{len(stocks)} 支\n")

    # 資料範圍：需要約 90 個交易日 ≈ 160 個日曆天
    end_date   = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=160)).strftime("%Y-%m-%d")

    # ── 批次下載全市場資料（yfinance）──
    print("[2] 下載股價資料（yfinance）...")
    stock_data = fetch_all_stocks(stocks, start_date, end_date)

    if not stock_data:
        print("無法取得任何股票資料，結束執行")
        sys.exit(1)

    # ── 套用策略 ──
    print("\n[3] 套用爆量追蹤策略...")
    results       = []
    total_scanned = 0
    total_skipped = 0

    for s in stocks:
        sid = s["stock_id"]
        df  = stock_data.get(sid)

        if df is None or df.empty or len(df) < 70:
            total_skipped += 1
            continue

        total_scanned += 1
        try:
            close  = df["Close"].values.astype(float)
            open_  = df["Open"].values.astype(float)
            high   = df["High"].values.astype(float)
            low    = df["Low"].values.astype(float)
            volume = df["Volume"].values.astype(float)
            dates  = df.index

            passed, result = check_strategy(close, open_, high, low, volume, dates)

            if passed:
                result["stock_id"] = sid
                result["name"]     = s["name"]
                result["market"]   = s["market"]
                results.append(result)
        except Exception:
            pass

    # ── 輸出結果 ──
    print(f"\n{'='*55}")
    print(f"  篩選完成！符合條件：{len(results)} 支")
    coverage_rate = round(total_scanned / len(stocks) * 100, 1) if stocks else 0
    print(f"  掃描覆蓋率：{total_scanned:,} / {len(stocks):,}（{coverage_rate}%）")
    if total_skipped:
        print(f"  資料不足跳過：{total_skipped} 支")
    print(f"{'='*55}\n")

    if results:
        results.sort(key=lambda x: x["t_vol_ratio"], reverse=True)
        print(f"{'代號':<6} {'名稱':<10} {'T日':>10} {'量比':>6} {'T漲幅':>8} {'洗盤天':>6} {'模組四':>6}")
        print("-" * 60)
        for r in results:
            p4 = "★" if r["phase4_activated"] else " "
            print(
                f"{r['stock_id']:<6} {r['name'][:8]:<10} "
                f"{r['t_date']:>10} {r['t_vol_ratio']:>5.1f}x "
                f"{r['t_change_pct']:>+7.2f}% {r['days_since_t']:>5}天  {p4}"
            )

    output = {
        "strategy_id": "volume_breakout",
        "updated": TODAY,
        "total": len(results),
        "scan_coverage": {
            "scanned": total_scanned,
            "total": len(stocks),
            "rate": round(total_scanned / len(stocks) * 100, 1) if stocks else 0,
            "skipped_batches": total_skipped,
        },
        "results": results,
    }

    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n結果已寫入：{os.path.abspath(OUTPUT_PATH)}")

    # ── 寫入歷史紀錄 ──
    history_dir = os.path.join(SCRIPT_DIR, "..", "data", "history")
    os.makedirs(history_dir, exist_ok=True)
    history_path = os.path.join(history_dir, f"volume_breakout_{TODAY}.json")
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"歷史紀錄已寫入：{os.path.abspath(history_path)}")

    # ── LINE 推播通知 ──
    send_line_notification(results)

    return results


FLEX_MAX_STOCKS = 15          # Flex Message 最多顯示股票數，避免超過 LINE 50KB 限制
FLEX_COLOR_PRIMARY = "#0c6b3e"
FLEX_COLOR_PHASE4_ON = "#a86200"
FLEX_COLOR_PHASE4_OFF = "#cccccc"


def build_flex_message(results):
    """組裝 Flex Message JSON"""

    if not results:
        bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "📊 爆量追蹤選股", "weight": "bold", "size": "lg", "color": FLEX_COLOR_PRIMARY},
                ],
                "paddingAll": "20px",
                "backgroundColor": "#f7f8fa"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "今日無符合條件標的", "size": "md", "color": "#888888", "align": "center", "margin": "xl"}
                ],
                "paddingAll": "20px"
            }
        }
        return {"type": "flex", "altText": f"📊 爆量追蹤選股 {TODAY}：無符合條件標的", "contents": bubble}

    stock_rows = []
    for r in results[:FLEX_MAX_STOCKS]:
        p4_color = FLEX_COLOR_PHASE4_ON if r["phase4_activated"] else FLEX_COLOR_PHASE4_OFF
        p4_text = "★ 發動" if r["phase4_activated"] else "—"

        stock_rows.append({"type": "separator", "margin": "md"})
        stock_rows.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": r["stock_id"], "size": "md", "weight": "bold", "color": FLEX_COLOR_PRIMARY},
                        {"type": "text", "text": r["name"], "size": "xs", "color": "#555555"}
                    ],
                    "flex": 3
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"{r['t_vol_ratio']}x", "size": "sm", "align": "center", "weight": "bold"},
                        {"type": "text", "text": f"{r['t_change_pct']:+.1f}%", "size": "xs", "align": "center", "color": "#c0392b"}
                    ],
                    "flex": 2
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"{r['days_since_t']}天", "size": "xs", "align": "center", "color": "#888888"},
                        {"type": "text", "text": p4_text, "size": "xs", "align": "center", "color": p4_color, "weight": "bold"}
                    ],
                    "flex": 2
                }
            ],
            "margin": "md",
            "paddingAll": "4px"
        })

    if len(results) > FLEX_MAX_STOCKS:
        stock_rows.append({"type": "separator", "margin": "md"})
        stock_rows.append({"type": "text", "text": f"...還有 {len(results) - FLEX_MAX_STOCKS} 支，請查看完整報告", "size": "xs", "color": "#aaaaaa", "margin": "md", "align": "center"})

    phase4_count = sum(1 for r in results if r["phase4_activated"])

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "📊 爆量追蹤選股", "weight": "bold", "size": "lg", "color": FLEX_COLOR_PRIMARY},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"📅 {TODAY}", "size": "xs", "color": "#aaaaaa"},
                        {"type": "text", "text": f"✅ {len(results)} 支符合", "size": "xs", "color": FLEX_COLOR_PRIMARY, "align": "end"},
                    ],
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"★ 模組四啟動：{phase4_count} 支", "size": "xs", "color": FLEX_COLOR_PHASE4_ON}
                    ],
                    "margin": "sm"
                }
            ],
            "paddingAll": "20px",
            "backgroundColor": "#f7f8fa"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "代號/名稱", "size": "xxs", "color": "#aaaaaa", "flex": 3},
                        {"type": "text", "text": "量比/漲幅", "size": "xxs", "color": "#aaaaaa", "flex": 2, "align": "center"},
                        {"type": "text", "text": "洗盤/模四", "size": "xxs", "color": "#aaaaaa", "flex": 2, "align": "center"},
                    ]
                },
                *stock_rows
            ],
            "paddingAll": "20px"
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "action": {
                        "type": "uri",
                        "label": "📈 查看完整報告",
                        "uri": "https://weeiywun.github.io/twstockscan/"
                    },
                    "style": "primary",
                    "color": "#0c6b3e",
                    "height": "sm"
                }
            ],
            "paddingAll": "12px"
        }
    }

    return {"type": "flex", "altText": f"📊 爆量追蹤選股 {TODAY}：{len(results)} 支符合條件", "contents": bubble}


def send_line_notification(results):
    """透過 LINE Messaging API 推播爆量追蹤掃描結果（Flex Message）。"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    # 支援多人：LINE_USER_IDS 以逗號分隔，例如 "Uabc123,Uxyz789"
    # 相容舊版單一 LINE_USER_ID
    raw_ids = os.environ.get("LINE_USER_IDS") or os.environ.get("LINE_USER_ID")

    if not token or not raw_ids:
        print("\n[LINE] 環境變數未設定，跳過推播通知")
        return

    user_ids = [uid.strip() for uid in raw_ids.split(",") if uid.strip()]
    print(f"[LINE] 推播對象：{len(user_ids)} 人，IDs = {[uid[:8]+'...' for uid in user_ids]}")

    flex_msg = build_flex_message(results)

    payload = {
        "userIds": user_ids,
        "messages": [flex_msg],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        resp = requests.post(
            "https://api.line.me/v2/bot/message/multicast",
            json=payload,
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            print("[LINE] 推播通知已成功送出")
        else:
            print(f"[LINE] 推播失敗：HTTP {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[LINE] 推播通知發生例外：{e}")


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    main(quick_test=quick)
