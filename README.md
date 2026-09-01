# CryptoTrade

A **paper-trading** engine that runs **42 isolated virtual sub-accounts**, each
executing a different trading strategy against the same BTC/USDT (or ETH/USDT)
candle stream. Every account starts with **$1,000** of virtual capital and is
tracked independently in [`docs/data.json`](docs/data.json).

No real orders are ever placed. Fills are simulated against exchange OHLCV data
with a **0.1% spot fee deducted on both sides**.

> Research and education only. This is not financial advice, and paper results
> do not transfer to live trading.

---

## Quick start

```bash
pip install -r requirements.txt          # only dependency: ccxt

python bot.py --init                     # create docs/data.json (42 x $1,000)
python bot.py                            # one tick against live Kraken data
python bot.py --symbol ETH/USDT          # alternate market
python bot.py --dry-run                  # evaluate, print, write nothing
```

Each invocation is a single, stateless tick: read state → fetch candles →
evaluate all 42 strategies → write state back. That makes it safe to run from
cron or GitHub Actions.

---

## The 42 strategies

### Momentum & Trend Following

| # | Account id | Strategy | Entry | Exit |
|---|---|---|---|---|
| 1 | `01_rsi_mean_reversion` | RSI Mean Reversion | RSI(14) < 30 | RSI(14) > 70 |
| 2 | `02_dual_ema_crossover` | Dual EMA Crossover (9/21) | EMA9 crosses above EMA21 | EMA9 crosses below EMA21 |
| 3 | `03_macd_histogram_reversal` | MACD Signal Crossover | MACD crosses above Signal | MACD crosses below Signal |
| 4 | `04_triple_moving_average` | Triple MA Trend (20/50/200) | SMA20 > SMA50 > SMA200 | SMA20 < SMA50 |
| 5 | `05_supertrend_atr` | Supertrend ATR Trailing Stop | ATR(10, ×3) flips bullish | flips bearish / stop breached |
| 6 | `13_adx_dmi_trend` | ADX DMI Trend Strength | ADX(14) > 25 and +DI > −DI | ADX < 20 or −DI takes the lead |
| 7 | `14_ichimoku_cloud` | Ichimoku Cloud Breakout | TK cross above the cloud, cloud green | close re-enters the cloud |
| 8 | `15_parabolic_sar` | Parabolic SAR Flip | SAR dot flips below price | SAR dot flips above price |
| 9 | `16_roc_momentum` | ROC Momentum Burst | ROC(12) crosses above 0 | ROC(12) crosses below 0 |
| 10 | `17_aroon_trend` | Aroon Trend | Aroon Up > 70 and Up > Down | Aroon Down > 70 or Down > Up |
| 11 | `18_heikin_ashi_trend` | Heikin-Ashi Trend | 3 wick-free HA candles, colour flip | HA candle flips colour |
| 12 | `19_trix_momentum` | TRIX Signal Crossover | TRIX(15) crosses above its 9 signal | TRIX crosses below its signal |
| 13 | `20_ema_ribbon_consensus` | EMA Ribbon Consensus | EMA 8/13/21/34/55 fully aligned up | any ribbon crossover down |

### Mean Reversion & Channels

| # | Account id | Strategy | Entry | Exit |
|---|---|---|---|---|
| 14 | `06_bollinger_mean_reversion` | Bollinger Bands Mean Reversion | close < Lower Band (20, 2) | close reaches Middle Band |
| 15 | `07_keltner_breakout` | Keltner Channel Breakout | close > EMA20 + 2·ATR | close falls below EMA20 |
| 16 | `08_stoch_rsi_reversal` | Stochastic RSI Reversal | %K crosses above %D below 20 | %K crosses below %D above 80 |

### Mean Reversion & Oscillators

