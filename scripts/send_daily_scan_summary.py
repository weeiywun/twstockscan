#!/usr/bin/env python3
"""
每日選股掃描完成通知
- 讀取 volume_signal.json / right_top.json / trust_momentum.json
- 統計今日入選標的數量
- 以 LINE Flex Message 推播摘要
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
VOLUME_PATH = os.path.join(DATA_DIR, "volume_signal.json")
RIGHT_TOP_PATH = os.path.join(DATA_DIR, "right_top.json")
TRUST_PATH = os.path.join(DATA_DIR, "trust_momentum.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")
SITE_URL = "https://weeiywun.github.io/twstockscan/?unlock=perf"

FLEX_PRIMARY = "#0c6b3e"
FLEX_ACCENT = "#f0883e"
FLEX_MUTED = "#888888"
FLEX_BG = "#f7f8fa"
MAX_PREVIEW = 5


def load_results(path: str) -> list[dict]:
    return load_section(path, "results")


def load_section(path: str, key: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"[summary] 找不到 {path}")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get(key, [])


def today_unique_results(results: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for item in results:
        if item.get("signal_date") != TODAY:
            continue
        sid = item.get("stock_id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        unique.append(item)
    return unique


def stock_preview(items: list[dict], metric_key: str, metric_suffix: str) -> str:
    if not items:
        return "今日無入選標的"
    parts = []
    for item in items[:MAX_PREVIEW]:
        metric = item.get(metric_key)
        metric_text = f" {metric:.2f}{metric_suffix}" if isinstance(metric, (int, float)) else ""
        parts.append(f"{item.get('stock_id', '')} {item.get('name', '')}{metric_text}".strip())
    if len(items) > MAX_PREVIEW:
        parts.append(f"+{len(items) - MAX_PREVIEW}")
    return "、".join(parts)


def summary_row(label: str, count: int, color: str, preview: str) -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "xs",
        "contents": [
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": label, "size": "sm", "color": "#333333", "weight": "bold", "flex": 4},
                    {"type": "text", "text": f"{count} 支", "size": "lg", "color": color, "weight": "bold", "align": "end", "flex": 2},
                ],
            },
            {"type": "text", "text": preview, "size": "xs", "color": FLEX_MUTED, "wrap": True},
        ],
        "paddingAll": "12px",
        "backgroundColor": "#ffffff",
        "cornerRadius": "6px",
    }


def build_flex_message(
    volume_items: list[dict],
    right_top_items: list[dict],
    trust_items: list[dict],
    foreign_items: list[dict],
    confluence_items: list[dict],
) -> dict:
    volume_preview = stock_preview(volume_items, "vol_ratio", "x")
    right_top_preview = stock_preview(right_top_items, "vol_ratio", "x")
    inst_preview = stock_preview(confluence_items or trust_items or foreign_items, "inst_net_5d", "張")
    inst_count = len(trust_items) + len(foreign_items) + len(confluence_items)
    total_count = len(volume_items) + len(right_top_items) + inst_count

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "backgroundColor": FLEX_BG,
            "contents": [
                {"type": "text", "text": "每日選股掃描完成", "weight": "bold", "size": "lg", "color": FLEX_PRIMARY},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                        {"type": "text", "text": f"日期 {TODAY}", "size": "xs", "color": "#aaaaaa"},
                        {
                            "type": "text",
                            "text": f"共 {total_count} 支",
                            "size": "xs",
                            "color": FLEX_ACCENT,
                            "align": "end",
                        },
                    ],
                },
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "md",
            "backgroundColor": FLEX_BG,
            "contents": [
                summary_row("量增訊號", len(volume_items), FLEX_PRIMARY, volume_preview),
                summary_row("右上角", len(right_top_items), FLEX_ACCENT, right_top_preview),
                summary_row(
                    "法人動能",
                    inst_count,
                    "#0f766e",
                    f"投信 {len(trust_items)} / 外資 {len(foreign_items)} / 共振 {len(confluence_items)}｜{inst_preview}",
                ),
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
        "altText": (
            f"每日選股掃描 {TODAY}：量增訊號 {len(volume_items)} 支 / "
            f"右上角 {len(right_top_items)} 支 / 法人動能 {inst_count} 支"
        ),
        "contents": bubble,
    }


def send_line_message(message: dict) -> bool:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    raw_ids = os.environ.get("LINE_USER_IDS") or os.environ.get("LINE_USER_ID")
    if not token or not raw_ids:
        print("[LINE] 未設定 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_IDS，略過成功通知")
        return True

    user_ids = [u.strip() for u in raw_ids.split(",") if u.strip()]
    if not user_ids:
        print("[LINE] LINE_USER_IDS 為空，略過成功通知")
        return True

    payload = json.dumps({"to": user_ids, "messages": [message]}).encode("utf-8")
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
    volume_items = today_unique_results(load_results(VOLUME_PATH))
    right_top_items = today_unique_results(load_results(RIGHT_TOP_PATH))
    trust_items = today_unique_results(load_section(TRUST_PATH, "trust_results"))
    foreign_items = today_unique_results(load_section(TRUST_PATH, "foreign_results"))
    confluence_items = today_unique_results(load_section(TRUST_PATH, "confluence_results"))
    print(
        f"[summary] 量增訊號 {len(volume_items)} 支 / 右上角 {len(right_top_items)} 支 / "
        f"法人動能 投信 {len(trust_items)} 支 外資 {len(foreign_items)} 支 共振 {len(confluence_items)} 支"
    )

    message = build_flex_message(volume_items, right_top_items, trust_items, foreign_items, confluence_items)
    return 0 if send_line_message(message) else 1


if __name__ == "__main__":
    raise SystemExit(main())
