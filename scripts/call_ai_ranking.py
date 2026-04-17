"""
AI Stock Ranking  —  call_ai_ranking.py
讀取 data/chips_big_holder.json → 呼叫 Gemini 2.0 Flash → 輸出 data/ai_recommendations.json
"""

import json
import os
import sys
import requests
from datetime import datetime, timezone, timedelta

DATA_FILE   = "data/chips_big_holder.json"
OUTPUT_FILE = "data/ai_recommendations.json"
MODEL       = "gemini-2.0-flash"
API_URL     = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

PROMPT_TEMPLATE = """\
你是台股波段操作分析師，操作週期 1-3 個月，以價差為主。

以下是通過「千張大戶籌碼策略」的篩選名單（已符合：大戶比例>30%、連續4週增持、EMA26乖離-10%~+5%）：

{stock_json}

欄位說明：
- big_4w_chg：大戶4週增持幅度（%）
- deviation：現價對 EMA26 的乖離率（負值代表低於均線，尚未被追高）
- big_pct_latest：最新週千張大戶持股比例（%）
- close：現價

請選出最適合波段操作的前3名，依以下優先順序評分：
1. big_4w_chg 越大越好（主力積極佈局）
2. deviation 越負越好（低位、有上漲空間）
3. 公司非金融、非高配息傳產、非牛皮股；偏好有獲利能力、被市場低估的成長型標的
4. 流動性足夠、適合1-3個月波段持倉

嚴格只回傳以下 JSON，不加任何說明文字：
{
  "ranked": [
    {
      "rank": 1,
      "stock_id": "代號",
      "name": "名稱",
      "score": 88,
      "reason": "從波段操作角度說明推薦理由，繁體中文，2句話以內"
    }
  ]
}
"""


def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(results):
    slim = [
        {
            "stock_id":       r["stock_id"],
            "name":           r["name"],
            "industry":       r.get("industry", ""),
            "close":          r["close"],
            "deviation":      r["deviation"],
            "big_pct_latest": r["big_pct_latest"],
            "big_4w_chg":     r["big_4w_chg"],
        }
        for r in results
    ]
    return PROMPT_TEMPLATE.format(stock_json=json.dumps(slim, ensure_ascii=False, indent=2))


def call_gemini(prompt, api_key):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    resp = requests.post(
        API_URL,
        params={"key": api_key},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def main():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("❌ GEMINI_API_KEY 未設定", file=sys.stderr)
        sys.exit(1)

    data = load_data()
    results = data.get("results", [])

    if not results:
        print("⚠️  無篩選結果，跳過 AI 分析")
        output = {
            "strategy":     "chips_big_holder",
            "generated_at": _now_tw(),
            "model":        MODEL,
            "data_updated": data.get("updated", ""),
            "ranked":       [],
        }
    else:
        prompt = build_prompt(results)
        ranked_data = call_gemini(prompt, api_key)
        output = {
            "strategy":     "chips_big_holder",
            "generated_at": _now_tw(),
            "model":        MODEL,
            "data_updated": data.get("updated", ""),
            "ranked":       ranked_data.get("ranked", [])[:3],
        }
        print(f"✅ AI 分析完成，推薦 {len(output['ranked'])} 檔")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 已寫入 {OUTPUT_FILE}")


def _now_tw():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")


if __name__ == "__main__":
    main()
