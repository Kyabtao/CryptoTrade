/* CryptoTrade dashboard — shared chrome (nav + update message).

   The navigation bar is now purely navigation: the "last update" details that
   used to live inside it are rendered as a dismissible message strip at the top
   of the page body instead (see renderUpdateMessage). */

const BOT = {
  name: "Umair’s Bot",
  handle: "@umairs_bot",
  tagline: "Systematic paper trader · 42 strategies, one candle at a time",
  initials: "UB",
};

const NAV_ITEMS = [
  { href: "index.html", label: "Dashboard" },
  { href: "strategies.html", label: "Strategies" },
  { href: "learn.html", label: "Learn" },
  { href: "market.html", label: "Market" },
  { href: "compare.html", label: "Compare" },
  { href: "portfolio.html", label: "Portfolio" },
  { href: "analytics.html", label: "Analytics" },
  { href: "risk.html", label: "Risk" },
  { href: "trades.html", label: "Trades" },
  { href: "profile.html", label: "Profile" },
];

/* Render the top navigation. `active` is the current file name.

   Layout notes (see style.css):
   - desktop: one row — brand · links · identity chip
   - tablet (≤1100px): the links drop to a second, full-width row so every
     page stays reachable without hidden horizontal scrolling
   - phone (≤760px): the links become a fixed bottom tab bar. The blurred
     backdrop lives on `.nav::before` (not on `.nav` itself) because a
     `backdrop-filter` element becomes the containing block for `position:
     fixed` descendants — putting it on `.nav` pinned the "bottom" bar inside
     the 58px header. */
function renderNav(active) {
  const links = NAV_ITEMS.map(
    (n) => `<a href="${n.href}"${n.href === active ? ' class="active" aria-current="page"' : ""}>${n.label}</a>`
  ).join("");
  document.write(`
  <nav class="nav" id="siteNav">
    <div class="nav-inner">
      <a class="brand" href="index.html"><span class="logo">₿</span> CryptoTrade</a>
      <div class="nav-links" id="navLinks" aria-label="Primary navigation">${links}</div>
      <a class="nav-who" href="profile.html" title="Bot profile &amp; account rules">
        <span class="avatar">${BOT.initials}</span>
        <span class="who-text"><b>${BOT.name}</b><span class="hide-sm">${BOT.handle}</span></span>
      </a>
    </div>
  </nav>
  <div id="updateMessage"></div>`);
  document.addEventListener("DOMContentLoaded", initNavChrome);
}

/* Keep `--nav-h` (used by sticky table headers, scroll-padding and the basics
   TOC) equal to the real rendered height of the header, and make sure the
   active link is visible when the link strip has to scroll. */
function initNavChrome() {
  const nav = document.getElementById("siteNav");
  const links = document.getElementById("navLinks");
  if (!nav) return;
  const setH = () => document.documentElement.style.setProperty("--nav-h", nav.offsetHeight + "px");
  setH();
  if (window.ResizeObserver) new ResizeObserver(setH).observe(nav);
  else window.addEventListener("resize", setH);

  const act = links && links.querySelector("a.active");
  if (act && links.scrollWidth > links.clientWidth + 2) {
    const target = act.offsetLeft - (links.clientWidth - act.offsetWidth) / 2;
    links.scrollLeft = Math.max(0, target);
  }
}

/* The "last update" details, as a message rather than a nav item. */
function renderUpdateMessage(meta, extra) {
  const host = document.getElementById("updateMessage");
  if (!host) return;
  const updated = meta.updated_at ? new Date(meta.updated_at) : null;
  const ageMin = updated ? Math.max(0, Math.round((Date.now() - updated.getTime()) / 60000)) : null;
  const fresh = ageMin != null && ageMin <= 45;
  const candle = meta.last_candle_ts ? new Date(meta.last_candle_ts) : null;

  host.innerHTML = `
    <div class="wrap">
      <div class="msg ${fresh ? "ok" : "warn"}" id="updateMsg">
        <span class="msg-dot"></span>
        <div class="msg-body">
          <div class="msg-title">
            ${fresh ? "State is up to date" : "State may be stale"} —
            last update <b>${fmtTs(meta.updated_at)}</b>
            ${ageMin != null ? `<span class="mini">(${ageMin < 1 ? "just now" : ageMin + " min ago"})</span>` : ""}
          </div>
          <div class="msg-sub">
            Run <b>#${meta.run_count ?? "—"}</b> ·
            ${esc(meta.symbol || "—")} <b>${meta.timeframe || ""}</b> candles ·
            last closed candle <b>${candle ? fmtTs(candle.toISOString()) : "—"}</b> ·
            last price <b class="num">${fmtPrice(meta.last_price)}</b> ·
            bot v${esc(meta.bot_version || "?")}
            ${extra ? " · " + extra : ""}
          </div>
        </div>
        <button class="msg-x" onclick="this.closest('.msg').remove()" title="Dismiss">✕</button>
      </div>
    </div>`;
}

/* Small helper shared by several pages. */
function pageHero(title, sub) {
  return `<div class="hero"><div><h1>${esc(title)}</h1><div class="sub">${sub}</div></div></div>`;
}

/* ---------- balance / capital breakdown (shared by profile + drawers) ----------
   Splits an equity figure into the part sitting as cash (liquid, available
   to trade) and the part held in the market (crypto at the last price).
   `x` may be an enriched account or the enriched portfolio (enrichState). */
function balanceBar(x, opts = {}) {
  const cash = x.totalCash != null ? x.totalCash : x.balance || 0;
  const mkt = x.totalMarketValue != null ? x.totalMarketValue : x.marketValue || 0;
  const total = cash + mkt;
  const pctMkt = total > 0 ? (mkt / total) * 100 : 0;
  const pctCash = total > 0 ? 100 - pctMkt : 0;
  const asset = opts.asset || "crypto";
  return `
    <div class="balbar" role="img" aria-label="${pctCash.toFixed(0)}% cash, ${pctMkt.toFixed(0)}% in market">
      <span class="seg cash" style="width:${pctCash.toFixed(2)}%"></span>
      <span class="seg mkt" style="width:${pctMkt.toFixed(2)}%"></span>
    </div>
    <div class="balbar-legend">
      <span><i class="sw cash"></i> Liquid cash <b class="num">${fmtUSD(cash)}</b> <span class="mini">(${pctCash.toFixed(1)}%)</span></span>
      <span><i class="sw mkt"></i> In market (${esc(asset)}) <b class="num">${fmtUSD(mkt)}</b> <span class="mini">(${pctMkt.toFixed(1)}%)</span></span>
    </div>`;
}
