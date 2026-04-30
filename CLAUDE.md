# whisperx — Project Conventions (Single Source of Truth)

This file is read at the start of every Claude Code session. It documents
locked project conventions. Override anything here only with explicit user
sign-off.

## Stack

- **Backend:** FastAPI (Python 3.12, `uv` for venv) — `app/`
- **Frontend:** Vite + React 19 + TypeScript — `frontend/`
- **DB:** SQLite (dev) via Alembic migrations — `alembic/`
- **Tests:** pytest (backend), vitest + playwright (frontend)

## Package Manager — frontend is **bun-only**

Use `bun` for installs / scripts. Do NOT introduce `npm`, `yarn`, or `pnpm`
artifacts (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`). Lockfile is
`bun.lock`.

Common commands (always `cd frontend && ...`):

| Command | Purpose |
| --- | --- |
| `bun install` | Install deps |
| `bun add <pkg>` | Add runtime dep |
| `bun add -D <pkg>` | Add devDep |
| `bun run dev` | Vite dev server (port 5173, base `/ui`) |
| `bun run build` | tsc + vite build |
| `bun run lint` | eslint |
| `bun run test` | Vitest run (unit + integration in jsdom) |
| `bun run test:watch` | Vitest watch |
| `bun run test:e2e` | Playwright e2e (auto-starts dev server) |
| `bun run test:e2e:ui` | Playwright UI mode |

## Test Strategy — Three Tiers

### 1. Unit + Integration (Vitest + RTL + jsdom + MSW)

- Location: `frontend/src/**/*.test.ts` / `*.test.tsx`
- Runner: `bun run test`
- Backend mocking: MSW handlers in `frontend/src/tests/msw/`
- Coverage: components, hooks, stores, api wrappers, MSW-backed integration

### 2. End-to-end (Playwright + Chromium)

- Location: `frontend/e2e/<feature>/<NN>-<spec-name>.spec.ts`
- Runner: `bun run test:e2e` (auto-starts `bun run dev` via `webServer`)
- Backend mocking: `page.route().fulfill()` — no real backend hit
- Shared fixtures: `frontend/e2e/_fixtures/`
  - `auth.ts` — `signedInPage` fixture (mocks `/api/account/me`, seeds csrf cookie)
  - `mocks.ts` — per-endpoint route mock helpers (SRP, composable)
- Screenshots: `frontend/e2e/screenshots/<spec>/<step>.png` (gitignored, regen each run)
- Why Playwright: viewport/responsive layout, focus traps, BroadcastChannel
  cross-tab, real `setTimeout` wall-clock — none of which jsdom faithfully
  simulates. RTL covers logic; Playwright covers browser-only behaviour.

**Phase 15 e2e suite covers manual UAT items 1-5 from
`.planning/phases/15-account-dashboard-hardening-billing-stubs/15-VERIFICATION.md`:**

| Spec | UAT | Coverage |
| --- | --- | --- |
| `01-responsive.spec.ts` | 1 | Account page renders 375 / 768 / 1280 |
| `02-upgrade-dialog.spec.ts` | 2 | 501-swallow + 2s auto-close |
| `03-delete-account.spec.ts` | 3 | Type-email gate + redirect to `/login` |
| `04-logout-all-cross-tab.spec.ts` | 4 | BroadcastChannel('auth') propagation |
| `05-design-parity.spec.ts` | 5 | Account vs keys side-by-side at 1280 |

### 3. Backend (pytest)

- Location: `tests/unit/` and `tests/integration/`
- Runner: `uv run pytest`

## Code Quality (locked policies)

- **DRY** — single source of truth per concept. apiClient is the SOLE non-WS
  network entry (UI-11). Auth state lives only in `authStore`.
- **SRP** — page = orchestrator; api wrapper = transport; store = state;
  dialog = own form/confirm state machine.
- **Tiger-style** — assert at boundaries (page state BEFORE action, after).
- **No nested-if spaghetti** — early-return / early-throw.
- **Self-explanatory names** — `signedInPage`, `tabA`, `tabB`,
  `mockAccountSummary`, not `p`, `t1`, `mock1`.
- **Subtype-first error handling** — `RateLimitError` matched BEFORE
  `ApiClientError` (the former extends the latter; reverse breaks the
  rate-limit branch silently).

## File-Path Layout (key dirs only)

```
whisperx/
├── app/                              FastAPI backend
├── tests/                            pytest backend tests
├── frontend/
│   ├── src/
│   │   ├── components/               UI components
│   │   ├── routes/                   Page-level components + AppRouter + RequireAuth
│   │   ├── lib/
│   │   │   ├── apiClient.ts          SOLE HTTP entry (UI-11)
│   │   │   ├── api/                  Typed wrappers per resource (accountApi, keysApi, …)
│   │   │   └── stores/               Zustand stores (authStore, …)
│   │   └── tests/msw/                MSW handlers + barrel
│   ├── e2e/
│   │   ├── _fixtures/                auth + mocks (shared)
│   │   ├── account-page/             UAT 1-5 specs
│   │   └── screenshots/              gitignored, regen each run
│   ├── playwright.config.ts
│   └── package.json
└── .planning/                        gsd-* phase artefacts (CONTEXT, PLAN, SUMMARY, VERIFICATION)
```

## Conventions Cheat-Sheet

- Cookies: server-set HttpOnly session + non-HttpOnly csrf_token. apiClient
  attaches `X-CSRF-Token` on POST/PUT/PATCH/DELETE automatically.
- 401 handling: apiClient redirects to `/login?next=<currentUrl>` UNLESS
  `suppress401Redirect: true` is passed (used by `authStore.refresh()` boot
  probe, `accountApi.fetchAccountSummary`).
- 429 handling: `RateLimitError` thrown — caller renders inline countdown.
- Cross-tab auth sync: `BroadcastChannel('auth')` — `{type: 'login'|'logout'}`.
- Auto-close timer: dialogs use `setTimeout(close, 2000)` — Vitest spies the
  callback, Playwright asserts the wall-clock window.
