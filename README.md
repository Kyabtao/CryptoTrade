# CryptoTrade

A **paper-trading** engine that runs **12 isolated virtual sub-accounts**, each
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

python bot.py --init                     # create docs/data.json (12 x $1,000)
python bot.py                            # one tick against live Binance data
python bot.py --symbol ETH/USDT          # alternate market
python bot.py --dry-run                  # evaluate, print, write nothing
```

Each invocation is a single, stateless tick: read state → fetch candles →
evaluate all 12 strategies → write state back. That makes it safe to run from
cron or GitHub Actions.

---

## The 12 strategies

| # | Account id | Strategy | Entry | Exit |
|---|---|---|---|---|
| 1 | `01_rsi_mean_reversion` | RSI Mean Reversion | RSI(14) < 30 | RSI(14) > 70 |
| 2 | `02_dual_ema_crossover` | Dual EMA Crossover | EMA9 crosses above EMA21 | EMA9 crosses below EMA21 |
| 3 | `03_macd_histogram_reversal` | MACD Signal Crossover | MACD crosses above Signal | MACD crosses below Signal |
| 4 | `04_triple_moving_average` | Triple MA Trend | SMA20 > SMA50 > SMA200 | SMA20 < SMA50 |
| 5 | `05_supertrend_atr` | Supertrend Trailing Stop | ATR(10, ×3) flips bullish | flips bearish / stop breached |
| 6 | `06_bollinger_mean_reversion` | Bollinger Mean Reversion | close < Lower Band (20, 2) | close reaches Middle Band |
| 7 | `07_keltner_breakout` | Keltner Breakout | close > EMA20 + 2·ATR | close falls below EMA20 |
| 8 | `08_stoch_rsi_reversal` | Stochastic RSI | %K crosses above %D below 20 | %K crosses below %D above 80 |
| 9 | `09_vwap_pullback` | Session VWAP Pullback | close < VWAP and RSI > 40 | close ≥ VWAP + 1.5% |
| 10 | `10_donchian_breakout` | Donchian Turtle | close breaks the 20-candle high | close breaks the 10-candle low |
| 11 | `11_dynamic_dca` | Dynamic DCA | every 4th candle, ×2 if 24h is red | *(accumulates; optional take-profit)* |
| 12 | `12_arithmetic_grid` | Fixed-Step Arithmetic Grid | limit buys each 1% step down | take-profit one step up |

Strategies 1–10 follow a **single-position model**: a buy is refused while a
position is open. Strategies 11 and 12 are the documented exceptions and may
hold many lots at once (tracked FIFO).

---

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
| **Min order size** | Orders under 10 USDT notional are refused, mirroring Binance spot. |
| **Position sizing** | 95% of free cash per entry (`--alloc`), leaving room for the fee. |
| **Double runs** | Re-running inside the same candle is a no-op unless `--force` is passed. |
| **Candle count** | `--limit 100` by default. Because strategy 4 needs SMA(200), the fetch is automatically widened to 205 with a logged warning when that strategy is enabled. |

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
- **Results depend on synthetic-free live data.** The test-suite verifies
  mechanics, not edge; a strategy that beats a seeded random walk here has no
  implied edge in the real market.
