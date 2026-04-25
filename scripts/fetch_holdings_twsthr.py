#!/usr/bin/env python3
"""
大戶持股分析器 v3.0  (Layer 1 週末籌碼海選)
讀取 data/big1000.csv（千張大戶）與 data/big400.csv（400張大戶）
股價/EMA120 透過 FinMind API 取得。

篩選邏輯：
  先決安全濾網：5日均量 > 500張、|乖離EMA120| <= 10%、千張大戶比例 > 30%
  標籤（可複選）：
    持續成長 +1：連續兩週 R > 0%（任一門檻）
    雙軌觸發 +3：R_400 >= 2.0% 或 R_1000 >= 1.25%
    單周增幅 +5：最新一週 R > 3.0%（任一門檻）
  R = (本週持股% - 上週持股%) / 上週持股% * 100%
"""

import csv, json, os, re, time
from datetime import datetime, timedelta, timezone
from finmind_client import fetch_stock_price

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
CSV_1000    = os.path.join(DATA_DIR, "big1000.csv")
CSV_400     = os.path.join(DATA_DIR, "big400.csv")
OUTPUT_PATH = os.path.join(DATA_DIR, "chips_big_holder.json")

TW_TZ         = timezone(timedelta(hours=8))
TODAY         = datetime.now(TW_TZ).strftime("%Y-%m-%d")
START_DATE    = (datetime.now(TW_TZ) - timedelta(days=180)).strftime("%Y-%m-%d")
BIG_PCT_MIN   = 30.0
EMA_PERIOD    = 120
VOL_MIN_LOTS  = 500
DEV_MIN, DEV_MAX = -10.0, 10.0
BBW_MAX       = 15.0
FINMIND_SLEEP = 0.35
FLEX_MAX      = 15
FC_PRIMARY    = "#e66e29"
FC_ACCENT     = "#0c6b3e"


# ── CSV 解析 ──────────────────────────────────────────────────

def parse_csv(path, encoding):
    stocks = {}
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        headers   = reader.fieldnames or []
        date_cols = sorted([h for h in headers if re.fullmatch(r"\d{8}", h)])
        for row in reader:
            raw = (row.get("股票") or "").strip()
            if not raw:
                continue
            parts = raw.split(None, 1)
            if len(parts) < 2 or not re.fullmatch(r"\d{4}", parts[0]):
                continue
            sid, name = parts[0], parts[1].strip()
            mc_raw = (row.get("市值(億)") or "").replace(",", "").strip()
            try:
                market_cap = float(mc_raw) if mc_raw else None
            except ValueError:
                market_cap = None
            pct_map = {}
            for d in date_cols:
                val = (row.get(d) or "").strip()
                try:
                    pct_map[d] = float(val)
                except ValueError:
                    pass
            stocks[sid] = {
                "name": name, "industry": (row.get("類別") or "").strip(),
                "market_cap": market_cap, "pct_map": pct_map,
            }
    return stocks, date_cols


# ── 標籤計算 ──────────────────────────────────────────────────

def calc_r(pct_map, date_cols, week_offset=0):
    valid = [d for d in date_cols if d in pct_map]
    idx = -(week_offset + 1)
    if len(valid) < abs(idx) + 1:
        return None
    this_w = pct_map[valid[idx]]
    prev_w = pct_map[valid[idx - 1]]
    if prev_w == 0:
        return None
    return (this_w - prev_w) / prev_w * 100.0


def compute_tags(pct_1000, dates_1000, pct_400, dates_400):
    tags, score = [], 0
    r1n = calc_r(pct_1000, dates_1000, 0)
    r1p = calc_r(pct_1000, dates_1000, 1)
    r4n = calc_r(pct_400, dates_400, 0) if pct_400 else None
    r4p = calc_r(pct_400, dates_400, 1) if pct_400 else None

    g1 = r1n is not None and r1p is not None and r1n > 0 and r1p > 0
    g4 = r4n is not None and r4p is not None and r4n > 0 and r4p > 0
    if g1 or g4:
        tags.append("持續成長"); score += 1

    if (r4n is not None and r4n >= 2.0) or (r1n is not None and r1n >= 1.25):
        tags.append("雙軌觸發"); score += 3

    if (r1n is not None and r1n > 3.0) or (r4n is not None and r4n > 3.0):
        tags.append("單周增幅"); score += 5

    return tags, score