| # | Account id | Strategy | Entry | Exit |
|---|---|---|---|---|
| 17 | `21_williams_r_reversal` | Williams %R Reversal | %R turns up out of < −80 | %R turns down out of > −20 |
| 18 | `22_cci_mean_reversion` | CCI Mean Reversion | CCI(20) crosses up through −100 | CCI crosses down through +100 |
| 19 | `23_connors_rsi_pullback` | Connors RSI(2) Pullback | Connors RSI(3,2,100) < 10 | Connors RSI > 90 |
| 20 | `24_zscore_mean_reversion` | Z-Score Mean Reversion | z-score(20) < −2 | z-score returns to 0 |
| 21 | `25_mfi_flow_reversal` | Money Flow Index Reversal | MFI(14) crosses up out of < 20 | MFI crosses down out of > 80 |
| 22 | `26_chande_momentum` | Chande Momentum Oscillator | CMO(20) crosses up through −50 | CMO crosses down through +50 |

### Volume & Volatility

| # | Account id | Strategy | Entry | Exit |
|---|---|---|---|---|
| 23 | `09_vwap_pullback` | Session VWAP Pullback | close < VWAP and RSI > 40 | close ≥ VWAP + 1.5% |
| 24 | `10_donchian_breakout` | Donchian Turtle Breakout (20/10) | close breaks the 20-candle high | close breaks the 10-candle low |
| 25 | `27_obv_trend_breakout` | OBV Trend Breakout | OBV breaks its 20-candle high, close up | OBV breaks its 20-candle low |
| 26 | `28_volume_spike_breakout` | Volume Spike Breakout | volume > 2× SMA20 with a 20-candle high break | close breaks the 10-candle low |
| 27 | `29_volatility_squeeze` | Volatility Squeeze Breakout | TTM squeeze releases, close > mid band | close falls below the middle band |
| 28 | `30_elder_ray_power` | Elder-Ray Power Shift | bear power lifts toward 0, bull power > 0 | bull power rolls over |

### Price Action

| # | Account id | Strategy | Entry | Exit |
|---|---|---|---|---|
| 29 | `31_engulfing_reversal` | Engulfing Candle Reversal | bullish engulfing at a 20-candle low | bearish engulfing or stop |
| 30 | `32_fibonacci_pullback` | Fibonacci Retracement Pullback | pullback into the 0.382–0.618 retracement | new swing high taken or stop |
| 31 | `33_pivot_point_bounce` | Pivot Point Bounce | bounce off prior-session S1 or the pivot | prior-session R1 reached |
| 32 | `34_opening_range_breakout` | Opening Range Breakout | UTC open + 1h range broken upward | back inside the opening range |

### Risk & Trailing

| # | Account id | Strategy | Entry | Exit |
|---|---|---|---|---|
| 33 | `35_chandelier_trend_ride` | Chandelier Exit Trend Ride | uptrend confirmed, entry on a pullback | 3×ATR chandelier stop |

### Execution-Based & Portfolio

| # | Account id | Strategy | Entry | Exit |
|---|---|---|---|---|
| 34 | `11_dynamic_dca` | Dynamic DCA (Dip Multiplier) ‡ | every 4th candle, ×2 if 24h is red | *(accumulates; optional take-profit)* |
| 35 | `12_arithmetic_grid` | Fixed-Step Arithmetic Grid ‡ | limit buys each 1% step down | take-profit one step up |
| 36 | `36_martingale_dip` | Martingale Dip Accumulator ‡ | each −2% dip, size doubles (max 4 steps) | *(accumulates; optional take-profit)* |
| 37 | `37_anti_martingale_pyramid` | Anti-Martingale Pyramid ‡ | 20-candle high breakout, adds at each +2% leg | 3% trail below the tracked peak |
| 38 | `38_kelly_fraction_sizer` | Kelly Fraction Position Sizing | Donchian(20) breakout, sized by half-Kelly | close breaks the 10-candle low |

### Composite & Hybrid

