#!/usr/bin/env python3
"""
法人標籤更新器
讀取 data/chips_big_holder.json，查詢 FinMind 法人買賣超，更新 tags 欄位後寫回。
可單獨執行，也可由 holdings_scan workflow 完成後觸發。
"""

import json, os, time
from datetime import datetime, timedelta, timezone
from finmind_client import fetch_institutional

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "chips_big_holder.json")

TW_TZ            = timezone(timedelta(hours=8))
INST_START_DATE  = (datetime.now(TW_TZ) - timedelta(days=20)).strftime("%Y-%m-%d")
FINMIND_SLEEP    = 0.35
INST_LABELS      = {"外資連買", "投信連買"}


def compute_institutional_tags(stock_id, token):
    inst = fetch_institutional(stock_id, INST_START_DATE, token)
    if not inst:
        return []
    tags = []
    for key, label in [("foreign", "外資連買"), ("trust", "投信連買")]:
        vals = inst.get(key, [])[-10:]
        if not vals:
            continue
        buy_days = sum(1 for v in vals if v > 0)
        if buy_days > 5 and sum(vals) > 0:
            tags.append(label)
    return tags


def main():
    print("=== 法人標籤更新器 ===")
    token = os.environ.get("FINMIND_TOKEN", "")
    if not token:
        print("⚠️  FINMIND_TOKEN 未設定")

    if not os.path.exists(OUTPUT_PATH):
        print(f"❌ 找不到 {OUTPUT_PATH}，請先執行大戶持股分析")
        return

    with open(OUTPUT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    print(f"載入 {len(results)} 支標的，開始查詢法人資料...")

    # 前 3 支印詳細診斷，其餘正常執行
    updated_count = 0
    for i, r in enumerate(results, 1):
        # 移除舊的法人標籤（支援重複執行）
        r["tags"] = [t for t in r.get("tags", []) if t not in INST_LABELS]

        inst_tags = compute_institutional_tags(r["stock_id"], token)
        if inst_tags:
            r["tags"] = r["tags"] + inst_tags
            updated_count += 1
            print(f"  {r['stock_id']} {r['name']}: {inst_tags}")

        time.sleep(FINMIND_SLEEP)
        if i % 20 == 0:
            print(f"  進度：{i}/{len(results)}")

    data["updated"] = datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成：{updated_count} 支加入法人標籤，已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
