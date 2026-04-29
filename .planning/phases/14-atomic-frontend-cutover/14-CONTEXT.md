# Phase 14: Atomic Frontend Cutover + Test Infra - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning
**Mode:** Auto-generated (decisions locked in STATE.md from milestone discuss)
**Atomic Pair:** Phase 14 frontend MUST deploy in lockstep with Phase 13 backend.

<domain>
## Phase Boundary

Browser users land on a working auth shell — login/register/dashboard/keys/usage flows all functional, existing transcription UI preserved at `/`, all network calls flow through the central client. Vitest+RTL+MSW infrastructure verifies critical flows.

In scope:
- Router shell using `react-router-dom` v7 (already in deps): `<BrowserRouter basename="/ui">` with routes `/`, `/login`, `/register`, `/dashboard/keys`, `/dashboard/usage`, `/dashboard/account` (placeholder for Phase 15)
- `<TranscribePage>` route at `/` renders the existing UploadDropzone + FileQueueList + ConnectionStatus components VERBATIM (move, don't rewrite)
- Login page (email + password + react-hook-form + zod validation + shadcn `<Form>` styling + submit-disabled-while-loading)
- Register page (email + password + password-confirm + terms checkbox + zxcvbn-style password strength meter)
- After login/register → redirect to `?next=` URL or `/`
- `/dashboard/keys` page: lists keys (name/prefix/created_at/last_used_at/status); create-key modal that shows raw key ONCE with copy-to-clipboard; revoke confirmation modal
- `/dashboard/usage` page: current-hour quota counter + daily-minutes counter + trial countdown badge ("Trial: X days left" or "Trial not started" before first key)
- Central `frontend/src/lib/apiClient.ts` wrapper:
  - Auto-attaches `credentials: 'include'`
  - Auto-attaches `X-CSRF-Token` header (read from `csrf_token` cookie via `document.cookie`)
  - 401 → redirect to `/login?next=<currentUrl>`
  - 429 → surface inline error with Retry-After countdown (no toast spam)
- Zustand auth store (login/logout/user state) — add `zustand` dep
- `BroadcastChannel('auth')` synchronizes login/logout state across browser tabs
- Vitest 3.2 + jsdom + @testing-library/react 16 + @testing-library/user-event 14 + @testing-library/jest-dom 6 + MSW 2.13
- Test setup: `frontend/src/tests/setup.ts` + MSW handlers `frontend/src/tests/msw/handlers.ts` + worker init in `frontend/public/`
- Tests cover: apiClient 401 redirect, login form validation + happy path, register form validation, API key creation flow (show-once + copy), authStore login/logout, BroadcastChannel cross-tab sync; regression smoke for upload/transcribe/progress/export
- Built behind same `AUTH_V2_ENABLED` flag as backend — frontend bundles route registrations conditionally on a feature flag (or simply ships both since UI is read by user)

Out of scope (deferred):
- AUTH-06 logout-all-devices UI button — Phase 15
- SCOPE-06 type-email-confirmation full account delete — Phase 15
- BILL-05/06 checkout/webhook UI — Phase 15
- UI-07 Account dashboard polish (plan_tier card, upgrade-to-pro CTA, delete-account flow) — Phase 15
- Cross-user matrix tests (already on backend) — Phase 16
- Migration runbook docs — Phase 17

</domain>

<decisions>
## Implementation Decisions

(Locked from STATE.md "v1.2 entry decisions".)

### Router & Layout

- `react-router-dom` v7 (already a dep)
- `<BrowserRouter basename="/ui">`
- Routes:
  - `/` → `<TranscribePage>` (existing UploadDropzone + FileQueueList + ConnectionStatus)
  - `/login` → `<LoginPage>`
  - `/register` → `<RegisterPage>`
  - `/dashboard/keys` → `<KeysDashboardPage>`
  - `/dashboard/usage` → `<UsageDashboardPage>`
  - `/dashboard/account` → placeholder `<AccountStubPage>` (Phase 15 fills in)
- Auth-required routes wrapped in `<RequireAuth>` HOC that redirects to `/login?next=<currentUrl>` if `authStore.user === null`
- Public routes: `/login`, `/register`

### Forms (UI-02, UI-03)

- Library: `react-hook-form` (add dep)
- Validation: `zod` (add dep) + `@hookform/resolvers` (add dep)
- Styling: shadcn/ui (already partially in via clsx, tailwind-merge, class-variance-authority, radix primitives)
- Submit-disabled-while-loading via `formState.isSubmitting`
- Generic non-enumerating error messages on login (matches backend Phase 13)
- Password strength meter on register: roll-our-own zxcvbn-style heuristic (no external library required) — score from regex/length checks (8/12/16 chars; mixed case; digits; symbols)
- Terms-of-service checkbox required to enable submit on register

### Central API Client (UI-11)

- File: `frontend/src/lib/apiClient.ts`
- Wraps `fetch()`:
  - `credentials: 'include'` (cookie session)
  - Auto-attaches `X-CSRF-Token` header by reading `csrf_token` cookie via `document.cookie` parser
  - On 401: `window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname + window.location.search)`
  - On 429: extracts `Retry-After` header; surfaces error with countdown (use shadcn `<Alert>` or sonner toast — but only ONE per request, not spam)
  - Throws typed errors on 4xx/5xx (not 401/429 which redirect/inline-handle)
- Existing `frontend/src/lib/api/*` and `frontend/src/lib/upload/*` modules are refactored to USE apiClient (no direct fetch)
- WebSocket helper wraps WS connection: requests ticket via `apiClient.post('/api/ws/ticket', {task_id})`, then opens `ws://...?ticket=<token>` (UI-11 scope)

### Auth Store (Zustand)

- Add `zustand` dep
- Store: `frontend/src/lib/stores/authStore.ts`
- State: `{ user: { id, email, plan_tier } | null, login(creds), logout(), refresh() }`
- `login(creds)`: calls apiClient.post('/auth/login', creds) → sets user state → broadcast `'auth'` channel
- `logout()`: calls apiClient.post('/auth/logout') → clears user → broadcast `'auth'` channel → redirect to `/login`
- `BroadcastChannel('auth')` listener in store init; on remote logout, clear local user
- Initial state hydration: on mount, attempt `apiClient.get('/api/account/me')` (or call /api/keys with cookie — backend returns 401 if not auth'd)

### CSRF Cookie Read

- Cookies are non-httpOnly for csrf_token (intentional — frontend needs to read it)
- `frontend/src/lib/cookies.ts` helper: `readCookie(name: string): string | null` parses `document.cookie`
- apiClient calls this on every request to attach `X-CSRF-Token` header

### Test Infrastructure (TEST-01..06)

- Add devDeps:
  - `vitest@^3.2`
  - `jsdom@^25` (for browser env)
  - `@testing-library/react@^16.1`
  - `@testing-library/user-event@^14.6`
  - `@testing-library/jest-dom@^6.6`
  - `msw@^2.13`
- `frontend/vitest.config.ts` — `environment: 'jsdom'`, `setupFiles: ['./src/tests/setup.ts']`, `globals: true`
- `frontend/src/tests/setup.ts` — imports `@testing-library/jest-dom/vitest`; starts MSW worker; cleanup on each test
- `frontend/src/tests/msw/handlers.ts` — handlers for `/auth/*`, `/api/keys`, `/api/ws/ticket`, etc. — return mock JSON
- `frontend/public/mockServiceWorker.js` — MSW init script (run `npx msw init public/`)
- Tests:
  - `tests/lib/apiClient.test.ts` — 401 redirect, 429 inline error, X-CSRF-Token attachment
  - `tests/routes/LoginPage.test.tsx` — validation, happy path, error display
  - `tests/routes/RegisterPage.test.tsx` — validation, password strength, terms checkbox
  - `tests/routes/KeysDashboardPage.test.tsx` — create modal, show-once, copy-to-clipboard, revoke confirm
  - `tests/lib/stores/authStore.test.ts` — login, logout, BroadcastChannel sync
  - `tests/regression/smoke.test.tsx` — upload, transcribe, progress, export still work

### shadcn/ui

- Already partially in via radix primitives + clsx + tailwind-merge + class-variance-authority + lucide-react
- Add: `<Button>`, `<Form>`, `<Input>`, `<Label>`, `<Card>`, `<Dialog>`, `<Alert>`, `<Badge>` components via shadcn CLI: `npx shadcn@latest add button form input label card dialog alert badge`
- Tailwind v4 already in via `@tailwindcss/vite`
- Use sonner (already in deps) for non-error toasts

### `/frontend-design` Skill Invocation

- The user explicitly mandated `/frontend-design` skill for ALL frontend phases.
- Plans MUST direct executors to invoke `/frontend-design` (or apply its principles — visual quality, density, hierarchy, polish) when building auth UI pages.
- Pages must reach a "super pro modern UI" bar (UI-13).

### Code Quality (locked from user)

- **DRY** — single apiClient wrapper; single authStore; single zod schema for login/register; shared `<Field>` component for form rows
- **SRP** — pages are dumb orchestrators; logic in stores/hooks; styling via tailwind utility + shadcn components
- **/tiger-style** — typed errors from apiClient; assert on app boot that `import.meta.env.VITE_API_BASE_URL` is set; CSRF token attachment is mandatory not optional
- **No spaghetti** — early returns; guard clauses; max 2 nesting levels in components
- **Self-explanatory names** — `<LoginPage>`, `<RegisterPage>`, `<KeysDashboardPage>`, `apiClient.get/post/put/delete`, `authStore.login`, no abbreviations

### Claude's Discretion

- Whether to put MSW handlers in one file or split per resource — recommend split for clarity (`auth.handlers.ts`, `keys.handlers.ts`, etc.) re-exported from `handlers.ts`
- Whether to use shadcn `<Form>` with controlled or uncontrolled inputs — recommend react-hook-form's `<FormField>` adapter (recommended pattern in shadcn docs)
- BroadcastChannel polyfill — Vitest's jsdom doesn't have BroadcastChannel; use `vi.stubGlobal` in setup.ts to provide a working polyfill for tests
- Whether to add `react-error-boundary` — yes, wrap each route page

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `frontend/src/components/upload/*` — UploadDropzone, FileQueueList, FileQueueItem, ConnectionStatus — MOVE verbatim to TranscribePage; do NOT rewrite
- `frontend/src/components/transcript/*` — transcript viewer components — keep at /
- `frontend/src/components/ui/*` — already-installed shadcn primitives (likely Button, Card, Input, etc.)
- `frontend/src/lib/api/*` — existing API call helpers — REFACTOR to use new apiClient wrapper instead of direct fetch
- `frontend/src/lib/upload/*` — existing TUS upload helpers — extend to use apiClient for ticket retrieval
- `frontend/src/App.tsx` — current entry — ADD `<BrowserRouter>` wrap
- `frontend/src/main.tsx` — bootstraps React; minor change for Router

### Established Patterns

- Tailwind v4 via @tailwindcss/vite
- Radix primitives via @radix-ui/*
- Lucide icons via lucide-react
- Sonner toasts via sonner
- TypeScript strict mode

### Integration Points

- `frontend/src/App.tsx` — wrap with BrowserRouter; add Routes
- `frontend/src/main.tsx` — minor (no change unless we add a global error boundary)
- `frontend/package.json` — add deps: zustand, react-hook-form, zod, @hookform/resolvers, vitest, jsdom, @testing-library/*, msw
- `frontend/tsconfig.app.json` and `vite.config.ts` — may need test config
- New files: `frontend/src/routes/*`, `frontend/src/lib/apiClient.ts`, `frontend/src/lib/stores/authStore.ts`, `frontend/src/tests/setup.ts`, `frontend/src/tests/msw/*`

</code_context>

<specifics>
## Specific Ideas

- Built behind `AUTH_V2_ENABLED` semantically — but in practice the frontend always renders the new shell and falls back gracefully if backend returns 503/501 on V2 routes
- Cross-tab sync via BroadcastChannel — when user logs out in tab A, tab B's authStore listener clears local user state and triggers `<RequireAuth>` redirect on next render
- `/dashboard/account` is a placeholder route that just shows "Coming in v1.2 polish (Phase 15)" — Phase 15 fills in plan_tier card, upgrade CTA, delete-account flow
- All auth pages use shadcn/ui Card-on-page layout for the "super pro modern UI" bar — apply `/frontend-design` skill principles
- 401 redirect MUST preserve `?next=` so user lands back where they came after login

</specifics>

<deferred>
## Deferred Ideas

- Logout-all-devices button — Phase 15 (AUTH-06)
- Type-email-confirmation full account delete — Phase 15 (SCOPE-06)
- Stripe checkout / webhook UI integration — Phase 15 (BILL-05/06 stubs are 501-only here)
- Account dashboard plan_tier card + upgrade-to-pro CTA — Phase 15 (UI-07)
- Settings page (theme, language, etc.) — out of scope
- Mobile-responsive optimization beyond standard tailwind breakpoints — v1.3+

</deferred>