| # | Account id | Strategy | Entry | Exit |
|---|---|---|---|---|
| 39 | `39_multi_indicator_consensus` | Multi-Indicator Consensus Vote | ≥3 of 5 independent votes agree | ≥3 votes turn the other way |
| 40 | `40_trend_pullback_confluence` | Trend + Pullback Confluence | RSI(14) < 35 **and** close > SMA200 > SMA50 | RSI > 60 or trend breaks |
| 41 | `41_volatility_regime_switcher` | Volatility Regime Switcher | ATR percentile ≥ 70 → fade, ≤ 30 → break out | per the active sub-regime |
| 42 | `42_sibling_performance_allocator` | Sibling Performance Allocator | peers' median return ≥ 0 (else stands aside) | median return turns negative |

‡ These 4 accounts are exempt from the one-position-per-account rule and may hold several concurrent lots: `11_dynamic_dca`, `12_arithmetic_grid`, `36_martingale_dip`, `37_anti_martingale_pyramid`.

Strategy `42` is the one account that is **not** fully isolated: it reads a read-only snapshot of
every sibling's return to decide whether to participate at all. It never writes to another
account, and there is a test asserting that observing a peer leaves it unmutated. Every other
account is completely independent — its own cash, its own lots, its own indicator state.

## State file

`docs/data.json` holds the whole portfolio. Each account tracks the required
fields plus enough history to audit every fill:

```jsonc
{
  "meta": { "run_count": 128, "last_candle_ts": 1704067200000, "fee_rate": 0.001, ... },
  "accounts": {
    "01_rsi_mean_reversion": {
      "balance_usd": 1077.17,        // free cash
      "crypto_holdings": 0.0,        // base-currency quantity
      "entry_price": null,           // weighted average of open lots
      "unrealized_pnl": 0.0,
      "realized_pnl": 77.17,
      "total_fees": 3.41,
      "lots": [ { "qty": ..., "price": ..., "fee": ... } ],
      "strategy_state": { ... },     // per-strategy memory (grid ladder, DCA counter)
      "trades": [
        {
          "timestamp": "2024-01-01T01:00:00Z",
          "side": "sell", "price": 50123.4, "qty": 0.0189,
          "notional": 947.3, "fee": 0.947,
          "pnl": 12.04, "gross_pnl": 13.93,
          "exit_reason": "RSI(14)=74.31 > 70 (overbought)"
        }
      ]
    }
  }
}
```

Writes are **atomic** (temp file + `os.replace`) and keep a rotating
`data.json.bak`. A corrupt or truncated file is quarantined to
`data.json.corrupt` and rebuilt rather than crashing the run.

---

## How execution is simulated

| Concern | Behaviour |
|---|---|
| **Signal candle** | The in-progress candle is dropped. Signals use the last *closed* candle, so nothing can repaint against a partial bar. |
| **Fill price** | Close of the signal candle, optionally degraded by `--slippage`. Grid limit orders fill at their own ladder price. |
| **Fees** | 0.1% of notional, charged on buys (added to cost) and sells (netted from proceeds). |
| **Insufficient funds** | The order is refused and logged — cash is never allowed to go negative. |
| **Min order size** | Orders under 10 USDT notional are refused, mirroring exchange minimums. |
| **Position sizing** | 95% of free cash per entry (`--alloc`), leaving room for the fee. |
| **Double runs** | Re-running inside the same candle is a no-op unless `--force` is passed. |
| **Candle count** | `--limit 100` by default. Because strategies 4 and 40 need SMA(200), the fetch is automatically widened to 205 with a logged warning when either is enabled. |

The engine maintains a hard accounting invariant, asserted by the test-suite:

```
equity == starting_balance + realized_pnl + unrealized_pnl − open_entry_fees
```

---

## CLI

