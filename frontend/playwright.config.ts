import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for whisperx frontend e2e suite.
 *
 * Covers Phase 15 manual UAT items 1-5 (responsive, dialogs, cross-tab,
 * design parity). Real backend NOT required — all `/api/*`, `/auth/*`,
 * `/billing/*` calls intercepted via `page.route()` in fixtures/specs.
 *
 * Dev server: `bun run dev` -> Vite at http://localhost:5173, base path /ui.
 * Single worker locally to avoid port races; CI inherits.
 */
// Force IPv4 host. Port chosen above Windows' default Hyper-V TCP exclusion
// range (5173-5272) — Vite's `EACCES` there blocks the dev server even when
// the port is otherwise unused. Verify with:
//   netsh interface ipv4 show excludedportrange protocol=tcp
const HOST = '127.0.0.1';
const PORT = 5273;
// Trailing slash REQUIRED — Vite's `base: '/ui/'` returns 404 on bare `/ui`.
const BASE_URL = `http://${HOST}:${PORT}/ui/`;

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : [['list']],

  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    video: 'off',
    screenshot: 'off',
  },

  projects: [
    {
      name: 'chromium',
      testIgnore: ['**/phase19/**'],
      use: { ...devices['Desktop Chrome'] },
    },
    {
      // Phase 19 verification specs hit the REAL backend on :8000 via the
      // Vite proxy (no page.route mocks). Requires `uvicorn app.main:app`
      // running on http://localhost:8000 BEFORE `bun run test:e2e`.
      name: 'phase19-real-backend',
      testMatch: ['**/phase19/**/*.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: `bun run dev -- --host ${HOST} --port ${PORT} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
