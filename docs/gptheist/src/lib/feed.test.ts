import { describe, expect, it, vi } from 'vitest';
import { createDeskStore } from '../store/deskStore';
import { createSimFeed } from './feed';

describe('createSimFeed', () => {
  it('emits clock updates on tick and stops after unsubscribe', () => {
    const store = createDeskStore(3);
    const feed = createSimFeed(store);
    const onClock = vi.fn();

    const unsub = feed.subscribe('clock', onClock);
    store.getState().tick();
    expect(onClock).toHaveBeenCalledTimes(1);

    unsub();
    store.getState().tick();
    expect(onClock).toHaveBeenCalledTimes(1);
  });

  it('emits a new event payload when the log grows', () => {
    const store = createDeskStore(3);
    const feed = createSimFeed(store);
    const onEvent = vi.fn();
    feed.subscribe('events', onEvent);

    const wait = store.getState().nextEventIn;
    for (let i = 0; i < wait; i += 1) store.getState().tick();

    expect(onEvent).toHaveBeenCalledTimes(1);
    const payload = onEvent.mock.calls[0]?.[0] as { code?: string } | null;
    expect(payload).not.toBeNull();
  });

  it('does not emit when the watched slice is unchanged', () => {
    const store = createDeskStore(3);
    const feed = createSimFeed(store);
    const onHandoffs = vi.fn();
    feed.subscribe('handoffs', onHandoffs);

    // A tick that does not produce an event leaves handoffs untouched.
    if (store.getState().nextEventIn > 1) store.getState().tick();
    expect(onHandoffs).not.toHaveBeenCalled();
  });
});
