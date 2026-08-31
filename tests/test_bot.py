"""Test-suite for bot.py.

Everything here drives the *real* engine: strategies, broker, FIFO lot book,
state persistence and the CLI. Synthetic OHLCV replaces the exchange so the
suite runs offline and deterministically.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))

import bot as botmod  # noqa: E402
from bot import (  # noqa: E402
    STRATEGY_CLASSES,
    Account,
    Broker,
    Candle,
    Config,
    Engine,
    MarketData,
    StateStore,
    atr,
    bollinger,
    donchian,
    ema,
    keltner,
    macd,
    rsi,
    session_vwap,
    sma,
    stoch_rsi,
    supertrend,
    run_replay,
)
import synthetic as syn  # noqa: E402


ALL_IDS = [c.id for c in STRATEGY_CLASSES]


@pytest.fixture
def cfg(tmp_path):
    return Config(state_path=str(tmp_path / "data.json"))


@pytest.fixture
def quiet_log():
    log = logging.getLogger("bot")
    log.setLevel(logging.ERROR)
    log.addHandler(logging.NullHandler())
    return log


def make_engine(strategy_ids, tmp_path, **cfg_kwargs) -> Engine:
    """An Engine running only ``strategy_ids`` (all others disabled)."""
    cfg = Config(state_path=str(tmp_path / "data.json"), **cfg_kwargs)
    cfg.disabled = [sid for sid in ALL_IDS if sid not in strategy_ids]
    log = logging.getLogger("bot")
    log.setLevel(logging.ERROR)
    log.addHandler(logging.NullHandler())
    engine = Engine(cfg, log)
    engine.load_state(reset=True)
    return engine


def replay(engine: Engine, candles, limit: int = 300):
    return run_replay(engine, candles, limit)


def account(engine: Engine, sid: str) -> Account:
    return engine.accounts[sid]


# ========================================================================== #
# Indicators
# ========================================================================== #


class TestIndicators:
    def test_sma_known_values(self):
        assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]

    def test_sma_short_series_is_all_none(self):
        assert sma([1, 2], 5) == [None, None]

    def test_ema_seed_is_sma_then_smooths(self):
        series = [1.0, 2.0, 3.0, 4.0, 5.0]
        out = ema(series, 3)
        assert out[:2] == [None, None]
        assert out[2] == pytest.approx(2.0)          # SMA seed
        assert out[3] == pytest.approx(4 * 0.5 + 2.0 * 0.5)   # k = 2/4 = 0.5

    def test_rsi_all_gains_is_100(self):
        out = rsi([float(i) for i in range(1, 30)], 14)
        assert out[-1] == pytest.approx(100.0)

    def test_rsi_all_losses_is_zero(self):
        out = rsi([float(100 - i) for i in range(30)], 14)
        assert out[-1] == pytest.approx(0.0, abs=1e-9)

    def test_rsi_flat_series_is_neutral_50(self):
        out = rsi([100.0] * 30, 14)
        assert out[-1] == pytest.approx(50.0)

    def test_rsi_wilders_matches_analytic_value(self):
        """First Wilder RSI is the plain gain/loss average over the seed window.

        Derived here from the same input instead of hard-coding a published
        constant, which is normally quoted from higher-precision source data.
        """
        closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                  45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        avg_gain = sum(c for c in changes if c > 0) / 14
        avg_loss = sum(-c for c in changes if c < 0) / 14
        expected = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

        out = rsi(closes, 14)
        assert out[14] == pytest.approx(expected, abs=1e-9)
        assert out[14] == pytest.approx(70.4641, abs=1e-3)
        assert out[:14] == [None] * 14, "RSI must not emit values during warm-up"

    def test_rsi_smoothing_is_wilders_not_simple(self):
        """After the seed, RSI must use Wilder's recursive smoothing."""
        closes = [100.0] + [100.0 + i * 0.5 for i in range(1, 20)] + [95.0]
        out = rsi(closes, 14)
        seed_gain, seed_loss = 0.5, 0.0
        avg_gain = seed_gain
        avg_loss = seed_loss
        for i in range(15, len(closes)):
            delta = closes[i] - closes[i - 1]
            avg_gain = (avg_gain * 13 + max(delta, 0.0)) / 14
            avg_loss = (avg_loss * 13 + max(-delta, 0.0)) / 14
            expected = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
            assert out[i] == pytest.approx(expected, abs=1e-9)

    def test_atr_warmup_length(self):
        h = [10.0 + i * 0.1 for i in range(30)]
        l = [9.0 + i * 0.1 for i in range(30)]
        c = [9.5 + i * 0.1 for i in range(30)]
        out = atr(h, l, c, 10)
        assert out[:10] == [None] * 10
        assert out[10] is not None
        assert out[10] == pytest.approx(1.0, abs=0.15)

    def test_bollinger_bands_order_and_width(self):
        closes = [100.0 + (i % 5) for i in range(40)]
        upper, mid, lower = bollinger(closes, 20, 2.0)
        assert upper[-1] > mid[-1] > lower[-1]
        assert mid[-1] == pytest.approx(sum(closes[-20:]) / 20)
        # symmetric around the middle band
        assert (upper[-1] - mid[-1]) == pytest.approx(mid[-1] - lower[-1])

    def test_keltner_uses_atr_not_stdev(self):
        h = [100.0 + i for i in range(40)]
        l = [98.0 + i for i in range(40)]
        c = [99.0 + i for i in range(40)]
        upper, mid, lower = keltner(h, l, c, 20, 2.0)
        a = atr(h, l, c, 20)[-1]
        assert mid[-1] == pytest.approx(ema(c, 20)[-1])
        assert upper[-1] == pytest.approx(mid[-1] + 2 * a)
        assert lower[-1] == pytest.approx(mid[-1] - 2 * a)

    def test_macd_histogram_is_line_minus_signal(self):
        closes = [100.0 + 0.5 * i + (3 if i % 7 == 0 else 0) for i in range(120)]
        line, sig, hist = macd(closes, 12, 26, 9)
        for i in range(len(closes)):
            if hist[i] is not None:
                assert hist[i] == pytest.approx(line[i] - sig[i])
        assert hist[-1] is not None

    def test_donchian_excludes_current_candle(self):
        highs = [10.0] * 25
        lows = [5.0] * 25
        highs[-1] = 999.0   # a huge current bar must NOT inflate the channel
        lows[-1] = 0.001
        upper, mid, lower = donchian(highs, lows, 20, 10)
        assert upper[-1] == pytest.approx(10.0)
        assert lower[-1] == pytest.approx(5.0)

    def test_supertrend_flips_with_regime(self):
        down = syn.ramp(100.0, -0.8, 60)
        closes = down + syn.ramp(down[-1], 1.0, 60)
        candles = syn.ohlc_from_closes(closes)
        _, direction = supertrend([c.high for c in candles], [c.low for c in candles], closes, 10, 3.0)
        valid = [d for d in direction if d is not None]
        assert -1 in valid and 1 in valid, "supertrend never flipped across a V-shaped market"

    def test_stoch_rsi_bounded_0_100(self):
        closes = syn.multi_regime(40)
        k, d = stoch_rsi(closes, 14, 14, 3, 3)
        vals = [v for v in k + d if v is not None]
        assert vals, "StochRSI produced nothing"
        assert all(0.0 <= v <= 100.0 for v in vals)

    def test_session_vwap_resets_at_utc_midnight(self):
        # 4 candles at 23:15 on day 1 and 4 at 00:15 on day 2.
        day1 = 1704067200000 + 23 * 3600 * 1000
        candles = [
            Candle(day1 + i * 900000, 100.0, 101.0, 99.0, 100.0, 10.0) for i in range(4)
        ]
        day2 = day1 + 3600 * 1000
        candles += [
            Candle(day2 + i * 900000, 200.0, 201.0, 199.0, 200.0, 10.0) for i in range(4)
        ]
        vwap, n = session_vwap(candles)
        assert n == 4, "VWAP should only count the current UTC session"
        assert vwap == pytest.approx(200.0, abs=1.0)

    def test_supertrend_line_is_a_real_trailing_stop(self):
        """The defining property of a trailing stop: it only ratchets in the
        direction of the trend, and price sits on the correct side of it."""
        import random
        rng = random.Random(99)
        px, closes = 100.0, []
        for _ in range(400):
            px *= 1 + rng.gauss(0.0005, 0.012)
            closes.append(px)
        candles = syn.ohlc_from_closes(closes, spread=0.004)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        line, direction = supertrend(highs, lows, closes, 10, 3.0)

        seen_up = seen_down = False
        prev_line = prev_dir = None
        for i, (ln, d) in enumerate(zip(line, direction)):
            if ln is None or d is None:
                continue
            if d == 1:
                seen_up = True
                assert closes[i] >= ln - 1e-9, "price closed below an active long stop"
                if prev_dir == 1 and prev_line is not None:
                    assert ln >= prev_line - 1e-9, "long stop moved DOWN (not trailing)"
            else:
                seen_down = True
                assert closes[i] <= ln + 1e-9, "price closed above an active short stop"
                if prev_dir == -1 and prev_line is not None:
                    assert ln <= prev_line + 1e-9, "short stop moved UP (not trailing)"
            prev_line, prev_dir = ln, d
        assert seen_up and seen_down, "supertrend never entered both regimes"

    def test_supertrend_multiplier_widens_the_channel(self):
        closes = syn.noisy_trend(100.0, 0.0, 1.0, 200, seed=21)
        candles = syn.ohlc_from_closes(closes, spread=0.004)
        h, l = [c.high for c in candles], [c.low for c in candles]
        tight = supertrend(h, l, closes, 10, 1.5)[1]
        wide = supertrend(h, l, closes, 10, 5.0)[1]
        flips_tight = sum(1 for a, b in zip(tight, tight[1:]) if a is not None and b is not None and a != b)
        flips_wide = sum(1 for a, b in zip(wide, wide[1:]) if a is not None and b is not None and a != b)
        assert flips_wide < flips_tight, "a wider ATR multiplier must flip less often"

    def test_stoch_rsi_extremes_track_the_rsi_window(self):
        """Raw StochRSI must be 0 at the window's lowest RSI and 100 at the highest."""
        closes = syn.noisy_trend(100.0, 0.0, 1.5, 200, seed=31)
        r = rsi(closes, 14)
        k, _ = stoch_rsi(closes, 14, 14, 1, 1)   # k_period=1 -> raw StochRSI
        checked = 0
        for i in range(len(closes)):
            if k[i] is None:
                continue
            window = [v for v in r[max(0, i - 13) : i + 1] if v is not None]
            if len(window) < 14:
                continue
            hi, lo = max(window), min(window)
            if hi - lo <= 1e-12:
                continue
            expected = (r[i] - lo) / (hi - lo) * 100.0
            assert k[i] == pytest.approx(expected, abs=1e-9)
            if r[i] == lo:
                assert k[i] == pytest.approx(0.0)
            if r[i] == hi:
                assert k[i] == pytest.approx(100.0)
            checked += 1
        assert checked > 20

    def test_stoch_rsi_d_is_the_average_of_k(self):
        closes = syn.noisy_trend(100.0, 0.0, 1.2, 150, seed=41)
        k, d = stoch_rsi(closes, 14, 14, 3, 3)
        checked = 0
        for i in range(3, len(closes)):
            if d[i] is None:
                continue
            window = k[i - 2 : i + 1]
            if any(v is None for v in window):
                continue
            assert d[i] == pytest.approx(sum(window) / 3.0)
            checked += 1
        assert checked > 20

    def test_session_vwap_is_volume_weighted(self):
        base = 1704067200000
        candles = [
            Candle(base, 100, 100, 100, 100.0, 1.0),
            Candle(base + 900000, 200, 200, 200, 200.0, 3.0),
        ]
        vwap, _ = session_vwap(candles)
        assert vwap == pytest.approx((100 * 1 + 200 * 3) / 4)


    def test_market_data_rejects_raw_floats_with_a_clear_error(self):
        with pytest.raises(TypeError, match="Candle objects"):
            MarketData("BTC/USDT", "15m", [1.0, 2.0, 3.0])


