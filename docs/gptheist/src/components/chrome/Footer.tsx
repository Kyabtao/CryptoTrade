/**
 * Footer: the mandatory SIMULATED DATA badge plus a quiet link back to the
 * parent CryptoTrade dashboard. Kept out of the header so the desk's top bar
 * stays pixel-faithful to the reference.
 */
export function Footer() {
  return (
    <footer className="col-span-12 flex flex-wrap items-center gap-x-4 gap-y-2 px-1 pb-2 pt-1">
      <span className="inline-flex items-center gap-2 rounded-full border border-amber/40 bg-amber/10 px-3 py-1">
        <span aria-hidden="true" className="size-1.5 rounded-full bg-amber" />
        <span className="num text-[10px] font-semibold tracking-[0.12em] text-amber">
          SIMULATED DATA
        </span>
      </span>
      <span className="label num text-[9px] text-faint">
        no exchange, wallet or market API is contacted — all figures are generated locally
      </span>
      <a
        href="../../index.html"
        className="num ml-auto text-[11px] font-semibold text-info underline-offset-2 hover:underline"
      >
        ← CryptoTrade dashboard
      </a>
    </footer>
  );
}