```
python bot.py [options]

  --symbol BTC/USDT          market to trade
  --timeframe 15m            candle timeframe
  --limit 100                candles requested from the exchange
  --state docs/data.json     state file path
  --fee-rate 0.001           per-side fee as a fraction
  --slippage 0.0             adverse slippage per fill
  --alloc 0.95               fraction of cash used per entry
  --min-notional 10          minimum order notional (USDT)
  --max-trades-per-run 25    circuit breaker: stop filling after N orders per tick
  --stop-loss-pct / --take-profit-pct
                             optional global risk overlay (off by default)
  --param ID.key=value       override one strategy parameter
  --disable ID               skip a strategy (repeatable)
  --init                     create the state file and exit
  --reset --yes              wipe state and start every account fresh
  --dry-run                  evaluate and report without persisting
  --replay FILE.csv          offline: replay ts,o,h,l,c,v data instead of the exchange
  --force                    reprocess a candle already handled
```

Every option also has an environment-variable form (`BOT_SYMBOL`,
`BOT_FEE_RATE`, `BOT_STATE_PATH`, …) for use in CI.

**Examples**

```bash
# Retune a strategy without editing code
python bot.py --param 01_rsi_mean_reversion.rsi_buy=25 \
              --param 12_arithmetic_grid.step_pct=0.5

# Backtest against your own CSV of 15m candles
python bot.py --replay history.csv --reset --yes

# Run with a 2% stop-loss and 5% take-profit on every account
python bot.py --stop-loss-pct 2 --take-profit-pct 5
```

---

## GitHub Actions

Two workflows live in [`ci/workflows/`](ci/workflows):

| File | Trigger | Purpose |
|---|---|---|
| `paper-trade.yml` | `*/15 * * * *` + manual dispatch | run a tick, commit `docs/data.json` back, publish a summary table and an artifact |
| `tests.yml` | push / PR | run the offline test-suite on Python 3.10–3.12 |

They are kept out of `.github/workflows/` in the repository because committing
to that directory needs the `workflows` scope, which automated tokens usually
lack. **Activate them once, locally:**

```bash
./scripts/install-workflows.sh
git add .github/workflows && git commit -m "ci: enable workflows" && git push
```

Then:

1. Confirm **Settings → Actions → General → Workflow permissions** is set to
   *Read and write*, so the job can commit the updated state file.
2. Merge to your **default** branch — scheduled workflows only run there.
3. Optionally trigger a run by hand from the **Actions** tab.

A `concurrency` group prevents overlapping runs, and the bot's duplicate-candle
guard makes a late or repeated schedule harmless. Scheduled runs on GitHub can
be delayed under load — this affects cadence, not correctness.

---

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q          # 82 tests
python -m pyflakes bot.py tests/
```

The test-suite runs **entirely offline** against deterministic synthetic OHLCV,
driving the same `Engine.process_market` code path that a live run uses. It
covers indicator maths (including Wilder RSI, the Supertrend trailing-stop
ratchet property and StochRSI bounds), the broker's fee model and rejection
guards, FIFO lot accounting, the accounting invariant over long replays, atomic
persistence, and the CLI end-to-end.

`bot.py` is deliberately dependency-light: only `ccxt` at runtime, with all
indicators implemented in pure Python.

---

## Limitations

- **Paper trading only.** There is no order book, so fills assume the full
  candle range was tradable and ignore real depth, partial fills and latency.
- **Grid fills are optimistic.** A limit order is treated as filled whenever the
  candle's low/high reaches its level, which overstates fills in fast markets.
- **No funding, borrow or shorting.** This models spot only.
- **Exchange access.** Market data comes from **Kraken** (`api.kraken.com`),
  chosen because Binance's `api.binance.com` returns HTTP 451 to United States
  IP addresses and GitHub-hosted runners are US-based — a scheduled Binance tick
  would die at the data-fetch step. Swapping is a one-line change in
  `build_exchange()`; the engine only ever calls `fetch_ohlcv`, and
  `Engine.fetch_live(exchange=...)` accepts any client for testing.
- **Live connectivity is not covered by the test-suite.** The offline suite
  drives the real engine through a fake exchange, so exchange reachability and
  symbol availability are only exercised by an actual run.
- **Results depend on synthetic-free live data.** The test-suite verifies
  mechanics, not edge; a strategy that beats a seeded random walk here has no
  implied edge in the real market.