# ========================================================================== #
# Currency / exchange selection (INR support)
# ========================================================================== #


class _FakeExchange:
    """Minimal ccxt stand-in so symbol validation can be tested offline."""

    def __init__(self, markets, exc_id="fake"):
        self.markets = markets
        self.id = exc_id
        self.loaded = 0

    def load_markets(self):
        self.loaded += 1
        return self.markets


class TestCurrencyHandling:
    def test_quote_extraction(self):
        assert botmod.quote_of("BTC/INR") == "INR"
        assert botmod.quote_of("ETH/INR") == "INR"
        assert botmod.quote_of("BTC/USDT") == "USDT"
        assert botmod.quote_of("btc/inr") == "INR"
        assert botmod.quote_of("BTC/USD:BTC") == "USD", "settlement suffix must be stripped"

    def test_balance_key_per_currency(self):
        assert botmod.balance_key_for("INR") == "balance_inr"
        assert botmod.balance_key_for("USDT") == "balance_usd"
        assert botmod.balance_key_for("USD") == "balance_usd"
        assert botmod.balance_key_for("USDC") == "balance_usd"
        assert botmod.balance_key_for("EUR") == "balance_eur"

    def test_currency_symbols(self):
        assert botmod.currency_symbol_for("INR") == "\u20b9"
        assert botmod.currency_symbol_for("USDT") == "$"
        assert botmod.currency_symbol_for("XYZ") == "", "unknown currency renders bare"

    def test_config_defaults_are_inr(self):
        cfg = Config()
        assert cfg.symbol == "BTC/INR"
        assert cfg.starting_balance == 10000.0
        assert cfg.quote_currency == "INR"
        assert cfg.balance_key == "balance_inr"
        assert cfg.currency_symbol == "\u20b9"
        assert cfg.min_notional == 100.0

    def test_exchange_is_chosen_from_the_quote_currency(self):
        """Binance has no INR spot book, so INR must not default to it."""
        assert Config(symbol="BTC/INR").resolved_exchange == "zebpay"
        assert Config(symbol="ETH/INR").resolved_exchange == "zebpay"
        assert Config(symbol="BTC/USDT").resolved_exchange == "binance"

    def test_explicit_exchange_wins(self):
        assert Config(symbol="BTC/INR", exchange="mudrex").resolved_exchange == "mudrex"

    def test_symbol_validation_passes_for_a_listed_pair(self, tmp_path):
        engine = make_engine(["01_rsi_mean_reversion"], tmp_path)
        ex = _FakeExchange({"BTC/INR": {}, "ETH/INR": {}})
        engine._validate_symbol(ex)
        assert ex.loaded == 1

    def test_symbol_validation_names_alternatives(self, tmp_path):
        engine = make_engine(["01_rsi_mean_reversion"], tmp_path)
        engine.cfg.symbol = "BTC/INR"
        ex = _FakeExchange({"BTC/USDT": {}, "ETH/USDT": {}}, exc_id="binance")
        with pytest.raises(RuntimeError) as ei:
            engine._validate_symbol(ex)
        msg = str(ei.value)
        assert "does not list BTC/INR" in msg
        assert "zebpay" in msg, "must suggest an exchange that actually lists INR"

    def test_symbol_validation_lists_same_quote_markets(self, tmp_path):
        engine = make_engine(["01_rsi_mean_reversion"], tmp_path)
        engine.cfg.symbol = "DOGE/INR"
        ex = _FakeExchange({"BTC/INR": {}, "ETH/INR": {}}, exc_id="zebpay")
        with pytest.raises(RuntimeError) as ei:
            engine._validate_symbol(ex)
        assert "BTC/INR" in str(ei.value), "should show which INR pairs do exist"

    def test_symbol_validation_survives_a_network_error(self, tmp_path):
        """An unreachable markets endpoint must not block trading."""
        engine = make_engine(["01_rsi_mean_reversion"], tmp_path)

        class _Down:
            id = "down"
            markets = {}

            def load_markets(self):
                raise OSError("no network")

        engine._validate_symbol(_Down())   # must not raise

    def test_usd_mode_still_works_end_to_end(self, tmp_path):
        """Switching back to a USD venue must restore the old schema."""
        cfg = Config(state_path=str(tmp_path / "usd.json"), symbol="BTC/USDT")
        log = logging.getLogger("bot"); log.addHandler(logging.NullHandler())
        engine = Engine(cfg, log)
        engine.load_state(reset=True)
        acc = engine.accounts["01_rsi_mean_reversion"]
        assert acc.balance_key == "balance_usd"
        assert acc.quote_currency == "USDT"
        dumped = acc.to_dict()
        assert "balance_usd" in dumped and "balance_inr" not in dumped

    def test_env_vars_configure_the_currency(self, monkeypatch):
        monkeypatch.setenv("BOT_SYMBOL", "ETH/INR")
        monkeypatch.setenv("BOT_STARTING_BALANCE", "25000")
        monkeypatch.setenv("BOT_EXCHANGE", "mudrex")
        cfg = Config.from_env()
        assert cfg.symbol == "ETH/INR"
        assert cfg.starting_balance == 25000.0
        assert cfg.resolved_exchange == "mudrex"
        assert cfg.balance_key == "balance_inr"

    def test_summary_report_is_denominated_in_rupees(self):
        summary = {
            "01_rsi_mean_reversion": {
                "name": "RSI", "equity": 10500.0, "return_pct": 5.0, "balance": 0.0,
                "holdings": 0.0, "entry_price": None, "unrealized_pnl": 0.0,
                "realized_pnl": 500.0, "trades": 2, "action": "hold", "reason": "",
                "rejections": [],
            }
        }
        out = botmod.format_summary(summary, 5000000.0, "BTC/INR", "INR")
        assert "\u20b9" in out, "report must show the rupee sign"
        assert "INR" in out
        assert "10,500.00" in out

        md = botmod.format_markdown(summary, 5000000.0, "BTC/INR", 1, "INR")
        assert "\u20b910,500.00 INR" in md


