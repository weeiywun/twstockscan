#!/usr/bin/env python3
"""
量增訊號標的營收維護主腳本
觸發條件：量增訊號掃出新標的（首次進入）
流程：月營收評級 + 籌碼量化評分 → 寫入 ai_analysis.json
每日也更新 active 標的現價、損益、剩餘天數，並處理到期移轉。
未釘選歷史保留 5 個交易日；釘選標的持續保留。
"""

import json
import os
import time
from datetime import date, datetime, timedelta, timezone

from finmind_client import fetch_stock_price, fetch_month_revenue, load_price_cache, get_stock_price_from_cache

# ── 路徑 ──────────────────────────────────────────────
SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_DIR         = os.path.join(SCRIPT_DIR, "..", "data")
VS_PATH          = os.path.join(DATA_DIR, "volume_signal.json")
SA_PATH          = os.path.join(DATA_DIR, "ai_analysis.json")
CHIPS_PATH       = os.path.join(DATA_DIR, "chips_big_holder.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")

# ── 觀察天數 ──────────────────────────────────────────
OBSERVE_TRADING_DAYS = 10   # 入選後觀察 10 個交易日
HISTORY_KEEP_TRADING_DAYS = 5

# ════════════════════════════════════════════════════
#  v1.6 評分引擎
# ════════════════════════════════════════════════════

def _quant_chip_trapezoid(big_pct: float) -> float:
    """籌碼集中度：梯形防禦模型 (0-10分)"""
    if big_pct < 30:             return 0.0
    elif big_pct < 45:           return (big_pct - 30) / 15 * 10.0
    elif big_pct <= 65:          return 10.0
    elif big_pct <= 80:          return (80 - big_pct) / 15 * 10.0
    else:                        return 0.0

def _quant_trend(cumulative_3w: float) -> float:
    """籌碼趨勢：近三週累積增幅 (0-10分)"""
    return min(max(cumulative_3w / 5 * 10.0, 0.0), 10.0)

def _quant_revenue(yoy_curr: float, mom_curr: float, yoy_last: float) -> tuple[float, str]:
    """營收動能：雙引擎矩陣 (回傳分數與等級)"""
    if yoy_curr > 0 and mom_curr > 0:
        return (10.0, 'S') if yoy_curr > yoy_last else (8.0, 'A')
    elif yoy_curr > 0:
        return (6.0, 'B')
    elif mom_curr > 0:
        return (4.0, 'C')
    else:
        return (0.0, 'D')

def compute_revenue_metrics(revenue_data: list[dict]) -> tuple[float, float, float] | None:
    """從月營收列表計算 (yoy_curr, mom_curr, yoy_last)，需至少 14 筆。"""
    if not revenue_data or len(revenue_data) < 14:
        return None
    rev_curr       = revenue_data[-1]["revenue"]
    rev_last_month = revenue_data[-2]["revenue"]
    rev_12m_ago    = revenue_data[-13]["revenue"]
    rev_13m_ago    = revenue_data[-14]["revenue"]
    if not all([rev_last_month, rev_12m_ago, rev_13m_ago]):
        return None
    yoy_curr = (rev_curr - rev_12m_ago)    / rev_12m_ago    * 100
    mom_curr = (rev_curr - rev_last_month) / rev_last_month * 100
    yoy_last = (rev_last_month - rev_13m_ago) / rev_13m_ago * 100
    return round(yoy_curr, 1), round(mom_curr, 1), round(yoy_last, 1)

def calculate_v1_6_score(
    ai_news_score: float,
    ai_industry_score: float,
    chip_3w_pct: float,
    chip_big_pct: float,
    rev_yoy_curr: float,
    rev_mom_curr: float,
    rev_yoy_last: float,
) -> dict:
    """主計算引擎：產出最終 0-100 分與決策建議"""
    trend_score          = _quant_trend(chip_3w_pct)
    chip_score           = _quant_chip_trapezoid(chip_big_pct)
    rev_score, rev_grade = _quant_revenue(rev_yoy_curr, rev_mom_curr, rev_yoy_last)

    base_raw = (
        ai_news_score     * 0.25 +
        ai_industry_score * 0.15 +
        trend_score       * 0.20 +
        chip_score        * 0.20 +
        rev_score         * 0.20
    )
    base_score = base_raw * 10

    multiplier = 1.0
    action_log = "基礎計分"
    if rev_grade == 'D' and trend_score <= 2:
        multiplier = 0.6
        action_log = "觸發致命懲罰 (營收衰退或主力未買)"
    elif trend_score >= 8 and rev_grade == 'C':
        multiplier = 1.25
        action_log = "觸發營收破冰共振 (谷底翻揚且主力狂買)"

    final_score = min(round(base_score * multiplier), 100)

    if final_score >= 70:
        recommendation = "buy"
    elif final_score >= 50:
        recommendation = "watch"
    else:
        recommendation = "avoid"

    return {
        "final_score":    final_score,
        "recommendation": recommendation,
        "base_score":     round(base_score, 1),
        "multiplier":     multiplier,
        "action_log":     action_log,
        "rev_grade":      rev_grade,
        "quant_scores": {
            "trend_score": round(trend_score, 1),
            "chip_score":  round(chip_score, 1),
            "rev_score":   round(rev_score, 1),
        },
    }


