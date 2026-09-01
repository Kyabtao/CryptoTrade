#!/usr/bin/env python3
"""Generate docs/assets/strategies.json from the strategy classes in bot.py.

The HTML dashboard reads this catalog so the entry/exit logic, parameters and
categories shown on the pages always match the code. Run after adding or
editing a strategy:

    python scripts/generate_strategy_catalog.py
"""

from __future__ import annotations

import json
import os
import sys

# Allow running from any directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot  # noqa: E402

# Human-readable entry/exit descriptions, one per strategy id. Kept in step with
# the README strategy table.
SIGNALS = {
    "01_rsi_mean_reversion": ("RSI(14) < 30 (oversold)", "RSI(14) > 70 (overbought)"),
    "02_dual_ema_crossover": ("EMA9 crosses above EMA21", "EMA9 crosses below EMA21"),
    "03_macd_histogram_reversal": ("MACD line crosses above signal", "MACD line crosses below signal"),
    "04_triple_moving_average": ("SMA20 > SMA50 > SMA200 aligned", "SMA20 drops below SMA50"),
    "05_supertrend_atr": ("Supertrend (ATR 10, ×3) flips bullish", "flips bearish / stop breached"),
    "13_adx_dmi_trend": ("ADX(14) > 25 and +DI > −DI", "ADX < 20 or −DI takes the lead"),
    "14_ichimoku_cloud": ("TK cross above the cloud, cloud green", "close re-enters the cloud"),
    "15_parabolic_sar": ("SAR dot flips below price", "SAR dot flips above price"),
    "16_roc_momentum": ("ROC(12) crosses above entry level", "ROC(12) loses momentum"),
    "17_aroon_trend": ("Aroon Up > 70 and Up > Down", "Aroon Down > 70 or Down > Up"),
    "18_heikin_ashi_trend": ("3 wick-free HA candles, colour flip", "HA candle flips colour"),
    "19_trix_momentum": ("TRIX(15) crosses above its 9-signal", "TRIX crosses below its signal"),
    "20_ema_ribbon_consensus": ("EMA 8/13/21/34/55 fully aligned up", "any ribbon crossover down"),
    "06_bollinger_mean_reversion": ("close < Lower Band (20, 2)", "close reaches Middle Band"),
    "07_keltner_breakout": ("close > EMA20 + 2·ATR", "close falls below EMA20"),
    "08_stoch_rsi_reversal": ("%K crosses above %D below 20", "%K crosses below %D above 80"),
    "21_williams_r_reversal": ("%R turns up out of < −80", "%R turns down out of > −20"),
    "22_cci_mean_reversion": ("CCI(20) crosses up through −100", "CCI crosses down through +100"),
    "23_connors_rsi_pullback": ("Connors RSI(3,2,100) < 10", "Connors RSI > 90"),
    "24_zscore_mean_reversion": ("z-score(20) < −2", "z-score returns to 0"),
    "25_mfi_flow_reversal": ("MFI(14) crosses up out of < 20", "MFI crosses down out of > 80"),
    "26_chande_momentum": ("CMO(20) crosses up through −50", "CMO crosses down through +50"),
    "09_vwap_pullback": ("close < VWAP and RSI > 40", "close ≥ VWAP + 1.5%"),
    "10_donchian_breakout": ("close breaks the 20-candle high", "close breaks the 10-candle low"),
    "27_obv_trend_breakout": ("OBV breaks its 20-candle high, close up", "OBV breaks its 20-candle low"),
    "28_volume_spike_breakout": ("volume > 2× SMA20 with a 20-candle high break", "close breaks the 10-candle low"),
    "29_volatility_squeeze": ("TTM squeeze releases, close > mid band", "close falls below the middle band"),
    "30_elder_ray_power": ("bear power lifts toward 0, bull power > 0", "bull power rolls over"),
    "31_engulfing_reversal": ("bullish engulfing at a 20-candle low", "bearish engulfing or stop"),
    "32_fibonacci_pullback": ("pullback into the 0.382–0.618 retracement", "new swing high taken or stop"),
    "33_pivot_point_bounce": ("bounce off prior-session S1 / pivot", "prior-session R1 reached"),
    "34_opening_range_breakout": ("UTC open + 1h range broken upward", "back inside the opening range"),
    "35_chandelier_trend_ride": ("uptrend confirmed, entry on a pullback", "3×ATR chandelier stop"),
    "11_dynamic_dca": ("every 4th candle, ×2 if 24h is red", "accumulates; optional take-profit"),
    "12_arithmetic_grid": ("limit buys each 1% step down", "take-profit one step up"),
    "36_martingale_dip": ("each −2% dip, size doubles (max 4 steps)", "accumulates; optional take-profit"),
    "37_anti_martingale_pyramid": ("20-candle high breakout, adds at each +2% leg", "3% trail below the tracked peak"),
    "38_kelly_fraction_sizer": ("Donchian(20) breakout, sized by half-Kelly", "close breaks the 10-candle low"),
    "39_multi_indicator_consensus": ("≥3 of 5 independent votes agree", "≥3 votes turn the other way"),
    "40_trend_pullback_confluence": ("RSI(14) < 35 and close > SMA200 > SMA50", "RSI > 60 or trend breaks"),
    "41_volatility_regime_switcher": ("ATR percentile ≥ 70 → fade, ≤ 30 → break out", "per the active sub-regime"),
    "42_sibling_performance_allocator": ("peers' median return ≥ 0 (else stands aside)", "median return turns negative"),
}


def build_catalog() -> list:
    catalog = []
    for cls in bot.STRATEGY_CLASSES:
        entry, exit_ = SIGNALS.get(cls.id, ("—", "—"))
        params = {}
        for key, value in cls.params.items():
            params[key] = value
        catalog.append(
            {
                "id": cls.id,
                "name": cls.name,
                "category": cls.category,
                "warmup": cls.warmup,
                "single_position": cls.single_position,
                "entry": entry,
                "exit": exit_,
                "params": params,
            }
        )
    return catalog


def main() -> int:
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "docs", "assets")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "strategies.json")
    catalog = build_catalog()
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=2, sort_keys=False)
        fh.write("\n")
    print(f"Wrote {len(catalog)} strategies to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