# ========================================================================== #
# Broker: fees, guards, FIFO
# ========================================================================== #


class TestBroker:
    def _acc(self, balance=1000.0):
        return Account("test", "Test", balance)

    def _broker(self, cfg):
        log = logging.getLogger("test")
        log.addHandler(logging.NullHandler())
        return Broker(cfg, log)

    def test_buy_deducts_exact_tenth_percent_fee(self, cfg):
        acc, br = self._acc(), self._broker(cfg)
        trade = br.buy(acc, 50000.0, notional=500.0, reason="t")
        assert trade is not None
        assert trade["qty"] == pytest.approx(0.01)
        assert trade["fee"] == pytest.approx(0.5)              # 0.1% of 500
        assert acc.balance == pytest.approx(1000.0 - 500.0 - 0.5)
        assert acc.total_fees == pytest.approx(0.5)

    def test_sell_deducts_fee_and_books_net_pnl(self, cfg):
        acc, br = self._acc(), self._broker(cfg)
        br.buy(acc, 50000.0, notional=500.0, reason="entry")   # fee 0.5
        trade = br.sell(acc, 55000.0, reason="exit")           # fee 0.55
        assert trade is not None
        assert trade["fee"] == pytest.approx(0.55)
        assert trade["gross_pnl"] == pytest.approx(50.0)
        assert trade["pnl"] == pytest.approx(50.0 - 0.5 - 0.55)
        assert acc.realized_pnl == pytest.approx(trade["pnl"])
        assert acc.crypto_holdings == 0.0
        assert acc.balance == pytest.approx(1000.0 + trade["pnl"])

    def test_insufficient_balance_is_rejected(self, cfg):
        acc, br = self._acc(balance=100.0), self._broker(cfg)
        assert br.buy(acc, 50000.0, notional=500.0, reason="too big") is None
        assert acc.balance == 100.0
        assert not acc.lots
        assert acc.rejections and "insufficient balance" in acc.rejections[0]

    def test_fee_headroom_is_counted_in_the_guard(self, cfg):
        """Buying with 100% of cash must fail: cost + fee exceeds balance."""
        acc, br = self._acc(balance=1000.0), self._broker(cfg)
        assert br.buy(acc, 100.0, notional=1000.0, reason="all in") is None
        assert br.buy(acc, 100.0, notional=998.0, reason="fits") is not None

    def test_below_min_notional_is_rejected(self, cfg):
        assert cfg.min_notional == 100.0, "INR venues enforce a ~Rs 100 floor"
        acc, br = self._acc(), self._broker(cfg)
        assert br.buy(acc, 50000.0, notional=50.0, reason="dust") is None
        assert any("min notional" in r for r in acc.rejections)
        assert any("INR" in r for r in acc.rejections), "rejection should name the currency"

    def test_sell_without_position_is_rejected(self, cfg):
        acc, br = self._acc(), self._broker(cfg)
        assert br.sell(acc, 50000.0, reason="nothing to sell") is None
        assert any("no open position" in r for r in acc.rejections)

    def test_fifo_realizes_oldest_lot_first(self, cfg):
        acc, br = self._acc(balance=10000.0), self._broker(cfg)
        br.buy(acc, 100.0, notional=100.0, reason="lot1")   # 1.0 unit @ 100
        br.buy(acc, 200.0, notional=100.0, reason="lot2")   # 0.5 unit @ 200
        assert len(acc.lots) == 2
        trade = br.sell(acc, 150.0, qty=1.0, reason="partial")
        # FIFO consumes lot1 (1.0 @ 100) -> gross = 150 - 100 = 50
        assert trade["gross_pnl"] == pytest.approx(50.0)
        assert len(acc.lots) == 1
        assert acc.lots[0].price == pytest.approx(200.0)
        assert acc.lots[0].qty == pytest.approx(0.5)

    def test_entry_price_is_lot_weighted_average(self, cfg):
        acc, br = self._acc(balance=10000.0), self._broker(cfg)
        br.buy(acc, 100.0, notional=100.0, reason="a")   # 1.0 @ 100
        br.buy(acc, 300.0, notional=300.0, reason="b")   # 1.0 @ 300
        acc.mark_to_market(300.0)
        assert acc.entry_price == pytest.approx(200.0)
        assert acc.unrealized_pnl == pytest.approx((300.0 - 200.0) * 2.0)

    def test_slippage_is_adverse_on_both_sides(self, cfg):
        cfg.slippage = 0.001
        log = logging.getLogger("test"); log.addHandler(logging.NullHandler())
        acc, br = self._acc(), Broker(cfg, log)
        buy = br.buy(acc, 50000.0, notional=500.0, reason="s")
        sell = br.sell(acc, 50000.0, reason="s")
        assert buy["price"] == pytest.approx(50050.0)
        assert sell["price"] == pytest.approx(49950.0)
        assert sell["pnl"] < 0, "a round trip at the same reference price must lose money"


