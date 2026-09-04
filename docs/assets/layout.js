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

/* Render the top navigation. `active` is the current file name. */
function renderNav(active) {
  const links = NAV_ITEMS.map(
    (n) => `<a href="${n.href}"${n.href === active ? ' class="active"' : ""}>${n.label}</a>`
  ).join("");
  document.write(`
  <nav class="nav">
    <div class="nav-inner">
      <a class="brand" href="index.html"><span class="logo">₿</span> CryptoTrade</a>
      <div class="nav-links" aria-label="Primary navigation">${links}</div>
      <a class="nav-who" href="profile.html" title="Bot profile &amp; account rules">
        <span class="avatar">${BOT.initials}</span>
        <span class="who-text"><b>${BOT.name}</b><span class="hide-sm">${BOT.handle}</span></span>
      </a>
    </div>
  </nav>
  <div id="updateMessage"></div>`);
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
