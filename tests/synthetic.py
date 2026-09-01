"""Deterministic synthetic market generators used by the test-suite.

These produce ``bot.Candle`` series so the *real* engine code paths can be
exercised without network access.
"""

from __future__ import annotations

import math
import random
import sys
import os
from typing import List, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import Candle  # noqa: E402

FIFTEEN_MIN_MS = 15 * 60 * 1000
# 2024-01-01T00:00:00Z
EPOCH_MS = 1704067200000


def ohlc_from_closes(closes: Sequence[float], spread: float = 0.004, volume: float = 100.0,
                     start_ms: int = EPOCH_MS, volume_spikes: bool = False,
                     spike_chance: float = 0.04, spike_mult: float = 3.5) -> List[Candle]:
    """Build OHLCV candles from a close path, placing open at the prior close.

    ``volume_spikes`` injects occasional high-volume bars. Real markets have
    them; a flat volume profile silently starves any volume-triggered strategy.
    """
    candles: List[Candle] = []
    prev_close = closes[0]
    spike_rng = random.Random(777)
    for i, close in enumerate(closes):
        rng = random.Random(1000 + i)
        lo = min(prev_close, close) * (1 - spread * rng.random())
        hi = max(prev_close, close) * (1 + spread * rng.random())
        vol = volume * (0.6 + 0.8 * rng.random())
        if volume_spikes and spike_rng.random() < spike_chance:
            vol *= spike_mult
        candles.append(
            Candle(
                ts=start_ms + i * FIFTEEN_MIN_MS,
                open=prev_close,
                high=max(hi, prev_close, close),
                low=min(lo, prev_close, close),
                close=close,
                volume=vol,
            )
        )
        prev_close = close
    return candles


def ramp(start: float, pct_per_candle: float, n: int) -> List[float]:
    """Geometric ramp: each candle moves ``pct_per_candle`` percent."""
    out = []
    px = start
    for _ in range(n):
        px *= 1.0 + pct_per_candle / 100.0
        out.append(px)
    return out


def flat(price: float, n: int, jitter_pct: float = 0.0) -> List[float]:
    out = []
    for i in range(n):
        wobble = math.sin(i * 1.7) * jitter_pct / 100.0
        out.append(price * (1.0 + wobble))
    return out



def multi_regime(n_per_regime: int = 100, start: float = 40000.0) -> List[float]:
    """A long, deterministic series that walks through every market regime the
    strategies care about: trend, crash, chop, rally, grind down."""
    rng = random.Random(42)
    path: List[float] = [start]
    px = start

    def walk(n: int, drift_pct: float, vol_pct: float) -> None:
        nonlocal px
        for _ in range(n):
            px *= 1.0 + (drift_pct + rng.gauss(0.0, vol_pct)) / 100.0
            px = max(px, 1.0)
            path.append(px)

    walk(n_per_regime, +0.25, 0.35)    # steady uptrend
    walk(n_per_regime, -0.55, 0.60)    # crash
    walk(n_per_regime, +0.02, 0.55)    # sideways chop
    walk(n_per_regime, +0.60, 0.40)    # strong rally
    walk(n_per_regime, -0.30, 0.45)    # grind lower
    walk(n_per_regime, +0.10, 0.75)    # high-volatility chop
    return path


def vwap_buy_series(start: float = 50000.0) -> List[Candle]:
    """Session where price sits below cumulative VWAP while RSI stays > 40.

    The open pushes higher (dragging VWAP up), then price settles into a tight
    oscillation just under it. Alternating moves keep RSI near 50 so it never
    drops into oversold territory.
    """
    closes = [start * (1.0 + 0.004 * i) for i in range(6)]
    base = closes[-1] * 0.99
    closes += [base * (1.0 + 0.0016 * math.sin(i * 2.3) - 0.0004 * i) for i in range(34)]
    return ohlc_from_closes(closes, spread=0.0008)


def vwap_round_trip_series(start: float = 50000.0) -> List[Candle]:
    """Dips under VWAP (entry) and then rallies >1.5% above it (exit)."""
    closes = [start * (1.0 + 0.004 * i) for i in range(6)]
    base = closes[-1] * 0.99
    closes += [base * (1.0 + 0.0016 * math.sin(i * 2.3) - 0.0004 * i) for i in range(20)]
    closes += ramp(closes[-1], 0.7, 18)
    return ohlc_from_closes(closes, spread=0.0008)


def to_csv(candles: Sequence[Candle], path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("ts,open,high,low,close,volume\n")
        for c in candles:
            fh.write(f"{c.ts},{c.open:.6f},{c.high:.6f},{c.low:.6f},{c.close:.6f},{c.volume:.6f}\n")
    return path


def noisy_trend(start: float, drift_pct: float, vol_pct: float, n: int, seed: int = 3) -> List[float]:
    """Geometric random walk with a directional drift.

    Constant-rate ramps are pathological for momentum indicators (MACD/EMA
    converge to a degenerate state), so realistic tests need noise.
    """
    rng = random.Random(seed)
    out: List[float] = []
    px = start
    for _ in range(n):
        px *= 1.0 + (drift_pct + rng.gauss(0.0, vol_pct)) / 100.0
        px = max(px, 1.0)
        out.append(px)
    return out


