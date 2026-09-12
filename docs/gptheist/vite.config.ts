import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// `base: './'` keeps every emitted URL relative, so the built bundle works both
// from a local static server and from GitHub Pages under
// /<repo>/gptheist/dist/ without any path rewriting.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // D3 pulls in a few modules that are tree-shaken away; keep the chunk graph
    // simple so the whole app stays in one small bundle (target < 400 kB gz).
    chunkSizeWarningLimit: 400,
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: false,
    // The app is viewed through a reverse proxy on an unfamiliar hostname;
    // without this Vite answers "Blocked request. This host is not allowed."
    allowedHosts: true,
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false,
    restoreMocks: true,
  },
});
