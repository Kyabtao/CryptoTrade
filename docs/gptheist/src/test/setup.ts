import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';

// jsdom ships no matchMedia; the reduced-motion hook needs a stub.
if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  const noop = () => undefined;
  const stub = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: noop,
      removeEventListener: noop,
      addListener: noop,
      removeListener: noop,
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
  Object.defineProperty(window, 'matchMedia', { writable: true, value: stub });
}

// Each test should start from an empty document; Vitest's jsdom environment
// does not unmount React trees between cases on its own.
afterEach(() => {
  cleanup();
});
