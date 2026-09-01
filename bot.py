#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot.py — Multi-strategy crypto PAPER-TRADING engine.

Runs 12 isolated virtual sub-accounts, each executing a distinct strategy against
the same BTC/USDT (or ETH/USDT) candle stream, and persists every account to
``docs/data.json``.

Design notes
------------
* **No real orders are ever placed.** Execution is simulated against exchange
  OHLCV data with a 0.1% spot taker fee deducted on both sides.
* **Signals are computed on the last *closed* candle.** The in-progress candle
  returned by the exchange is dropped before evaluation, so no strategy can
  repaint against a partial bar. Execution price is the close of that signal
  candle (optionally degraded by ``slippage``).
* **Indicators are implemented in pure Python** (no numpy/pandas). The only
  third-party dependency is ``ccxt``, which keeps scheduled CI runs cheap and
  removes a whole class of version-skew failures.
* **State writes are atomic** (tmp file + ``os.replace``) with a rotating
  ``.bak``, so a killed job can never leave a half-written ``data.json``.

Scheduled usage (GitHub Actions)::

    python bot.py                       # one tick, persists to docs/data.json
    python bot.py --symbol ETH/USDT     # alternate market
    python bot.py --replay hist.csv     # offline replay / backtest
    python bot.py --reset --yes         # rebuild the state file from scratch

This software is for research and education. It is not financial advice.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:
    import ccxt  # type: ignore
except ImportError:  # pragma: no cover - dependency guard
    ccxt = None


__version__ = "1.0.0"

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

STATE_VERSION = 1
DEFAULT_STATE_PATH = os.path.join("docs", "data.json")

EPS = 1e-12          # float comparison guard for quantities / balances
MIN_QTY_STEP = 1e-8  # quantities below this are treated as flat

# Minimum order notional (USDT). Orders smaller than this are rejected by the
# broker simulation, mirroring the per-market minimums real exchanges enforce.
DEFAULT_MIN_NOTIONAL = 10.0

# Per-run history snapshot for the HTML dashboard. One compact row is appended
# per tick (kept next to the state file) so the dashboard can draw equity and
# return curves without re-reading every historical candle. Older rows are
# pruned to keep the file bounded.
HISTORY_FILENAME = "history.json"
HISTORY_MAX_ENTRIES = 2016   # ~3 weeks of 15m ticks


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass
class Config:
    """Runtime configuration. Precedence: defaults < environment < CLI flags."""

    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    candle_limit: int = 100
    state_path: str = DEFAULT_STATE_PATH

    starting_balance: float = 1000.0
    fee_rate: float = 0.001          # 0.1% spot taker fee, applied both sides
    min_notional: float = DEFAULT_MIN_NOTIONAL
    slippage: float = 0.0            # fraction of price, applied adversely
    position_alloc: float = 0.95     # fraction of cash used by single-position buys

    # Risk overlay (disabled by default so strategies are compared on their own
    # merits). Set any of these to enable per-account hard exits.
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None

    # Guards
    skip_duplicate_candle: bool = True   # ignore re-runs inside the same candle
    max_trades_per_run: int = 25

    # Per-strategy parameter overrides: {"01_rsi_mean_reversion": {"rsi_buy": 25}}
    overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    disabled: List[str] = field(default_factory=list)

    @classmethod
    def from_env(cls, base: Optional["Config"] = None) -> "Config":
        cfg = base or cls()

        def _get(name: str) -> Optional[str]:
            return os.environ.get(name) or None

        def _apply(attr: str, env: str, cast) -> None:
            raw = _get(env)
            if raw is None:
                return
            try:
                setattr(cfg, attr, cast(raw))
            except (ValueError, TypeError):
                logging.warning("Ignoring invalid env %s=%r", env, raw)

        cfg.symbol = _get("BOT_SYMBOL") or cfg.symbol
        cfg.timeframe = _get("BOT_TIMEFRAME") or cfg.timeframe
        cfg.state_path = _get("BOT_STATE_PATH") or cfg.state_path
        _apply("candle_limit", "BOT_CANDLE_LIMIT", int)
        _apply("fee_rate", "BOT_FEE_RATE", float)
        _apply("slippage", "BOT_SLIPPAGE", float)
        _apply("position_alloc", "BOT_POSITION_ALLOC", float)
        _apply("min_notional", "BOT_MIN_NOTIONAL", float)
        _apply("stop_loss_pct", "BOT_STOP_LOSS_PCT", float)
        _apply("take_profit_pct", "BOT_TAKE_PROFIT_PCT", float)
        _apply("max_trades_per_run", "BOT_MAX_TRADES_PER_RUN", int)

        raw_disabled = _get("BOT_DISABLED_STRATEGIES")
        if raw_disabled:
            cfg.disabled = [s.strip() for s in raw_disabled.split(",") if s.strip()]
        return cfg


# --------------------------------------------------------------------------- #
# Candle / market data
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Candle:
    ts: int       # open time, epoch milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketData:
    """Immutable view over a series of *closed* candles plus cached arrays."""

    __slots__ = ("symbol", "timeframe", "candles", "_closes", "_highs", "_lows",
                 "_volumes", "_cache")

    def __init__(self, symbol: str, timeframe: str, candles: Sequence[Candle]):
        self.symbol = symbol
        self.timeframe = timeframe
        self.candles: List[Candle] = list(candles)
        bad = next((c for c in self.candles if not isinstance(c, Candle)), None)
        if bad is not None:
            raise TypeError(
                f"MarketData expects Candle objects, got {type(bad).__name__}. "
                "Wrap a raw close-price list with ohlc_from_closes() first."
            )
        self._closes = [c.close for c in self.candles]
        self._highs = [c.high for c in self.candles]
        self._lows = [c.low for c in self.candles]
        self._volumes = [c.volume for c in self.candles]
        # Per-candle memo. Every account is evaluated against the same window,
        # so shared indicators are computed once instead of once per strategy.
        self._cache: Dict[str, Any] = {}

    def cached(self, key: str, build: Callable[[], Any]) -> Any:
        """Memoize an indicator series for the lifetime of this candle window."""
        if key not in self._cache:
            self._cache[key] = build()
        return self._cache[key]

    def __len__(self) -> int:
        return len(self.candles)

    @property
    def closes(self) -> List[float]:
        return self._closes

    @property
    def highs(self) -> List[float]:
        return self._highs

    @property
    def lows(self) -> List[float]:
        return self._lows

    @property
    def volumes(self) -> List[float]:
        return self._volumes

    @property
    def price(self) -> float:
        """Execution reference price: close of the last closed candle."""
        return self._closes[-1]

    @property
    def last_ts(self) -> int:
        return self.candles[-1].ts

    def warmup_ok(self, needed: int) -> bool:
        return len(self.candles) >= needed

    def change_pct(self, lookback: int) -> Optional[float]:
        """Percentage change over ``lookback`` candles. Falls back to the
        oldest available candle when history is shorter than requested."""
        n = len(self._closes)
        if n < 2:
            return None
        idx = max(0, n - 1 - lookback)
        base = self._closes[idx]
        if base <= EPS:
            return None
        return (self._closes[-1] - base) / base * 100.0


# --------------------------------------------------------------------------- #
# Indicators (pure Python, None-safe; ``None`` marks the warm-up region)
# --------------------------------------------------------------------------- #


def rolling(values: Sequence[Optional[float]], period: int, fn: Callable[[List[float]], float]) -> List[Optional[float]]:
    """Apply ``fn`` to a trailing window; emit ``None`` until ``period``
    consecutive non-``None`` values are available."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0:
        return out
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        if any(v is None for v in window):
            continue
        out[i] = fn(list(window))  # type: ignore[arg-type]
    return out


def sma(values: Sequence[Optional[float]], period: int) -> List[Optional[float]]:
    return rolling(values, period, lambda w: sum(w) / len(w))


def stdev(values: Sequence[Optional[float]], period: int) -> List[Optional[float]]:
    def _std(w: List[float]) -> float:
        mean = sum(w) / len(w)
        return math.sqrt(sum((x - mean) ** 2 for x in w) / len(w))  # population stdev

    return rolling(values, period, _std)


def ema(values: Sequence[Optional[float]], period: int) -> List[Optional[float]]:
    """Classic EMA seeded with the SMA of the first ``period`` values."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    if any(v is None for v in values[:period]):
        return out
    k = 2.0 / (period + 1)
    prev = sum(values[:period]) / period  # type: ignore[arg-type]
    out[period - 1] = prev
    for i in range(period, len(values)):
        v = values[i]
        if v is None:
            out[i] = None
            continue
        prev = v * k + prev * (1 - k)
        out[i] = prev
    return out


def ema_over_valid(values: Sequence[Optional[float]], period: int) -> List[Optional[float]]:
    """EMA that starts at the first run of ``period`` non-``None`` values.

    Unlike :func:`ema`, this tolerates a warm-up region of ``None`` at the head
    of the series, which is what chained indicators (TRIX, MACD signal) produce.
    """
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period <= 0:
        return out
    start = None
    for i in range(n - period + 1):
        if all(v is not None for v in values[i : i + period]):
            start = i
            break
    if start is None:
        return out
    k = 2.0 / (period + 1)
    prev = sum(values[start : start + period]) / period  # type: ignore[arg-type]
    out[start + period - 1] = prev
    for i in range(start + period, n):
        v = values[i]
        if v is None:
            continue
        prev = v * k + prev * (1 - k)
        out[i] = prev
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss <= EPS:
        return 100.0 if avg_gain > EPS else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def rsi(values: Sequence[Optional[float]], period: int = 14) -> List[Optional[float]]:
    """Wilder's RSI with Wilder smoothing."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n < period + 1 or period <= 0:
        return out
    closes = [float(v) if v is not None else float("nan") for v in values]
    if any(math.isnan(c) for c in closes[: period + 1]):
        return out

    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi_value(avg_gain, avg_loss)

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    for i in range(1, len(closes)):
        out[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    return out


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> List[Optional[float]]:
    """Wilder's ATR."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < period + 1 or period <= 0:
        return out
    tr = true_range(highs, lows, closes)
    first_window = tr[1 : period + 1]
    if any(v is None for v in first_window):
        return out
    prev = sum(first_window) / period  # type: ignore[arg-type]
    out[period] = prev
    for i in range(period + 1, n):
        v = tr[i]
        if v is None:
            out[i] = None
            continue
        prev = (prev * (period - 1) + v) / period
        out[i] = prev
    return out


