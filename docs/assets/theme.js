/* CryptoTrade dashboard — site-wide cream/dark theme.

   This file loads FIRST on every page (before data.js) so the saved palette
   is applied to <body> before anything renders or draws. The toggle button
   itself is rendered by renderNav() in layout.js (#siteThemeBtn); desk.html
   ships its own button bound to the same localStorage key ("siteTheme"), so
   the choice follows you across the whole site.

   Why pages need a helper at all: SVG presentation attributes do not support
   var(), so code that draws charts with concrete colours calls siteInk() at
   draw time to pick ink/dim for the active palette. Toggling also dispatches
   a resize event — chart pages redraw themselves from their existing
   debounced resize handlers, which re-resolve every colour. */
(function () {
  let cream = false;
  try { cream = localStorage.getItem("siteTheme") === "cream"; } catch (e) { /* private mode */ }

  function apply() {
    document.body.classList.toggle("theme-cream", cream);
  }
  apply();

  /* Ink colours for SVG-drawing code; call at draw time, not at load time. */
  window.siteInk = function () {
    return cream ? { text: "#141414", dim: "#56564f" } : { text: "#e6eaf2", dim: "#97a1b5" };
  };

  window.siteSetTheme = function (on) {
    cream = !!on;
    try { localStorage.setItem("siteTheme", cream ? "cream" : "dark"); } catch (e) { /* ignore */ }
    apply();
    const btn = document.getElementById("siteThemeBtn");
    if (btn) {
      btn.textContent = cream ? "🌙" : "☀";
      btn.setAttribute("aria-pressed", String(cream));
      btn.title = cream ? "Switch to dark" : "Switch to cream";
    }
    /* chart pages redraw from their debounced resize handlers */
    window.dispatchEvent(new Event("resize"));
  };

  function wire() {
    const btn = document.getElementById("siteThemeBtn");
    if (!btn) return;
    btn.textContent = cream ? "🌙" : "☀";
    btn.setAttribute("aria-pressed", String(cream));
    btn.title = cream ? "Switch to dark" : "Switch to cream";
    btn.addEventListener("click", () => window.siteSetTheme(!cream));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();
})();
