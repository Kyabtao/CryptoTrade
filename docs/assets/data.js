/* CryptoTrade dashboard — shared data loading + formatting.
   Pages fetch the JSON state files (written by bot.py on every scheduled tick)
   so the UI always reflects the latest run with no build step. */

const CB = Date.now();

async function fetchJSON(url) {
  const sep = url.includes("?") ? "&" : "?";
  const res = await fetch(url + sep + "cb=" + CB, { cache: "no-store" });
  if (!res.ok) throw new Error("HTTP " + res.status + " for " + url);
  return res.json();
}

async function loadState() {
  return fetchJSON("data.json");
}

async function loadHistory() {
  try {
    return await fetchJSON("history.json");
  } catch (e) {
    return [];
  }
}

async function loadCatalog() {
  try {
    return await fetchJSON("assets/strategies.json");
  } catch (e) {
    return null;
  }
}

async function loadLessons() {
  try {
    return await fetchJSON("assets/lessons.json");
  } catch (e) {
    return null;
  }
}

async function loadIndicators() {
  try {
    return await fetchJSON("assets/indicators.json");
  } catch (e) {
    return null;
  }
}

async function loadCandles() {
  try {
    return await fetchJSON("candles.json");
  } catch (e) {
    return null;
  }
}

/* ---------- formatting helpers ---------- */

/* Escape a value before interpolating it into innerHTML. */
function esc(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const usdFmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2, minimumFractionDigits: 2 });
const usdFmt0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const numFmt = new Intl.NumberFormat("en-US");

function fmtUSD(v) { return v == null || isNaN(v) ? "—" : usdFmt.format(v); }
function fmtUSD0(v) { return v == null || isNaN(v) ? "—" : usdFmt0.format(v); }
function fmtNum(v, dp) {
  if (v == null || isNaN(v)) return "—";
  if (dp == null) return numFmt.format(v);
  return v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
}
function fmtPct(v, dp = 2) {
  if (v == null || isNaN(v)) return "—";
  const s = v.toFixed(dp);
  return (v > 0 ? "+" : "") + s + "%";
}
function fmtPrice(v) {
  if (v == null || isNaN(v)) return "—";
  if (v >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  if (v >= 1) return v.toLocaleString("en-US", { maximumFractionDigits: 4, minimumFractionDigits: 2 });
  return v.toLocaleString("en-US", { maximumFractionDigits: 8 });
}
function fmtQty(v) {
  if (v == null || isNaN(v)) return "—";
  if (Math.abs(v) < 0.0001 && v !== 0) return v.toExponential(4);
  return v.toLocaleString("en-US", { maximumFractionDigits: 6 });
}
function fmtTs(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
function fmtTsShort(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
function pctClass(v) { return v > 0 ? "pos" : (v < 0 ? "neg" : "neu"); }

/* ---------- account enrichment ---------- */

function enrichAccount(raw, price, startingBalance) {
  /* Equity = liquid cash + the market value of whatever crypto is held,
     marked at the last closed-candle price. */
  const cash = raw.balance_usd || 0;
  const marketValue = (raw.crypto_holdings || 0) * price;
  const equity = cash + marketValue;
  const base = raw.starting_balance || startingBalance || 1000;
  const returnPct = (equity / base - 1) * 100;
  const trades = raw.trades || [];
  const closed = trades.filter((t) => t.side === "sell");
  const wins = closed.filter((t) => (t.pnl || 0) > 0).length;
  const losses = closed.filter((t) => (t.pnl || 0) <= 0).length;
  const pnls = closed.map((t) => t.pnl || 0);
  const inPosition = (raw.crypto_holdings || 0) > 1e-8;
  return {
    id: raw.strategy_id,
    name: raw.name,
    raw,
    equity,
    returnPct,
    balance: cash,                 // liquid cash (USDT) sitting in the wallet
    marketValue,                   // value of crypto currently held in the market
    holdings: raw.crypto_holdings || 0,
    costBasis: (raw.lots || []).reduce((s, l) => s + (l.qty || 0) * (l.price || 0), 0),
    entryPrice: raw.entry_price,
    unrealizedPnl: raw.unrealized_pnl || 0,
    realizedPnl: raw.realized_pnl || 0,
    totalFees: raw.total_fees || 0,
    trades,
    tradesCount: trades.length,
    closed,
    closedCount: closed.length,
    wins,
    losses,
    winRate: closed.length ? (wins / closed.length) * 100 : 0,
    best: pnls.length ? Math.max(...pnls) : 0,
    worst: pnls.length ? Math.min(...pnls) : 0,
    inPosition,
    lots: raw.lots || [],
    strategyState: raw.strategy_state || {},
  };
}

function enrichState(state) {
  const meta = state.meta || {};
  const price = meta.last_price || 0;
  const starting = meta.starting_balance || 1000;
  const rawAccounts = state.accounts || {};
  const accounts = Object.keys(rawAccounts)
    .map((id) => enrichAccount(rawAccounts[id], price, starting))
    .sort((a, b) => a.id.localeCompare(b.id));
  const totalEquity = accounts.reduce((s, a) => s + a.equity, 0);
  const totalCash = accounts.reduce((s, a) => s + a.balance, 0);
  const totalMarketValue = accounts.reduce((s, a) => s + a.marketValue, 0);
  const totalHoldings = accounts.reduce((s, a) => s + a.holdings, 0);
  const totalCostBasis = accounts.reduce((s, a) => s + a.costBasis, 0);
  const totalUnrealized = accounts.reduce((s, a) => s + a.unrealizedPnl, 0);
  const totalRealized = accounts.reduce((s, a) => s + a.realizedPnl, 0);
  const totalFunded = accounts.reduce((s, a) => s + (a.raw.starting_balance || starting), 0);
  const totalReturnPct = (totalEquity / (totalFunded || accounts.length * starting || 1) - 1) * 100;
  const totalTrades = accounts.reduce((s, a) => s + a.tradesCount, 0);
  const totalFees = accounts.reduce((s, a) => s + a.totalFees, 0);
  const openCount = accounts.filter((a) => a.inPosition).length;
  const baseAsset = (meta.symbol || "BTC/USDT").split("/")[0];
  const quoteAsset = (meta.symbol || "BTC/USDT").split("/")[1] || "USDT";
  return {
    meta, price, starting, accounts,
    totalEquity, totalReturnPct, totalTrades, totalFees, openCount,
    // wallet breakdown: what is liquid vs. what is deployed in the market
    totalCash, totalMarketValue, totalHoldings, totalCostBasis,
    totalUnrealized, totalRealized, totalFunded,
    baseAsset, quoteAsset,
  };
}

/* category → colour for charts */
const CAT_COLORS = [
  "#3b82f6", "#22c55e", "#f59e0b", "#a78bfa", "#06b6d4",
  "#ef4444", "#ec4899", "#84cc16", "#f97316", "#14b8a6",
];
function categoryColor(cat, cats) {
  const idx = cats.indexOf(cat);
  return CAT_COLORS[idx >= 0 ? idx : cats.length % CAT_COLORS.length];
}
