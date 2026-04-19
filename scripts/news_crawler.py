#!/usr/bin/env python3
"""
新聞爬蟲模組
主要來源：鉅亨網 cnyes API
備援來源：FinMind TaiwanStockNews
每支股票抓近 5 天、最多 10 篇標題 + 摘要（不需全文，節省 token）
"""

import os
import requests
from datetime import datetime, timedelta, timezone

TW_TZ = timezone(timedelta(hours=8))
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://news.cnyes.com/",
}

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"


# ── 鉅亨網 ───────────────────────────────────────────

def _cnyes_fetch(stock_id: str, limit: int = 10) -> list[dict]:
    """
    鉅亨網個股新聞 API
    回傳格式：[{"title": str, "summary": str, "date": str}, ...]
    """
    now_ts   = int(datetime.now(TW_TZ).timestamp())
    start_ts = int((datetime.now(TW_TZ) - timedelta(days=5)).timestamp())

    url = "https://api.cnyes.com/media/api/v1/newslist/category/tw_stock"
    params = {
        "symbolId": stock_id,
        "limit":    limit,
        "startAt":  start_ts,
        "endAt":    now_ts,
    }

    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        items = data.get("items", {}).get("data", [])
        results = []
        for item in items[:limit]:
            results.append({
                "title":   item.get("title", "").strip(),
                "summary": item.get("summary", "").strip()[:200],
                "date":    item.get("publishAt", "")[:10] if item.get("publishAt") else "",
            })
        return results
    except Exception:
        return []


# ── FinMind 備援 ──────────────────────────────────────

def _finmind_fetch(stock_id: str, limit: int = 10) -> list[dict]:
    """FinMind TaiwanStockNews 備援"""
    token      = os.environ.get("FINMIND_TOKEN", "")
    start_date = (datetime.now(TW_TZ) - timedelta(days=5)).strftime("%Y-%m-%d")

    try:
        r = requests.get(FINMIND_API, params={
            "dataset":    "TaiwanStockNews",
            "data_id":    stock_id,
            "start_date": start_date,
            "token":      token,
        }, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        if data.get("status") != 200:
            return []
        items = data.get("data", [])
        results = []
        for item in items[:limit]:
            results.append({
                "title":   item.get("title", "").strip(),
                "summary": item.get("description", "").strip()[:200],
                "date":    item.get("date", "")[:10],
            })
        return results
    except Exception:
        return []


# ── 公開介面 ──────────────────────────────────────────

def fetch_news(stock_id: str, limit: int = 10) -> list[dict]:
    """
    抓取個股新聞，優先鉅亨網，失敗則用 FinMind。
    回傳 list of {"title", "summary", "date"}
    """
    news = _cnyes_fetch(stock_id, limit)
    if not news:
        news = _finmind_fetch(stock_id, limit)
    return news


def format_news_for_prompt(news: list[dict]) -> str:
    """將新聞列表格式化成 prompt 用的純文字"""
    if not news:
        return "（近期無相關新聞）"
    lines = []
    for i, n in enumerate(news, 1):
        title   = n.get("title", "")
        summary = n.get("summary", "")
        date    = n.get("date", "")
        line = f"{i}. [{date}] {title}"
        if summary and summary != title:
            line += f"\n   {summary}"
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    # 測試用
    sid = "2330"
    news = fetch_news(sid)
    print(f"=== {sid} 新聞 ({len(news)} 篇) ===")
    print(format_news_for_prompt(news))
