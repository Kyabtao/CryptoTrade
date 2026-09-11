import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';

// Each test should start from an empty document; Vitest's jsdom environment
// does not unmount React trees between cases on its own.
afterEach(() => {
  cleanup();
});
