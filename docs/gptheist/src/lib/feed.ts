import type { StoreApi } from 'zustand/vanilla';
import type { DeskState } from '../store/deskStore';

/**
 * DeskFeed — the seam between the desk and its data source.
 *
 * The shipped bundle never talks to the network; the SimulationEngine pushes
 * into the store and `createSimFeed` adapts the store to this interface. To go
 * live, implement `DeskFeed` over a WebSocket (or any push transport) and hand
 * it to the bootstrap instead — nothing else in the app needs to change:
 *
 *   class WebSocketDeskFeed implements DeskFeed {
 *     subscribe(topic, cb) {
 *       const onMsg = (e: MessageEvent) => { ... cb(parsed) ... };
 *       this.ws.addEventListener('message', onMsg);
 *       this.ws.send(JSON.stringify({ subscribe: topic }));
 *       return () => this.ws.removeEventListener('message', onMsg);
 *     }
 *   }
 */

export type DeskTopic = 'balance' | 'events' | 'clock' | 'handoffs';

export type DeskFeed = {
  /**
   * Observe one topic. Returns an unsubscribe function. Handlers receive the
   * latest payload whenever it changes.
   */
  subscribe: (topic: DeskTopic, cb: (payload: unknown) => void) => () => void;
};

/** Adapt the local simulation store to the DeskFeed interface. */
export function createSimFeed(store: StoreApi<DeskState>): DeskFeed {
  const select = (topic: DeskTopic, s: DeskState): unknown => {
    switch (topic) {
      case 'balance':
        return s.balanceEth;
      case 'events':
        return s.events[0] ?? null;
      case 'clock':
        return s.wallMin;
      case 'handoffs':
        return s.handoffs;
    }
  };

  return {
    subscribe(topic, cb) {
      let prev = select(topic, store.getState());
      return store.subscribe((state) => {
        const next = select(topic, state);
        if (next !== prev) {
          prev = next;
          cb(next);
        }
      });
    },
  };
}
