#!/usr/bin/env python3
"""
爬取 PTT Stock 版 [標的] 文章，解析股票代號、多空方向與推噓數。
採滾動 30 天視窗，輸出 data/ptt_stock.json。
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "ptt_stock.json")

TW_TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TW_TZ)
TODAY = NOW.date()
RETAIN_DAYS = 30

PTT_BASE = "https://www.ptt.cc"
PTT_STOCK_INDEX = f"{PTT_BASE}/bbs/Stock/index.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Cookie": "over18=1",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

# 台股代號：4位(上市)、5位(上櫃)、6位0開頭(ETF)
# 用 (?<!\d) / (?!\d) 取代 \b，避免 Python Unicode 模式把中文視為 \w
STOCK_CODE_RE = re.compile(r'(?<!\d)(0[0-9]{4,5}|[1-9][0-9]{3,4})(?!\d)')
# 美股 ticker：2~5 個大寫英文字母，後可接 .US
# 用 (?<![A-Za-z]) / (?![A-Za-z]) 取代 \b，避免中文字符也被視為 \w
US_TICKER_RE = re.compile(r'(?<![A-Za-z])([A-Z]{2,5})(?:\.US)?(?![A-Za-z])')

# 多空情緒關鍵字（順序重要，長字串先比對）
SENTIMENT_PATTERNS = [
    (re.compile(r'中性|觀望|持有'), "neutral"),
    (re.compile(r'偏多|看多|小多'),  "bullish"),
    (re.compile(r'偏空|看空|小空'),  "bearish"),
    (re.compile(r'\b多\b|多$|多\s'), "bullish"),
    (re.compile(r'\b空\b|空$|空\s'), "bearish"),
]


def _parse_push_count(text: str) -> int:
    """解析 PTT 推文數：爆=100，X1~X9 = -10~-90，其餘為整數。"""
    text = text.strip()
    if text == "爆":
        return 100
    m = re.match(r'^X(\d)$', text)
    if m:
        return -int(m.group(1)) * 10
    try:
        return int(text)
    except ValueError:
        return 0


def _extract_stock_info(title: str) -> tuple[str | None, str | None, str | None, str]:
    """從標題解析 (stock_id, stock_name, sentiment, market)。
    market: 'TW' | 'US' | 'unknown'
    """
    clean = re.sub(r'^\[標的\]\s*', '', title).strip()

    stock_id: str | None = None
    stock_name: str | None = None
    market = "unknown"
    name_start = 0

    # 優先嘗試台股代號
    m = STOCK_CODE_RE.search(clean)
    if m:
        stock_id = m.group(1)
        name_start = m.end()
        market = "TW"
        # 名稱：緊接代號之後的中英文詞（忽略括號與空白）
        after = clean[name_start:].strip().lstrip("(（")
        nm = re.match(r'^([A-Za-z\u4e00-\u9fff\u3100-\u312f]+)', after)
        if nm:
            candidate = nm.group(1).strip()
            if len(candidate) >= 2:
                stock_name = candidate
    else:
        # 嘗試美股 ticker（開頭第一組大寫英文）
        mu = US_TICKER_RE.search(clean)
        if mu:
            # 排除常見中文注音或干擾詞
            _IGNORE = {"ETF", "EPS", "ROE", "ROA", "OTC", "IPO", "GDP", "KD", "MA"}
            ticker = mu.group(1)
            if ticker not in _IGNORE:
                stock_id = ticker
                market = "US"
                name_start = mu.end()

    # 情緒
    sentiment: str | None = None
    for pattern, label in SENTIMENT_PATTERNS:
        if pattern.search(clean):
            sentiment = label
            break

    return stock_id, stock_name, sentiment, market


def _full_date(date_str: str) -> str:
    """把 PTT 的 M/DD 格式補成 YYYY-MM-DD。"""
    m = re.match(r'(\d{1,2})/(\d{1,2})', date_str.strip())
    if not m:
        return TODAY.isoformat()
    month, day = int(m.group(1)), int(m.group(2))
    year = TODAY.year
    if month > TODAY.month or (month == TODAY.month and day > TODAY.day):
        year -= 1
    return f"{year}-{month:02d}-{day:02d}"


def fetch_page(url: str) -> BeautifulSoup | None:
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")
    except Exception as exc:
        print(f"  ⚠️  fetch 失敗 {url}：{exc}")
        return None


def parse_index_page(soup: BeautifulSoup) -> tuple[list[dict[str, Any]], str | None]:
    """解析文章列表頁，回傳 (posts, prev_page_url)。"""
    posts: list[dict[str, Any]] = []

    for ent in soup.select("div.r-ent"):
        title_tag = ent.select_one("div.title a")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        if not title.startswith("[標的]"):
            continue

        link = title_tag.get("href", "")
        nrec_span = ent.select_one("div.nrec span")
        push_raw = nrec_span.get_text(strip=True) if nrec_span else "0"
        push_net = _parse_push_count(push_raw)

        author = (ent.select_one("div.author") or ent.select_one("div.meta div.author"))
        date_el = ent.select_one("div.date")
        author_text = author.get_text(strip=True) if author else ""
        date_text = date_el.get_text(strip=True) if date_el else ""

        stock_id, stock_name, sentiment, market = _extract_stock_info(title)

        article_id_m = re.search(r'(M\.\d+\.A\.\w+)', link)
        post_id = article_id_m.group(1) if article_id_m else link

        posts.append({
            "id": post_id,
            "url": PTT_BASE + link,
            "title": title,
            "stock_id": stock_id,
            "stock_name": stock_name,
            "sentiment": sentiment,
            "market": market,
            "author": author_text,
            "date": _full_date(date_text),
            "pushes": max(push_net, 0),
            "boos": max(-push_net, 0),
        })

    # 找「上頁」按鈕（PTT 實際文字為 '‹ 上頁'）
    prev_url: str | None = None
    for a in soup.select("div.action-bar a.btn.wide"):
        if "上頁" in a.get_text():
            href = a.get("href", "")
            if href and "index" in href and href != "/bbs/Stock/index.html":
                prev_url = PTT_BASE + href
            break

    return posts, prev_url


def load_existing() -> list[dict[str, Any]]:
    if not os.path.exists(OUTPUT_PATH):
        return []
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            return json.load(f).get("posts", [])
    except Exception:
        return []


def build_stocks_summary(posts: list[dict[str, Any]]) -> dict[str, Any]:
    stocks: dict[str, dict[str, Any]] = {}
    for p in posts:
        sid = p.get("stock_id")
        if not sid:
            continue
        if sid not in stocks:
            stocks[sid] = {
                "stock_id": sid,
                "stock_name": p.get("stock_name") or sid,
                "posts_30d": 0,
                "bullish": 0,
                "bearish": 0,
                "neutral": 0,
                "unknown": 0,
                "net_pushes": 0,
                "latest_date": "",
            }
        s = stocks[sid]
        s["posts_30d"] += 1
        s["net_pushes"] += p.get("pushes", 0) - p.get("boos", 0)
        sent = p.get("sentiment")
        if sent == "bullish":
            s["bullish"] += 1
        elif sent == "bearish":
            s["bearish"] += 1
        elif sent == "neutral":
            s["neutral"] += 1
        else:
            s["unknown"] += 1
        date = p.get("date", "")
        if date > s["latest_date"]:
            s["latest_date"] = date
            if p.get("stock_name"):
                s["stock_name"] = p["stock_name"]

    return dict(
        sorted(stocks.items(), key=lambda x: (-x[1]["posts_30d"], -x[1]["net_pushes"]))
    )


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"=== PTT Stock [標的] 爬取 {NOW.strftime('%Y-%m-%d %H:%M')} ===")

    existing = load_existing()
    existing_ids = {p["id"] for p in existing}
    print(f"  現有資料：{len(existing)} 筆")

    # 爬取最新頁，遇到全是舊文章就停，最多翻 5 頁
    new_posts: list[dict[str, Any]] = []
    url: str | None = PTT_STOCK_INDEX
    pages_fetched = 0

    while url and pages_fetched < 5:
        print(f"  爬取：{url}")
        soup = fetch_page(url)
        if not soup:
            break

        page_posts, prev_url = parse_index_page(soup)
        new_on_page = [p for p in page_posts if p["id"] not in existing_ids]
        new_posts.extend(new_on_page)

        print(f"    [標的] {len(page_posts)} 篇，新增 {len(new_on_page)} 篇")

        pages_fetched += 1
        # 本頁有找到 [標的] 文章、但全是舊資料 → 停止往前翻
        if page_posts and not new_on_page:
            break
        url = prev_url
        if url:
            time.sleep(0.8)

    print(f"  本次新增：{len(new_posts)} 篇")

    # 合併、去重、保留 30 天
    cutoff = (TODAY - timedelta(days=RETAIN_DAYS)).isoformat()
    all_posts = new_posts + existing
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for p in all_posts:
        pid = p["id"]
        if pid in seen:
            continue
        seen.add(pid)
        if (p.get("date") or "") >= cutoff:
            merged.append(p)

    merged.sort(key=lambda p: p.get("date", ""), reverse=True)
    print(f"  保留（{RETAIN_DAYS} 天內）：{len(merged)} 筆")

    stocks = build_stocks_summary(merged)

    out: dict[str, Any] = {
        "updated": TODAY.isoformat(),
        "retain_days": RETAIN_DAYS,
        "total_posts": len(merged),
        "posts": merged,
        "stocks": stocks,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  ✅ 輸出 ptt_stock.json：{len(merged)} 篇文章，{len(stocks)} 支標的")
    if stocks:
        print("  熱門標的 TOP 5：")
        for s in list(stocks.values())[:5]:
            bull, bear = s["bullish"], s["bearish"]
            print(
                f"    {s['stock_id']} {s['stock_name']}：{s['posts_30d']} 篇  "
                f"多 {bull} / 空 {bear}  推 {s['net_pushes']:+d}  ({s['latest_date']})"
            )


if __name__ == "__main__":
    main()