def macd(
    values: Sequence[Optional[float]], fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    line: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            line[i] = ema_fast[i] - ema_slow[i]  # type: ignore[operator]

    idx = [i for i, v in enumerate(line) if v is not None]
    sig: List[Optional[float]] = [None] * len(values)
    hist: List[Optional[float]] = [None] * len(values)
    if len(idx) >= signal:
        sub = [line[i] for i in idx]
        sig_sub = ema(sub, signal)
        for j, i in enumerate(idx):
            sig[i] = sig_sub[j]
            if sig_sub[j] is not None:
                hist[i] = line[i] - sig_sub[j]  # type: ignore[operator]
    return line, sig, hist


def bollinger(
    closes: Sequence[Optional[float]], period: int = 20, mult: float = 2.0
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    mid = sma(closes, period)
    sd = stdev(closes, period)
    upper: List[Optional[float]] = [None] * len(closes)
    lower: List[Optional[float]] = [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is not None and sd[i] is not None:
            upper[i] = mid[i] + mult * sd[i]  # type: ignore[operator]
            lower[i] = mid[i] - mult * sd[i]  # type: ignore[operator]
    return upper, mid, lower


def keltner(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[Optional[float]],
    period: int = 20,
    mult: float = 2.0,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Keltner Channel: EMA(period) +/- mult * ATR(period)."""
    mid = ema(closes, period)
    a = atr(highs, lows, [c if c is not None else 0.0 for c in closes], period)
    upper: List[Optional[float]] = [None] * len(closes)
    lower: List[Optional[float]] = [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is not None and a[i] is not None:
            upper[i] = mid[i] + mult * a[i]  # type: ignore[operator]
            lower[i] = mid[i] - mult * a[i]  # type: ignore[operator]
    return upper, mid, lower


def stoch_rsi(
    closes: Sequence[Optional[float]],
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_period: int = 3,
    d_period: int = 3,
) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Stochastic RSI. %K = SMA of raw StochRSI, %D = SMA of %K."""
    r = rsi(closes, rsi_period)
    raw: List[Optional[float]] = [None] * len(closes)
    for i in range(len(closes)):
        window = [v for v in r[max(0, i - stoch_period + 1) : i + 1] if v is not None]
        if len(window) < stoch_period or r[i] is None:
            continue
        hi, lo = max(window), min(window)
        raw[i] = 50.0 if hi - lo <= EPS else (r[i] - lo) / (hi - lo) * 100.0
    k = sma(raw, k_period)
    d = sma(k, d_period)
    return k, d


def donchian(
    highs: Sequence[float], lows: Sequence[float], up_period: int, down_period: int
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Donchian channel using strictly *prior* candles, so a breakout cannot
    be self-referential against the current bar's own high/low."""
    n = len(highs)
    upper: List[Optional[float]] = [None] * n
    lower: List[Optional[float]] = [None] * n
    mid: List[Optional[float]] = [None] * n
    for i in range(n):
        if i >= up_period:
            upper[i] = max(highs[i - up_period : i])
        if i >= down_period:
            lower[i] = min(lows[i - down_period : i])
        if upper[i] is not None and lower[i] is not None:
            mid[i] = (upper[i] + lower[i]) / 2.0
    return upper, mid, lower


def supertrend(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 10,
    multiplier: float = 3.0,
) -> Tuple[List[Optional[float]], List[Optional[int]]]:
    """Supertrend.

    Returns ``(line, direction)`` where ``direction`` is ``+1`` for an uptrend
    (price above the trailing stop) and ``-1`` for a downtrend.
    """
    n = len(closes)
    line: List[Optional[float]] = [None] * n
    direction: List[Optional[int]] = [None] * n
    a = atr(highs, lows, closes, period)

    start = next((i for i, v in enumerate(a) if v is not None), None)
    if start is None:
        return line, direction

    prev_final_upper = (highs[start] + lows[start]) / 2.0 + multiplier * a[start]  # type: ignore[operator]
    prev_final_lower = (highs[start] + lows[start]) / 2.0 - multiplier * a[start]  # type: ignore[operator]
    prev_dir = 1 if closes[start] >= (highs[start] + lows[start]) / 2.0 else -1
    line[start] = prev_final_lower if prev_dir == 1 else prev_final_upper
    direction[start] = prev_dir

    for i in range(start + 1, n):
        atr_i = a[i]
        if atr_i is None:
            continue
        hl2 = (highs[i] + lows[i]) / 2.0
        basic_upper = hl2 + multiplier * atr_i
        basic_lower = hl2 - multiplier * atr_i

        final_upper = basic_upper
        if basic_upper > prev_final_upper and closes[i - 1] <= prev_final_upper:
            final_upper = prev_final_upper
        final_lower = basic_lower
        if basic_lower < prev_final_lower and closes[i - 1] >= prev_final_lower:
            final_lower = prev_final_lower

        if closes[i] > prev_final_upper:
            cur_dir = 1
        elif closes[i] < prev_final_lower:
            cur_dir = -1
        else:
            cur_dir = prev_dir

        line[i] = final_lower if cur_dir == 1 else final_upper
        direction[i] = cur_dir
        prev_final_upper, prev_final_lower, prev_dir = final_upper, final_lower, cur_dir

    return line, direction


def session_vwap(candles: Sequence[Candle]) -> Tuple[float, int]:
    """Cumulative VWAP since the start of the current UTC session.

    Returns ``(vwap, candles_in_session)``.
    """
    if not candles:
        return 0.0, 0
    last = candles[-1]
    day_start_ms = int(
        datetime.fromtimestamp(last.ts / 1000.0, tz=timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
        * 1000
    )
    pv = 0.0
    vol = 0.0
    count = 0
    for c in candles:
        if c.ts < day_start_ms:
            continue
        tp = (c.high + c.low + c.close) / 3.0
        pv += tp * c.volume
        vol += c.volume
        count += 1
    if vol <= EPS:
        return last.close, count
    return pv / vol, count


def crossed_above(prev: Optional[float], cur: Optional[float], ref_prev: Optional[float], ref_cur: Optional[float]) -> bool:
    if None in (prev, cur, ref_prev, ref_cur):
        return False
    return prev <= ref_prev and cur > ref_cur  # type: ignore[operator]


def crossed_below(prev: Optional[float], cur: Optional[float], ref_prev: Optional[float], ref_cur: Optional[float]) -> bool:
    if None in (prev, cur, ref_prev, ref_cur):
        return False
    return prev >= ref_prev and cur < ref_cur  # type: ignore[operator]


def adx_dmi(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Wilder's ADX with +DI / -DI. Returns ``(adx, plus_di, minus_di)``."""
    n = len(closes)
    adx: List[Optional[float]] = [None] * n
    plus: List[Optional[float]] = [None] * n
    minus: List[Optional[float]] = [None] * n
    if n < 2 * period + 1 or period <= 0:
        return adx, plus, minus

    tr_list: List[float] = [0.0]
    pdm: List[float] = [0.0]
    mdm: List[float] = [0.0]
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        tr_list.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
        pdm.append(up if (up > down and up > 0) else 0.0)
        mdm.append(down if (down > up and down > 0) else 0.0)

    atr_s = sum(tr_list[1 : period + 1])
    pdm_s = sum(pdm[1 : period + 1])
    mdm_s = sum(mdm[1 : period + 1])

    dx: List[Optional[float]] = [None] * n

    def _di(smooth_dm: float) -> float:
        return 100.0 * smooth_dm / atr_s if atr_s > EPS else 0.0

    plus[period] = _di(pdm_s)
    minus[period] = _di(mdm_s)
    s = plus[period] + minus[period]
    dx[period] = 100.0 * abs(plus[period] - minus[period]) / s if s > EPS else 0.0

    for i in range(period + 1, n):
        atr_s = atr_s - atr_s / period + tr_list[i]
        pdm_s = pdm_s - pdm_s / period + pdm[i]
        mdm_s = mdm_s - mdm_s / period + mdm[i]
        plus[i] = _di(pdm_s)
        minus[i] = _di(mdm_s)
        s = plus[i] + minus[i]
        dx[i] = 100.0 * abs(plus[i] - minus[i]) / s if s > EPS else 0.0

    # ADX = Wilder smoothing of DX, seeded with the SMA of the first `period` DX values.
    start = 2 * period
    if start >= n:
        return adx, plus, minus
    window = [dx[i] for i in range(period, start) if dx[i] is not None]
    if len(window) < period:
        return adx, plus, minus
    prev = sum(window) / period
    adx[start - 1] = prev
    for i in range(start, n):
        if dx[i] is None:
            continue
        prev = (prev * (period - 1) + dx[i]) / period
        adx[i] = prev
    return adx, plus, minus


def ichimoku(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    tenkan: int = 9,
    kijun: int = 26,
    senkou_b: int = 52,
    displacement: int = 26,
) -> Dict[str, List[Optional[float]]]:
    """Ichimoku Kinko Hyo.

    The cloud returned at index ``i`` is the one *visible* at that bar, i.e. it
    was computed ``displacement`` bars earlier. That avoids look-ahead.
    """
    n = len(closes)
    out = {
        "tenkan": [None] * n,
        "kijun": [None] * n,
        "senkou_a": [None] * n,
        "senkou_b": [None] * n,
        "cloud_top": [None] * n,
        "cloud_bottom": [None] * n,
    }

    def _midline(period: int) -> List[Optional[float]]:
        res: List[Optional[float]] = [None] * n
        for i in range(period - 1, n):
            res[i] = (max(highs[i - period + 1 : i + 1]) + min(lows[i - period + 1 : i + 1])) / 2.0
        return res

    t = _midline(tenkan)
    k = _midline(kijun)
    sb_raw = _midline(senkou_b)
    out["tenkan"], out["kijun"] = t, k

    for i in range(n):
        if t[i] is None or k[i] is None:
            continue
        j = i + displacement
        if j < n:
            out["senkou_a"][j] = (t[i] + k[i]) / 2.0
        if sb_raw[i] is not None and j < n:
            out["senkou_b"][j] = sb_raw[i]

    for i in range(n):
        a, b = out["senkou_a"][i], out["senkou_b"][i]
        if a is not None and b is not None:
            out["cloud_top"][i] = max(a, b)
            out["cloud_bottom"][i] = min(a, b)
    return out


def parabolic_sar(
    highs: Sequence[float],
    lows: Sequence[float],
    step: float = 0.02,
    maximum: float = 0.2,
) -> List[Optional[float]]:
    """Wilder's Parabolic SAR. Values sit *below* price in an uptrend."""
    n = len(highs)
    sar: List[Optional[float]] = [None] * n
    if n < 3:
        return sar

    bull = highs[1] + lows[1] >= highs[0] + lows[0]
    sar[0] = lows[0] if bull else highs[0]
    af = step
    ep = highs[0] if bull else lows[0]

    for i in range(1, n):
        prev = sar[i - 1]
        cur = prev + af * (ep - prev)
        if bull:
            cur = min(cur, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
            if lows[i] < cur:                       # reverse to downtrend
                bull = False
                cur = ep
                ep = lows[i]
                af = step
            elif highs[i] > ep:
                ep = highs[i]
                af = min(af + step, maximum)
        else:
            cur = max(cur, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
            if highs[i] > cur:                      # reverse to uptrend
                bull = True
                cur = ep
                ep = highs[i]
                af = step
            elif lows[i] < ep:
                ep = lows[i]
                af = min(af + step, maximum)
        sar[i] = cur
    return sar


def roc(values: Sequence[Optional[float]], period: int = 12) -> List[Optional[float]]:
    """Rate of change, in percent."""
    out: List[Optional[float]] = [None] * len(values)
    for i in range(period, len(values)):
        a, b = values[i - period], values[i]
        if a is None or b is None or abs(a) <= EPS:
            continue
        out[i] = (b - a) / a * 100.0
    return out


def aroon(highs: Sequence[float], lows: Sequence[float], period: int = 25):
    """Aroon Up / Down: bars since the extreme, scaled to 0-100."""
    n = len(highs)
    up: List[Optional[float]] = [None] * n
    down: List[Optional[float]] = [None] * n
    for i in range(period, n):
        window_h = highs[i - period : i + 1]
        window_l = lows[i - period : i + 1]
        up[i] = 100.0 * (period - window_h[::-1].index(max(window_h))) / period
        down[i] = 100.0 * (period - window_l[::-1].index(min(window_l))) / period
    return up, down


def heikin_ashi(candles: Sequence["Candle"]) -> List[Tuple[float, float, float, float]]:
    """Heikin-Ashi (open, high, low, close) tuples."""
    out: List[Tuple[float, float, float, float]] = []
    prev_o = prev_c = None
    for c in candles:
        ha_c = (c.open + c.high + c.low + c.close) / 4.0
        ha_o = c.open if prev_o is None else (prev_o + prev_c) / 2.0
        ha_h = max(c.high, ha_o, ha_c)
        ha_l = min(c.low, ha_o, ha_c)
        out.append((ha_o, ha_h, ha_l, ha_c))
        prev_o, prev_c = ha_o, ha_c
    return out


def trix(values: Sequence[Optional[float]], period: int = 15, signal: int = 9):
    """TRIX: 1% rate of change of a triple-smoothed EMA, plus its signal line."""
    e1 = ema(values, period)
    e2 = ema_over_valid(e1, period)
    e3 = ema_over_valid(e2, period)
    line = roc(e3, 1)
    n = len(values)
    sig: List[Optional[float]] = [None] * n
    idx = [i for i, v in enumerate(line) if v is not None]
    if len(idx) >= signal:
        sub = [line[i] for i in idx]
        es = ema(sub, signal)
        for j, i in enumerate(idx):
            sig[i] = es[j]
    return line, sig


def williams_r(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
               period: int = 14) -> List[Optional[float]]:
    """Williams %R, ranging -100 (lowest) to 0 (highest)."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    for i in range(period - 1, n):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        if hh - ll <= EPS:
            continue
        out[i] = (hh - closes[i]) / (hh - ll) * -100.0
    return out


def cci(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
        period: int = 20) -> List[Optional[float]]:
    """Commodity Channel Index."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    tp = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    for i in range(period - 1, n):
        window = tp[i - period + 1 : i + 1]
        mean = sum(window) / period
        mean_dev = sum(abs(x - mean) for x in window) / period
        if mean_dev <= EPS:
            continue
        out[i] = (tp[i] - mean) / (0.015 * mean_dev)
    return out


def percent_rank(values: Sequence[Optional[float]], period: int = 100) -> List[Optional[float]]:
    """Percentile rank of the latest value within its trailing window (0-100)."""
    out: List[Optional[float]] = [None] * len(values)
    for i in range(period, len(values)):
        window = [v for v in values[i - period : i] if v is not None]
        cur = values[i]
        if cur is None or len(window) < period // 2:
            continue
        below = sum(1 for v in window if v < cur)
        out[i] = 100.0 * below / len(window)
    return out


def up_down_streak(closes: Sequence[float]) -> List[float]:
    """Signed count of consecutive up (+) or down (-) closes."""
    out: List[float] = [0.0] * len(closes)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + 1 if out[i - 1] > 0 else 1.0
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - 1 if out[i - 1] < 0 else -1.0
        else:
            out[i] = out[i - 1]
    return out


def connors_rsi(closes: Sequence[float], rsi_period: int = 3, streak_period: int = 2,
                rank_period: int = 100) -> List[Optional[float]]:
    """Connors RSI: mean of RSI(price), RSI(streak) and the ROC percent rank."""
    n = len(closes)
    price_rsi = rsi(closes, rsi_period)
    streak_vals = up_down_streak(closes)
    streak_rsi = rsi([float(v) for v in streak_vals], streak_period)
    roc_vals = roc(closes, 1)
    pr = percent_rank(roc_vals, rank_period)
    out: List[Optional[float]] = [None] * n
    for i in range(n):
        parts = [price_rsi[i], streak_rsi[i], pr[i]]
        if any(p is None for p in parts):
            continue
        out[i] = sum(parts) / 3.0  # type: ignore[arg-type]
    return out


def zscore(values: Sequence[Optional[float]], period: int = 20) -> List[Optional[float]]:
    sd = stdev(values, period)
    mid = sma(values, period)
    out: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if sd[i] is None or mid[i] is None or sd[i] <= EPS or values[i] is None:
            continue
        out[i] = (values[i] - mid[i]) / sd[i]  # type: ignore[operator]
    return out


def mfi(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
        volumes: Sequence[float], period: int = 14) -> List[Optional[float]]:
    """Money Flow Index: volume-weighted RSI."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    tp = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    for i in range(period, n):
        pos = neg = 0.0
        for j in range(i - period + 1, i + 1):
            flow = tp[j] * volumes[j]
            if tp[j] > tp[j - 1]:
                pos += flow
            elif tp[j] < tp[j - 1]:
                neg += flow
        if neg <= EPS:
            out[i] = 100.0 if pos > EPS else 50.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + pos / neg)
    return out


def chande_momentum(closes: Sequence[float], period: int = 20) -> List[Optional[float]]:
    """Chande Momentum Oscillator, -100 to +100."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    for i in range(period, n):
        gains = losses = 0.0
        for j in range(i - period + 1, i + 1):
            d = closes[j] - closes[j - 1]
            if d > 0:
                gains += d
            else:
                losses -= d
        total = gains + losses
        out[i] = 100.0 * (gains - losses) / total if total > EPS else 0.0
    return out


def obv(closes: Sequence[float], volumes: Sequence[float]) -> List[float]:
    """On-Balance Volume, cumulative."""
    out: List[float] = [0.0] * len(closes)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def elder_ray(highs: Sequence[float], lows: Sequence[float], closes: Sequence[Optional[float]],
               period: int = 13):
    """Elder-Ray bull power (high - EMA) and bear power (low - EMA)."""
    mid = ema(closes, period)
    bull: List[Optional[float]] = [None] * len(closes)
    bear: List[Optional[float]] = [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is None:
            continue
        bull[i] = highs[i] - mid[i]  # type: ignore[operator]
        bear[i] = lows[i] - mid[i]   # type: ignore[operator]
    return bull, bear


def chandelier_exit(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
                    period: int = 22, multiplier: float = 3.0):
    """Chandelier long/short exits, hung from the extreme of the lookback."""
    n = len(closes)
    a = atr(highs, lows, closes, period)
    long_exit: List[Optional[float]] = [None] * n
    short_exit: List[Optional[float]] = [None] * n
    for i in range(period - 1, n):
        if a[i] is None:
            continue
        long_exit[i] = max(highs[i - period + 1 : i + 1]) - multiplier * a[i]  # type: ignore[operator]
        short_exit[i] = min(lows[i - period + 1 : i + 1]) + multiplier * a[i]  # type: ignore[operator]
    return long_exit, short_exit


def fibonacci_levels(high: float, low: float) -> Dict[str, float]:
    """Retracement levels of a swing, keyed by ratio."""
    span = high - low
    return {
        "0.236": high - 0.236 * span,
        "0.382": high - 0.382 * span,
        "0.500": high - 0.500 * span,
        "0.618": high - 0.618 * span,
        "0.786": high - 0.786 * span,
    }


def pivot_points(high: float, low: float, close: float) -> Dict[str, float]:
    """Classic floor-trader pivots from the prior session."""
    p = (high + low + close) / 3.0
    return {
        "r2": p + (high - low),
        "r1": 2 * p - low,
        "p": p,
        "s1": 2 * p - high,
        "s2": p - (high - low),
    }


def prior_session_hlc(candles: Sequence["Candle"]) -> Optional[Tuple[float, float, float]]:
    """High/low/close of the UTC session *before* the latest candle's session."""
    if not candles:
        return None

    def _day(ts: int) -> int:
        return ts // 86_400_000

    last_day = _day(candles[-1].ts)
    prev = [c for c in candles if _day(c.ts) == last_day - 1]
    if not prev:
        return None
    return max(c.high for c in prev), min(c.low for c in prev), prev[-1].close


def opening_range(candles: Sequence["Candle"], minutes: int = 60) -> Optional[Tuple[float, float, int]]:
    """High/low of the first ``minutes`` of the current UTC session, plus the
    number of candles that have elapsed since the session opened."""
    if not candles:
        return None
    last = candles[-1]
    day_start_ms = (last.ts // 86_400_000) * 86_400_000
    cutoff = day_start_ms + minutes * 60_000
    or_candles = [c for c in candles if day_start_ms <= c.ts < cutoff]
    elapsed = sum(1 for c in candles if c.ts >= day_start_ms)
    if not or_candles:
        return None
    return max(c.high for c in or_candles), min(c.low for c in or_candles), elapsed


def atr_percentile(atr_series: Sequence[Optional[float]], lookback: int = 100) -> List[Optional[float]]:
    """Percentile rank of the current ATR within its trailing window (0-100)."""
    return percent_rank(list(atr_series), lookback)


def is_bullish_engulfing(prev: "Candle", cur: "Candle") -> bool:
    return (prev.close < prev.open          # prior bar red
            and cur.close > cur.open        # current bar green
            and cur.close >= prev.open      # body engulfs
            and cur.open <= prev.close)


def is_bearish_engulfing(prev: "Candle", cur: "Candle") -> bool:
    return (prev.close > prev.open
            and cur.close < cur.open
            and cur.open >= prev.close
            and cur.close <= prev.open)


def squeeze_on(
    bb_upper: Optional[float], bb_lower: Optional[float],
    kc_upper: Optional[float], kc_lower: Optional[float],
) -> bool:
    """TTM Squeeze: Bollinger Bands nested inside the Keltner Channel."""
    if None in (bb_upper, bb_lower, kc_upper, kc_lower):
        return False
    return bb_upper < kc_upper and bb_lower > kc_lower  # type: ignore[operator]


# --------------------------------------------------------------------------- #
# Trading primitives
# --------------------------------------------------------------------------- #


@dataclass
class Decision:
    """What a strategy wants to do this candle."""

    action: str = "hold"            # "buy" | "sell" | "hold"
    notional: Optional[float] = None
    qty: Optional[float] = None
    reason: str = ""
    limit_price: Optional[float] = None   # set by limit-order strategies (grid)
    grid_level: Optional[int] = None

    @property
    def is_buy(self) -> bool:
        return self.action == "buy"

    @property
    def is_sell(self) -> bool:
        return self.action == "sell"


class Rejection(Exception):
    """Raised internally when an order cannot be simulated."""


@dataclass
class Lot:
    qty: float
    price: float
    fee: float

    def to_dict(self) -> Dict[str, Any]:
        return {"qty": self.qty, "price": self.price, "fee": self.fee}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Lot":
        return cls(qty=float(d["qty"]), price=float(d["price"]), fee=float(d.get("fee", 0.0)))


class Account:
    """One isolated virtual sub-account."""

    def __init__(self, account_id: str, name: str, starting_balance: float):
        self.id = account_id
        self.name = name
        self.balance_usd = float(starting_balance)
        self.starting_balance = float(starting_balance)
        self.crypto_holdings = 0.0
        self.entry_price: Optional[float] = None
        self.unrealized_pnl = 0.0
        self.realized_pnl = 0.0
        self.total_fees = 0.0
        self.trades: List[Dict[str, Any]] = []
        self.lots: List[Lot] = []
        self.strategy_state: Dict[str, Any] = {}
        self.last_candle_ts: Optional[int] = None
        self.rejections: List[str] = []
        self.errors: List[str] = []
        self.rejection_repeats: Dict[str, int] = {}
        # Transient order queue for multi-position strategies (grid). Never
        # persisted: it is drained within the same candle it is created.
        self.pending_orders: List["Decision"] = []

    # -- derived ------------------------------------------------------------ #

    @property
    def open_entry_fee(self) -> float:
        return sum(l.fee for l in self.lots)

    @property
    def in_position(self) -> bool:
        return self.crypto_holdings > MIN_QTY_STEP

    def equity(self, price: float) -> float:
        return self.balance_usd + self.crypto_holdings * price

    def mark_to_market(self, price: float) -> None:
        """Recompute entry price / unrealized PnL from the FIFO lot book."""
        total_qty = sum(l.qty for l in self.lots)
        if total_qty <= MIN_QTY_STEP:
            self.lots = []
            self.crypto_holdings = 0.0
            self.entry_price = None
            self.unrealized_pnl = 0.0
            return
        self.crypto_holdings = total_qty
        self.entry_price = sum(l.qty * l.price for l in self.lots) / total_qty
        self.unrealized_pnl = (price - self.entry_price) * total_qty

    def stats(self) -> Dict[str, Any]:
        closed = [t for t in self.trades if t["side"] == "sell"]
        wins = [t for t in closed if t["pnl"] > 0]
        losses = [t for t in closed if t["pnl"] <= 0]
        pnls = [t["pnl"] for t in closed]
        return {
            "trades": len(self.trades),
            "closed_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(closed) * 100.0) if closed else 0.0,
            "best_trade": max(pnls) if pnls else 0.0,
            "worst_trade": min(pnls) if pnls else 0.0,
        }

    # -- persistence -------------------------------------------------------- #

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.id,
            "name": self.name,
            "balance_usd": round(self.balance_usd, 8),
            "crypto_holdings": round(self.crypto_holdings, 12),
            "entry_price": None if self.entry_price is None else round(self.entry_price, 8),
            "unrealized_pnl": round(self.unrealized_pnl, 8),
            "realized_pnl": round(self.realized_pnl, 8),
            "total_fees": round(self.total_fees, 8),
            "starting_balance": round(self.starting_balance, 8),
            "last_candle_ts": self.last_candle_ts,
            "lots": [l.to_dict() for l in self.lots],
            "strategy_state": self.strategy_state,
            "trades": self.trades,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any], starting_balance: float) -> "Account":
        acc = cls(
            account_id=d.get("strategy_id") or d.get("id", "unknown"),
            name=d.get("name", d.get("strategy_id", "unknown")),
            starting_balance=float(d.get("starting_balance", starting_balance)),
        )
        acc.balance_usd = float(d.get("balance_usd", acc.starting_balance))
        acc.crypto_holdings = float(d.get("crypto_holdings", 0.0))
        entry = d.get("entry_price")
        acc.entry_price = float(entry) if entry is not None else None
        acc.unrealized_pnl = float(d.get("unrealized_pnl", 0.0))
        acc.realized_pnl = float(d.get("realized_pnl", 0.0))
        acc.total_fees = float(d.get("total_fees", 0.0))
        acc.last_candle_ts = d.get("last_candle_ts")
        acc.trades = list(d.get("trades", []))
        acc.strategy_state = dict(d.get("strategy_state", {}) or {})
        acc.lots = [Lot.from_dict(l) for l in d.get("lots", [])]
        # Reconcile holdings with the lot book in case of an older state file.
        if not acc.lots and acc.crypto_holdings > MIN_QTY_STEP and acc.entry_price:
            acc.lots = [Lot(qty=acc.crypto_holdings, price=acc.entry_price, fee=0.0)]
        elif acc.lots:
            acc.crypto_holdings = sum(l.qty for l in acc.lots)
        return acc


class Broker:
    """Simulated spot broker: fee model, FIFO lot book, risk guards."""

    def __init__(self, cfg: Config, log: logging.Logger):
        self.cfg = cfg
        self.log = log

    def _fill_price(self, price: float, side: str) -> float:
        """Apply adverse slippage to the reference price."""
        slip = self.cfg.slippage
        if slip <= 0:
            return price
        return price * (1 + slip) if side == "buy" else price * (1 - slip)

    def buy(
        self,
        acc: Account,
        ref_price: float,
        notional: Optional[float] = None,
        qty: Optional[float] = None,
        reason: str = "",
        candle_ts: Optional[int] = None,
        ts_iso: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        price = self._fill_price(ref_price, "buy")
        if price <= EPS:
            self._reject(acc, f"invalid price {price!r}")
            return None

        if qty is None:
            if notional is None or notional <= EPS:
                self._reject(acc, "buy with neither qty nor notional")
                return None
            qty = notional / price

        cost = qty * price
        fee = cost * self.cfg.fee_rate
        required = cost + fee

        if required > acc.balance_usd + 1e-9:
            self._reject(
                acc,
                f"insufficient balance: need {required:.4f} USDT, have {acc.balance_usd:.4f} USDT",
            )
            return None
        if cost < self.cfg.min_notional:
            self._reject(
                acc,
                f"order {cost:.4f} USDT below min notional {self.cfg.min_notional:.2f} USDT",
            )
            return None
        if qty <= MIN_QTY_STEP:
            self._reject(acc, "computed quantity rounds to zero")
            return None

        acc.balance_usd -= required
        acc.total_fees += fee
        acc.lots.append(Lot(qty=qty, price=price, fee=fee))
        acc.crypto_holdings += qty

        trade = {
            "timestamp": ts_iso or utcnow_iso(),
            "candle_ts": candle_ts,
            "side": "buy",
            "price": price,
            "qty": qty,
            "notional": cost,
            "fee": fee,
            "pnl": 0.0,
            "gross_pnl": 0.0,
            "exit_reason": None,
            "entry_reason": reason,
            "balance_after": acc.balance_usd,
            "holdings_after": acc.crypto_holdings,
        }
        acc.trades.append(trade)
        self.log.info("    BUY  %s  qty=%.10f @ %.4f  cost=%.4f  fee=%.4f  (%s)",
                      acc.id, qty, price, cost, fee, reason)
        return trade

    def sell(
        self,
        acc: Account,
        ref_price: float,
        qty: Optional[float] = None,
        reason: str = "",
        candle_ts: Optional[int] = None,
        ts_iso: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not acc.in_position:
            self._reject(acc, "sell with no open position")
            return None
        price = self._fill_price(ref_price, "sell")
        if price <= EPS:
            self._reject(acc, f"invalid price {price!r}")
            return None

        if qty is None or qty >= acc.crypto_holdings - MIN_QTY_STEP:
            qty = acc.crypto_holdings

        proceeds = qty * price
        fee = proceeds * self.cfg.fee_rate

        # Consume lots FIFO so realized PnL is attributable per lot.
        remaining = qty
        entry_cost = 0.0
        entry_fee = 0.0
        new_lots: List[Lot] = []
        for lot in acc.lots:
            if remaining <= MIN_QTY_STEP:
                new_lots.append(lot)
                continue
            take = min(lot.qty, remaining)
            entry_cost += take * lot.price
            entry_fee += lot.fee * (take / lot.qty) if lot.qty > EPS else 0.0
            remaining -= take
            leftover = lot.qty - take
            if leftover > MIN_QTY_STEP:
                new_lots.append(Lot(qty=leftover, price=lot.price, fee=lot.fee * (leftover / lot.qty)))
        acc.lots = new_lots

        gross_pnl = proceeds - entry_cost
        net_pnl = gross_pnl - entry_fee - fee

        acc.balance_usd += proceeds - fee
        acc.total_fees += fee
        acc.realized_pnl += net_pnl
        acc.crypto_holdings = sum(l.qty for l in acc.lots)

        trade = {
            "timestamp": ts_iso or utcnow_iso(),
            "candle_ts": candle_ts,
            "side": "sell",
            "price": price,
            "qty": qty,
            "notional": proceeds,
            "fee": fee,
            "pnl": net_pnl,
            "gross_pnl": gross_pnl,
            "exit_reason": reason,
            "entry_reason": None,
            "balance_after": acc.balance_usd,
            "holdings_after": acc.crypto_holdings,
        }
        acc.trades.append(trade)
        self.log.info("    SELL %s  qty=%.10f @ %.4f  pnl=%+.4f  fee=%.4f  (%s)",
                      acc.id, qty, price, net_pnl, fee, reason)
        return trade

    def _reject(self, acc: Account, message: str) -> None:
        if message in acc.rejections:
            acc.rejection_repeats[message] = acc.rejection_repeats.get(message, 1) + 1
            self.log.debug("    SKIP %s (repeat): %s", acc.id, message)
            return
        acc.rejections.append(message)
        self.log.warning("    SKIP %s: %s", acc.id, message)


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #


class Strategy:
    """Base class. Subclasses implement :meth:`evaluate`."""

    id: str = "base"
    name: str = "Base"
    category: str = "misc"
    single_position: bool = True
    warmup: int = 30
    params: Dict[str, Any] = {}

    def __init__(self, overrides: Optional[Dict[str, Any]] = None):
        self.p: Dict[str, Any] = dict(self.__class__.params)
        if overrides:
            unknown = set(overrides) - set(self.p)
            if unknown:
                logging.warning("[%s] ignoring unknown params: %s", self.id, ", ".join(sorted(unknown)))
            for k, v in overrides.items():
                if k in self.p:
                    self.p[k] = v

    # -- helpers ------------------------------------------------------------ #

    def buy(self, notional: Optional[float] = None, qty: Optional[float] = None, reason: str = "",
            limit_price: Optional[float] = None) -> Decision:
        return Decision("buy", notional=notional, qty=qty, reason=reason, limit_price=limit_price)

    def sell(self, reason: str = "", qty: Optional[float] = None, limit_price: Optional[float] = None) -> Decision:
        return Decision("sell", qty=qty, reason=reason, limit_price=limit_price)

    def hold(self, reason: str = "") -> Decision:
        return Decision("hold", reason=reason)

    def size_notional(self, acc: Account, cfg: Optional[Config] = None) -> float:
        """Cash to commit to a single-position entry.

        A per-strategy ``alloc`` wins; otherwise fall back to the global
        ``position_alloc`` so ``--alloc``/``BOT_POSITION_ALLOC`` tune everything.
        """
        alloc = self.p.get("alloc")
        if alloc is None:
            alloc = cfg.position_alloc if cfg is not None else 0.95
        alloc = max(0.0, min(1.0, float(alloc)))
        return acc.balance_usd * alloc

    # -- entry point -------------------------------------------------------- #

    def decide(self, acc: Account, md: MarketData, cfg: Config,
               portfolio: Optional[Dict[str, Any]] = None) -> Decision:
        if not md.warmup_ok(self.warmup):
            return self.hold(f"warmup {len(md)}/{self.warmup}")
        try:
            decision = self.evaluate(acc, md, cfg, portfolio)
        except Exception as exc:  # never let one strategy kill the run
            # Recorded, not just logged: a strategy that raises on every candle
            # would otherwise look identical to one that simply never signals.
            note = f"{type(exc).__name__}: {exc}"
            if note not in acc.errors:
                acc.errors.append(note)
            logging.exception("[%s] evaluation failed: %s", self.id, exc)
            return self.hold(f"error: {exc}")

        if decision.is_buy and self.single_position and acc.in_position:
            return self.hold(f"already in position (entry {acc.entry_price:.4f})")
        if decision.is_sell and not acc.in_position:
            return self.hold("no position to close")
        return decision

    def evaluate(self, acc: Account, md: MarketData, cfg: Config,
                 portfolio: Optional[Dict[str, Any]] = None) -> Decision:  # pragma: no cover
        raise NotImplementedError


# ---- 1. RSI Mean Reversion ------------------------------------------------ #


class RsiMeanReversion(Strategy):
    id = "01_rsi_mean_reversion"
    name = "RSI Mean Reversion"
    category = "Momentum & Trend Following"
    warmup = 20
    params = {"rsi_period": 14, "rsi_buy": 30.0, "rsi_sell": 70.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        r = rsi(md.closes, int(self.p["rsi_period"]))
        cur = r[-1]
        if cur is None:
            return self.hold("RSI warming up")
        if cur < self.p["rsi_buy"]:
            return self.buy(self.size_notional(acc, cfg), reason=f"RSI({self.p['rsi_period']})={cur:.2f} < {self.p['rsi_buy']:.0f} (oversold)")
        if cur > self.p["rsi_sell"]:
            return self.sell(f"RSI({self.p['rsi_period']})={cur:.2f} > {self.p['rsi_sell']:.0f} (overbought)")
        return self.hold(f"RSI={cur:.2f} neutral")


# ---- 2. Dual EMA Crossover ------------------------------------------------ #


class DualEmaCrossover(Strategy):
    id = "02_dual_ema_crossover"
    name = "Dual EMA Crossover (9/21)"
    category = "Momentum & Trend Following"
    warmup = 30
    params = {"fast": 9, "slow": 21, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        f = ema(md.closes, int(self.p["fast"]))
        s = ema(md.closes, int(self.p["slow"]))
        if crossed_above(f[-2], f[-1], s[-2], s[-1]):
            return self.buy(self.size_notional(acc, cfg), reason=f"EMA{self.p['fast']} crossed above EMA{self.p['slow']}")
        if crossed_below(f[-2], f[-1], s[-2], s[-1]):
            return self.sell(f"EMA{self.p['fast']} crossed below EMA{self.p['slow']}")
        return self.hold(f"EMA{self.p['fast']}={f[-1]:.2f} vs EMA{self.p['slow']}={s[-1]:.2f}")


# ---- 3. MACD Histogram Reversal ------------------------------------------- #


class MacdHistogramReversal(Strategy):
    id = "03_macd_histogram_reversal"
    name = "MACD Signal Crossover"
    category = "Momentum & Trend Following"
    warmup = 45
    params = {"fast": 12, "slow": 26, "signal": 9, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        line, sig, hist = macd(md.closes, int(self.p["fast"]), int(self.p["slow"]), int(self.p["signal"]))
        if hist[-1] is None or hist[-2] is None:
            return self.hold("MACD warming up")
        if hist[-2] <= 0 < hist[-1]:
            return self.buy(self.size_notional(acc, cfg), reason=f"MACD line crossed above signal (hist {hist[-1]:+.2f})")
        if hist[-2] >= 0 > hist[-1]:
            return self.sell(f"MACD line crossed below signal (hist {hist[-1]:+.2f})")
        return self.hold(f"MACD hist={hist[-1]:+.2f}")


# ---- 4. Triple Moving Average --------------------------------------------- #


class TripleMovingAverage(Strategy):
    id = "04_triple_moving_average"
    name = "Triple MA Trend (20/50/200)"
    category = "Momentum & Trend Following"
    warmup = 200
    params = {"fast": 20, "mid": 50, "slow": 200, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        s_fast = sma(md.closes, int(self.p["fast"]))
        s_mid = sma(md.closes, int(self.p["mid"]))
        s_slow = sma(md.closes, int(self.p["slow"]))
        if None in (s_fast[-1], s_mid[-1], s_slow[-1]):
            return self.hold("SMA200 warming up")

        bullish = s_fast[-1] > s_mid[-1] > s_slow[-1]  # type: ignore[operator]
        breakdown = s_fast[-1] < s_mid[-1]            # type: ignore[operator]

        if bullish and not acc.in_position:
            return self.buy(
                self.size_notional(acc, cfg),
                reason=(
                    f"trend confirmed SMA{self.p['fast']}={s_fast[-1]:.2f} > "
                    f"SMA{self.p['mid']}={s_mid[-1]:.2f} > SMA{self.p['slow']}={s_slow[-1]:.2f}"
                ),
            )
        if acc.in_position and breakdown:
            return self.sell(f"SMA{self.p['fast']} dropped below SMA{self.p['mid']}")
        if acc.in_position:
            return self.hold("trend intact")
        return self.hold("no trend alignment")


# ---- 5. Supertrend / ATR --------------------------------------------------- #


class SupertrendAtr(Strategy):
    id = "05_supertrend_atr"
    name = "Supertrend ATR Trailing Stop"
    category = "Momentum & Trend Following"
    warmup = 25
    params = {"atr_period": 10, "multiplier": 3.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        line, direction = supertrend(md.highs, md.lows, md.closes, int(self.p["atr_period"]), float(self.p["multiplier"]))
        d_cur, d_prev = direction[-1], direction[-2]
        if d_cur is None or d_prev is None:
            return self.hold("Supertrend warming up")
        stop = line[-1] or 0.0
        acc.strategy_state["supertrend_stop"] = stop
        acc.strategy_state["supertrend_direction"] = d_cur

        if d_prev == -1 and d_cur == 1:
            return self.buy(self.size_notional(acc, cfg), reason=f"Supertrend flipped bullish (stop {stop:.2f})")
        if d_prev == 1 and d_cur == -1:
            return self.sell(f"Supertrend flipped bearish (stop {stop:.2f})")
        if d_cur == 1 and acc.in_position and md.price < stop:
            return self.sell(f"ATR trailing stop breached at {stop:.2f}")
        return self.hold(f"Supertrend dir={d_cur:+d} stop={stop:.2f}")


# ---- 6. Bollinger Bands Mean Reversion ------------------------------------ #


class BollingerMeanReversion(Strategy):
    id = "06_bollinger_mean_reversion"
    name = "Bollinger Bands Mean Reversion"
    category = "Mean Reversion & Channels"
    warmup = 25
    params = {"period": 20, "mult": 2.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        upper, mid, lower = bollinger(md.closes, int(self.p["period"]), float(self.p["mult"]))
        if None in (upper[-1], mid[-1], lower[-1]):
            return self.hold("Bollinger warming up")
        close = md.price
        if close < lower[-1]:
            return self.buy(self.size_notional(acc, cfg), reason=f"close {close:.2f} < lower band {lower[-1]:.2f}")
        if acc.in_position and close >= mid[-1]:
            return self.sell(f"close {close:.2f} reached middle band {mid[-1]:.2f}")
        return self.hold(f"close {close:.2f} inside bands")


# ---- 7. Keltner Channel Breakout ------------------------------------------ #


class KeltnerBreakout(Strategy):
    id = "07_keltner_breakout"
    name = "Keltner Channel Breakout"
    category = "Mean Reversion & Channels"
    warmup = 25
    params = {"period": 20, "mult": 2.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        upper, mid, lower = keltner(md.highs, md.lows, md.closes, int(self.p["period"]), float(self.p["mult"]))
        if None in (upper[-1], mid[-1]):
            return self.hold("Keltner warming up")
        close = md.price
        if close > upper[-1]:
            return self.buy(self.size_notional(acc, cfg), reason=f"close {close:.2f} > upper Keltner {upper[-1]:.2f}")
        if acc.in_position and close < mid[-1]:
            return self.sell(f"close {close:.2f} back below middle line {mid[-1]:.2f}")
        return self.hold(f"close {close:.2f} inside channel")


# ---- 8. Stochastic RSI ----------------------------------------------------- #


class StochRsiReversal(Strategy):
    id = "08_stoch_rsi_reversal"
    name = "Stochastic RSI Reversal"
    category = "Mean Reversion & Channels"
    warmup = 35
    params = {
        "rsi_period": 14,
        "stoch_period": 14,
        "k_period": 3,
        "d_period": 3,
        "oversold": 20.0,
        "overbought": 80.0,
        "alloc": None,
    }

    def evaluate(self, acc, md, cfg, portfolio=None):
        k, d = stoch_rsi(
            md.closes,
            int(self.p["rsi_period"]),
            int(self.p["stoch_period"]),
            int(self.p["k_period"]),
            int(self.p["d_period"]),
        )
        if None in (k[-1], k[-2], d[-1], d[-2]):
            return self.hold("StochRSI warming up")

        buy_cross = k[-2] < d[-2] and k[-1] > d[-1] and k[-2] <= self.p["oversold"]
        sell_cross = k[-2] > d[-2] and k[-1] < d[-1] and k[-2] >= self.p["overbought"]

        if buy_cross:
            return self.buy(self.size_notional(acc, cfg), reason=f"%K crossed above %D in oversold zone (K={k[-1]:.1f})")
        if sell_cross:
            return self.sell(f"%K crossed below %D in overbought zone (K={k[-1]:.1f})")
        return self.hold(f"%K={k[-1]:.1f} %D={d[-1]:.1f}")


# ---- 9. VWAP Pullback ------------------------------------------------------ #


class VwapPullback(Strategy):
    id = "09_vwap_pullback"
    name = "Session VWAP Pullback"
    category = "Volume & Volatility"
    warmup = 20
    params = {"rsi_period": 14, "rsi_min": 40.0, "extension_pct": 1.5, "min_session_candles": 2, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        vwap, n_session = session_vwap(md.candles)
        acc.strategy_state["vwap"] = vwap
        if n_session < int(self.p["min_session_candles"]):
            return self.hold(f"session too young ({n_session} candles)")

        close = md.price
        r = rsi(md.closes, int(self.p["rsi_period"]))[-1]
        if r is None:
            return self.hold("RSI warming up")

        ext_threshold = vwap * (1.0 + float(self.p["extension_pct"]) / 100.0)
        if close >= ext_threshold:
            return self.sell(f"price {close:.2f} extended {self.p['extension_pct']}% above VWAP {vwap:.2f}")
        if close < vwap and r > self.p["rsi_min"]:
            return self.buy(
                self.size_notional(acc, cfg),
                reason=f"price {close:.2f} < VWAP {vwap:.2f} with RSI {r:.1f} > {self.p['rsi_min']:.0f}",
            )
        return self.hold(f"price {close:.2f} vs VWAP {vwap:.2f}, RSI {r:.1f}")


# ---- 10. Donchian Breakout (Turtle) --------------------------------------- #


class DonchianBreakout(Strategy):
    id = "10_donchian_breakout"
    name = "Donchian Turtle Breakout (20/10)"
    category = "Volume & Volatility"
    warmup = 25
    params = {"entry_period": 20, "exit_period": 10, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        upper, mid, lower = donchian(md.highs, md.lows, int(self.p["entry_period"]), int(self.p["exit_period"]))
        if upper[-1] is None or lower[-1] is None:
            return self.hold("Donchian warming up")
        close = md.price
        if close > upper[-1]:
            return self.buy(self.size_notional(acc, cfg), reason=f"close {close:.2f} broke {self.p['entry_period']}-candle high {upper[-1]:.2f}")
        if acc.in_position and close < lower[-1]:
            return self.sell(f"close {close:.2f} broke {self.p['exit_period']}-candle low {lower[-1]:.2f}")
        return self.hold(f"close {close:.2f} inside channel")


# ---- 11. Dynamic DCA ------------------------------------------------------- #


class DynamicDca(Strategy):
    """Periodic accumulation. Buys every ``interval`` candles and doubles the
    order when the trailing 24h change is negative. Never holds a single
    position; accumulates a ladder of lots."""

    id = "11_dynamic_dca"
    name = "Dynamic DCA (Dip Multiplier)"
    category = "Execution-Based & Portfolio"
    single_position = False
    warmup = 2
    params = {
        "interval_candles": 4,       # every 4 x 15m candles == hourly
        "base_notional": 50.0,
        "dip_multiplier": 2.0,
        "lookback_24h": 96,          # 96 x 15m == 24h
        "take_profit_pct": None,     # optional: exit whole stack at +X%
    }

    def evaluate(self, acc, md, cfg, portfolio=None):
        st = acc.strategy_state
        runs = int(st.get("runs", 0)) + 1
        st["runs"] = runs
        st["last_price"] = md.price

        # Optional take-profit on the whole accumulated stack.
        tp = self.p.get("take_profit_pct")
        if tp and acc.in_position and acc.entry_price:
            gain_pct = (md.price - acc.entry_price) / acc.entry_price * 100.0
            if gain_pct >= float(tp):
                st["runs"] = 0
                return self.sell(f"DCA stack take-profit at +{gain_pct:.2f}%")

        interval = int(self.p["interval_candles"])
        if runs % interval != 0:
            return self.hold(f"DCA tick {runs}/{interval}")

        change = md.change_pct(int(self.p["lookback_24h"]))
        st["last_24h_change_pct"] = change
        base = float(self.p["base_notional"])
        notional = base
        if change is not None and change < 0:
            notional = base * float(self.p["dip_multiplier"])

        label = f"24h {change:+.2f}%" if change is not None else "24h n/a"
        affordable = acc.balance_usd / (1.0 + cfg.fee_rate) if cfg.fee_rate > 0 else acc.balance_usd
        if notional > affordable:
            return self.hold(f"DCA order {notional:.2f} exceeds affordable cash {affordable:.2f}")
        return self.buy(
            notional=notional,
            reason=f"scheduled DCA buy #{runs} ({label})" + (" [dip x2]" if notional > base else ""),
        )


# ---- 12. Fixed-Step Arithmetic Grid --------------------------------------- #


class ArithmeticGrid(Strategy):
    """Virtual limit ladder around an anchor price.

    The ladder is *arithmetic*: levels are spaced by a constant absolute price
    increment equal to ``step_pct`` of the anchor, rather than by a compounding
    percentage. Each buy level takes profit exactly one step above its own fill
    price, so every completed round trip books ``step_pct`` gross less two fees.
    """

    id = "12_arithmetic_grid"
    name = "Fixed-Step Arithmetic Grid"
    category = "Execution-Based & Portfolio"
    single_position = False
    warmup = 2
    params = {
        "step_pct": 1.0,          # 1% absolute spacing (relative to anchor)
        "levels_each_side": 5,    # 5 buy levels below anchor, 5 sell levels above
        "capital_pct": 0.95,      # share of current equity committed to the grid
        "reanchor_pct": 6.0,      # rebuild ladder when price leaves channel by this much
    }

    # -- ladder construction ------------------------------------------------ #

    def _build_ladder(self, acc: Account, anchor: float, price: float) -> None:
        """Build (or rebuild) the ladder around ``anchor``.

        Per-level capital is sized from the account's *current* equity, so a
        losing grid scales down instead of repeatedly attempting orders the
        broker must refuse, and a winning grid compounds.
        """
        step_pct = float(self.p["step_pct"]) / 100.0
        n = int(self.p["levels_each_side"])
        step_price = anchor * step_pct
        capital = max(acc.equity(price), 0.0) * float(self.p["capital_pct"])
        per_level = capital / n if n > 0 else 0.0

        levels = []
        for i in range(-n, n + 1):
            levels.append(
                {
                    "index": i,
                    "price": anchor + i * step_price,
                    "side": "buy" if i < 0 else ("neutral" if i == 0 else "sell"),
                    "qty": per_level / (anchor + i * step_price) if (anchor + i * step_price) > EPS else 0.0,
                    "holding": False,
                    "fills": 0,
                }
            )
        acc.strategy_state["grid"] = {
            "anchor": anchor,
            "step_price": step_price,
            "per_level_usd": per_level,
            "levels": levels,
            "round_trips": 0,
            "rebuilt": acc.strategy_state.get("grid", {}).get("rebuilt", 0),
        }

    def evaluate(self, acc, md, cfg, portfolio=None):
        grid = acc.strategy_state.get("grid")
        price = md.price
        if not grid:
            self._build_ladder(acc, price, price)
            grid = acc.strategy_state["grid"]
            acc.strategy_state["grid_log"] = [f"grid anchored at {price:.2f}"]

        anchor = float(grid["anchor"])
        deviation_pct = (price - anchor) / anchor * 100.0 if anchor > EPS else 0.0

        # Re-anchor when price has drifted out of the channel. Inventory from
        # the old ladder has no matching levels any more, so it is liquidated
        # rather than orphaned in the lot book.
        if abs(deviation_pct) > float(self.p["reanchor_pct"]):
            rebuilt = int(grid.get("rebuilt", 0)) + 1
            if acc.in_position:
                acc.pending_orders.append(
                    Decision(
                        "sell",
                        qty=acc.crypto_holdings,
                        reason=f"grid re-anchored after {deviation_pct:+.2f}% drift — inventory liquidated",
                    )
                )
            self._build_ladder(acc, price, price)
            grid = acc.strategy_state["grid"]
            grid["rebuilt"] = rebuilt
            acc.strategy_state["grid_log"].append(
                f"re-anchored at {price:.2f} after {deviation_pct:+.2f}% drift (rebuild #{rebuilt})"
            )
            return self.hold(f"grid re-anchored at {price:.2f}")

        candle = md.candles[-1]
        levels = grid["levels"]
        step_price = float(grid["step_price"])

        # 1) Sell pass first (nearest the anchor outwards) so freed capital is
        #    available to the buy pass within the same candle.
        for lvl in sorted([l for l in levels if l["index"] < 0], key=lambda x: -x["index"]):
            if not lvl["holding"] or lvl["qty"] <= MIN_QTY_STEP:
                continue
            target = lvl["price"] + step_price
            if candle.high >= target:
                gross_yield_pct = (target - lvl["price"]) / lvl["price"] * 100.0
                acc.pending_orders.append(
                    Decision(
                        "sell",
                        qty=lvl["qty"],
                        reason=f"grid level {lvl['index']} take-profit at {target:.2f} (+{gross_yield_pct:.2f}% gross)",
                        limit_price=target,
                        grid_level=lvl["index"],
                    )
                )
                lvl["holding"] = False
                grid["round_trips"] = int(grid.get("round_trips", 0)) + 1

        # 2) Buy pass (deepest level first, mirroring the order price fell).
        for lvl in sorted([l for l in levels if l["index"] < 0], key=lambda x: x["index"]):
            if lvl["holding"]:
                continue
            if candle.low <= lvl["price"]:
                notional = lvl["qty"] * lvl["price"]
                acc.pending_orders.append(
                    Decision(
                        "buy",
                        notional=notional,
                        reason=f"grid level {lvl['index']} limit buy filled at {lvl['price']:.2f}",
                        limit_price=lvl["price"],
                        grid_level=lvl["index"],
                    )
                )
                lvl["holding"] = True
                lvl["fills"] = int(lvl.get("fills", 0)) + 1

        holding_levels = sum(1 for l in levels if l["holding"])
        return self.hold(
            f"grid ok: {holding_levels}/{int(self.p['levels_each_side'])} levels loaded, "
            f"{grid.get('round_trips', 0)} round trips"
        )


# ---- 13. ADX / DMI Trend Strength ------------------------------------------ #


class AdxDmiTrend(Strategy):
    id = "13_adx_dmi_trend"
    name = "ADX DMI Trend Strength"
    category = "Momentum & Trend Following"
    warmup = 35
    params = {"period": 14, "adx_min": 25.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"adx{self.p['period']}"
        adx, pdi, mdi = md.cached(
            key, lambda: adx_dmi(md.highs, md.lows, md.closes, int(self.p["period"]))
        )
        if None in (adx[-1], adx[-2], pdi[-1], pdi[-2], mdi[-1], mdi[-2]):
            return self.hold("ADX warming up")
        strong = adx[-1] >= self.p["adx_min"]
        up_cross = pdi[-2] <= mdi[-2] and pdi[-1] > mdi[-1]
        down_cross = pdi[-2] >= mdi[-2] and pdi[-1] < mdi[-1]

        if up_cross and strong:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"+DI crossed above -DI with ADX {adx[-1]:.1f} >= {self.p['adx_min']:.0f}")
        if acc.in_position and (down_cross or adx[-1] < self.p["adx_min"] * 0.8):
            why = "-DI crossed above +DI" if down_cross else f"ADX faded to {adx[-1]:.1f}"
            return self.sell(why)
        return self.hold(f"ADX={adx[-1]:.1f} +DI={pdi[-1]:.1f} -DI={mdi[-1]:.1f}")


# ---- 14. Ichimoku Cloud ----------------------------------------------------- #


class IchimokuCloud(Strategy):
    id = "14_ichimoku_cloud"
    name = "Ichimoku Cloud Breakout"
    category = "Momentum & Trend Following"
    warmup = 80
    params = {"tenkan": 9, "kijun": 26, "senkou_b": 52, "displacement": 26, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"ichi{self.p['tenkan']}-{self.p['kijun']}-{self.p['senkou_b']}"
        ichi = md.cached(key, lambda: ichimoku(
            md.highs, md.lows, md.closes,
            int(self.p["tenkan"]), int(self.p["kijun"]),
            int(self.p["senkou_b"]), int(self.p["displacement"]),
        ))
        top, bottom = ichi["cloud_top"][-1], ichi["cloud_bottom"][-1]
        t, k = ichi["tenkan"][-1], ichi["kijun"][-1]
        if None in (top, bottom, t, k):
            return self.hold("Ichimoku warming up")
        close = md.price

        if close > top and t > k:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"close {close:.2f} above cloud top {top:.2f}, tenkan > kijun")
        if acc.in_position and (close < bottom or t < k):
            why = f"close fell below cloud bottom {bottom:.2f}" if close < bottom else "tenkan crossed below kijun"
            return self.sell(why)
        return self.hold(f"inside cloud ({bottom:.2f}-{top:.2f})" if bottom <= close <= top
                         else f"close {close:.2f} outside cloud, tenkan-kijun {t - k:+.2f}")


# ---- 15. Parabolic SAR ------------------------------------------------------ #


class ParabolicSarFlip(Strategy):
    id = "15_parabolic_sar"
    name = "Parabolic SAR Flip"
    category = "Momentum & Trend Following"
    warmup = 15
    params = {"step": 0.02, "maximum": 0.2, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"sar{self.p['step']}-{self.p['maximum']}"
        sar = md.cached(key, lambda: parabolic_sar(md.highs, md.lows, float(self.p["step"]), float(self.p["maximum"])))
        if sar[-1] is None or sar[-2] is None:
            return self.hold("SAR warming up")
        below_now = md.closes[-1] > sar[-1]
        below_prev = md.closes[-2] > sar[-2]

        if below_now and not below_prev:
            return self.buy(self.size_notional(acc, cfg), reason=f"SAR flipped below price (stop {sar[-1]:.2f})")
        if acc.in_position and not below_now:
            return self.sell(f"SAR flipped above price (stop {sar[-1]:.2f})")
        return self.hold(f"SAR {sar[-1]:.2f} {'below' if below_now else 'above'} close {md.price:.2f}")


# ---- 16. ROC Momentum ------------------------------------------------------- #


class RocMomentum(Strategy):
    id = "16_roc_momentum"
    name = "ROC Momentum Burst"
    category = "Momentum & Trend Following"
    warmup = 20
    params = {"period": 12, "entry_pct": 2.0, "exit_pct": 0.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"roc{self.p['period']}"
        r = md.cached(key, lambda: roc(md.closes, int(self.p["period"])))
        if r[-1] is None:
            return self.hold("ROC warming up")
        if r[-1] >= self.p["entry_pct"]:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"ROC({self.p['period']})={r[-1]:+.2f}% >= {self.p['entry_pct']:.1f}%")
        if acc.in_position and r[-1] <= self.p["exit_pct"]:
            return self.sell(f"ROC({self.p['period']})={r[-1]:+.2f}% lost momentum")
        return self.hold(f"ROC={r[-1]:+.2f}%")


# ---- 17. Aroon -------------------------------------------------------------- #


class AroonTrend(Strategy):
    id = "17_aroon_trend"
    name = "Aroon Trend"
    category = "Momentum & Trend Following"
    warmup = 30
    params = {"period": 25, "strong": 70.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"aroon{self.p['period']}"
        up, down = md.cached(key, lambda: aroon(md.highs, md.lows, int(self.p["period"])))
        if None in (up[-1], up[-2], down[-1], down[-2]):
            return self.hold("Aroon warming up")
        up_cross = up[-2] <= down[-2] and up[-1] > down[-1]
        down_cross = up[-2] >= down[-2] and up[-1] < down[-1]

        if up_cross and up[-1] >= self.p["strong"]:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"Aroon Up crossed above Down at {up[-1]:.0f} (fresh high)")
        if acc.in_position and down_cross:
            return self.sell(f"Aroon Down crossed above Up at {down[-1]:.0f} (fresh low)")
        return self.hold(f"Aroon up={up[-1]:.0f} down={down[-1]:.0f}")


# ---- 18. Heikin-Ashi -------------------------------------------------------- #


class HeikinAshiTrend(Strategy):
    id = "18_heikin_ashi_trend"
    name = "Heikin-Ashi Trend"
    category = "Momentum & Trend Following"
    warmup = 12
    params = {"confirm_bars": 3, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        ha = md.cached("heikin_ashi", lambda: heikin_ashi(md.candles))
        need = int(self.p["confirm_bars"])
        if len(ha) < need + 1:
            return self.hold("Heikin-Ashi warming up")
        last = ha[-need:]

        # A clean bullish HA bar has no lower wick: open == low.
        bullish = all(c > o and abs(o - l) <= EPS for o, h, l, c in last)
        bearish = all(c < o and abs(h - o) <= EPS for o, h, l, c in last)

        if bullish:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"{need} consecutive lower-wick-free bullish Heikin-Ashi bars")
        if acc.in_position and bearish:
            return self.sell(f"{need} consecutive upper-wick-free bearish Heikin-Ashi bars")
        return self.hold(f"HA close {ha[-1][3]:.2f}, no {need}-bar run")


# ---- 19. TRIX --------------------------------------------------------------- #


class TrixMomentum(Strategy):
    id = "19_trix_momentum"
    name = "TRIX Signal Crossover"
    category = "Momentum & Trend Following"
    warmup = 60
    params = {"period": 15, "signal": 9, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"trix{self.p['period']}-{self.p['signal']}"
        line, sig = md.cached(key, lambda: trix(md.closes, int(self.p["period"]), int(self.p["signal"])))
        if None in (line[-1], line[-2], sig[-1], sig[-2]):
            return self.hold("TRIX warming up")
        if line[-2] <= sig[-2] and line[-1] > sig[-1]:
            return self.buy(self.size_notional(acc, cfg), reason=f"TRIX crossed above signal ({line[-1]:+.4f})")
        if acc.in_position and line[-2] >= sig[-2] and line[-1] < sig[-1]:
            return self.sell(f"TRIX crossed below signal ({line[-1]:+.4f})")
        return self.hold(f"TRIX {line[-1]:+.4f} vs signal {sig[-1]:+.4f}")


# ---- 20. EMA Ribbon --------------------------------------------------------- #


class EmaRibbonConsensus(Strategy):
    id = "20_ema_ribbon_consensus"
    name = "EMA Ribbon Consensus"
    category = "Momentum & Trend Following"
    warmup = 60
    params = {"periods": "8,13,21,34,55", "alloc": None}

    def _series(self, md):
        periods = [int(p) for p in str(self.p["periods"]).split(",")]
        out = []
        for p in periods:
            out.append(md.cached(f"ema{p}", lambda p=p: ema(md.closes, p))[-1])
        return periods, out

    def evaluate(self, acc, md, cfg, portfolio=None):
        periods, vals = self._series(md)
        if any(v is None for v in vals):
            return self.hold("ribbon warming up")
        bullish = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
        bearish = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))

        if bullish:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"EMA ribbon aligned bullish ({self.p['periods']})")
        if acc.in_position and bearish:
            return self.sell(f"EMA ribbon aligned bearish ({self.p['periods']})")
        return self.hold("ribbon tangled")


# ---- 21. Williams %R -------------------------------------------------------- #


class WilliamsRReversal(Strategy):
    id = "21_williams_r_reversal"
    name = "Williams %R Reversal"
    category = "Mean Reversion & Oscillators"
    warmup = 20
    params = {"period": 14, "oversold": -80.0, "overbought": -20.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"wr{self.p['period']}"
        wr = md.cached(key, lambda: williams_r(md.highs, md.lows, md.closes, int(self.p["period"])))
        if wr[-1] is None or wr[-2] is None:
            return self.hold("Williams %R warming up")
        # Enter on the turn out of the zone, not on the way in.
        if wr[-2] <= self.p["oversold"] and wr[-1] > self.p["oversold"]:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"Williams %R turned up out of oversold ({wr[-1]:.1f})")
        if acc.in_position and wr[-1] >= self.p["overbought"]:
            return self.sell(f"Williams %R reached overbought ({wr[-1]:.1f})")
        return self.hold(f"Williams %R={wr[-1]:.1f}")


# ---- 22. CCI ---------------------------------------------------------------- #


class CciMeanReversion(Strategy):
    id = "22_cci_mean_reversion"
    name = "CCI Mean Reversion"
    category = "Mean Reversion & Oscillators"
    warmup = 25
    params = {"period": 20, "lower": -100.0, "upper": 100.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"cci{self.p['period']}"
        v = md.cached(key, lambda: cci(md.highs, md.lows, md.closes, int(self.p["period"])))
        if v[-1] is None or v[-2] is None:
            return self.hold("CCI warming up")
        if v[-2] <= self.p["lower"] and v[-1] > self.p["lower"]:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"CCI turned up through {self.p['lower']:.0f} ({v[-1]:+.0f})")
        if acc.in_position and v[-2] >= self.p["upper"] and v[-1] < self.p["upper"]:
            return self.sell(f"CCI turned down through {self.p['upper']:.0f} ({v[-1]:+.0f})")
        return self.hold(f"CCI={v[-1]:+.0f}")


# ---- 23. Connors RSI -------------------------------------------------------- #


class ConnorsRsiPullback(Strategy):
    id = "23_connors_rsi_pullback"
    name = "Connors RSI(2) Pullback"
    category = "Mean Reversion & Oscillators"
    warmup = 110
    params = {"rsi_period": 3, "streak_period": 2, "rank_period": 100,
              "buy_below": 10.0, "sell_above": 90.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"crsi{self.p['rsi_period']}-{self.p['streak_period']}-{self.p['rank_period']}"
        v = md.cached(key, lambda: connors_rsi(
            md.closes, int(self.p["rsi_period"]), int(self.p["streak_period"]), int(self.p["rank_period"])
        ))
        if v[-1] is None:
            return self.hold("Connors RSI warming up")
        if v[-1] <= self.p["buy_below"]:
            return self.buy(self.size_notional(acc, cfg), reason=f"Connors RSI {v[-1]:.1f} <= {self.p['buy_below']:.0f}")
        if acc.in_position and v[-1] >= self.p["sell_above"]:
            return self.sell(f"Connors RSI {v[-1]:.1f} >= {self.p['sell_above']:.0f}")
        return self.hold(f"Connors RSI={v[-1]:.1f}")


# ---- 24. Z-Score ------------------------------------------------------------ #


class ZScoreMeanReversion(Strategy):
    id = "24_zscore_mean_reversion"
    name = "Z-Score Mean Reversion"
    category = "Mean Reversion & Oscillators"
    warmup = 25
    params = {"period": 20, "entry_z": -2.0, "exit_z": 0.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"z{self.p['period']}"
        z = md.cached(key, lambda: zscore(md.closes, int(self.p["period"])))
        if z[-1] is None:
            return self.hold("z-score warming up (flat window)")
        if z[-1] <= self.p["entry_z"]:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"z-score {z[-1]:+.2f} <= {self.p['entry_z']:.1f} (stretched below mean)")
        if acc.in_position and z[-1] >= self.p["exit_z"]:
            return self.sell(f"z-score reverted to {z[-1]:+.2f}")
        return self.hold(f"z-score={z[-1]:+.2f}")


# ---- 25. MFI ---------------------------------------------------------------- #


class MfiFlowReversal(Strategy):
    id = "25_mfi_flow_reversal"
    name = "Money Flow Index Reversal"
    category = "Mean Reversion & Oscillators"
    warmup = 20
    params = {"period": 14, "oversold": 20.0, "overbought": 80.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"mfi{self.p['period']}"
        v = md.cached(key, lambda: mfi(md.highs, md.lows, md.closes, md.volumes, int(self.p["period"])))
        if v[-1] is None:
            return self.hold("MFI warming up")
        if v[-1] <= self.p["oversold"]:
            return self.buy(self.size_notional(acc, cfg), reason=f"MFI {v[-1]:.1f} <= {self.p['oversold']:.0f}")
        if acc.in_position and v[-1] >= self.p["overbought"]:
            return self.sell(f"MFI {v[-1]:.1f} >= {self.p['overbought']:.0f}")
        return self.hold(f"MFI={v[-1]:.1f}")


# ---- 26. Chande Momentum ---------------------------------------------------- #


class ChandeMomentum(Strategy):
    id = "26_chande_momentum"
    name = "Chande Momentum Oscillator"
    category = "Mean Reversion & Oscillators"
    warmup = 25
    params = {"period": 20, "entry": -50.0, "exit": 50.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"cmo{self.p['period']}"
        v = md.cached(key, lambda: chande_momentum(md.closes, int(self.p["period"])))
        if v[-1] is None or v[-2] is None:
            return self.hold("CMO warming up")
        if v[-2] <= self.p["entry"] and v[-1] > self.p["entry"]:
            return self.buy(self.size_notional(acc, cfg), reason=f"CMO turned up through {self.p['entry']:.0f} ({v[-1]:+.0f})")
        if acc.in_position and v[-2] >= self.p["exit"] and v[-1] < self.p["exit"]:
            return self.sell(f"CMO turned down through {self.p['exit']:.0f} ({v[-1]:+.0f})")
        return self.hold(f"CMO={v[-1]:+.0f}")


# ---- 27. OBV ---------------------------------------------------------------- #


class ObvTrendBreakout(Strategy):
    id = "27_obv_trend_breakout"
    name = "OBV Trend Breakout"
    category = "Volume & Volatility"
    warmup = 25
    params = {"lookback": 20, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        o = md.cached("obv", lambda: obv(md.closes, md.volumes))
        n = int(self.p["lookback"])
        if len(o) < n + 2:
            return self.hold("OBV warming up")
        prior = o[-n - 1 : -1]                      # strictly prior window
        new_high = o[-1] > max(prior)
        new_low = o[-1] < min(prior)

        if new_high and md.closes[-1] > max(md.closes[-n - 1 : -1]):
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"OBV made a {n}-candle high with price confirming")
        if acc.in_position and new_low:
            return self.sell(f"OBV made a {n}-candle low (distribution)")
        return self.hold(f"OBV inside its {n}-candle range")


# ---- 28. Volume Spike Breakout ---------------------------------------------- #


class VolumeSpikeBreakout(Strategy):
    id = "28_volume_spike_breakout"
    name = "Volume Spike Breakout"
    category = "Volume & Volatility"
    warmup = 25
    params = {"lookback": 20, "volume_mult": 2.0, "exit_lookback": 10, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        n = int(self.p["lookback"])
        vols = md.volumes[-n - 1 : -1]
        avg_vol = sum(vols) / len(vols) if vols else 0.0
        spike = avg_vol > EPS and md.volumes[-1] >= avg_vol * float(self.p["volume_mult"])
        prior_high = max(md.highs[-n - 1 : -1])
        exit_low = min(md.lows[-int(self.p["exit_lookback"]) - 1 : -1])

        if spike and md.closes[-1] > prior_high:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"volume {md.volumes[-1] / avg_vol:.1f}x average with a close above the {n}-candle high")
        if acc.in_position and md.closes[-1] < exit_low:
            return self.sell(f"close broke the {self.p['exit_lookback']}-candle low")
        return self.hold(f"volume {md.volumes[-1] / avg_vol:.2f}x average" if avg_vol > EPS else "no volume history")


# ---- 29. Volatility Squeeze -------------------------------------------------- #


class VolatilitySqueezeBreakout(Strategy):
    id = "29_volatility_squeeze"
    name = "Volatility Squeeze Breakout"
    category = "Volume & Volatility"
    warmup = 25
    params = {"bb_period": 20, "bb_mult": 2.0, "kc_period": 20, "kc_mult": 1.5, "alloc": None}

    def _bands(self, md):
        """Bollinger and Keltner bands as full series (computed once per candle)."""
        key = f"squeeze{self.p['bb_period']}-{self.p['kc_period']}"
        return md.cached(key, lambda: (
            bollinger(md.closes, int(self.p["bb_period"]), float(self.p["bb_mult"])),
            keltner(md.highs, md.lows, md.closes, int(self.p["kc_period"]), float(self.p["kc_mult"])),
        ))

    def evaluate(self, acc, md, cfg, portfolio=None):
        (bu_s, bm_s, bl_s), (ku_s, _, kl_s) = self._bands(md)
        bu, bm, bl = bu_s[-1], bm_s[-1], bl_s[-1]
        ku, kl = ku_s[-1], kl_s[-1]
        if None in (bu, bm, bl, ku, kl, bu_s[-2], bl_s[-2], ku_s[-2], kl_s[-2]):
            return self.hold("squeeze bands warming up")

        was_squeezed = squeeze_on(bu_s[-2], bl_s[-2], ku_s[-2], kl_s[-2])
        now_squeezed = squeeze_on(bu, bl, ku, kl)

        # TTM fires on the *release*, taking the direction from momentum
        # (close vs the middle band) rather than demanding a band break on the
        # very same candle, which almost never coincides.
        if was_squeezed and not now_squeezed and md.closes[-1] > bm:
            return self.buy(self.size_notional(acc, cfg),
                            reason="volatility squeeze released upward: bands expanded with close above the middle band")
        if acc.in_position and md.closes[-1] < bm:
            return self.sell(f"close fell back below the middle band {bm:.2f}")
        return self.hold("squeezed" if now_squeezed else "no squeeze")


# ---- 30. Elder-Ray ----------------------------------------------------------- #


class ElderRayPower(Strategy):
    id = "30_elder_ray_power"
    name = "Elder-Ray Power Shift"
    category = "Volume & Volatility"
    warmup = 20
    params = {"period": 13, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        key = f"elder{self.p['period']}"
        bull, bear = md.cached(key, lambda: elder_ray(md.highs, md.lows, md.closes, int(self.p["period"])))
        if None in (bull[-1], bull[-2], bear[-1], bear[-2]):
            return self.hold("Elder-Ray warming up")
        # Bears lose control when bear power lifts back through zero.
        if bear[-2] <= 0 < bear[-1] and bull[-1] > 0:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"bear power lifted to {bear[-1]:+.2f} with bull power {bull[-1]:+.2f}")
        if acc.in_position and bull[-2] >= 0 > bull[-1]:
            return self.sell(f"bull power fell to {bull[-1]:+.2f}")
        return self.hold(f"bull={bull[-1]:+.2f} bear={bear[-1]:+.2f}")


# ---- 31. Candlestick Engulfing ---------------------------------------------- #


class EngulfingReversal(Strategy):
    id = "31_engulfing_reversal"
    name = "Engulfing Candle Reversal"
    category = "Price Action"
    warmup = 25
    params = {"trend_lookback": 10, "trend_pct": 1.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        prev, cur = md.candles[-2], md.candles[-1]
        n = int(self.p["trend_lookback"])
        pct = float(self.p["trend_pct"])
        before = md.closes[-n - 2]
        downtrend = before > EPS and (prev.close - before) / before * 100.0 <= -pct
        uptrend = before > EPS and (prev.close - before) / before * 100.0 >= pct

        if downtrend and is_bullish_engulfing(prev, cur):
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"bullish engulfing after a {n}-candle downtrend")
        if acc.in_position and uptrend and is_bearish_engulfing(prev, cur):
            return self.sell(f"bearish engulfing after a {n}-candle uptrend")
        return self.hold("no engulfing reversal")


# ---- 32. Fibonacci Retracement ---------------------------------------------- #


class FibonacciPullback(Strategy):
    id = "32_fibonacci_pullback"
    name = "Fibonacci Retracement Pullback"
    category = "Price Action"
    warmup = 55
    params = {"swing_lookback": 50, "entry_level": "0.618", "exit_level": "0.236", "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        n = int(self.p["swing_lookback"])
        swing_high = max(md.highs[-n - 1 : -1])
        swing_low = min(md.lows[-n - 1 : -1])
        if swing_high - swing_low <= EPS:
            return self.hold("no swing range")
        uptrend = md.closes[-2] > md.closes[-n - 1]
        levels = fibonacci_levels(swing_high, swing_low)
        entry = levels[str(self.p["entry_level"])]
        exit_lv = levels[str(self.p["exit_level"])]

        if uptrend and md.closes[-2] > entry and md.closes[-1] <= entry:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"pullback to the {self.p['entry_level']} retracement at {entry:.2f}")
        if acc.in_position and md.price >= exit_lv:
            return self.sell(f"rallied back to the {self.p['exit_level']} retracement at {exit_lv:.2f}")
        return self.hold(f"close {md.price:.2f} vs {self.p['entry_level']} level {entry:.2f}")


# ---- 33. Pivot Points -------------------------------------------------------- #


class PivotPointBounce(Strategy):
    id = "33_pivot_point_bounce"
    name = "Pivot Point Bounce"
    category = "Price Action"
    warmup = 5
    params = {"alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        hlc = prior_session_hlc(md.candles)
        if hlc is None:
            return self.hold("no prior session for pivots")
        p = pivot_points(*hlc)
        acc.strategy_state["pivots"] = {k: round(v, 4) for k, v in p.items()}
        prev_close, close = md.closes[-2], md.closes[-1]

        # Bounce: dipped to or below S1 on the prior candle, then reclaimed it.
        if prev_close <= p["s1"] < close:
            return self.buy(self.size_notional(acc, cfg), reason=f"reclaimed S1 at {p['s1']:.2f}")
        if acc.in_position and close >= p["r1"]:
            return self.sell(f"reached R1 at {p['r1']:.2f}")
        return self.hold(f"close {close:.2f} vs pivot {p['p']:.2f}")


# ---- 34. Opening Range Breakout ---------------------------------------------- #


class OpeningRangeBreakout(Strategy):
    id = "34_opening_range_breakout"
    name = "Opening Range Breakout"
    category = "Price Action"
    warmup = 10
    params = {"minutes": 60, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        rng = opening_range(md.candles, int(self.p["minutes"]))
        if rng is None:
            return self.hold("no opening range yet")
        hi, lo, elapsed = rng
        if elapsed <= int(self.p["minutes"]) // 15:
            return self.hold(f"opening range still forming ({elapsed} candles)")
        acc.strategy_state["opening_range"] = {"high": hi, "low": lo}

        if md.closes[-2] <= hi and md.closes[-1] > hi:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"broke above the opening range high {hi:.2f}")
        if acc.in_position and md.closes[-1] < lo:
            return self.sell(f"broke below the opening range low {lo:.2f}")
        return self.hold(f"inside opening range {lo:.2f}-{hi:.2f}")


# ---- 35. Chandelier Exit ----------------------------------------------------- #


class ChandelierTrendRide(Strategy):
    id = "35_chandelier_trend_ride"
    name = "Chandelier Exit Trend Ride"
    category = "Risk & Trailing"
    warmup = 60
    params = {"trend_period": 50, "atr_period": 22, "multiplier": 3.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        trend_s = md.cached(f"ema{self.p['trend_period']}",
                            lambda: ema(md.closes, int(self.p["trend_period"])))
        key = f"chand{self.p['atr_period']}-{self.p['multiplier']}"
        long_x, _ = md.cached(key, lambda: chandelier_exit(
            md.highs, md.lows, md.closes, int(self.p["atr_period"]), float(self.p["multiplier"])
        ))
        if trend_s[-1] is None or trend_s[-2] is None or long_x[-1] is None:
            return self.hold("chandelier warming up")
        trend = trend_s[-1]
        acc.strategy_state["chandelier_stop"] = long_x[-1]

        if md.closes[-2] <= trend_s[-2] and md.price > trend:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"close crossed above EMA{self.p['trend_period']} ({trend:.2f})")
        if acc.in_position and md.price < long_x[-1]:
            return self.sell(f"chandelier trailing stop breached at {long_x[-1]:.2f}")
        return self.hold(f"stop {long_x[-1]:.2f}, close {md.price:.2f}")


# ---- 36. Martingale Dip Accumulator ------------------------------------------- #


class MartingaleDipAccumulator(Strategy):
    """Buys each successive dip with a doubled order, capped by a multiplier
    limit and by available cash. Accumulates; never sells by default."""

    id = "36_martingale_dip"
    name = "Martingale Dip Accumulator"
    category = "Execution-Based & Portfolio"
    single_position = False
    warmup = 5
    params = {
        "dip_pct": 2.0,            # buy again after each 2% drop
        "base_notional": 100.0,
        "multiplier": 2.0,
        "max_steps": 4,            # cap the doubling so the account cannot blow up
        "take_profit_pct": None,
    }

    def evaluate(self, acc, md, cfg, portfolio=None):
        st = acc.strategy_state
        price = md.price

        tp = self.p.get("take_profit_pct")
        if tp and acc.in_position and acc.entry_price:
            gain = (price - acc.entry_price) / acc.entry_price * 100.0
            if gain >= float(tp):
                st["steps"] = 0
                st["anchor_price"] = price
                return self.sell(f"martingale stack take-profit at +{gain:.2f}%")

        # Before the first fill the reference tracks the running peak, so the
        # strategy measures a dip from recent price action rather than waiting
        # for price to fall below the very first candle it ever saw.
        anchor = st.get("anchor_price")
        if anchor is None:
            st["anchor_price"] = price
            st["steps"] = 0
            return self.hold(f"martingale anchored at {price:.2f}")
        if int(st.get("steps", 0)) == 0 and price > anchor:
            st["anchor_price"] = price
            anchor = price

        drop_pct = (price - anchor) / anchor * 100.0
        steps = int(st.get("steps", 0))
        if drop_pct > -float(self.p["dip_pct"]):
            return self.hold(f"{drop_pct:+.2f}% from anchor {anchor:.2f}")
        if steps >= int(self.p["max_steps"]):
            return self.hold(f"max {self.p['max_steps']} martingale steps reached")

        notional = float(self.p["base_notional"]) * (float(self.p["multiplier"]) ** steps)
        affordable = acc.balance_usd / (1.0 + cfg.fee_rate) if cfg.fee_rate > 0 else acc.balance_usd
        if notional > affordable:
            return self.hold(f"martingale step {steps} needs {notional:.2f}, only {affordable:.2f} available")

        st["steps"] = steps + 1
        st["anchor_price"] = price
        return self.buy(notional=notional,
                        reason=f"martingale step {steps + 1} after a {drop_pct:.2f}% dip")


# ---- 37. Anti-Martingale Pyramid ---------------------------------------------- #


class AntiMartingalePyramid(Strategy):
    """Adds to a winning position on each new leg up and trails the whole stack
    below the peak. The opposite of the martingale: it presses winners."""

    id = "37_anti_martingale_pyramid"
    name = "Anti-Martingale Pyramid"
    category = "Execution-Based & Portfolio"
    single_position = False
    warmup = 25
    params = {
        "entry_lookback": 20,     # initial entry on a new N-candle high
        "add_pct": 2.0,           # add again after each further 2% rise
        "max_adds": 3,
        "trail_pct": 3.0,         # exit the whole stack 3% below the peak
        "size_pct": 0.30,         # fraction of starting balance per leg
    }

    def evaluate(self, acc, md, cfg, portfolio=None):
        st = acc.strategy_state
        price = md.price
        n = int(self.p["entry_lookback"])
        prior_high = max(md.highs[-n - 1 : -1])
        leg_notional = acc.starting_balance * float(self.p["size_pct"])

        if not acc.in_position:
            if md.closes[-2] <= prior_high and price > prior_high:
                st["adds"] = 0
                st["last_add_price"] = price
                st["peak_price"] = price
                affordable = acc.balance_usd / (1.0 + cfg.fee_rate) if cfg.fee_rate > 0 else acc.balance_usd
                notional = min(leg_notional, affordable)
                if notional <= 0:
                    return self.hold("no cash for the pyramid entry")
                return self.buy(notional=notional,
                                reason=f"pyramid entry on a new {n}-candle high {prior_high:.2f}")
            return self.hold(f"no {n}-candle high breakout")

        st["peak_price"] = max(float(st.get("peak_price", price)), price)
        peak = float(st["peak_price"])
        adds = int(st.get("adds", 0))

        if price <= peak * (1.0 - float(self.p["trail_pct"]) / 100.0):
            st["adds"] = 0
            st.pop("peak_price", None)
            st.pop("last_add_price", None)
            drawdown = (price - peak) / peak * 100.0
            return self.sell(reason=f"pyramid trail hit {drawdown:.2f}% below peak {peak:.2f}")

        last_add = float(st.get("last_add_price", price))
        if adds < int(self.p["max_adds"]) and price >= last_add * (1.0 + float(self.p["add_pct"]) / 100.0):
            affordable = acc.balance_usd / (1.0 + cfg.fee_rate) if cfg.fee_rate > 0 else acc.balance_usd
            notional = min(leg_notional, affordable)
            if notional > cfg.min_notional:
                st["adds"] = adds + 1
                st["last_add_price"] = price
                return self.buy(notional=notional, reason=f"pyramid add #{adds + 1} at +{self.p['add_pct']}%")
        return self.hold(f"pyramid: {adds} adds, peak {peak:.2f}")


# ---- 38. Kelly Fraction Sizer -------------------------------------------------- #


class KellyFractionSizer(Strategy):
    """Enters on a Donchian breakout but sizes the position with the Kelly
    criterion estimated from this account's own closed-trade history."""

    id = "38_kelly_fraction_sizer"
    name = "Kelly Fraction Position Sizing"
    category = "Execution-Based & Portfolio"
    warmup = 25
    params = {
        "entry_period": 20,
        "exit_period": 10,
        "min_trades": 10,       # history needed before Kelly is trusted
        "default_fraction": 0.10,
        "max_fraction": 0.50,   # fractional Kelly cap
        "kelly_fraction": 0.5,  # half-Kelly: less variance for the same edge
    }

    def _kelly(self, acc: Account) -> Tuple[float, str]:
        closed = [t for t in acc.trades if t["side"] == "sell"]
        wins = [t["pnl"] for t in closed if t["pnl"] > 0]
        losses = [-t["pnl"] for t in closed if t["pnl"] <= 0]
        if len(closed) < int(self.p["min_trades"]) or not wins or not losses:
            return float(self.p["default_fraction"]), f"history {len(closed)}<{self.p['min_trades']}, default"
        p = len(wins) / len(closed)
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)
        if avg_loss <= EPS:
            return float(self.p["default_fraction"]), "no losses recorded, default"
        b = avg_win / avg_loss
        full = p - (1.0 - p) / b
        if full <= 0:
            return 0.0, f"negative edge (p={p:.2f}, b={b:.2f}) -> stand aside"
        frac = min(full * float(self.p["kelly_fraction"]), float(self.p["max_fraction"]))
        return frac, f"p={p:.2f} b={b:.2f} full-Kelly={full:.2f}"

    def evaluate(self, acc, md, cfg, portfolio=None):
        upper, _, lower = donchian(md.highs, md.lows, int(self.p["entry_period"]), int(self.p["exit_period"]))
        if upper[-1] is None or lower[-1] is None:
            return self.hold("Donchian warming up")

        if md.price > upper[-1]:
            frac, why = self._kelly(acc)
            acc.strategy_state["kelly"] = {"fraction": frac, "detail": why}
            if frac <= 0:
                return self.hold(f"Kelly says no bet: {why}")
            notional = acc.balance_usd * frac
            return self.buy(notional=notional, reason=f"breakout, Kelly fraction {frac:.1%} ({why})")
        if acc.in_position and md.price < lower[-1]:
            return self.sell(f"close broke the {self.p['exit_period']}-candle low")
        return self.hold(f"inside channel, Kelly={acc.strategy_state.get('kelly', {}).get('fraction')}")


# ---- 39. Multi-Indicator Consensus --------------------------------------------- #


class MultiIndicatorConsensus(Strategy):
    """Hybrid: casts one vote per indicator and trades only on a majority.

    A blended signal trades far less often than any single component, which is
    the point -- it filters the whipsaw each individual oscillator produces.
    """

    id = "39_multi_indicator_consensus"
    name = "Multi-Indicator Consensus Vote"
    category = "Composite & Hybrid"
    warmup = 45
    params = {"threshold": 3, "alloc": None}

    def _votes(self, md):
        votes = {}
        r = md.cached("rsi14", lambda: rsi(md.closes, 14))[-1]
        if r is not None:
            votes["rsi"] = 1 if r < 40 else (-1 if r > 60 else 0)

        f = md.cached("ema9", lambda: ema(md.closes, 9))
        s = md.cached("ema21", lambda: ema(md.closes, 21))
        if f[-1] is not None and s[-1] is not None:
            votes["ema_cross"] = 1 if f[-1] > s[-1] else -1

        _, _, hist = md.cached("macd", lambda: macd(md.closes, 12, 26, 9))
        if hist[-1] is not None:
            votes["macd"] = 1 if hist[-1] > 0 else -1

        _, mid, _ = md.cached("bb", lambda: bollinger(md.closes, 20, 2.0))
        if mid[-1] is not None:
            votes["bollinger"] = 1 if md.price < mid[-1] else -1

        k, d = md.cached("stochrsi", lambda: stoch_rsi(md.closes, 14, 14, 3, 3))
        if k[-1] is not None and d[-1] is not None:
            votes["stoch_rsi"] = 1 if k[-1] > d[-1] else -1
        return votes

    def evaluate(self, acc, md, cfg, portfolio=None):
        votes = self._votes(md)
        if len(votes) < 5:
            return self.hold(f"only {len(votes)}/5 indicators ready")
        score = sum(votes.values())
        acc.strategy_state["consensus"] = {"votes": votes, "score": score}
        threshold = int(self.p["threshold"])

        if score >= threshold:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"{score}/5 indicators bullish {sorted(k for k, v in votes.items() if v > 0)}")
        if acc.in_position and score <= -threshold:
            return self.sell(f"{score}/5 indicators bearish {sorted(k for k, v in votes.items() if v < 0)}")
        return self.hold(f"consensus {score:+d}/5 (threshold +/-{threshold})")


# ---- 40. Trend + Pullback Confluence -------------------------------------------- #


class TrendPullbackConfluence(Strategy):
    """Hybrid: a long-term trend filter gates a short-term mean-reversion entry.

    Buys dips only while the higher timeframe agrees, which is the classic fix
    for a naked RSI strategy that keeps catching falling knives.
    """

    id = "40_trend_pullback_confluence"
    name = "Trend + Pullback Confluence"
    category = "Composite & Hybrid"
    warmup = 200
    params = {"trend_period": 200, "mid_period": 50, "rsi_period": 14,
              "rsi_buy": 35.0, "rsi_sell": 65.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        slow = md.cached(f"sma{self.p['trend_period']}",
                         lambda: sma(md.closes, int(self.p["trend_period"])))[-1]
        mid = md.cached(f"sma{self.p['mid_period']}",
                        lambda: sma(md.closes, int(self.p["mid_period"])))[-1]
        r = md.cached(f"rsi{self.p['rsi_period']}",
                      lambda: rsi(md.closes, int(self.p["rsi_period"])))[-1]
        if None in (slow, mid, r):
            return self.hold("confluence warming up")

        uptrend = md.price > slow and mid > slow
        if uptrend and r < self.p["rsi_buy"]:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"pullback RSI {r:.1f} < {self.p['rsi_buy']:.0f} inside an uptrend above SMA{self.p['trend_period']}")
        if acc.in_position and (r > self.p["rsi_sell"] or md.price < mid):
            why = f"RSI recovered to {r:.1f}" if r > self.p["rsi_sell"] else f"lost SMA{self.p['mid_period']}"
            return self.sell(why)
        return self.hold(f"trend={'up' if uptrend else 'down'}, RSI {r:.1f}")


# ---- 41. Volatility Regime Switcher ---------------------------------------------- #


class VolatilityRegimeSwitcher(Strategy):
    """Hybrid: the ATR percentile picks which sub-strategy runs.

    High volatility favours mean reversion (Bollinger); low volatility favours
    breakout (Donchian). One account, two behaviours, chosen by regime.
    """

    id = "41_volatility_regime_switcher"
    name = "Volatility Regime Switcher"
    category = "Composite & Hybrid"
    warmup = 120
    params = {"atr_period": 14, "percentile_lookback": 100, "high_vol": 70.0,
              "low_vol": 30.0, "bb_period": 20, "bb_mult": 2.0,
              "entry_period": 20, "exit_period": 10, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        a = md.cached(f"atr{self.p['atr_period']}",
                      lambda: atr(md.highs, md.lows, md.closes, int(self.p["atr_period"])))
        pr = atr_percentile(a, int(self.p["percentile_lookback"]))[-1]
        if pr is None:
            return self.hold("ATR percentile warming up")
        acc.strategy_state["atr_percentile"] = pr

        if pr >= self.p["high_vol"]:
            regime = "mean-reversion"
            _, mid, lower = bollinger(md.closes, int(self.p["bb_period"]), float(self.p["bb_mult"]))
            if lower[-1] is not None and md.price < lower[-1]:
                return self.buy(self.size_notional(acc, cfg),
                                reason=f"[{regime}] ATR pct {pr:.0f} -> close below lower band {lower[-1]:.2f}")
            if acc.in_position and mid[-1] is not None and md.price >= mid[-1]:
                return self.sell(f"[{regime}] reverted to the middle band")
            return self.hold(f"[{regime}] ATR pct {pr:.0f}")

        if pr <= self.p["low_vol"]:
            regime = "breakout"
            upper, _, lower = donchian(md.highs, md.lows, int(self.p["entry_period"]), int(self.p["exit_period"]))
            if upper[-1] is not None and md.price > upper[-1]:
                return self.buy(self.size_notional(acc, cfg),
                                reason=f"[{regime}] ATR pct {pr:.0f} -> broke the {self.p['entry_period']}-candle high")
            if acc.in_position and lower[-1] is not None and md.price < lower[-1]:
                return self.sell(f"[{regime}] broke the {self.p['exit_period']}-candle low")
            return self.hold(f"[{regime}] ATR pct {pr:.0f}")

        return self.hold(f"neutral regime (ATR pct {pr:.0f})")


# ---- 42. Sibling Performance Allocator -------------------------------------------- #


class SiblingPerformanceAllocator(Strategy):
    """Meta-strategy: allocates based on how the *other* accounts are doing.

    When the ensemble of sibling strategies is collectively beating cash the
    market is tradeable, so this account participates; when the median sibling
    is underwater it stands aside.

    NOTE: this is the one deliberate exception to account isolation. It reads
    (never writes) a snapshot of the other accounts' equity.
    """

    id = "42_sibling_performance_allocator"
    name = "Sibling Performance Allocator"
    category = "Composite & Hybrid"
    warmup = 25
    params = {"momentum_lookback": 20, "median_floor_pct": 0.0, "alloc": None}

    def evaluate(self, acc, md, cfg, portfolio=None):
        if not portfolio:
            return self.hold("no portfolio snapshot available")
        peers = {sid: v for sid, v in portfolio.items() if sid != acc.id}
        if not peers:
            return self.hold("no sibling accounts to read")

        returns = sorted(v["return_pct"] for v in peers.values())
        n = len(returns)
        median = returns[n // 2] if n % 2 else (returns[n // 2 - 1] + returns[n // 2]) / 2.0
        best = max(peers.items(), key=lambda kv: kv[1]["return_pct"])
        acc.strategy_state["ensemble"] = {
            "median_return_pct": median,
            "peer_count": n,
            "leader": best[0],
            "leader_return_pct": best[1]["return_pct"],
        }

        # Ride the leader's signal only while the ensemble is healthy.
        healthy = median >= float(self.p["median_floor_pct"])
        if healthy and not acc.in_position:
            return self.buy(self.size_notional(acc, cfg),
                            reason=f"ensemble median {median:+.2f}% (leader {best[0]}) -> participate")
        if acc.in_position and not healthy:
            return self.sell(f"ensemble median {median:+.2f}% fell below {self.p['median_floor_pct']:.1f}% -> stand aside")
        return self.hold(f"ensemble median {median:+.2f}%, leader {best[0]}")


STRATEGY_CLASSES: List[type] = [
    # Momentum & Trend Following
    RsiMeanReversion,
    DualEmaCrossover,
    MacdHistogramReversal,
    TripleMovingAverage,
    SupertrendAtr,
    AdxDmiTrend,
    IchimokuCloud,
    ParabolicSarFlip,
    RocMomentum,
    AroonTrend,
    HeikinAshiTrend,
    TrixMomentum,
    EmaRibbonConsensus,
    # Mean Reversion & Oscillators
    BollingerMeanReversion,
    KeltnerBreakout,
    StochRsiReversal,
    WilliamsRReversal,
    CciMeanReversion,
    ConnorsRsiPullback,
    ZScoreMeanReversion,
    MfiFlowReversal,
    ChandeMomentum,
    # Volume & Volatility
    VwapPullback,
    DonchianBreakout,
    ObvTrendBreakout,
    VolumeSpikeBreakout,
    VolatilitySqueezeBreakout,
    ElderRayPower,
    # Price Action
    EngulfingReversal,
    FibonacciPullback,
    PivotPointBounce,
    OpeningRangeBreakout,
    # Risk & Trailing
    ChandelierTrendRide,
    # Execution-Based & Portfolio
    DynamicDca,
    ArithmeticGrid,
    MartingaleDipAccumulator,
    AntiMartingalePyramid,
    KellyFractionSizer,
    # Composite & Hybrid
    MultiIndicatorConsensus,
    TrendPullbackConfluence,
    VolatilityRegimeSwitcher,
    SiblingPerformanceAllocator,
]


# --------------------------------------------------------------------------- #
# State store
# --------------------------------------------------------------------------- #


class StateStore:
    """Atomic JSON persistence for ``docs/data.json``."""

    def __init__(self, path: str, log: logging.Logger):
        self.path = path
        self.log = log

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("state root is not an object")
            return data
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            backup = self.path + ".corrupt"
            try:
                os.replace(self.path, backup)
                self.log.error("State file unreadable (%s); moved to %s and starting fresh.", exc, backup)
            except OSError:
                self.log.error("State file unreadable (%s); starting fresh.", exc)
            return {}

    def save(self, data: Dict[str, Any]) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)

        if os.path.exists(self.path):
            try:
                with open(self.path, "rb") as src, open(self.path + ".bak", "wb") as dst:
                    dst.write(src.read())
            except OSError as exc:
                self.log.warning("Could not write backup: %s", exc)

        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)


def _fresh_account(strategy: Strategy, cfg: Config) -> Account:
    return Account(strategy.id, strategy.name, cfg.starting_balance)


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


def build_exchange() -> Any:
    """Construct the market-data client.

    Kraken rather than Binance: ``api.binance.com`` returns HTTP 451 to United
    States IP addresses, and GitHub-hosted runners are US-based, so a scheduled
    tick there would die at the data-fetch step. Kraken serves ``*/USDT`` spot
    from ``api.kraken.com`` with no such restriction and supports the 15m
    timeframe this bot runs on.

    The engine only ever calls ``fetch_ohlcv`` on this object, so it is trivial
    to swap: pass your own client to ``Engine.fetch_live(exchange=...)``.
    """
    if ccxt is None:
        raise RuntimeError("ccxt is not installed. Run: pip install ccxt")
    # Kraken is spot-only in ccxt, so no defaultType option is required.
    return ccxt.kraken({"enableRateLimit": True, "timeout": 30000})


class Engine:
    def __init__(self, cfg: Config, log: logging.Logger):
        self.cfg = cfg
        self.log = log
        self.store = StateStore(cfg.state_path, log)
        self.broker = Broker(cfg, log)
        self.strategies: List[Strategy] = []
        for cls in STRATEGY_CLASSES:
            if cls.id in cfg.disabled:
                log.info("Strategy %s disabled", cls.id)
                continue
            self.strategies.append(cls(cfg.overrides.get(cls.id)))
        self.accounts: Dict[str, Account] = {}
        self.state: Dict[str, Any] = {}

    # -- state management --------------------------------------------------- #

    def load_state(self, reset: bool = False) -> None:
        raw = {} if reset else self.store.load()
        meta = raw.get("meta", {})
        accounts_raw = raw.get("accounts", {})

        self.state = {
            "meta": {
                "version": STATE_VERSION,
                "created_at": meta.get("created_at") or utcnow_iso(),
                "updated_at": utcnow_iso(),
                "symbol": self.cfg.symbol,
                "timeframe": self.cfg.timeframe,
                "starting_balance": self.cfg.starting_balance,
                "fee_rate": self.cfg.fee_rate,
                "run_count": int(meta.get("run_count", 0)),
                "candles_processed": int(meta.get("candles_processed", 0)),
                "last_candle_ts": meta.get("last_candle_ts"),
                "prev_candle_ts": meta.get("last_candle_ts"),
                "bot_version": __version__,
            },
            "accounts": {},
        }

        for strategy in self.strategies:
            saved = accounts_raw.get(strategy.id)
            if saved:
                self.accounts[strategy.id] = Account.from_dict(saved, self.cfg.starting_balance)
            else:
                self.accounts[strategy.id] = _fresh_account(strategy, self.cfg)
                self.log.info("Initialised new account %s with %.2f USDT", strategy.id, self.cfg.starting_balance)

    def snapshot_state(self) -> Dict[str, Any]:
        """Fill ``state["accounts"]`` from the live account objects without
        writing anything, so callers (replay history tracking) can read a
        consistent snapshot of the current portfolio."""
        self.state["meta"]["updated_at"] = utcnow_iso()
        self.state["accounts"] = {
            strategy.id: self.accounts[strategy.id].to_dict() for strategy in self.strategies
        }
        return self.state

    def persist(self) -> None:
        self.store.save(self.snapshot_state())

    # -- market data -------------------------------------------------------- #

    def required_candles(self) -> int:
        warmups = [s.warmup for s in self.strategies] or [50]
        # +1 because the in-progress candle is dropped before evaluation.
        return max(warmups) + 5

    def fetch_live(self, exchange=None) -> MarketData:
        ex = exchange or build_exchange()

        limit = max(self.cfg.candle_limit, self.required_candles())
        if limit > self.cfg.candle_limit:
            self.log.warning(
                "Raising candle limit %d -> %d to satisfy the largest strategy warm-up (SMA200).",
                self.cfg.candle_limit, limit,
            )

        last_err: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                rows = ex.fetch_ohlcv(self.cfg.symbol, timeframe=self.cfg.timeframe, limit=limit)
                break
            except Exception as exc:  # noqa: BLE001 - network layer is broad by nature
                last_err = exc
                wait = 2.0 * attempt
                self.log.warning("OHLCV fetch failed (attempt %d/3): %s — retrying in %.1fs", attempt, exc, wait)
                time.sleep(wait)
        else:
            raise RuntimeError(f"Could not fetch OHLCV after 3 attempts: {last_err}")

        candles = [Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in rows]
        if len(candles) < 2:
            raise RuntimeError(f"Exchange returned only {len(candles)} candles")
        return MarketData(self.cfg.symbol, self.cfg.timeframe, candles)

    # -- execution ---------------------------------------------------------- #

    def _apply_risk_overlay(self, acc: Account, md: MarketData, decision: Decision) -> Decision:
        """Optional global stop-loss / take-profit, applied before signals."""
        if not acc.in_position or not acc.entry_price:
            return decision
        change_pct = (md.price - acc.entry_price) / acc.entry_price * 100.0
        if self.cfg.stop_loss_pct is not None and change_pct <= -abs(self.cfg.stop_loss_pct):
            return Decision("sell", reason=f"stop-loss hit ({change_pct:+.2f}%)")
        if self.cfg.take_profit_pct is not None and change_pct >= abs(self.cfg.take_profit_pct):
            return Decision("sell", reason=f"take-profit hit ({change_pct:+.2f}%)")
        return decision

    def _execute_pending_orders(self, acc: Account, md: MarketData) -> int:
        """Execute the queued orders of a multi-position strategy.

        Limit orders fill at their own limit price, not at the candle close.
        A rejected order rolls its grid level back so the ladder stays
        consistent with the lot book.
        """
        pending = acc.pending_orders
        acc.pending_orders = []
        executed = 0

        for decision in pending:
            ref = decision.limit_price if decision.limit_price else md.price
            trade: Optional[Dict[str, Any]] = None

            if decision.is_sell:
                trade = self.broker.sell(
                    acc, ref, qty=decision.qty, reason=decision.reason,
                    candle_ts=md.last_ts, ts_iso=ms_to_iso(md.last_ts),
                )
            elif decision.is_buy:
                trade = self.broker.buy(
                    acc, ref, notional=decision.notional, reason=decision.reason,
                    candle_ts=md.last_ts, ts_iso=ms_to_iso(md.last_ts),
                )

            if trade is not None:
                executed += 1
                if decision.grid_level is not None:
                    trade["grid_level"] = decision.grid_level
            elif decision.grid_level is not None:
                # Broker refused the fill: undo the ladder flag.
                for lvl in acc.strategy_state.get("grid", {}).get("levels", []):
                    if lvl["index"] == decision.grid_level:
                        lvl["holding"] = decision.is_sell
                        break
        return executed

    def process_market(self, md_raw: MarketData) -> Dict[str, Any]:
        """Run every account against one candle. ``md_raw`` may include the
        in-progress candle; it is dropped here."""
        closed = md_raw.candles[:-1]
        if len(closed) < 2:
            raise RuntimeError("Not enough closed candles to evaluate")
        md = MarketData(md_raw.symbol, md_raw.timeframe, closed)

        meta = self.state["meta"]
        meta["run_count"] += 1
        meta["candles_processed"] += 1
        meta["last_candle_ts"] = md.last_ts
        meta["last_price"] = md.price

        self.log.info("=" * 78)
        self.log.info("Run #%d | %s %s | signal candle %s | close %.4f | closed candles %d",
                      meta["run_count"], md.symbol, md.timeframe, ms_to_iso(md.last_ts), md.price, len(md))
        self.log.info("=" * 78)

        duplicate = self.cfg.skip_duplicate_candle and meta.get("prev_candle_ts") == md.last_ts
        if duplicate:
            self.log.warning("Candle %s already processed — use --force to override.", ms_to_iso(md.last_ts))

        total_executed = 0
        summary: Dict[str, Any] = {}

        # Read-only cross-account snapshot, rebuilt each candle. Only the
        # portfolio meta-strategy consults it; every other account stays
        # strictly isolated.
        portfolio: Dict[str, Any] = {}
        for sid, acc in self.accounts.items():
            eq = acc.equity(md.price)
            portfolio[sid] = {
                "equity": eq,
                "return_pct": (eq / acc.starting_balance - 1.0) * 100.0 if acc.starting_balance else 0.0,
                "trades": len(acc.trades),
                "in_position": acc.in_position,
            }

        for strategy in self.strategies:
            acc = self.accounts[strategy.id]
            acc.rejections = []
            if acc.errors:
                self.log.error("[%s] %d evaluation error(s): %s",
                               strategy.id, len(acc.errors), "; ".join(acc.errors[:3]))
            acc.rejection_repeats = {}

            if duplicate:
                acc.mark_to_market(md.price)
                summary[strategy.id] = {"skipped": True}
                continue

            if acc.last_candle_ts == md.last_ts and self.cfg.skip_duplicate_candle:
                self.log.info("[%s] candle already processed for this account — skipping", strategy.id)
                acc.mark_to_market(md.price)
                summary[strategy.id] = {"skipped": True}
                continue

            self.log.info("[%s] %s", strategy.id, strategy.name)
            decision = strategy.decide(acc, md, self.cfg, portfolio)
            decision = self._apply_risk_overlay(acc, md, decision)

            if total_executed >= self.cfg.max_trades_per_run:
                self.log.error(
                    "[%s] circuit breaker: %d fills this run reached --max-trades-per-run; "
                    "skipping the remaining accounts.",
                    strategy.id, total_executed,
                )
                acc.mark_to_market(md.price)
                summary[strategy.id] = {"skipped": True, "circuit_breaker": True}
                continue

            ref_price = decision.limit_price if decision.limit_price else md.price
            executed = 0
            if decision.is_buy:
                trade = self.broker.buy(
                    acc, ref_price, notional=decision.notional, qty=decision.qty,
                    reason=decision.reason, candle_ts=md.last_ts, ts_iso=ms_to_iso(md.last_ts),
                )
                executed = 1 if trade else 0
            elif decision.is_sell:
                trade = self.broker.sell(
                    acc, ref_price, qty=decision.qty, reason=decision.reason,
                    candle_ts=md.last_ts, ts_iso=ms_to_iso(md.last_ts),
                )
                executed = 1 if trade else 0
            else:
                if decision.reason:
                    self.log.info("    HOLD %s (%s)", strategy.id, decision.reason)

            executed += self._execute_pending_orders(acc, md)
            total_executed += executed

            acc.last_candle_ts = md.last_ts
            acc.mark_to_market(md.price)
            equity = acc.equity(md.price)
            summary[strategy.id] = {
                "name": strategy.name,
                "equity": equity,
                "return_pct": (equity / acc.starting_balance - 1.0) * 100.0,
                "balance": acc.balance_usd,
                "holdings": acc.crypto_holdings,
                "entry_price": acc.entry_price,
                "unrealized_pnl": acc.unrealized_pnl,
                "realized_pnl": acc.realized_pnl,
                "trades": len(acc.trades),
                "action": decision.action,
                "reason": decision.reason,
                "errors": list(acc.errors),
                "rejections": [
                    f"{r} (x{acc.rejection_repeats[r]})" if acc.rejection_repeats.get(r, 1) > 1 else r
                    for r in acc.rejections
                ],
            }

        meta["prev_candle_ts"] = md.last_ts
        meta["total_trades"] = sum(len(a.trades) for a in self.accounts.values())
        return summary


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def format_summary(summary: Dict[str, Any], price: float, symbol: str) -> str:
    rows = [s for s in summary.values() if not s.get("skipped")]
    if not rows:
        return "No strategies processed this run (duplicate candle)."

    header = f"{'STRATEGY':<34} {'EQUITY':>11} {'RET %':>8} {'POS':>5} {'TRD':>5} {'ACTION':>6}"
    sep = "-" * len(header)
    lines = [
        "",
        f"PORTFOLIO SNAPSHOT — {symbol} @ {price:.4f}",
        sep,
        header,
        sep,
    ]
    total_equity = 0.0
    for sid, row in summary.items():
        if row.get("skipped"):
            lines.append(f"{sid:<34} {'(duplicate candle skipped)':>45}")
            continue
        total_equity += row["equity"]
        pos = "LONG" if (row["holdings"] or 0) > MIN_QTY_STEP else "flat"
        lines.append(
            f"{sid:<34} {row['equity']:>11.2f} {row['return_pct']:>+8.2f} {pos:>5} {row['trades']:>5} {row['action']:>6}"
        )
    lines.append(sep)
    lines.append(f"{'TOTAL EQUITY':<34} {total_equity:>11.2f}   ({len(rows)} strategies)")
    lines.append("")
    return "\n".join(lines)


def format_markdown(summary: Dict[str, Any], price: float, symbol: str, run_count: int) -> str:
    rows = [(sid, s) for sid, s in summary.items() if not s.get("skipped")]
    total = sum(s["equity"] for _, s in rows)
    out = [
        f"### CryptoTrade paper-trading run #{run_count}",
        "",
        f"**{symbol}** @ `{price:.4f}` — total virtual equity **${total:,.2f}**",
        "",
        "| Strategy | Equity | Return | Position | Trades | Last action |",
        "| --- | ---: | ---: | :---: | ---: | :--- |",
    ]
    for sid, s in rows:
        pos = "LONG" if (s["holdings"] or 0) > MIN_QTY_STEP else "flat"
        reason = (s.get("reason") or "").replace("|", "\\|")[:60]
        out.append(
            f"| `{sid}` | ${s['equity']:,.2f} | {s['return_pct']:+.2f}% | {pos} | {s['trades']} | {s['action']} — {reason} |"
        )
    out.append(f"| **Total** | **${total:,.2f}** | | | | |")
    return "\n".join(out)


def write_github_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")
    except OSError:
        pass


def history_path(state_path: str) -> str:
    """Where the per-run history snapshot lives, next to the state file."""
    directory = os.path.dirname(os.path.abspath(state_path))
    return os.path.join(directory, HISTORY_FILENAME)


def append_history(state: Dict[str, Any], state_path: str,
                   max_entries: int = HISTORY_MAX_ENTRIES) -> None:
    """Append (or refresh) a compact per-run snapshot for the dashboard.

    Each row stores the run counter, candle timestamp, reference price, total
    virtual equity/return and one return percentage per account. Per-account
    returns are sufficient to rebuild every equity curve because all accounts
    share the same starting balance. This never raises: a dashboard file should
    not be able to fail a trading tick.
    """
    log = logging.getLogger("bot")
    meta = state.get("meta", {})
    accounts = state.get("accounts", {})
    price = float(meta.get("last_price") or 0.0)
    candle_ts = meta.get("last_candle_ts")

    starting = float(meta.get("starting_balance") or 0.0)
    rets: Dict[str, float] = {}
    equity = 0.0
    for sid, acc in accounts.items():
        bal = float(acc.get("balance_usd", 0.0))
        hold = float(acc.get("crypto_holdings", 0.0))
        eq = bal + hold * price
        equity += eq
        base = float(acc.get("starting_balance", starting)) or starting
        rets[sid] = round((eq / base - 1.0) * 100.0, 4) if base else 0.0
    total_base = len(accounts) * starting if starting else 0.0
    total_return = round((equity / total_base - 1.0) * 100.0, 4) if total_base else 0.0

    entry = {
        "run": int(meta.get("run_count", 0)),
        "ts": meta.get("updated_at") or utcnow_iso(),
        "candle_ts": candle_ts,
        "price": round(price, 4),
        "equity": round(equity, 2),
        "return_pct": total_return,
        "trades": int(meta.get("total_trades", 0)),
        "rets": rets,
    }

    path = history_path(state_path)
    try:
        rows: List[Dict[str, Any]] = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, list):
                    rows = loaded
            except (json.JSONDecodeError, ValueError, OSError):
                rows = []
        # A re-run of the same candle refreshes the last row instead of adding a
        # duplicate point, so the chart stays one point per candle.
        if rows and rows[-1].get("candle_ts") == candle_ts:
            rows[-1] = entry
        else:
            rows.append(entry)
        if len(rows) > max_entries:
            rows = rows[-max_entries:]
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, separators=(",", ":"))
            fh.write("\n")
    except OSError as exc:
        log.warning("Could not write history snapshot %s: %s", path, exc)


# --------------------------------------------------------------------------- #
# Data sources
# --------------------------------------------------------------------------- #


def load_replay_csv(path: str) -> List[Candle]:
    """Load ``ts_ms,open,high,low,close,volume`` rows (header optional)."""
    candles: List[Candle] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.replace(";", ",").split(",")]
            if lineno == 1 and not parts[0].replace(".", "").isdigit():
                continue  # header row
            if len(parts) < 6:
                raise ValueError(f"{path}:{lineno}: expected 6 columns, got {len(parts)}")
            candles.append(
                Candle(int(float(parts[0])), float(parts[1]), float(parts[2]),
                       float(parts[3]), float(parts[4]), float(parts[5]))
            )
    if len(candles) < 3:
        raise ValueError(f"{path}: need at least 3 candles, found {len(candles)}")
    return candles


def run_replay(engine: Engine, candles: List[Candle], limit: int,
               record_history: bool = False) -> Dict[str, Any]:
    """Drive the real engine one candle at a time from a static series.

    The window handed to the engine always ends with an "in-progress" bar, so
    replay exercises exactly the same code path (including the drop of the
    live candle) as a scheduled live run.

    With ``record_history`` set, one history snapshot is appended per candle so
    the HTML dashboard can draw the equity curve of the whole backtest.
    """
    summary: Dict[str, Any] = {}
    n = len(candles)
    # i indexes the last *closed* candle; i+1 is the in-progress bar the engine
    # will discard. Stopping at n-1 guarantees every iteration advances.
    for i in range(1, n - 1):
        start = max(0, i + 2 - limit)
        window = candles[start : i + 2]      # last element is the "in-progress" bar
        if len(window) < 3:
            continue
        md = MarketData(engine.cfg.symbol, engine.cfg.timeframe, window)
        summary = engine.process_market(md)
        if record_history:
            append_history(engine.snapshot_state(), engine.cfg.state_path)
    return summary


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bot.py",
        description="Multi-strategy crypto paper-trading engine (12 isolated virtual accounts).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--symbol", help="Market to trade (e.g. BTC/USDT, ETH/USDT)")
    p.add_argument("--timeframe", help="Candle timeframe (e.g. 15m, 1h)")
    p.add_argument("--limit", type=int, help="Candles requested from the exchange")
    p.add_argument("--state", help="Path to the JSON state file")
    p.add_argument("--fee-rate", type=float, help="Per-side fee as a fraction (0.001 = 0.1%%)")
    p.add_argument("--slippage", type=float, help="Adverse slippage fraction per fill")
    p.add_argument("--alloc", type=float, help="Fraction of cash used by single-position buys")
    p.add_argument("--min-notional", type=float, help="Minimum order notional in quote currency")
    p.add_argument("--max-trades-per-run", type=int,
                   help="Circuit breaker: stop filling once this many orders execute in one tick")
    p.add_argument("--stop-loss-pct", type=float, help="Global stop-loss %% (enables the risk overlay)")
    p.add_argument("--take-profit-pct", type=float, help="Global take-profit %% (enables the risk overlay)")
    p.add_argument("--disable", action="append", default=[], help="Strategy id to disable (repeatable)")
    p.add_argument("--param", action="append", default=[], metavar="STRAT.key=value",
                   help="Override a strategy parameter, e.g. --param 01_rsi_mean_reversion.rsi_buy=25")
    p.add_argument("--reset", action="store_true", help="Discard existing state and start every account fresh")
    p.add_argument("--init", action="store_true",
                   help="Create the state file with 12 fresh accounts and exit (no market data needed)")
    p.add_argument("--yes", action="store_true", help="Skip the --reset confirmation prompt")
    p.add_argument("--force", action="store_true", help="Process the candle even if it was already handled")
    p.add_argument("--replay", metavar="CSV", help="Offline mode: replay ts,o,h,l,c,v CSV instead of hitting the exchange")
    p.add_argument("--dry-run", action="store_true", help="Evaluate and report without writing the state file")
    p.add_argument("--log-level", default=os.environ.get("BOT_LOG_LEVEL", "INFO"),
                   dest="log_level", help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def parse_param_overrides(items: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if "." not in item or "=" not in item:
            raise ValueError(f"--param expects STRATEGY.key=value, got {item!r}")
        strat, rest = item.split(".", 1)
        key, raw = rest.split("=", 1)
        value: Any
        lowered = raw.strip().lower()
        if lowered in ("none", "null"):
            value = None
        elif lowered in ("true", "false"):
            value = lowered == "true"
        else:
            try:
                value = int(raw)
            except ValueError:
                try:
                    value = float(raw)
                except ValueError:
                    value = raw
        out.setdefault(strat.strip(), {})[key.strip()] = value
    return out


def setup_logging(level: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    return logging.getLogger("bot")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.log_level_explicit = "--log-level" in list(argv or []) or bool(os.environ.get("BOT_LOG_LEVEL"))
    log = setup_logging(args.log_level)

    cfg = Config.from_env()
    if args.symbol:
        cfg.symbol = args.symbol
    if args.timeframe:
        cfg.timeframe = args.timeframe
    if args.limit:
        cfg.candle_limit = args.limit
    if args.state:
        cfg.state_path = args.state
    if args.fee_rate is not None:
        cfg.fee_rate = args.fee_rate
    if args.slippage is not None:
        cfg.slippage = args.slippage
    if args.alloc is not None:
        cfg.position_alloc = args.alloc
    if args.min_notional is not None:
        cfg.min_notional = args.min_notional
    if args.max_trades_per_run is not None:
        cfg.max_trades_per_run = args.max_trades_per_run
    if args.stop_loss_pct is not None:
        cfg.stop_loss_pct = args.stop_loss_pct
    if args.take_profit_pct is not None:
        cfg.take_profit_pct = args.take_profit_pct
    if args.force:
        cfg.skip_duplicate_candle = False
    cfg.disabled = list(dict.fromkeys(list(cfg.disabled) + list(args.disable)))

    try:
        cfg.overrides = parse_param_overrides(args.param)
    except ValueError as exc:
        log.error("%s", exc)
        return 2

    if args.init:
        engine = Engine(cfg, log)
        engine.load_state(reset=True)
        engine.persist()
        print(f"Initialised {len(engine.strategies)} virtual accounts with "
              f"{cfg.starting_balance:.2f} USDT each in {cfg.state_path}")
        return 0

    if args.reset and not args.yes:
        if sys.stdin.isatty():
            answer = input(f"This will wipe {cfg.state_path}. Type 'yes' to confirm: ").strip().lower()
            if answer != "yes":
                log.info("Aborted.")
                return 1
        else:
            log.warning("--reset used without --yes in a non-interactive shell; proceeding.")

    engine = Engine(cfg, log)
    engine.load_state(reset=args.reset)

    log.info("CryptoTrade v%s | %s %s | fee %.3f%% | state %s | %d strategies",
             __version__, cfg.symbol, cfg.timeframe, cfg.fee_rate * 100, cfg.state_path, len(engine.strategies))

    try:
        if args.replay:
            # Replaying hundreds of candles at INFO is unusable; stay quiet
            # unless the caller explicitly asked for more.
            if not args.log_level_explicit:
                logging.getLogger("bot").setLevel(logging.WARNING)
            candles = load_replay_csv(args.replay)
            limit = max(cfg.candle_limit, engine.required_candles())
            log.info("Replay mode: %d candles from %s (window %d)", len(candles), args.replay, limit)
            summary = run_replay(engine, candles, limit, record_history=not args.dry_run)
            md_price = engine.state["meta"].get("last_price", 0.0)
        else:
            md = engine.fetch_live()
            summary = engine.process_market(md)
            md_price = md.candles[-2].close if len(md.candles) >= 2 else md.price
    except KeyboardInterrupt:
        log.warning("Interrupted.")
        return 130
    except Exception as exc:  # noqa: BLE001 - top-level guard for CI
        log.error("Run failed: %s", exc)
        if log.isEnabledFor(logging.DEBUG):
            raise
        return 1

    report = format_summary(summary, md_price, cfg.symbol)
    print(report)
    write_github_summary(format_markdown(summary, md_price, cfg.symbol, engine.state["meta"]["run_count"]))

    if args.dry_run:
        # Always visible: a dry run must never look like a persisted run.
        print(f"[dry-run] evaluated {engine.state['meta']['run_count']} run(s); state file not written.")
    else:
        engine.persist()
        append_history(engine.state, cfg.state_path)
        log.info("State saved to %s", cfg.state_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
