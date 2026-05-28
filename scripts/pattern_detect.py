#!/usr/bin/env python3
"""
型態偵測 + 型態分（Pattern Score）模組
=====================================

設計原則（取代「來源疊加分數」當主排序）：
  1. 狀態分類為主排序：值得看圖 / 先觀察 / 太遠不追 / 型態破壞
  2. 型態分（0-100）只在同一狀態內做次排序
  3. 同步輸出 關鍵價 / 失效價 / 標籤 / 可信度

輸入：price_cache 切出的單支 DataFrame，欄位需為
       date, open, max, min, close, volume_lots（與 get_stock_price_from_cache 一致）
       max=最高, min=最低, volume_lots=成交量(張)

對外主入口：analyze(df, **context) -> PatternResult

注意：嚴格 VCP 段數辨識仍以既有 scan_vcp.py 為準，本模組只做輕量 pivot 收斂判斷；
      若要更嚴謹，可把 vcp.json 的命中結果用 context 傳進來覆蓋。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────
#  型態可信度（規則化辨識的雜訊差異，越高越可靠）
# ─────────────────────────────────────────────────────────────
PATTERN_CONF = {
    "long_consolidation_breakout": 1.00,  # 長期盤整後第一根突破，最可靠
    "platform_breakout_retest":    0.95,  # 平台突破後回測守住
    "w_bottom_neckline":           0.80,  # W 底突破頸線
    "vcp_pivot":                   0.70,  # VCP 收斂接近 pivot（段數辨識雜訊最大）
    "box_near_top":                0.60,  # 箱型接近上緣
}
PATTERN_BASE = {
    "platform_breakout_retest":    25,
    "long_consolidation_breakout": 24,
    "w_bottom_neckline":           22,
    "vcp_pivot":                   20,
    "box_near_top":                14,
}
PATTERN_LABEL = {
    "long_consolidation_breakout": "長盤突破首日",
    "platform_breakout_retest":    "平台突破回測",
    "w_bottom_neckline":           "W底突破頸線",
    "vcp_pivot":                   "VCP接近pivot",
    "box_near_top":                "箱頂整理",
}


@dataclass
class PatternResult:
    stock_id: str = ""
    state: str = "先觀察"          # 值得看圖 / 先觀察 / 太遠不追 / 型態破壞
    score: float = 0.0            # 0-100，僅同狀態內排序用
    subs: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    patterns: list = field(default_factory=list)
    key_level: Optional[float] = None     # 頸線 / pivot / 平台上緣
    invalidation: Optional[float] = None  # 失效價
    confidence: float = 1.0

    def as_dict(self) -> dict:
        return {
            "stock_id": self.stock_id,
            "pattern_state": self.state,
            "pattern_score": round(self.score, 1),
            "pattern_subs": {k: round(v, 1) for k, v in self.subs.items()},
            "pattern_tags": self.tags,
            "patterns": self.patterns,
            "key_level": round(self.key_level, 2) if self.key_level else None,
            "invalidation": round(self.invalidation, 2) if self.invalidation else None,
            "pattern_confidence": round(self.confidence, 2),
        }


# ═════════════════════════════════════════════════════════════
#  指標計算
# ═════════════════════════════════════════════════════════════
def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _bbw_pct(close: pd.Series, period: int = 20) -> pd.Series:
    """Bollinger Band Width %（與 repo 既有 bbw 量級一致，約 5~15）"""
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    return (4 * std / mid * 100)


def _swing_idx(values: np.ndarray, window: int = 3, kind: str = "low") -> list[int]:
    """簡單分形擺動點：左右各 window 根都不更低(高)即為 swing low(high)。"""
    n = len(values)
    out = []
    for i in range(window, n - window):
        seg = values[i - window: i + window + 1]
        if kind == "low" and values[i] == seg.min() and (seg == values[i]).sum() == 1:
            out.append(i)
        if kind == "high" and values[i] == seg.max() and (seg == values[i]).sum() == 1:
            out.append(i)
    return out


# ═════════════════════════════════════════════════════════════
#  型態偵測
# ═════════════════════════════════════════════════════════════
def _detect_platform_box(high, low, close, lookback=60, exclude=3):
    """
    箱型 / 平台高點偵測。
    回傳 (box_high, box_range_pct, broke_today, near_top)
    """
    if len(close) < lookback + exclude:
        lookback = len(close) - exclude - 1
    base_hi = high[-(lookback + exclude):-exclude]
    base_lo = low[-(lookback + exclude):-exclude]
    if len(base_hi) < 10:
        return None, None, False, False
    box_high = float(base_hi.max())
    box_low = float(base_lo.min())
    box_range_pct = (box_high - box_low) / box_low * 100 if box_low else 999
    c = float(close[-1])
    broke_today = c > box_high and float(close[-2]) <= box_high
    near_top = (box_high * 0.95) <= c <= (box_high * 1.005)
    return box_high, box_range_pct, broke_today, near_top


def _detect_w_bottom(high, low, close, lookback=80):
    """
    W 底 + 頸線偵測。
    回傳 dict 或 None：{neckline, l1, l2, state}
      state: forming / breakout / retest
    """
    seg_lo = low[-lookback:]
    seg_hi = high[-lookback:]
    lows = _swing_idx(seg_lo, window=3, kind="low")
    if len(lows) < 2:
        return None
    # 取最後兩個明顯低點
    l2_i = lows[-1]
    l1_i = lows[-2]
    if l2_i - l1_i < 8:                      # 兩低需有時間間隔
        if len(lows) >= 3:
            l1_i = lows[-3]
        else:
            return None
    l1, l2 = float(seg_lo[l1_i]), float(seg_lo[l2_i])
    if l2 < l1 * 0.97:                        # 第二低明顯破第一低 → 非 W 底
        return None
    # 兩低之間的反彈高點 = 頸線
    mid = seg_hi[l1_i:l2_i + 1]
    if len(mid) == 0:
        return None
    neckline = float(mid.max())
    if neckline < max(l1, l2) * 1.06:         # 中間反彈高度不足
        return None
    c, c_prev = float(close[-1]), float(close[-2])
    if c_prev <= neckline < c:
        state = "breakout"
    elif c > neckline and abs(c - neckline) / neckline <= 0.03:
        state = "retest"
    elif c < neckline:
        state = "forming"
    else:
        state = "breakout"
    return {"neckline": neckline, "l1": l1, "l2": l2, "state": state}


def _detect_breakout_retest(high, low, close, vol, box_high):
    """
    平台突破後回測守住：近 N 日曾突破 box_high，現價回落到 box_high 附近且守住。
    """
    if box_high is None or len(close) < 12:
        return False
    window = close[-10:]
    broke = (window > box_high).any()
    c = float(close[-1])
    near = box_high * 0.97 <= c <= box_high * 1.05
    low_held = float(low[-5:].min()) >= box_high * 0.95
    return bool(broke and near and low_held)


def _detect_vcp_pivot(high, low, close, bbw):
    """輕量 VCP：近期波動收斂(BBW 低且下降) + 貼近近 40 日高點 pivot。"""
    if len(close) < 40 or np.isnan(bbw[-1]):
        return None
    bbw_falling = bbw[-1] < np.nanmean(bbw[-20:-1])
    tight = bbw[-1] <= 9
    pivot = float(high[-40:-1].max())
    c = float(close[-1])
    near_pivot = pivot * 0.92 <= c <= pivot * 1.03
    if bbw_falling and tight and near_pivot:
        return {"pivot": pivot}
    return None


# ═════════════════════════════════════════════════════════════
#  評分核心
# ═════════════════════════════════════════════════════════════
def _score(m: dict) -> tuple[float, dict, list, float]:
    subs, tags = {}, []

    # 1. 價格結構 30
    s1 = (8 if m["ema_bull"] else 0) \
        + (8 if m["above_ema20"] and m["above_ema60"] else 4 if m["above_ema20"] else 0) \
        + (6 if m["ema20_slope_up"] else 0) \
        + (5 if m["higher_low"] else 0) \
        + (3 if m["contraction"] else 0)
    subs["結構"] = min(s1, 30)
    if m["ema_bull"]:
        tags.append("均線多頭")

    # 2. 型態辨識 25（主型態最高 + 次型態 0.3 倍小加分，封頂 25）
    hits = [p for p in m["patterns"] if p in PATTERN_BASE]
    conf = 1.0
    if hits:
        primary = max(hits, key=lambda p: PATTERN_BASE[p] * PATTERN_CONF[p])
        conf = PATTERN_CONF[primary]
        base = PATTERN_BASE[primary] * conf
        sec = sum(PATTERN_BASE[p] * PATTERN_CONF[p] for p in hits if p != primary)
        s2 = min(base + 0.3 * sec, 25)
        tags.append(PATTERN_LABEL[primary])
    else:
        s2 = 0.0
    subs["型態"] = round(s2, 1)

    # 3. 量價品質 20
    bvr = m["breakout_vol_ratio"] or 0
    s3 = (6 if bvr >= 1.5 else 0) + (4 if bvr >= 2.5 else 0) \
        + (5 if m["vol_dry_in_base"] else 0) \
        + (5 if m["retest_no_heavy_break"] else 0)
    subs["量價"] = min(s3, 20)
    if m["vol_dry_in_base"]:
        tags.append("量縮整理")

    # 4. 位置風險 15（同時拿來當降級判斷）
    s4 = 0
    if m["dist_to_key_pct"] is not None and 0 <= m["dist_to_key_pct"] <= 5:
        s4 += 6
    if m["dev_ema20_pct"] is not None and abs(m["dev_ema20_pct"]) <= 8:
        s4 += 4
    if (m["week_chg_pct"] or 0) <= 12:
        s4 += 3
    if not m["upper_shadow_risk"]:
        s4 += 2
    subs["位置"] = min(s4, 15)

    # 5. 籌碼確認 10（背景，不主導，只當 tie-breaker）
    s5 = (4 if m["big_trend_up"] else 0) + (2 if m["inst_buying"] else 0) \
        + min((m["source_count"] or 1) - 1, 4)
    subs["籌碼"] = min(s5, 10)
    if m["big_trend_up"]:
        tags.append("大戶上升")

    return sum(subs.values()), subs, tags, conf


def _classify_state(m: dict, subs: dict) -> tuple[str, list]:
    extra = []
    if m["pattern_broken"]:
        return "型態破壞", extra
    if (m["dev_ema20_pct"] is not None and m["dev_ema20_pct"] > 15) \
            or (m["track_pnl_pct"] or 0) > 14 \
            or (m["week_chg_pct"] or 0) > 18:
        extra.append("已延伸/過熱")
        return "太遠不追", extra
    if (subs["型態"] + subs["位置"]) >= 28 and subs["結構"] >= 18:
        return "值得看圖", extra
    return "先觀察", extra


# ═════════════════════════════════════════════════════════════
#  主入口
# ═════════════════════════════════════════════════════════════
def analyze(
    df: pd.DataFrame,
    stock_id: str = "",
    *,
    track_pnl_pct: Optional[float] = None,
    big_trend_up: bool = False,
    inst_buying: bool = False,
    source_count: int = 1,
    vcp_hit: bool = False,          # 可用 scan_vcp.py 的嚴格結果覆蓋
) -> Optional[PatternResult]:
    """df 需 >= 60 根日線；不足回傳 None。"""
    if df is None or len(df) < 60:
        return None
    df = df.sort_values("date").reset_index(drop=True)
    close = df["close"].to_numpy(dtype=float)
    high = df["max"].to_numpy(dtype=float)
    low = df["min"].to_numpy(dtype=float)
    vol = df["volume_lots"].to_numpy(dtype=float)

    ema5 = _ema(df["close"], 5).to_numpy()
    ema20 = _ema(df["close"], 20).to_numpy()
    ema60 = _ema(df["close"], 60).to_numpy()
    bbw = _bbw_pct(df["close"]).to_numpy()
    c = close[-1]

    # ── 結構旗標 ──
    ema_bull = ema5[-1] > ema20[-1] > ema60[-1]
    above_ema20 = c > ema20[-1]
    above_ema60 = c > ema60[-1]
    ema20_slope_up = ema20[-1] > ema20[-6]
    sw_lows = _swing_idx(low[-40:], window=3, kind="low")
    higher_low = len(sw_lows) >= 2 and low[-40:][sw_lows[-1]] > low[-40:][sw_lows[-2]]
    contraction = (not np.isnan(bbw[-1])) and bbw[-1] <= 10 and bbw[-1] < np.nanmean(bbw[-20:-1])

    # ── 型態偵測 ──
    box_high, box_range, broke_today, near_top = _detect_platform_box(high, low, close)
    w = _detect_w_bottom(high, low, close)
    retest_ok = _detect_breakout_retest(high, low, close, vol, box_high)
    vcp = _detect_vcp_pivot(high, low, close, bbw)

    patterns, key_level, invalidation = [], None, None
    if broke_today and box_range is not None and box_range <= 25:
        patterns.append("long_consolidation_breakout")
        key_level, invalidation = box_high, box_high * 0.97
    if retest_ok:
        patterns.append("platform_breakout_retest")
        key_level, invalidation = box_high, box_high * 0.97
    if w and w["state"] in ("breakout", "retest"):
        patterns.append("w_bottom_neckline")
        key_level, invalidation = w["neckline"], w["neckline"] * 0.97
    if vcp or vcp_hit:
        patterns.append("vcp_pivot")
        if vcp:
            key_level = key_level or vcp["pivot"]
            invalidation = invalidation or vcp["pivot"] * 0.93
    if not patterns and near_top:
        patterns.append("box_near_top")
        key_level = box_high

    dist_to_key_pct = (c - key_level) / key_level * 100 if key_level else None

    # ── 量價 ──
    vol10 = vol[-11:-1].mean() if len(vol) > 11 else vol.mean()
    breakout_vol_ratio = vol[-1] / vol10 if vol10 else 0
    base_vol = vol[-30:-5].mean() if len(vol) > 35 else vol.mean()
    vol_dry_in_base = vol[-5:].mean() <= base_vol * 0.9
    retest_no_heavy_break = (key_level is None) or (
        low[-5:].min() >= key_level * 0.95 and vol[-3:].mean() <= vol10
    )

    # ── 位置 / 風險 ──
    dev_ema20_pct = (c - ema20[-1]) / ema20[-1] * 100
    week_chg_pct = (c - close[-6]) / close[-6] * 100 if len(close) > 6 else 0
    rng = high[-1] - low[-1]
    upper_shadow_risk = rng > 0 and (high[-1] - c) / rng > 0.5 and rng / c > 0.05
    pattern_broken = bool(key_level and c < key_level * 0.97 and dev_ema20_pct < -3)

    metrics = dict(
        ema_bull=ema_bull, above_ema20=above_ema20, above_ema60=above_ema60,
        ema20_slope_up=ema20_slope_up, higher_low=higher_low, contraction=contraction,
        patterns=patterns,
        breakout_vol_ratio=breakout_vol_ratio, vol_dry_in_base=vol_dry_in_base,
        retest_no_heavy_break=retest_no_heavy_break,
        dist_to_key_pct=dist_to_key_pct, dev_ema20_pct=dev_ema20_pct,
        week_chg_pct=week_chg_pct, upper_shadow_risk=upper_shadow_risk,
        track_pnl_pct=track_pnl_pct, pattern_broken=pattern_broken,
        big_trend_up=big_trend_up, inst_buying=inst_buying, source_count=source_count,
    )

    score, subs, tags, conf = _score(metrics)
    state, extra = _classify_state(metrics, subs)
    tags += extra

    return PatternResult(
        stock_id=stock_id, state=state, score=score, subs=subs, tags=tags,
        patterns=patterns, key_level=key_level, invalidation=invalidation, confidence=conf,
    )


# 同一狀態內排序用的鍵（狀態優先，分數次之，來源數 tie-break）
STATE_ORDER = {"值得看圖": 0, "先觀察": 1, "太遠不追": 2, "型態破壞": 3}


def sort_key(r: PatternResult, source_count: int = 1):
    return (STATE_ORDER.get(r.state, 9), -r.score, -source_count)


# ─────────────────────────────────────────────────────────────
#  Demo / 煙霧測試
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    def _synthetic(kind: str) -> pd.DataFrame:
        """產生測試用 OHLCV，驗證模組可執行。"""
        n = 120
        dates = pd.date_range("2026-01-01", periods=n, freq="B")
        rng = np.random.default_rng(42)
        if kind == "breakout":
            base = np.concatenate([np.full(90, 50) + rng.normal(0, 0.6, 90),
                                   np.linspace(50, 58, 30)])
        elif kind == "wbottom":
            base = np.concatenate([np.linspace(60, 42, 30), np.linspace(42, 50, 15),
                                   np.linspace(50, 43, 15), np.linspace(43, 53, 60)])
        else:  # extended
            base = np.linspace(40, 90, n) + rng.normal(0, 1, n)
        close = np.maximum(base, 1)
        high = close * (1 + abs(rng.normal(0, 0.01, n)))
        low = close * (1 - abs(rng.normal(0, 0.01, n)))
        vol = rng.integers(800, 1500, n).astype(float)
        vol[-1] *= 2.5
        return pd.DataFrame({"date": dates, "open": close, "max": high,
                             "min": low, "close": close, "volume_lots": vol})

    for kind in ["breakout", "wbottom", "extended"]:
        r = analyze(_synthetic(kind), stock_id=f"TEST-{kind}",
                    big_trend_up=True, source_count=3)
        print(f"\n=== {kind} ===")
        if r:
            d = r.as_dict()
            for k, v in d.items():
                print(f"  {k}: {v}")
        else:
            print("  (資料不足)")
    print("\n✅ pattern_detect 煙霧測試通過")
