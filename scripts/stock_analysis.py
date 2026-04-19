#!/usr/bin/env python3
"""
標的分析主腳本
觸發條件：量增訊號掃出新標的（首次進入）
流程：新聞爬蟲 → Claude API 評分 → 寫入 ai_analysis.json
每日也更新 active 標的現價、損益、剩餘天數，並處理到期移轉。
"""

import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone

import requests

from finmind_client import fetch_stock_price
from news_crawler import fetch_news, format_news_for_prompt

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

# ── 評分權重（第一版，後續迭代調整） ─────────────────────
# 質性（Claude 打分，各 0-10）× 權重
# 量化（現有數據換算 0-10）× 權重
# 加總後 × 10 → 最終 0-100 分
SCORE_WEIGHTS = {
    "法說會":   0.15,   # qualitative
    "利多利空": 0.15,   # qualitative
    "產業預期": 0.12,   # qualitative
    "特殊因素": 0.08,   # qualitative
    "籌碼集中": 0.20,   # quantitative: big_pct_1000
    "籌碼趨勢": 0.20,   # quantitative: cumulative_3w
    "量能":     0.10,   # quantitative: vol_ratio
}
# sum(weights) == 1.0

# ── 建議門檻 ──────────────────────────────────────────
THRESHOLD_BUY   = 70
THRESHOLD_WATCH = 50


# ════════════════════════════════════════════════════
#  量化分數換算（0-10）
# ════════════════════════════════════════════════════

def _quant_chip(big_pct: float) -> float:
    """千張大戶比例 30%→0, 50%→10，線性"""
    return min(max((big_pct - 30) / 20 * 10, 0), 10)

def _quant_trend(cumulative_3w: float) -> float:
    """3週增幅 0%→0, 5%→10，線性，上限 10"""
    return min(max(cumulative_3w / 5 * 10, 0), 10)

def _quant_vol(vol_ratio: float) -> float:
    """量比 1.5x→0, 3x→10，線性"""
    return min(max((vol_ratio - 1.5) / 1.5 * 10, 0), 10)


def compute_composite(claude_scores: dict, quant_data: dict) -> int:
    quant = {
        "籌碼集中": _quant_chip(quant_data.get("big_pct_1000") or 30),
        "籌碼趨勢": _quant_trend(quant_data.get("cumulative_3w") or 0),
        "量能":     _quant_vol(quant_data.get("vol_ratio") or 1.5),
    }
    all_scores = {**claude_scores, **quant}
    raw = sum(all_scores.get(k, 5) * w for k, w in SCORE_WEIGHTS.items())
    return round(raw * 10)   # 0-100


def recommendation_from_score(score: int) -> str:
    if score >= THRESHOLD_BUY:
        return "buy"
    if score >= THRESHOLD_WATCH:
        return "watch"
    return "avoid"


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


# ════════════════════════════════════════════════════
#  Claude API 分析
# ════════════════════════════════════════════════════

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

PROMPT_TEMPLATE = """你是台股分析師，請根據以下資料對股票進行客觀評分分析。

=== 股票資訊 ===
代號：{ticker}　名稱：{name}　產業：{industry}

=== 量化數據 ===
現價：{close}　千張大戶比例：{big_pct}%　3週籌碼增幅：{cumulative_3w}%　今日量比：{vol_ratio}x

=== 近期新聞（近 5 天）===
{news_text}

=== 評分規則 ===
請對以下四個維度各給 1~10 分（整數）：
1. 法說會：近期是否有正面財報、法說會前佈局、獲利上修等訊號
2. 利多利空：具體事件對股價的正負面影響強度
3. 產業預期：所屬產業趨勢與市場展望（正面=高分）
4. 特殊因素：轉單效應、併購、政策利多、技術突破等（無則給 5）

若新聞不足，請依產業背景合理推估，不可全給 5。

請只回覆以下 JSON，不加任何其他文字：
{{
  "scores": {{
    "法說會": <int>,
    "利多利空": <int>,
    "產業預期": <int>,
    "特殊因素": <int>
  }},
  "summary": "<一句話總結，30 字以內>",
  "risk": "<主要風險一句話，30 字以內>"
}}"""


