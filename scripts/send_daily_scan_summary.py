#!/usr/bin/env python3
"""
每日選股掃描完成通知。

維持既有 LINE Flex Message 卡片骨架：
- Header：日期與摘要
- Hero：績效追蹤折線圖
- Body：目前持倉摘要 + 精選觀察 Top 5
- Footer：回到前端績效頁
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
PERFORMANCE_PATH = os.path.join(DATA_DIR, "performance.json")
CURRENT_PRICES_PATH = os.path.join(DATA_DIR, "current_prices.json")
MOMENTUM_CANDIDATES_PATH = os.path.join(DATA_DIR, "momentum_candidates.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")
SITE_URL = "https://weeiywun.github.io/twstockscan/?unlock=perf"
PERFORMANCE_IMAGE_URL = "https://weeiywun.github.io/twstockscan/assets/line/performance-latest.png"

FLEX_PRIMARY = "#0c6b3e"
FLEX_ACCENT = "#f0883e"
FLEX_MUTED = "#888888"
FLEX_BG = "#f7f8fa"
FLEX_TEXT = "#333333"
FLEX_LIGHT = "#aaaaaa"
MAX_HOLDINGS = 4
MAX_FOCUS = 5


def performance_image_url() -> str:
    base_url = os.environ.get("LINE_PERFORMANCE_IMAGE_URL", PERFORMANCE_IMAGE_URL).strip()
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}v={TODAY.replace('-', '')}"


def load_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        print(f"[summary] 找不到 {path}")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_price(value: Any) -> str:
    n = num(value)
    return "--" if n is None else f"{n:.1f}"


def fmt_pct(value: Any) -> str:
    n = num(value)
    return "--" if n is None else f"{n:+.1f}%"


def flex_text(text: str, size: str = "xs", color: str = FLEX_MUTED, **extra: Any) -> dict:
    return {"type": "text", "text": text, "size": size, "color": color, **extra}


def remaining_shares(position: dict[str, Any]) -> int:
    shares = int(num(position.get("shares"), 0) or 0)
    exits = position.get("exits") or []
    sold = sum(int(num(exit_row.get("shares"), 0) or 0) for exit_row in exits)
    if position.get("exit_price") is not None and not exits:
        sold = shares
    return max(0, shares - sold)


def holding_comment(pnl_pct: float | None) -> str:
    if pnl_pct is None:
        return "等待現價"
    if pnl_pct >= 10:
        return "守移動停利"
    if pnl_pct >= 5:
        return "續抱觀察"
    if pnl_pct >= 0:
        return "接近成本"
    if pnl_pct >= -3:
        return "留意支撐"
    return "檢查停損"


def build_holdings() -> list[dict[str, Any]]:
    perf = load_json(PERFORMANCE_PATH)
    prices = load_json(CURRENT_PRICES_PATH).get("prices", {})
    holdings: list[dict[str, Any]] = []
    for pos in perf.get("positions", []):
        remain = remaining_shares(pos)
        if remain <= 0:
            continue
        sid = str(pos.get("stock_id") or "")
        current = num(prices.get(sid), num(pos.get("current_price"), num(pos.get("entry_price"))))
        cost = num(pos.get("cost_price"), num(pos.get("entry_price")))
        pnl_pct = ((current - cost) / cost * 100) if current is not None and cost else None
        holdings.append({
            "stock_id": sid,
            "name": pos.get("name") or "",
            "shares": remain,
            "cost": cost,
            "current": current,
            "pnl_pct": pnl_pct,
            "comment": holding_comment(pnl_pct),
        })
    holdings.sort(key=lambda row: row["pnl_pct"] if row["pnl_pct"] is not None else -999, reverse=True)
    return holdings


def build_focus_items() -> list[dict[str, Any]]:
    data = load_json(MOMENTUM_CANDIDATES_PATH)
    rows = data.get("focus_results") or [
        row for row in data.get("results", []) if row.get("focus_candidate")
    ]
    rows.sort(key=lambda row: (row.get("priority_rank", 9), -(num(row.get("score"), 0) or 0), row.get("stock_id", "")))
    return rows[:MAX_FOCUS]


def section_title(title: str, subtitle: str) -> dict:
    return {
        "type": "box",
        "layout": "horizontal",
        "contents": [
            flex_text(title, "sm", FLEX_TEXT, weight="bold", flex=3),
            flex_text(subtitle, "xs", FLEX_LIGHT, align="end", flex=2),
        ],
    }


def holding_row(item: dict[str, Any]) -> dict:
    pnl = num(item.get("pnl_pct"))
    pnl_color = FLEX_PRIMARY if pnl is not None and pnl >= 0 else "#d93025"
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "sm",
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "flex": 3,
                "contents": [
                    flex_text(f"{item['stock_id']} {item['name']}", "sm", FLEX_TEXT, weight="bold"),
                    flex_text(f"成本 {fmt_price(item.get('cost'))} / 現價 {fmt_price(item.get('current'))}", "xxs", FLEX_MUTED),
                ],
            },
            flex_text(fmt_pct(pnl), "sm", pnl_color, weight="bold", align="end", flex=1),
            flex_text(f"| {item['comment']}", "xs", FLEX_MUTED, align="end", flex=2),
        ],
        "paddingAll": "4px",
    }


def focus_row(item: dict[str, Any]) -> dict:
    metrics = item.get("metrics", {})
    vol_ratio = metrics.get("today_vol_ratio") or metrics.get("ignition_vol_ratio") or metrics.get("track_vol_ratio")
    track = metrics.get("track_pnl_pct")
    status = item.get("status") or "觀察"
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "sm",
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "flex": 3,
                "contents": [
                    flex_text(f"{item.get('stock_id', '')} {item.get('name', '')}", "sm", FLEX_TEXT, weight="bold"),
                    flex_text(status, "xxs", FLEX_ACCENT),
                ],
            },
            {
                "type": "box",
                "layout": "vertical",
                "flex": 2,
                "contents": [
                    flex_text(fmt_price(item.get("close")), "sm", FLEX_TEXT, weight="bold", align="center"),
                    flex_text("收盤", "xxs", FLEX_LIGHT, align="center"),
                ],
            },
            {
                "type": "box",
                "layout": "vertical",
                "flex": 2,
                "contents": [
                    flex_text(f"{num(vol_ratio, 0):.2f}x" if vol_ratio is not None else "--", "sm", FLEX_PRIMARY, weight="bold", align="center"),
                    flex_text(f"追蹤 {fmt_pct(track)}", "xxs", FLEX_MUTED, align="center"),
                ],
            },
        ],
        "paddingAll": "4px",
    }


def empty_row(text: str) -> dict:
    return flex_text(text, "xs", FLEX_MUTED, wrap=True, align="center")


def card_section(contents: list[dict]) -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "sm",
        "paddingAll": "12px",
        "backgroundColor": "#ffffff",
        "cornerRadius": "6px",
        "contents": contents,
    }


def build_flex_message(holdings: list[dict[str, Any]], focus_items: list[dict[str, Any]]) -> dict:
    holdings_content = [section_title("目前持倉", f"{len(holdings)} 檔")]
    holdings_content.extend([holding_row(item) for item in holdings[:MAX_HOLDINGS]])
    if not holdings:
        holdings_content.append(empty_row("目前沒有持倉資料"))

    focus_content = [section_title("精選觀察 Top 5", f"{len(focus_items)} 檔")]
    focus_content.extend([focus_row(item) for item in focus_items[:MAX_FOCUS]])
    if not focus_items:
        focus_content.append(empty_row("今日沒有符合精選觀察的標的"))

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "backgroundColor": FLEX_BG,
            "contents": [
                flex_text("每日選股掃描完成", "lg", FLEX_PRIMARY, weight="bold"),
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                        flex_text(f"日期 {TODAY}", "xs", FLEX_LIGHT),
                        flex_text(f"精選 {len(focus_items)} 檔", "xs", FLEX_ACCENT, align="end"),
                    ],
                },
            ],
        },
        "hero": {
            "type": "image",
            "url": performance_image_url(),
            "size": "full",
            "aspectRatio": "20:9",
            "aspectMode": "cover",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "md",
            "backgroundColor": FLEX_BG,
            "contents": [
                card_section(holdings_content),
                card_section(focus_content),
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": FLEX_PRIMARY,
                    "action": {"type": "uri", "label": "查看績效追蹤", "uri": SITE_URL},
                }
            ],
        },
    }
    return {
        "type": "flex",
        "altText": f"每日選股掃描 {TODAY}：精選觀察 {len(focus_items)} 檔",
        "contents": bubble,
    }


def send_line_message(message: dict) -> bool:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    raw_ids = os.environ.get("LINE_USER_IDS") or os.environ.get("LINE_USER_ID")
    if not token or not raw_ids:
        print("[LINE] 未設定 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_IDS，略過成功通知")
        return True

    user_ids = [user_id.strip() for user_id in raw_ids.split(",") if user_id.strip()]
    if not user_ids:
        print("[LINE] LINE_USER_IDS 為空，略過成功通知")
        return True

    payload = json.dumps({"to": user_ids, "messages": [message]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/multicast",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                print("[LINE] 每日掃描摘要推播成功")
                return True
            body = resp.read().decode("utf-8", errors="replace")
            print(f"[LINE] 每日掃描摘要推播失敗：HTTP {resp.status} {body}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[LINE] 每日掃描摘要推播失敗：HTTP {e.code} {body}")
        return False
    except urllib.error.URLError as e:
        print(f"[LINE] 每日掃描摘要推播例外：{e}")
        return False


def main() -> int:
    holdings = build_holdings()
    focus_items = build_focus_items()
    print(f"[summary] 持倉 {len(holdings)} 檔 / 精選觀察 {len(focus_items)} 檔")
    message = build_flex_message(holdings, focus_items)
    return 0 if send_line_message(message) else 1


if __name__ == "__main__":
    raise SystemExit(main())