# ════════════════════════════════════════════════════
#  交易日計算（忽略假日，只排週末，夠用）
# ════════════════════════════════════════════════════

def add_trading_days(start: date, n: int) -> date:
    """從 start 往後加 n 個交易日（週一到週五）"""
    d, added = start, 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def classify_priority(item: dict) -> tuple[str, list[str]]:
    scores = item.get("quant_scores") or {}
    rev_score = float(scores.get("rev_score") or 0)
    chip_score = float(scores.get("chip_score") or 0)
    trend_score = float(scores.get("trend_score") or 0)
    reasons: list[str] = []

    if rev_score >= 8:
        reasons.append("營收分數>=8")
    if chip_score >= 6:
        reasons.append("籌碼分數>=6")
    if trend_score >= 4:
        reasons.append("趨勢分數>=4")

    if rev_score >= 8 and chip_score >= 6:
        return "A", reasons or ["營收與籌碼共振"]
    if rev_score >= 6 or chip_score >= 6:
        return "B", reasons or ["單一品質條件達標"]
    return "C", reasons or ["品質條件待觀察"]

def trading_days_remaining(expire: date, today: date) -> int:
    """今日到 expire 之間還有幾個交易日（含 expire 當天）"""
    if today > expire:
        return 0
    d, count = today, 0
    while d <= expire:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def keep_history_item(item: dict, today: date) -> bool:
    if item.get("pinned"):
        return True
    remove_date = item.get("remove_date")
    return bool(remove_date) and date.fromisoformat(remove_date) >= today


def normalize_history_retention(items: list[dict], today: date) -> None:
    keep_until = add_trading_days(today, HISTORY_KEEP_TRADING_DAYS).isoformat()
    for item in items:
        if item.get("pinned"):
            continue
        remove_date = item.get("remove_date")
        if not remove_date or date.fromisoformat(remove_date) > date.fromisoformat(keep_until):
            item["remove_date"] = keep_until



# ════════════════════════════════════════════════════
#  現價更新
# ════════════════════════════════════════════════════

def fetch_close(stock_id: str, finmind_token: str, price_cache=None) -> float | None:
    start = (datetime.now(TW_TZ) - timedelta(days=5)).strftime("%Y-%m-%d")
    if price_cache is not None:
        df = get_stock_price_from_cache(price_cache, stock_id, start)
        if df is not None and len(df) > 0:
            return round(float(df.iloc[-1]["close"]), 2)
    df = fetch_stock_price(stock_id, start, TODAY, finmind_token)
    if df is None or len(df) == 0:
        return None
    return round(float(df.iloc[-1]["close"]), 2)


# ════════════════════════════════════════════════════
#  主流程
# ════════════════════════════════════════════════════

