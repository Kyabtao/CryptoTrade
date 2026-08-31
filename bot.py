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

# Binance spot minimum order notional (USDT). Orders smaller than this are
# rejected by the broker simulation, mirroring real exchange behaviour.
DEFAULT_MIN_NOTIONAL = 10.0


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

    __slots__ = ("symbol", "timeframe", "candles", "_closes", "_highs", "_lows", "_volumes")

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

    def decide(self, acc: Account, md: MarketData, cfg: Config) -> Decision:
        if not md.warmup_ok(self.warmup):
            return self.hold(f"warmup {len(md)}/{self.warmup}")
        try:
            decision = self.evaluate(acc, md, cfg)
        except Exception as exc:  # never let one strategy kill the run
            logging.exception("[%s] evaluation failed: %s", self.id, exc)
            return self.hold(f"error: {exc}")

        if decision.is_buy and self.single_position and acc.in_position:
            return self.hold(f"already in position (entry {acc.entry_price:.4f})")
        if decision.is_sell and not acc.in_position:
            return self.hold("no position to close")
        return decision

    def evaluate(self, acc: Account, md: MarketData, cfg: Config) -> Decision:  # pragma: no cover
        raise NotImplementedError


# ---- 1. RSI Mean Reversion ------------------------------------------------ #


class RsiMeanReversion(Strategy):
    id = "01_rsi_mean_reversion"
    name = "RSI Mean Reversion"
    category = "Momentum & Trend Following"
    warmup = 20
    params = {"rsi_period": 14, "rsi_buy": 30.0, "rsi_sell": 70.0, "alloc": None}

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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

    def evaluate(self, acc, md, cfg):
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


STRATEGY_CLASSES: List[type] = [
    RsiMeanReversion,
    DualEmaCrossover,
    MacdHistogramReversal,
    TripleMovingAverage,
    SupertrendAtr,
    BollingerMeanReversion,
    KeltnerBreakout,
    StochRsiReversal,
    VwapPullback,
    DonchianBreakout,
    DynamicDca,
    ArithmeticGrid,
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

    def persist(self) -> None:
        self.state["meta"]["updated_at"] = utcnow_iso()
        self.state["accounts"] = {
            strategy.id: self.accounts[strategy.id].to_dict() for strategy in self.strategies
        }
        self.store.save(self.state)

    # -- market data -------------------------------------------------------- #

    def required_candles(self) -> int:
        warmups = [s.warmup for s in self.strategies] or [50]
        # +1 because the in-progress candle is dropped before evaluation.
        return max(warmups) + 5

    def fetch_live(self, exchange=None) -> MarketData:
        if ccxt is None:
            raise RuntimeError("ccxt is not installed. Run: pip install ccxt")
        ex = exchange or ccxt.binance({"enableRateLimit": True, "timeout": 30000, "options": {"defaultType": "spot"}})

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

        for strategy in self.strategies:
            acc = self.accounts[strategy.id]
            acc.rejections = []
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
            decision = strategy.decide(acc, md, self.cfg)
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


def run_replay(engine: Engine, candles: List[Candle], limit: int) -> Dict[str, Any]:
    """Drive the real engine one candle at a time from a static series.

    The window handed to the engine always ends with an "in-progress" bar, so
    replay exercises exactly the same code path (including the drop of the
    live candle) as a scheduled live run.
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
            summary = run_replay(engine, candles, limit)
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
        log.info("State saved to %s", cfg.state_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
