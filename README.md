# CryptoTrade

A **paper-trading** engine that runs **12 isolated virtual sub-accounts**, each
executing a different trading strategy against the same candle stream. Every
account starts with **₹10,000** of virtual capital and is tracked independently
in [`docs/data.json`](docs/data.json).

Default market: **BTC/INR** on ZebPay, 15m candles. No real orders are ever
placed — fills are simulated against exchange OHLCV with a **0.1% fee deducted
on both sides**.

> Research and education only. This is not financial advice, and paper results
> do not transfer to live trading.

---

## Quick start

```bash
pip install -r requirements.txt          # only dependency: ccxt

python bot.py --init                     # create docs/data.json (12 x ₹10,000)
python bot.py                            # one tick against live BTC/INR data
python bot.py --symbol ETH/INR           # alternate INR market
python bot.py --dry-run                  # evaluate, print, write nothing
```

Each invocation is a single, stateless tick: read state → fetch candles →
evaluate all 12 strategies → write state back. That makes it safe to run from
cron or GitHub Actions.

---

## INR, exchanges, and an important caveat

**Binance has no INR spot order book** — INR on Binance is P2P only. A
`BTC/INR` request against `ccxt.binance()` therefore dies with `BadSymbol`.
The bot picks the venue from the quote currency instead:

| Quote | Default exchange | Why |
|---|---|---|
| `INR` | `zebpay` | FIU-registered, spot, 15m OHLCV |
| anything else | `binance` | deepest liquidity for USD-pegged pairs |

Override it with `--exchange`. Among the INR venues shipped in ccxt 4.5.76,
`zebpay`, `mudrex` and `delta` expose `fetchOHLCV` with a 15m timeframe;
`bitbns` does not expose OHLCV at all and cannot drive this bot. `wazirx` and
`coindcx` are not in that ccxt build.

Before fetching, the bot calls `load_markets()` and **validates the symbol**,
so a wrong pair fails immediately with the list of pairs that venue *does*
offer, rather than deep inside a network call:

```
RuntimeError: binance does not list BTC/INR. This exchange lists no INR spot
market (Binance INR is P2P only). Try --exchange zebpay, --exchange mudrex or
--exchange delta.
```

**Fees:** 0.1% is retained as the default because that is what this project
specifies, but note that Indian spot venues commonly charge more (ZebPay 0.45%,
WazirX 0.20%, CoinDCX 0.20–0.50%). Model your venue with `--fee-rate 0.0045`.

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

`docs/data.json` holds the whole portfolio. The cash key is named after the
quote currency, so an INR account reports `balance_inr` and never claims to
hold dollars:

```jsonc
{
  "meta": {
    "symbol": "BTC/INR", "quote_currency": "INR", "exchange": "zebpay",
    "starting_balance": 10000.0, "fee_rate": 0.001, "run_count": 128, ...
  },
  "accounts": {
    "01_rsi_mean_reversion": {
      "quote_currency": "INR",
      "balance_inr": 9469.00,        // free cash
      "crypto_holdings": 0.0000712,  // base-currency quantity
      "entry_price": null,           // weighted average of open lots
      "unrealized_pnl": 0.0,
      "realized_pnl": -531.00,
      "total_fees": 41.2,
      "lots": [ { "qty": ..., "price": ..., "fee": ... } ],
      "strategy_state": { ... },     // per-strategy memory (grid ladder, DCA counter)
      "trades": [
        {
          "timestamp": "2026-08-31T04:00:00Z",
          "side": "sell", "price": 9123456.0, "qty": 0.00104,
          "notional": 9488.4, "fee": 9.4884,
          "pnl": 210.5, "gross_pnl": 229.5,
          "exit_reason": "RSI(14)=74.31 > 70 (overbought)"
        }
      ]
    }
  }
}
```

