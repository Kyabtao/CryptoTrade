import { useEffect } from 'react';
import { Header } from './components/chrome/Header';
import { Footer } from './components/chrome/Footer';
import { KpiStrip } from './components/panels/KpiStrip';
import { BalanceHistoryPanel } from './components/panels/BalanceHistoryPanel';
import { ActivityLogPanel } from './components/panels/ActivityLogPanel';
import { RidgePanel } from './components/panels/RidgePanel';
import { ChordPanel } from './components/panels/ChordPanel';
import { LatticePanel } from './components/panels/LatticePanel';
import { RelationshipPanel } from './components/panels/RelationshipPanel';
import { RosterStrip } from './components/panels/RosterStrip';
import { deskStore, startEngine } from './store/deskStore';

/**
 * GPTHEIST DESK — application root.
 *
 * The 12-column shell is laid out exactly as the reference arranges it. The
 * SimulationEngine (Zustand store driven at 1 Hz) makes the clock, balance and
 * activity log live; visualisation milestones fill the remaining bodies.
 */
function App() {
  // 1 Hz engine; StrictMode's double-invocation is safe because the returned
  // stop function clears the interval on unmount.
  useEffect(() => startEngine(deskStore), []);

  return (
    <div className="min-h-screen bg-canvas">
      <a
        href="#desk-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-chip focus:border focus:border-hairline focus:bg-card focus:px-3 focus:py-1 focus:text-xs focus:text-ink"
      >
        Skip to content
      </a>
      <main id="desk-main" className="mx-auto grid max-w-[1600px] grid-cols-12 gap-4 px-4 py-4">
        <Header />
        <KpiStrip />
        <BalanceHistoryPanel />
        <ActivityLogPanel />
        <RidgePanel />
        <ChordPanel />
        <LatticePanel />
        <RelationshipPanel />
        <RosterStrip />
        <Footer />
      </main>
    </div>
  );
}

export default App;