def calc_cumulative_3w(pct_map, date_cols):
    valid = [d for d in date_cols if d in pct_map]
    if len(valid) < 4:
        return None
    latest, three_ago = pct_map[valid[-1]], pct_map[valid[-4]]
    if three_ago == 0:
        return None
    return round((latest - three_ago) / three_ago * 100.0, 2)


# ── FinMind 價格 ──────────────────────────────────────────────

def _calc_ema(closes, span):
    if len(closes) < span // 2:
        return None
    k = 2 / (span + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    return ema


def _calc_bbw(closes, period=20, num_std=2):
    """Bollinger Band Width = (Upper - Lower) / Middle × 100%"""
    if len(closes) < period:
        return None
    window = closes[-period:]
    sma    = sum(window) / period
    std    = (sum((c - sma) ** 2 for c in window) / period) ** 0.5
    if sma == 0:
        return None
    return round((num_std * 2 * std) / sma * 100.0, 2)


def enrich_with_price(stock_id, token):
    df = fetch_stock_price(stock_id, START_DATE, TODAY, token)
    if df is None or len(df) < 10:
        return None
    closes  = df["close"].tolist()
    volumes = df["volume_lots"].tolist()
    ema120  = _calc_ema(closes, EMA_PERIOD)
    if ema120 is None:
        return None
    close_now = closes[-1]
    deviation = round((close_now - ema120) / ema120 * 100.0, 2)
    vol_5d    = round(sum(volumes[-5:]) / min(5, len(volumes)), 0)
    wago      = closes[-6] if len(closes) >= 6 else closes[0]
    week_chg  = round((close_now - wago) / wago * 100.0, 2) if wago else None
    bbw       = _calc_bbw(closes)
    return {
        "close": round(close_now, 2), "ema120": round(ema120, 2),
        "deviation": deviation, "vol_5d_avg": int(vol_5d),
        "week_chg_pct": week_chg, "bbw": bbw,
    }


# ── LINE 推播 ──────────────────────────────────────────────────

def send_line_notification(results):
    import requests as req
    token   = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    raw_ids = os.environ.get("LINE_USER_IDS") or os.environ.get("LINE_USER_ID")
    if not token or not raw_ids:
        print("[LINE] 未設定，跳過"); return
    user_ids = [u.strip() for u in raw_ids.split(",") if u.strip()]
    items = sorted(results, key=lambda r: r["tag_score"], reverse=True)[:FLEX_MAX]
    rows = []
    for r in items:
        tag_str  = " ".join(r["tags"]) if r["tags"] else "—"
        cum_text = f"3週 {r['cumulative_3w']:+.1f}%" if r.get("cumulative_3w") is not None else "—"
        dev_text = f"乖離 {r['deviation']:+.1f}%" if r.get("deviation") is not None else "—"
        rows.append({"type": "separator", "margin": "md"})
        rows.append({"type": "box", "layout": "horizontal", "margin": "md", "paddingAll": "4px",
                     "contents": [
                         {"type": "box", "layout": "vertical", "flex": 3, "contents": [
                             {"type": "text", "text": r["stock_id"], "size": "md",
                              "weight": "bold", "color": FC_PRIMARY},
                             {"type": "text", "text": r["name"], "size": "xs", "color": "#555"},
                             {"type": "text", "text": tag_str, "size": "xxs", "color": FC_PRIMARY}]},
                         {"type": "box", "layout": "vertical", "flex": 2, "contents": [
                             {"type": "text", "text": f"{r['close']:.1f}" if r.get("close") else "—",
                              "size": "sm", "align": "center", "weight": "bold"},
                             {"type": "text", "text": dev_text, "size": "xs",
                              "align": "center", "color": "#888"}]},
                         {"type": "box", "layout": "vertical", "flex": 2, "contents": [
                             {"type": "text", "text": f"{r['big_pct_1000']:.1f}%",
                              "size": "sm", "align": "center", "weight": "bold"},
                             {"type": "text", "text": cum_text, "size": "xs",
                              "align": "center", "color": FC_ACCENT}]}]})
    if len(results) > FLEX_MAX:
        rows.append({"type": "text",
                     "text": f"...還有 {len(results) - FLEX_MAX} 支，請查看完整報告",
                     "size": "xs", "color": "#aaa", "margin": "md", "align": "center"})
    bubble = {
        "type": "bubble", "size": "mega",
        "header": {"type": "box", "layout": "vertical", "paddingAll": "20px",
                   "backgroundColor": "#f7f8fa", "contents": [
                       {"type": "text", "text": "◈ 籌碼集中選股",
                        "weight": "bold", "size": "lg", "color": FC_PRIMARY},
                       {"type": "box", "layout": "horizontal", "margin": "md",
                        "contents": [
                            {"type": "text", "text": f"📅 {TODAY}", "size": "xs", "color": "#aaa"},
                            {"type": "text", "text": f"✅ {len(results)} 支符合",
                             "size": "xs", "color": FC_ACCENT, "align": "end"}]}]},
        "body": {"type": "box", "layout": "vertical", "paddingAll": "20px",
                 "contents": [
                     {"type": "box", "layout": "horizontal", "contents": [
                         {"type": "text", "text": "代號/名稱/標籤", "size": "xxs",
                          "color": "#aaa", "flex": 3},
                         {"type": "text", "text": "收盤/乖離", "size": "xxs",
                          "color": "#aaa", "flex": 2, "align": "center"},
                         {"type": "text", "text": "千張%/3週", "size": "xxs",
                          "color": "#aaa", "flex": 2, "align": "center"}]},
                     *rows]},
        "footer": {"type": "box", "layout": "vertical", "paddingAll": "12px",
                   "contents": [{"type": "button", "style": "primary", "height": "sm",
                                 "color": FC_PRIMARY,
                                 "action": {"type": "uri", "label": "📈 查看完整報告",
                                            "uri": "https://weeiywun.github.io/twstockscan/"}}]},
    }
    flex_msg = {"type": "flex",
                "altText": f"◈ 籌碼集中選股 {TODAY}：{len(results)} 支符合條件",
                "contents": bubble}
    try:
        resp = req.post(
            "https://api.line.me/v2/bot/message/multicast",
            json={"to": user_ids, "messages": [flex_msg]},
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            timeout=15)
        print("[LINE] 推播成功" if resp.status_code == 200
              else f"[LINE] 推播失敗：HTTP {resp.status_code}")
    except Exception as e:
        print(f"[LINE] 推播例外：{e}")


# ── 主程式 ────────────────────────────────────────────────────

def now_tw():
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _write_output(results):
    output = {"strategy_id": "chips_big_holder", "updated": now_tw(), "results": results}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 已寫入 {OUTPUT_PATH}")


def load_prev_consecutive(output_path) -> dict:
    """載入上週結果，回傳 {stock_id: consecutive_weeks}"""
    if not os.path.exists(output_path):
        return {}
    try:
        with open(output_path, encoding="utf-8") as f:
            prev = json.load(f)
        return {r["stock_id"]: r.get("consecutive_weeks", 1)
                for r in prev.get("results", [])}
    except Exception:
        return {}


def main():
    print("=== 大戶持股分析器 v3.0 (Layer 1) ===")
    finmind_token = os.environ.get("FINMIND_TOKEN", "")
    if not finmind_token:
        print("⚠️  FINMIND_TOKEN 未設定")

    # 讀入上週結果，計算連續進榜週數
    prev_consecutive = load_prev_consecutive(OUTPUT_PATH)

    print("\nStep 1：讀取 big1000.csv / big400.csv...")
    stocks_1000, dates_1000 = parse_csv(CSV_1000, "utf-8-sig")
    stocks_400,  dates_400  = parse_csv(CSV_400,  "utf-8-sig")
    print(f"  big1000: {len(stocks_1000)} 支，{len(dates_1000)} 週")
    print(f"  big400:  {len(stocks_400)} 支，{len(dates_400)} 週")

    print(f"\nStep 2：初篩（千張大戶比例 > {BIG_PCT_MIN}%）並計算標籤...")
    candidates = []
    for sid, s1 in stocks_1000.items():
        if not s1["pct_map"]:
            continue
        latest_pct = s1["pct_map"].get(max(s1["pct_map"]))
        if latest_pct is None or latest_pct < BIG_PCT_MIN:
            continue
        s4 = stocks_400.get(sid)
        tags, score = compute_tags(
            s1["pct_map"], dates_1000,
            s4["pct_map"] if s4 else None,
            dates_400     if s4 else None)
        if score == 0:
            continue
        recent_d  = [d for d in dates_1000 if d in s1["pct_map"]][-4:]
        pct_trend = [round(s1["pct_map"][d], 2) for d in recent_d]
        d_labels  = [f"{d[4:6]}/{d[6:8]}" for d in recent_d]
        pct_400_t = None
        if s4:
            r4d = [d for d in dates_400 if d in s4["pct_map"]][-4:]
            pct_400_t = [round(s4["pct_map"][d], 2) for d in r4d]
        prev_weeks = prev_consecutive.get(sid, 0)
        consecutive_weeks = prev_weeks + 1 if prev_weeks >= 1 else 1

        candidates.append({
            "stock_id":          sid,
            "name":              s1["name"],
            "industry":          s1["industry"],
            "market_cap":        s1["market_cap"],
            "big_pct_1000":      round(latest_pct, 2),
            "big_pct_400":       round(s4["pct_map"].get(max(s4["pct_map"]), 0), 2) if s4 and s4["pct_map"] else None,
            "cumulative_3w":     calc_cumulative_3w(s1["pct_map"], dates_1000),
            "cumulative_3w_400":  round((pct_400_t[-1] - pct_400_t[0]) / pct_400_t[0] * 100.0, 2) if pct_400_t is not None and len(pct_400_t) == 4 and pct_400_t[0] != 0 else None,
            "tags":              tags,
            "tag_score":         score,
            "big_trend_1000":    pct_trend,
            "big_trend_400":     pct_400_t,
            "date_labels":       d_labels,
            "consecutive_weeks": consecutive_weeks,
        })

    print(f"  通過標籤篩選：{len(candidates)} 支")
    if not candidates:
        print("⚠️  無符合條件股票")
        _write_output([]); return

    print(f"\nStep 3：FinMind 取得股價（{len(candidates)} 支，間隔 {FINMIND_SLEEP}s）...")
    results, ok, fail = [], 0, 0
    for i, c in enumerate(candidates, 1):
        price = enrich_with_price(c["stock_id"], finmind_token)
        if price is None:
            fail += 1
        elif (price["vol_5d_avg"] < VOL_MIN_LOTS
              or not (DEV_MIN <= price["deviation"] <= DEV_MAX)
              or (price["bbw"] is not None and price["bbw"] > BBW_MAX)):
            pass
        else:
            ok += 1
            results.append({**c, **price})
        if i % 50 == 0:
            print(f"  進度：{i}/{len(candidates)}，通過 {len(results)} / 失敗 {fail}")
        time.sleep(FINMIND_SLEEP)

    results.sort(key=lambda r: (r.get("cumulative_3w") or 0) + (r.get("cumulative_3w_400") or 0), reverse=True)
    print(f"\n  最終入池 {len(results)} 支")
    _write_output(results)
    send_line_notification(results)


if __name__ == "__main__":
    main()