State files written before the INR switch (which used `balance_usd`) still
load — the reader falls back to the legacy key instead of silently resetting an
account to zero.

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
| **Min order size** | Orders under ₹100 notional are refused, mirroring Indian spot venues. |
| **Position sizing** | 95% of free cash per entry (`--alloc`), leaving room for the fee. |
| **Double runs** | Re-running inside the same candle is a no-op unless `--force` is passed. |
| **Runaway loops** | `--max-trades-per-run` (default 25) trips a circuit breaker for the tick. |
| **Candle count** | `--limit 100` by default. Because strategy 4 needs SMA(200), the fetch is automatically widened to 205 with a logged warning when that strategy is enabled. |

The engine maintains a hard accounting invariant, asserted by the test-suite:

```
equity == starting_balance + realized_pnl + unrealized_pnl − open_entry_fees
```

---

## CLI

```
python bot.py [options]

  --symbol BTC/INR           market to trade
  --exchange zebpay          ccxt exchange id (auto-selected from the quote)
  --starting-balance 10000   virtual cash per account, in the quote currency
  --timeframe 15m            candle timeframe
  --limit 100                candles requested from the exchange
  --state docs/data.json     state file path
  --fee-rate 0.001           per-side fee as a fraction
  --slippage 0.0             adverse slippage per fill
  --alloc 0.95               fraction of cash used per entry
  --min-notional 100         minimum order notional, in the quote currency
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
`BOT_EXCHANGE`, `BOT_STARTING_BALANCE`, `BOT_FEE_RATE`, `BOT_STATE_PATH`, …)
for use in CI.

**Examples**

```bash
# Model ZebPay's real fee instead of the nominal 0.1%
python bot.py --fee-rate 0.0045

# Retune a strategy without editing code
python bot.py --param 01_rsi_mean_reversion.rsi_buy=25 \
              --param 12_arithmetic_grid.step_pct=0.5

# Backtest against your own CSV of 15m candles
python bot.py --replay history.csv --reset --yes

# Switch back to a USD venue (state schema follows automatically)
python bot.py --symbol BTC/USDT --exchange binance
```

---

## GitHub Actions

Two workflows live in [`ci/workflows/`](ci/workflows):

| File | Trigger | Purpose |
|---|---|---|
| `paper-trade.yml` | `*/15 * * * *` + manual dispatch | run a tick on BTC/INR, commit `docs/data.json` back, publish a summary table and an artifact |
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
python -m pytest tests/ -q          # 98 tests
python -m pyflakes bot.py tests/
```

The test-suite runs **entirely offline** against deterministic synthetic OHLCV,
driving the same `Engine.process_market` code path that a live run uses. It
covers indicator maths (including Wilder RSI, the Supertrend trailing-stop
ratchet property and StochRSI bounds), the broker's fee model and rejection
guards, FIFO lot accounting, the accounting invariant over long replays,
currency and exchange selection, atomic persistence, and the CLI end-to-end.

Synthetic prices in the tests are unit-agnostic; the mechanics are scale-free,
so the same suite guards both the ₹10,000 INR default and a USD run.

`bot.py` is deliberately dependency-light: only `ccxt` at runtime, with all
indicators implemented in pure Python.

---

## Limitations

- **Paper trading only.** There is no order book, so fills assume the full
  candle range was tradable and ignore real depth, partial fills and latency.
- **Grid fills are optimistic.** A limit order is treated as filled whenever the
  candle's low/high reaches its level, which overstates fills in fast markets.
- **Live INR data is unverified here.** The test environment has no network
  access, so `zebpay`'s actual `BTC/INR` symbol string and 15m availability
  have not been confirmed against the live API. If the first live run reports
  an unknown symbol, pass `--exchange mudrex` or check the error's suggestion
  list.
- **No funding, borrow or shorting.** This models spot only.
- **Results depend on live data, not the seeded series.** The test-suite
  verifies mechanics, not edge; a strategy that beats a synthetic random walk
  here has no implied edge in the real market.