# ========================================================================== #
# Account / state persistence
# ========================================================================== #


class TestStateStore:
    def test_round_trip_preserves_account(self, tmp_path):
        path = str(tmp_path / "data.json")
        store = StateStore(path, logging.getLogger("t"))
        acc = Account("01_x", "X", 10000.0, "INR")
        acc.balance = 8123.4
        acc.lots = [botmod.Lot(qty=0.5, price=375.0, fee=0.1875)]
        acc.crypto_holdings = 0.5
        acc.entry_price = 375.0
        acc.trades = [{"side": "buy", "pnl": 0.0, "price": 375.0, "qty": 0.5,
                       "fee": 0.1875, "timestamp": "x", "exit_reason": None}]
        store.save({"meta": {"version": 1}, "accounts": {"01_x": acc.to_dict()}})

        raw = json.load(open(path))
        assert raw["accounts"]["01_x"]["balance_inr"] == pytest.approx(8123.4)
        assert "balance_usd" not in raw["accounts"]["01_x"], "INR account must not claim USD"
        restored = Account.from_dict(raw["accounts"]["01_x"], 10000.0, "INR")
        assert restored.balance == pytest.approx(8123.4)
        assert restored.quote_currency == "INR"
        assert restored.crypto_holdings == pytest.approx(0.5)
        assert restored.entry_price == pytest.approx(375.0)
        assert len(restored.lots) == 1
        assert restored.trades == acc.trades

    def test_save_is_atomic_and_leaves_a_backup(self, tmp_path):
        path = str(tmp_path / "data.json")
        store = StateStore(path, logging.getLogger("t"))
        store.save({"meta": {"run_count": 1}, "accounts": {}})
        store.save({"meta": {"run_count": 2}, "accounts": {}})
        assert json.load(open(path))["meta"]["run_count"] == 2
        assert json.load(open(path + ".bak"))["meta"]["run_count"] == 1
        assert not os.path.exists(path + ".tmp")

    def test_corrupt_state_is_quarantined_not_fatal(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text("{ this is not json", encoding="utf-8")
        store = StateStore(str(path), logging.getLogger("t"))
        assert store.load() == {}
        assert path.exists() is False
        assert (tmp_path / "data.json.corrupt").exists()

    def test_legacy_state_without_lots_is_reconciled(self):
        raw = {"strategy_id": "01_x", "name": "X", "balance_usd": 500.0,
               "crypto_holdings": 2.0, "entry_price": 250.0, "trades": []}
        acc = Account.from_dict(raw, 1000.0, "USDT")
        assert len(acc.lots) == 1
        assert acc.lots[0].qty == 2.0 and acc.lots[0].price == 250.0

    def test_legacy_balance_usd_key_still_loads_for_an_inr_account(self):
        """A pre-INR-switch state file must not silently reset to zero."""
        raw = {"strategy_id": "01_x", "name": "X", "balance_usd": 742.5, "trades": []}
        acc = Account.from_dict(raw, 10000.0, "INR")
        assert acc.balance == pytest.approx(742.5)
        assert acc.balance_key == "balance_inr"


# ========================================================================== #
# Strategies: each of the 12 must actually trade
# ========================================================================== #


class TestStrategiesFire:
    """Each strategy is run through the real Engine over a crafted series."""

    def _run(self, sid, candles, tmp_path, **cfg_kwargs):
        engine = make_engine([sid], tmp_path, **cfg_kwargs)
        replay(engine, candles)
        return account(engine, sid)

    def test_01_rsi_mean_reversion(self, tmp_path):
        closes = syn.ramp(50000.0, -0.6, 45)
        closes += syn.ramp(closes[-1], 0.7, 45)
        acc = self._run("01_rsi_mean_reversion", syn.ohlc_from_closes(closes), tmp_path)
        sides = {t["side"] for t in acc.trades}
        assert "buy" in sides, "RSI strategy never bought an oversold dip"
        assert "sell" in sides, "RSI strategy never sold an overbought spike"
        assert any("oversold" in (t.get("entry_reason") or "") for t in acc.trades)
        assert any("overbought" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_02_dual_ema_crossover(self, tmp_path):
        closes = syn.ramp(50000.0, -0.5, 40)                 # EMA9 below EMA21
        closes += syn.ramp(closes[-1], 0.8, 40)              # cross up -> buy
        closes += syn.ramp(closes[-1], -0.9, 40)             # cross down -> sell
        acc = self._run("02_dual_ema_crossover", syn.ohlc_from_closes(closes), tmp_path)
        assert any("crossed above" in (t.get("entry_reason") or "") for t in acc.trades)
        assert any("crossed below" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_03_macd_histogram_reversal(self, tmp_path):
        # Noisy regimes: a constant-rate ramp leaves MACD degenerate.
        down = syn.noisy_trend(50000.0, -0.55, 0.35, 70, seed=5)
        up = syn.noisy_trend(down[-1], +0.85, 0.35, 70, seed=6)
        over = syn.noisy_trend(up[-1], -0.95, 0.35, 70, seed=7)
        closes = down + up + over
        acc = self._run("03_macd_histogram_reversal", syn.ohlc_from_closes(closes), tmp_path)
        assert any("crossed above signal" in (t.get("entry_reason") or "") for t in acc.trades)
        assert any("crossed below signal" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_04_triple_moving_average(self, tmp_path):
        # 260 declining candles, a rally that aligns 20>50>200, then a crash.
        closes = syn.ramp(50000.0, -0.12, 260)
        closes += syn.ramp(closes[-1], 0.55, 70)
        closes += syn.ramp(closes[-1], -0.9, 40)
        acc = self._run("04_triple_moving_average", syn.ohlc_from_closes(closes), tmp_path)
        assert any("trend confirmed" in (t.get("entry_reason") or "") for t in acc.trades)
        assert any("dropped below" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_05_supertrend_atr(self, tmp_path):
        closes = syn.ramp(50000.0, -0.7, 50) + syn.ramp(50000.0 * 0.993 ** 50, 0.9, 50)
        closes += syn.ramp(closes[-1], -0.9, 40)
        acc = self._run("05_supertrend_atr", syn.ohlc_from_closes(closes), tmp_path)
        assert any("flipped bullish" in (t.get("entry_reason") or "") for t in acc.trades)
        assert any("flipped bearish" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_06_bollinger_mean_reversion(self, tmp_path):
        closes = syn.flat(50000.0, 40, jitter_pct=0.05)
        closes += [closes[-1] * 0.985]                       # pierce the lower band
        closes += syn.ramp(closes[-1], 0.35, 15)             # revert to the middle band
        acc = self._run("06_bollinger_mean_reversion", syn.ohlc_from_closes(closes), tmp_path)
        assert any("lower band" in (t.get("entry_reason") or "") for t in acc.trades)
        assert any("middle band" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_07_keltner_breakout(self, tmp_path):
        closes = syn.flat(50000.0, 40, jitter_pct=0.05)
        closes += [closes[-1] * 1.02]                        # break the upper channel
        closes += syn.ramp(closes[-1], -0.6, 20)             # fall back under the middle line
        acc = self._run("07_keltner_breakout", syn.ohlc_from_closes(closes), tmp_path)
        assert any("upper Keltner" in (t.get("entry_reason") or "") for t in acc.trades)
        assert any("middle line" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_08_stoch_rsi_reversal(self, tmp_path):
        import random
        rng = random.Random(11)
        closes = []
        px = 50000.0
        for _ in range(70):                       # noisy downtrend -> oversold
            px *= 1 + (-0.35 + rng.gauss(0, 0.45)) / 100
            closes.append(px)
        for _ in range(45):                       # reversal -> %K crosses up
            px *= 1 + (0.45 + rng.gauss(0, 0.35)) / 100
            closes.append(px)
        for _ in range(30):                       # top + roll over -> cross down
            px *= 1 + (-0.15 + rng.gauss(0, 0.5)) / 100
            closes.append(px)
        acc = self._run("08_stoch_rsi_reversal", syn.ohlc_from_closes(closes), tmp_path)
        assert any("oversold zone" in (t.get("entry_reason") or "") for t in acc.trades)
        assert any("overbought zone" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_09_vwap_pullback_buy(self, tmp_path):
        acc = self._run("09_vwap_pullback", syn.vwap_buy_series(), tmp_path)
        assert any("VWAP" in (t.get("entry_reason") or "") for t in acc.trades), \
            "VWAP strategy never bought a below-VWAP pullback"

    def test_09_vwap_pullback_sell(self, tmp_path):
        # Needs an entry first: the strategy only exits a position it holds.
        acc = self._run("09_vwap_pullback", syn.vwap_round_trip_series(), tmp_path)
        sides = [t["side"] for t in acc.trades]
        assert sides[:2] == ["buy", "sell"], f"expected an entry then an exit, got {sides[:4]}"
        assert any("extended" in (t.get("exit_reason") or "") for t in acc.trades), \
            "VWAP strategy never sold a 1.5% extension"

    def test_10_donchian_breakout(self, tmp_path):
        closes = syn.flat(50000.0, 30, jitter_pct=0.05)
        closes += [closes[-1] * 1.02]                        # 20-candle high breakout
        closes += syn.ramp(closes[-1], -0.7, 20)             # 10-candle low break
        acc = self._run("10_donchian_breakout", syn.ohlc_from_closes(closes), tmp_path)
        assert any("broke 20-candle high" in (t.get("entry_reason") or "") for t in acc.trades)
        assert any("broke 10-candle low" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_11_dynamic_dca_accumulates(self, tmp_path):
        closes = syn.flat(50000.0, 60, jitter_pct=0.1)
        acc = self._run("11_dynamic_dca", syn.ohlc_from_closes(closes), tmp_path)
        buys = [t for t in acc.trades if t["side"] == "buy"]
        assert len(buys) >= 10, "DCA should buy every 4th candle"
        assert acc.crypto_holdings > 0
        assert not [t for t in acc.trades if t["side"] == "sell"], "plain DCA never sells"

    def test_11_dca_doubles_the_order_on_a_24h_dip(self, tmp_path):
        closes = syn.ramp(50000.0, -0.2, 120)          # unambiguous 24h decline
        acc = self._run("11_dynamic_dca", syn.ohlc_from_closes(closes), tmp_path)
        buys = [t for t in acc.trades if t["side"] == "buy"]
        assert buys, "DCA never bought"
        doubled = [t for t in buys if t["notional"] > 900.0]
        assert doubled, "no order was doubled despite a negative 24h change"
        assert all("[dip x2]" in (t.get("entry_reason") or "") for t in doubled)

    def test_11_dca_stops_when_cash_runs_out(self, tmp_path):
        closes = syn.flat(50000.0, 400, jitter_pct=0.05)
        acc = self._run("11_dynamic_dca", syn.ohlc_from_closes(closes), tmp_path)
        assert acc.balance >= 0.0
        total_spent = sum(t["notional"] + t["fee"] for t in acc.trades if t["side"] == "buy")
        assert total_spent <= 10000.0 + 1e-6

    def test_12_grid_runs_a_profitable_round_trip(self, tmp_path):
        # Dip 1.2% (fills a buy level) then recover 1.2% (fills its take-profit).
        closes = syn.flat(50000.0, 20, jitter_pct=0.02)
        closes += syn.ramp(closes[-1], -0.4, 4)          # ~-1.6%, fills level -1
        closes += syn.ramp(closes[-1], 0.7, 4)           # back up through the target
        closes += syn.flat(closes[-1], 4, jitter_pct=0.02)
        acc = self._run("12_arithmetic_grid", syn.ohlc_from_closes(closes), tmp_path)
        buys = [t for t in acc.trades if t["side"] == "buy"]
        sells = [t for t in acc.trades if t["side"] == "sell"]
        assert buys, "grid never filled a buy level"
        assert sells, "grid never took profit one step above"
        assert any("take-profit" in (t.get("exit_reason") or "") for t in sells)
        rt = acc.strategy_state["grid"]["round_trips"]
        assert rt >= 1

    def test_12_grid_limit_orders_fill_at_the_ladder_price(self, tmp_path):
        closes = syn.flat(50000.0, 20, jitter_pct=0.02)
        closes += syn.ramp(closes[-1], -0.4, 4)
        closes += syn.flat(closes[-1], 3, jitter_pct=0.02)
        acc = self._run("12_arithmetic_grid", syn.ohlc_from_closes(closes), tmp_path)
        buys = [t for t in acc.trades if t["side"] == "buy"]
        assert buys
        anchor = acc.strategy_state["grid"]["anchor"]
        step = acc.strategy_state["grid"]["step_price"]
        for t in buys:
            expected = anchor + t["grid_level"] * step
            assert t["price"] == pytest.approx(expected), "grid must fill at its limit price"
            assert t["price"] <= anchor

    def test_12_grid_scales_with_equity_and_never_overspends(self, tmp_path):
        """The ladder is sized from current equity, so the broker never has to
        refuse a grid order for lack of funds."""
        engine = make_engine(["12_arithmetic_grid"], tmp_path)
        candles = syn.ohlc_from_closes(syn.multi_regime(90))
        replay(engine, candles)
        acc = account(engine, "12_arithmetic_grid")
        assert acc.trades, "grid never traded"
        assert not acc.rejections, f"grid orders were refused: {acc.rejections}"
        assert acc.balance >= 0.0

    def test_12_grid_reanchors_and_liquidates_on_a_large_drift(self, tmp_path):
        closes = syn.flat(50000.0, 20, jitter_pct=0.02)
        closes += syn.ramp(closes[-1], -0.4, 4)     # load some inventory
        closes += syn.ramp(closes[-1], -2.0, 5)     # >6% drift -> re-anchor
        closes += syn.flat(closes[-1], 3, jitter_pct=0.02)
        acc = self._run("12_arithmetic_grid", syn.ohlc_from_closes(closes), tmp_path)
        assert acc.strategy_state["grid"]["rebuilt"] >= 1
        assert any("re-anchored" in (t.get("exit_reason") or "") for t in acc.trades)


# ========================================================================== #
# Engine-level behaviour
# ========================================================================== #


class TestEngine:
    def test_all_twelve_accounts_start_at_ten_thousand_inr(self, tmp_path):
        engine = make_engine(ALL_IDS, tmp_path)
        assert len(engine.accounts) == 12
        for sid, acc in engine.accounts.items():
            assert acc.balance == 10000.0
            assert acc.quote_currency == "INR"
            assert acc.balance_key == "balance_inr"
            assert acc.crypto_holdings == 0.0
            assert acc.entry_price is None
            assert acc.trades == []

    def test_strategy_ids_match_the_spec_ordering(self):
        assert [c.id for c in STRATEGY_CLASSES] == [
            "01_rsi_mean_reversion", "02_dual_ema_crossover", "03_macd_histogram_reversal",
            "04_triple_moving_average", "05_supertrend_atr", "06_bollinger_mean_reversion",
            "07_keltner_breakout", "08_stoch_rsi_reversal", "09_vwap_pullback",
            "10_donchian_breakout", "11_dynamic_dca", "12_arithmetic_grid",
        ]

    def test_equity_invariant_over_a_long_replay(self, tmp_path):
        """equity == starting + realized + unrealized - open entry fees."""
        engine = make_engine(ALL_IDS, tmp_path)
        candles = syn.ohlc_from_closes(syn.multi_regime(90))
        replay(engine, candles)
        price = engine.state["meta"]["last_price"]
        checked = 0
        for sid, acc in engine.accounts.items():
            equity = acc.equity(price)
            expected = acc.starting_balance + acc.realized_pnl + acc.unrealized_pnl - acc.open_entry_fee
            assert equity == pytest.approx(expected, abs=1e-6), f"invariant broke for {sid}"
            assert acc.balance >= -1e-9, f"{sid} went into overdraft"
            checked += 1
        assert checked == 12

    def test_no_negative_quantities_and_fees_are_always_tenth_percent(self, tmp_path):
        engine = make_engine(ALL_IDS, tmp_path)
        replay(engine, syn.ohlc_from_closes(syn.multi_regime(90)))
        total = 0
        for acc in engine.accounts.values():
            for t in acc.trades:
                assert t["qty"] > 0
                assert t["price"] > 0
                assert t["fee"] == pytest.approx(t["notional"] * 0.001, rel=1e-9)
                assert t["fee"] > 0
                total += 1
        assert total > 0, "no trades were produced at all"

    def test_single_position_strategies_never_double_up(self, tmp_path):
        """Only DCA and the grid may hold more than one open lot."""
        engine = make_engine(ALL_IDS, tmp_path)
        replay(engine, syn.ohlc_from_closes(syn.multi_regime(90)))
        multi = {"11_dynamic_dca", "12_arithmetic_grid"}
        for sid, acc in engine.accounts.items():
            if sid in multi:
                continue
            assert len(acc.lots) <= 1, f"{sid} opened {len(acc.lots)} concurrent lots"

    def test_every_strategy_trades_over_a_rich_history(self, tmp_path):
        engine = make_engine(ALL_IDS, tmp_path)
        replay(engine, syn.ohlc_from_closes(syn.multi_regime(90)))
        silent = [sid for sid, a in engine.accounts.items() if not a.trades]
        assert not silent, f"strategies never traded: {silent}"

    def test_duplicate_candle_is_skipped(self, tmp_path):
        engine = make_engine(["11_dynamic_dca"], tmp_path)
        candles = syn.ohlc_from_closes(syn.flat(50000.0, 40, jitter_pct=0.1))
        replay(engine, candles)
        first = len(account(engine, "11_dynamic_dca").trades)
        assert first > 0
        # Re-feed the identical window: run_count advances but no new trades.
        window = candles[-30:]
        engine.process_market(MarketData("BTC/USDT", "15m", window))
        assert len(account(engine, "11_dynamic_dca").trades) == first

    def test_force_flag_reprocesses_the_same_candle(self, tmp_path):
        """Without the guard the candle is evaluated again; with it, skipped."""
        candles = syn.ohlc_from_closes(syn.flat(50000.0, 40, jitter_pct=0.1))

        forced = make_engine(["11_dynamic_dca"], tmp_path)
        forced.cfg.skip_duplicate_candle = False
        replay(forced, candles)
        runs_before = account(forced, "11_dynamic_dca").strategy_state["runs"]
        forced.process_market(MarketData("BTC/USDT", "15m", candles[-30:]))
        assert account(forced, "11_dynamic_dca").strategy_state["runs"] == runs_before + 1

        guarded = make_engine(["11_dynamic_dca"], tmp_path)
        replay(guarded, candles)
        runs_before = account(guarded, "11_dynamic_dca").strategy_state["runs"]
        guarded.process_market(MarketData("BTC/USDT", "15m", candles[-30:]))
        assert account(guarded, "11_dynamic_dca").strategy_state["runs"] == runs_before, \
            "the duplicate-candle guard failed to suppress re-evaluation"

    def test_in_progress_candle_is_dropped_before_signalling(self, tmp_path):
        """A wild live bar must not move the signal: it is discarded."""
        engine_a = make_engine(["01_rsi_mean_reversion"], tmp_path / "a")
        engine_b = make_engine(["01_rsi_mean_reversion"], tmp_path / "b")
        base = syn.ohlc_from_closes(syn.ramp(50000.0, -0.6, 40))
        replay(engine_a, base)

        spiked = list(base) + [Candle(base[-1].ts + 900000, 1.0, 99999.0, 1.0, 1.0, 1e9)]
        replay(engine_b, spiked)
        a = account(engine_a, "01_rsi_mean_reversion")
        b = account(engine_b, "01_rsi_mean_reversion")
        assert len(a.trades) == len(b.trades), "the in-progress candle leaked into the signal"

    def test_candle_limit_is_raised_to_cover_sma200(self, tmp_path):
        """A 100-candle fetch cannot satisfy SMA(200); the engine must widen it."""
        engine = make_engine(ALL_IDS, tmp_path)
        assert engine.required_candles() > 200
        assert max(engine.cfg.candle_limit, engine.required_candles()) >= 205

        only_short = make_engine(["01_rsi_mean_reversion"], tmp_path)
        assert only_short.required_candles() < 100, "RSI(14) must not force a wide fetch"

    def test_warmup_prevents_premature_signals(self, tmp_path):
        engine = make_engine(["04_triple_moving_average"], tmp_path)
        candles = syn.ohlc_from_closes(syn.ramp(50000.0, 0.3, 60))
        replay(engine, candles)
        assert account(engine, "04_triple_moving_average").trades == [], \
            "SMA200 strategy traded without 200 candles of history"

    def test_state_round_trips_across_engine_instances(self, tmp_path):
        engine = make_engine(ALL_IDS, tmp_path)
        replay(engine, syn.ohlc_from_closes(syn.multi_regime(60)))
        engine.persist()

        cfg2 = Config(state_path=str(tmp_path / "data.json"))
        log = logging.getLogger("bot"); log.addHandler(logging.NullHandler())
        engine2 = Engine(cfg2, log)
        engine2.load_state()
        for sid, acc in engine.accounts.items():
            restored = engine2.accounts[sid]
            assert restored.balance == pytest.approx(acc.balance, abs=1e-6)
            assert restored.crypto_holdings == pytest.approx(acc.crypto_holdings, abs=1e-9)
            assert restored.realized_pnl == pytest.approx(acc.realized_pnl, abs=1e-6)
            assert len(restored.trades) == len(acc.trades)

    def test_circuit_breaker_halts_all_fills(self, tmp_path):
        engine = make_engine(ALL_IDS, tmp_path, max_trades_per_run=0)
        replay(engine, syn.ohlc_from_closes(syn.multi_regime(60)))
        for sid, acc in engine.accounts.items():
            assert acc.trades == [], f"{sid} traded past the circuit breaker"

    def test_circuit_breaker_at_default_limit_does_not_interfere(self, tmp_path):
        engine = make_engine(ALL_IDS, tmp_path)
        assert engine.cfg.max_trades_per_run == 25
        replay(engine, syn.ohlc_from_closes(syn.multi_regime(60)))
        assert sum(len(a.trades) for a in engine.accounts.values()) > 25, \
            "a normal replay must not trip the breaker"

    def test_disabled_strategies_are_excluded(self, tmp_path):
        cfg = Config(state_path=str(tmp_path / "d.json"), disabled=["01_rsi_mean_reversion"])
        log = logging.getLogger("bot"); log.addHandler(logging.NullHandler())
        e2 = Engine(cfg, log)
        e2.load_state(reset=True)
        assert "01_rsi_mean_reversion" not in e2.accounts
        assert len(e2.accounts) == 11

    def test_risk_overlay_stop_loss_forces_an_exit(self, tmp_path):
        engine = make_engine(["01_rsi_mean_reversion"], tmp_path, stop_loss_pct=1.0)
        closes = syn.ramp(50000.0, -0.6, 40)      # buys the dip, then keeps falling
        closes += syn.ramp(closes[-1], -0.6, 20)
        replay(engine, syn.ohlc_from_closes(closes))
        acc = account(engine, "01_rsi_mean_reversion")
        assert any("stop-loss" in (t.get("exit_reason") or "") for t in acc.trades)

    def test_param_override_changes_behaviour(self, tmp_path):
        """rsi_buy=1 (impossible) must suppress entries; rsi_buy=99 forces them."""
        closes = syn.ramp(50000.0, -0.6, 40) + syn.ramp(50000.0 * 0.994 ** 40, 0.7, 40)
        candles = syn.ohlc_from_closes(closes)

        e_strict = make_engine(["01_rsi_mean_reversion"], tmp_path)
        e_strict.strategies[0].p["rsi_buy"] = -1.0     # RSI can never go below -1
        replay(e_strict, candles)

        e_loose = make_engine(["01_rsi_mean_reversion"], tmp_path)
        e_loose.strategies[0].p["rsi_buy"] = 101.0     # always "oversold"
        replay(e_loose, candles)

        n_strict = len(account(e_strict, "01_rsi_mean_reversion").trades)
        n_loose = len(account(e_loose, "01_rsi_mean_reversion").trades)
        assert n_strict == 0, "an unreachable threshold must suppress all entries"
        assert n_loose == 1, "an always-true threshold buys once then holds (single-position model)"

    def test_fee_drag_costs_money_on_a_flat_round_trip(self, tmp_path):
        """A buy+sell at an unchanged price must leave the account slightly poorer."""
        engine = make_engine(["06_bollinger_mean_reversion"], tmp_path)
        acc = account(engine, "06_bollinger_mean_reversion")
        br = engine.broker
        br.buy(acc, 50000.0, notional=9000.0, reason="in")
        br.sell(acc, 50000.0, reason="out")
        assert acc.equity(50000.0) < 10000.0
        # two-sided 0.1% on a 9,000 INR notional = 9.00 in, 9.00 out
        assert acc.equity(50000.0) == pytest.approx(10000.0 - 9.0 - 9.0, abs=1e-9)
        assert acc.total_fees == pytest.approx(18.0, abs=1e-9)


# ========================================================================== #
# CLI end-to-end
# ========================================================================== #


class TestCli:
    def _run(self, args, cwd=REPO_ROOT):
        return subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "bot.py")] + args,
            cwd=cwd, capture_output=True, text=True, timeout=180,
        )

    def test_help_and_version(self):
        assert self._run(["--help"]).returncode == 0
        v = self._run(["--version"])
        assert v.returncode == 0 and botmod.__version__ in v.stdout

    def test_replay_writes_a_complete_state_file(self, tmp_path):
        csv_path = syn.to_csv(syn.ohlc_from_closes(syn.multi_regime(60)), str(tmp_path / "hist.csv"))
        state = str(tmp_path / "data.json")
        r = self._run(["--replay", csv_path, "--state", state, "--reset", "--yes"])
        assert r.returncode == 0, r.stderr
        assert "PORTFOLIO SNAPSHOT" in r.stdout

        data = json.load(open(state))
        assert data["meta"]["version"] == 1
        assert data["meta"]["starting_balance"] == 10000.0
        assert data["meta"]["fee_rate"] == 0.001
        assert data["meta"]["symbol"] == "BTC/INR"
        assert data["meta"]["quote_currency"] == "INR"
        assert len(data["accounts"]) == 12
        for sid, acc in data["accounts"].items():
            for key in ("balance_inr", "crypto_holdings", "entry_price", "unrealized_pnl", "trades"):
                assert key in acc, f"{sid} missing {key}"
            assert "balance_usd" not in acc, f"{sid} must not report a USD balance"
        assert sum(len(a["trades"]) for a in data["accounts"].values()) > 0

    def test_dry_run_does_not_touch_disk(self, tmp_path):
        csv_path = syn.to_csv(syn.ohlc_from_closes(syn.multi_regime(40)), str(tmp_path / "hist.csv"))
        state = str(tmp_path / "data.json")
        r = self._run(["--replay", csv_path, "--state", state, "--dry-run"])
        assert r.returncode == 0, r.stderr
        assert not os.path.exists(state)
        assert "not written" in r.stdout

    def test_starting_balance_and_exchange_flags(self, tmp_path):
        csv_path = syn.to_csv(syn.ohlc_from_closes(syn.multi_regime(30)), str(tmp_path / "hist.csv"))
        state = str(tmp_path / "data.json")
        r = self._run(["--replay", csv_path, "--state", state, "--reset", "--yes",
                       "--starting-balance", "25000", "--exchange", "mudrex"])
        assert r.returncode == 0, r.stderr + r.stdout
        meta = json.load(open(state))["meta"]
        assert meta["starting_balance"] == 25000.0
        assert meta["exchange"] == "mudrex"
        assert "\u20b9" in r.stdout, "the run banner should be rupee-denominated"

    def test_usd_symbol_switches_schema_back(self, tmp_path):
        csv_path = syn.to_csv(syn.ohlc_from_closes(syn.multi_regime(30)), str(tmp_path / "hist.csv"))
        state = str(tmp_path / "data.json")
        r = self._run(["--replay", csv_path, "--state", state, "--reset", "--yes",
                       "--symbol", "BTC/USDT"])
        assert r.returncode == 0, r.stderr + r.stdout
        data = json.load(open(state))
        assert data["meta"]["quote_currency"] == "USDT"
        assert data["meta"]["exchange"] == "binance"
        acc = data["accounts"]["01_rsi_mean_reversion"]
        assert "balance_usd" in acc and "balance_inr" not in acc

    def test_symbol_flag_is_recorded_in_state(self, tmp_path):
        csv_path = syn.to_csv(syn.ohlc_from_closes(syn.multi_regime(30)), str(tmp_path / "hist.csv"))
        state = str(tmp_path / "data.json")
        r = self._run(["--replay", csv_path, "--state", state, "--symbol", "ETH/USDT", "--reset", "--yes"])
        assert r.returncode == 0, r.stderr
        assert json.load(open(state))["meta"]["symbol"] == "ETH/USDT"

    def test_param_override_from_cli(self, tmp_path):
        csv_path = syn.to_csv(syn.ohlc_from_closes(syn.multi_regime(30)), str(tmp_path / "hist.csv"))
        state = str(tmp_path / "data.json")
        r = self._run(["--replay", csv_path, "--state", state, "--reset", "--yes",
                       "--param", "11_dynamic_dca.base_notional=250",
                       "--param", "11_dynamic_dca.take_profit_pct=null"])
        assert r.returncode == 0, r.stderr + r.stdout
        buys = [t for t in json.load(open(state))["accounts"]["11_dynamic_dca"]["trades"] if t["side"] == "buy"]
        assert buys
        assert all(t["notional"] <= 500.0 + 1e-9 for t in buys), "base_notional override was ignored"

    def test_bad_param_syntax_exits_2(self, tmp_path):
        r = self._run(["--param", "nonsense", "--dry-run", "--replay", "/dev/null"])
        assert r.returncode == 2

    def test_disable_removes_an_account(self, tmp_path):
        csv_path = syn.to_csv(syn.ohlc_from_closes(syn.multi_regime(30)), str(tmp_path / "hist.csv"))
        state = str(tmp_path / "data.json")
        r = self._run(["--replay", csv_path, "--state", state, "--reset", "--yes",
                       "--disable", "04_triple_moving_average"])
        assert r.returncode == 0, r.stderr
        assert "04_triple_moving_average" not in json.load(open(state))["accounts"]

    def test_live_path_fails_cleanly_without_network(self, tmp_path):
        """A network failure must not corrupt or overwrite the state file."""
        state = tmp_path / "data.json"
        state.write_text(json.dumps({"meta": {"run_count": 7}, "accounts": {}}), encoding="utf-8")
        rc = botmod.main(["--state", str(state)])
        assert rc == 1
        assert json.load(open(state))["meta"]["run_count"] == 7, "state was clobbered on failure"

    def test_github_step_summary_is_written(self, tmp_path, monkeypatch):
        summary_file = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        csv_path = syn.to_csv(syn.ohlc_from_closes(syn.multi_regime(30)), str(tmp_path / "hist.csv"))
        rc = botmod.main(["--replay", csv_path, "--state", str(tmp_path / "data.json"),
                          "--reset", "--yes"])
        assert rc == 0
        text = summary_file.read_text()
        assert "### CryptoTrade paper-trading run" in text
        assert "| Strategy |" in text


# ========================================================================== #
# Replay parser
# ========================================================================== #


class TestReplayParser:
    def test_loads_with_and_without_header(self, tmp_path):
        p1 = tmp_path / "a.csv"
        syn.to_csv(syn.ohlc_from_closes([100.0, 101.0, 102.0, 103.0]), str(p1))
        rows = botmod.load_replay_csv(str(p1))
        assert len(rows) == 4 and rows[0].close == 100.0

        p2 = tmp_path / "b.csv"
        p2.write_text("1,1,1,1,1,1\n2,2,2,2,2,2\n3,3,3,3,3,3\n", encoding="utf-8")
        assert len(botmod.load_replay_csv(str(p2))) == 3

    def test_rejects_a_short_file(self, tmp_path):
        p = tmp_path / "c.csv"
        p.write_text("1,1,1,1,1,1\n", encoding="utf-8")
        with pytest.raises(ValueError):
            botmod.load_replay_csv(str(p))
