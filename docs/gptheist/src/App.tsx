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

/**
 * GPTHEIST DESK — application root.
 *
 * Milestone 2 lays the full 12-column shell exactly as the reference arranges
 * it: header, KPI strip, then rows 2-5 and the roster strip. Panel bodies are
 * placeholders; each visualisation milestone fills one in.
 */
function App() {
  return (
    <div className="min-h-screen bg-canvas">
      <main className="mx-auto grid max-w-[1600px] grid-cols-12 gap-4 px-4 py-4">
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