def call_gemini(stock: dict, news_text: str, api_key: str) -> dict | None:
    """呼叫 Gemini API，回傳解析後的 dict 或 None"""
    prompt = PROMPT_TEMPLATE.format(
        ticker        = stock["stock_id"],
        name          = stock["name"],
        industry      = stock.get("industry", "未知"),
        close         = stock.get("close", "—"),
        big_pct       = stock.get("big_pct_1000") or "—",
        cumulative_3w = stock.get("cumulative_3w") or "—",
        vol_ratio     = stock.get("vol_ratio") or "—",
        news_text     = news_text,
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    try:
        resp = requests.post(
            GEMINI_API_URL, params={"key": api_key}, json=payload, timeout=30
        )
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            print(f"  ⚠️  Gemini 回覆無法解析 JSON：{raw[:80]}")
            return None
        return json.loads(json_match.group())
    except Exception as e:
        print(f"  ⚠️  Gemini API 錯誤：{e}")
        return None


# ════════════════════════════════════════════════════
#  現價更新
# ════════════════════════════════════════════════════

def fetch_close(stock_id: str, finmind_token: str) -> float | None:
    start = (datetime.now(TW_TZ) - timedelta(days=5)).strftime("%Y-%m-%d")
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
    print("=== 標的分析腳本 ===")
    gemini_key    = os.environ.get("GEMINI_API_KEY", "")
    finmind_token = os.environ.get("FINMIND_TOKEN", "")

    if not gemini_key:
        print("⚠️  GEMINI_API_KEY 未設定，跳過 AI 分析")
    if not finmind_token:
        print("⚠️  FINMIND_TOKEN 未設定，無法更新現價")

    # ── 讀入資料 ─────────────────────────────────────
    vs_data   = load_json(VS_PATH)
    sa_data   = load_json(SA_PATH)
    today_obj = date.fromisoformat(TODAY)

    vs_results  = vs_data.get("results", [])        # 今日量增訊號
    active_list = sa_data.get("active", [])
    expired_list = sa_data.get("expired", [])

    active_tickers = {s["ticker"] for s in active_list}

    print(f"今日量增訊號：{len(vs_results)} 支　現有追蹤：{len(active_list)} 支")

    # expired 中有記錄代表曾被分析過（重複訊號）
    expired_map = {e["ticker"]: e for e in expired_list}

    # ── 判斷新進標的 ──────────────────────────────────
    new_stocks = [s for s in vs_results if s["stock_id"] not in active_tickers]
    print(f"新進標的：{len(new_stocks)} 支 → 觸發 AI 分析")

    # ── AI 分析新標的 ─────────────────────────────────
    for stock in new_stocks:
        sid  = stock["stock_id"]
        name = stock["name"]
        print(f"\n  分析 {sid} {name}...")

        # 新聞爬蟲
        news = fetch_news(sid, limit=10)
        print(f"    新聞：{len(news)} 篇")
        news_text = format_news_for_prompt(news)

        # Claude 評分
        ai_result = None
        if gemini_key:
            ai_result = call_gemini(stock, news_text, gemini_key)
            time.sleep(0.5)   # API rate limit buffer

        if ai_result:
            claude_scores = ai_result.get("scores", {})
            summary = ai_result.get("summary", "")
            risk    = ai_result.get("risk", "")
            print(f"    評分：{claude_scores}　摘要：{summary[:20]}...")
        else:
            # fallback：質性全給 5（中立）
            claude_scores = {"法說會": 5, "利多利空": 5, "產業預期": 5, "特殊因素": 5}
            summary = "AI 分析未能取得，以量化數據為主"
            risk    = "新聞資料不足，請手動確認基本面"

        composite = compute_composite(claude_scores, stock)
        rec       = recommendation_from_score(composite)

        expire_obj  = add_trading_days(today_obj, OBSERVE_TRADING_DAYS)
        days_remain = trading_days_remaining(expire_obj, today_obj)

        # 判斷是否為重複訊號（曾在 expired 清單中）
        prev_expired = expired_map.get(sid)
        is_repeat    = prev_expired is not None
        repeat_count = (prev_expired.get("repeat_count", 1) + 1) if is_repeat else 1

        entry = {
            "ticker":           sid,
            "name":             name,
            "industry":         stock.get("industry", ""),
            "trigger_date":     TODAY,
            "expire_date":      expire_obj.isoformat(),
            "days_remaining":   days_remain,
            "entry_price":      stock.get("close", 0),
            "current_price":    stock.get("close", 0),
            "pnl_pct":          0.0,
            "repeat":           is_repeat,
            "repeat_count":     repeat_count,
            "ai_analysis_date": TODAY,
            "composite_score":  composite,
            "recommendation":   rec,
            "scores":           claude_scores,
            "summary":          summary,
            "risk":             risk,
        }
        active_list.append(entry)
        print(f"    ✅ {sid} 綜合評分 {composite}（{rec}），到期 {expire_obj}")

    # ── 每日更新：active 現價 & 損益 & 剩餘天數 ─────────
    print(f"\n更新 active 標的現價（{len(active_list)} 支）...")
    still_active, newly_expired = [], []

    for item in active_list:
        sid = item["ticker"]

        # 更新剩餘天數
        expire_obj = date.fromisoformat(item["expire_date"])
        days_remain = trading_days_remaining(expire_obj, today_obj)
        item["days_remaining"] = days_remain

        # 更新現價
        if finmind_token:
            price = fetch_close(sid, finmind_token)
            if price:
                item["current_price"] = price
                entry_price = item.get("entry_price") or price
                item["pnl_pct"] = round((price - entry_price) / entry_price * 100, 2) if entry_price else 0.0
            time.sleep(0.35)

        if days_remain <= 0:
            # 移入歷史
            remove_date = (today_obj + timedelta(days=30)).isoformat()
            expired_entry = {
                "ticker":        item["ticker"],
                "name":          item["name"],
                "entry_date":    item["trigger_date"],
                "entry_price":   item["entry_price"],
                "current_price": item["current_price"],
                "pnl_pct":       item["pnl_pct"],
                "composite_score": item["composite_score"],
                "recommendation":  item["recommendation"],
                "repeat":          item.get("repeat", False),
                "repeat_count":    item.get("repeat_count", 1),
                "remove_date":     remove_date,
            }
            newly_expired.append(expired_entry)
            print(f"  📦 {sid} 到期 → 移入歷史")
        else:
            still_active.append(item)

    # ── 合併歷史、移除超過一個月的紀錄 ──────────────────
    expired_list.extend(newly_expired)
    expired_list = [
        e for e in expired_list
        if date.fromisoformat(e["remove_date"]) >= today_obj
    ]

    # 歷史區也每日更新現價
    if finmind_token:
        print(f"更新 expired 現價（{len(expired_list)} 支）...")
        for item in expired_list:
            price = fetch_close(item["ticker"], finmind_token)
            if price:
                item["current_price"] = price
                ep = item.get("entry_price") or price
                item["pnl_pct"] = round((price - ep) / ep * 100, 2) if ep else 0.0
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