def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print("=== 量增訊號標的營收維護腳本 ===")
    finmind_token = os.environ.get("FINMIND_TOKEN", "")

    if not finmind_token:
        print("⚠️  FINMIND_TOKEN 未設定，無法更新現價")

    # ── 載入價格快取（用於現價更新，避免逐支 API 請求）──
    price_cache = load_price_cache()
    if price_cache is not None:
        print(f"  price_cache.parquet 已載入：{price_cache['stock_id'].nunique()} 支")

    # ── 讀入資料 ─────────────────────────────────────
    vs_data   = load_json(VS_PATH)
    sa_data   = load_json(SA_PATH)
    today_obj = date.fromisoformat(TODAY)

    vs_results  = vs_data.get("results", [])        # 今日量增訊號
    active_list = sa_data.get("active", [])
    expired_list = sa_data.get("expired", [])

    active_tickers = {s["ticker"] for s in active_list}

    print(f"今日量增訊號：{len(vs_results)} 支　現有追蹤：{len(active_list)} 支")

    # ── 判斷新進標的 ──────────────────────────────────
    new_stocks = [s for s in vs_results if s["stock_id"] not in active_tickers]
    print(f"新進標的：{len(new_stocks)} 支")

    # ── 新標的入池 ────────────────────────────────────
    for stock in new_stocks:
        sid  = stock["stock_id"]
        name = stock["name"]
        print(f"\n  入池 {sid} {name}...")

        # 月營收
        yoy_curr = mom_curr = yoy_last = 0.0
        if finmind_token:
            rev_data = fetch_month_revenue(sid, finmind_token)
            metrics  = compute_revenue_metrics(rev_data) if rev_data else None
            if metrics:
                yoy_curr, mom_curr, yoy_last = metrics
                print(f"    月營收 YoY={yoy_curr:+.1f}% MoM={mom_curr:+.1f}%")
            else:
                print(f"    月營收資料不足，使用中立值")
            time.sleep(0.35)

        # 量化評分（ai_news / ai_industry 固定中立 5.0，不呼叫外部 AI）
        result = calculate_v1_6_score(
            ai_news_score     = 5.0,
            ai_industry_score = 5.0,
            chip_3w_pct       = stock.get("cumulative_3w") or 0.0,
            chip_big_pct      = stock.get("big_pct_1000") or 40.0,
            rev_yoy_curr      = yoy_curr,
            rev_mom_curr      = mom_curr,
            rev_yoy_last      = yoy_last,
        )

        expire_obj  = add_trading_days(today_obj, OBSERVE_TRADING_DAYS)
        days_remain = trading_days_remaining(expire_obj, today_obj)

        entry = {
            "ticker":         sid,
            "name":           name,
            "industry":       stock.get("industry", ""),
            "trigger_date":   TODAY,
            "expire_date":    expire_obj.isoformat(),
            "days_remaining": days_remain,
            "entry_price":    stock.get("close", 0),
            "current_price":  stock.get("close", 0),
            "pnl_pct":        0.0,
            "rev_grade":      result["rev_grade"],
            "quant_scores":   result["quant_scores"],
            "pinned":         False,
        }
        priority_level, priority_reason = classify_priority(entry)
        entry["priority_level"] = priority_level
        entry["priority_reason"] = priority_reason
        active_list.append(entry)
        print(f"    ✅ {sid} 入池，到期 {expire_obj}，營收等級 {result['rev_grade']}")

    # ── 每日更新：active 現價 & 損益 & 剩餘天數 ─────────
    print(f"\n更新 active 標的現價（{len(active_list)} 支）...")
    still_active, newly_expired = [], []

    for item in active_list:
        sid = item["ticker"]
        priority_level, priority_reason = classify_priority(item)
        item["priority_level"] = priority_level
        item["priority_reason"] = priority_reason

        # 更新剩餘天數
        expire_obj = date.fromisoformat(item["expire_date"])
        days_remain = trading_days_remaining(expire_obj, today_obj)
        item["days_remaining"] = days_remain

        # 更新現價
        if finmind_token:
            price = fetch_close(sid, finmind_token, price_cache)
            if price:
                item["current_price"] = price
                entry_price = item.get("entry_price") or price
                item["pnl_pct"] = round((price - entry_price) / entry_price * 100, 2) if entry_price else 0.0
            if price_cache is None:
                time.sleep(0.35)

        if days_remain <= 0:
            # 移入歷史
            remove_date = add_trading_days(today_obj, HISTORY_KEEP_TRADING_DAYS).isoformat()
            expired_entry = {
                **item,
                "entry_date":  item.get("trigger_date", item.get("entry_date", "")),
                "remove_date": remove_date,
                "pinned":      bool(item.get("pinned", False)),
            }
            newly_expired.append(expired_entry)
            print(f"  📦 {sid} 到期 → 移入歷史")
        else:
            still_active.append(item)

    # ── 合併歷史、移除未釘選且超過保留期限的紀錄 ─────────
    expired_list.extend(newly_expired)
    normalize_history_retention(expired_list, today_obj)
    expired_list = [
        e for e in expired_list
        if keep_history_item(e, today_obj)
    ]

    # 歷史區也每日更新現價
    if finmind_token:
        print(f"更新 expired 現價（{len(expired_list)} 支）...")
        for item in expired_list:
            price = fetch_close(item["ticker"], finmind_token, price_cache)
            if price:
                item["current_price"] = price
                ep = item.get("entry_price") or price
                item["pnl_pct"] = round((price - ep) / ep * 100, 2) if ep else 0.0
            if price_cache is None:
                time.sleep(0.35)

    # ── 寫出 ──────────────────────────────────────────
    sa_out = {
        "last_updated": TODAY,
        "active":       still_active,
        "expired":      expired_list,
    }
    save_json(SA_PATH, sa_out)
    print(f"\n✅ ai_analysis.json 已更新　active={len(still_active)}　expired={len(expired_list)}")


if __name__ == "__main__":
    main()
