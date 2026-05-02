---
slug: login-stuck-loading
status: resolved
trigger: |
  After entering wrong password and seeing the "Login failed" error message,
  clicking "Sign in" a second time started signing in and the page got stuck
  at "Loading…" (the AuthHydratingFallback rendered by RequireAuth/RedirectIfAuthed
  when authStore.isHydrating is true). Hard-reloading the browser tab still shows
  "Loading…" indefinitely.
created: 2026-05-01
updated: 2026-05-02
---

# Debug Session: login-stuck-loading

## Symptoms

- **Expected:** After clicking "Sign in" with valid (or invalid) credentials, the page either redirects to `/` (TranscribePage) on success or shows an inline error and stays on `/login` on failure. Hard-reloading `/ui/login` should always end up at the login form OR at the dashboard, never permanently at "Loading…".
- **Actual:** Page renders `<AuthHydratingFallback />` ("Loading…") indefinitely. The state never transitions to `isHydrating=false`.
- **Errors:** First wrong-password attempt correctly displayed "Login failed. Check your credentials." Second click of Sign in transitioned to "Loading…" and never came back. Hard reload reproduces the stuck state.
- **Timeline:** Started after the most recent frontend changes in this session — added `RedirectIfAuthed`, swapped `null` for `<AuthHydratingFallback />` in both gates, added `/ui` → `/ui/` redirect in vite config.
- **Reproduction:**
  1. Open `http://127.0.0.1:5273/ui/login`.
  2. Enter wrong password. Submit. See "Login failed" message.
  3. Click "Sign in" again (with same or new credentials). Page transitions to "Loading…".
  4. Hard reload (Ctrl+Shift+R). Page still stuck at "Loading…".

## Current Focus

- **status:** resolved
- **hypothesis:** confirmed — two compounding bugs (login 401 triggers redirectTo401 + boot probe lacks timeout)
- **next_action:** done

## Evidence

- source: `frontend/src/lib/apiClient.ts:129-135`
  - 401 path calls `redirectTo401()` UNLESS `opts.suppress401Redirect` is set.
  - `redirectTo401()` mutates `window.location.href = '/login?next=<currentUrl>'` (full reload).
- source: `frontend/src/lib/stores/authStore.ts:104-112` (pre-fix)
  - `login()` calls `apiClient.post('/auth/login', …)` with NO `suppress401Redirect`. A 401 from the login endpoint (wrong password) therefore triggers `window.location.href` mutation.
- source: `frontend/src/lib/api/accountApi.ts:30-35`
  - `fetchAccountSummary()` correctly passes `suppress401Redirect: true` — the boot probe is fine on the 401 path. The bug is exclusive to login/register POSTs.
- source: `frontend/src/main.tsx:13` (pre-fix)
  - Boot probe `void useAuthStore.getState().refresh()` has NO client-side timeout. If `/api/account/me` hangs (orchestrator hint: ~30s+ on first hit), `isHydrating` never flips false and `<AuthHydratingFallback />` stays mounted forever.
- source: `frontend/src/routes/RedirectIfAuthed.tsx:22-24`
  - New gate wrapping `/login` + `/register` shows `<AuthHydratingFallback />` while `isHydrating=true`. Previous behaviour: `/login` was NOT gated, so a slow probe never blocked the form. Regression introduced when public routes were wrapped.
- source: `frontend/src/routes/RequireAuth.tsx:25-27`
  - Same fallback. Old behaviour was `return null` — also blank, but never used on `/login`.

## Eliminated Hypotheses

- (H1) `login()` toggles `isHydrating=true` and fails to reset on error. ELIMINATED — `login()` does not touch `isHydrating` at all. Stuck state arises from the navigation triggered by `redirectTo401()` causing a full reload while the boot probe is slow.
- (H3) An unhandled exception bypasses the `finally` in `refresh()`. ELIMINATED — `finally` always runs in JS; `set({ isHydrating: false })` is unconditional. The bug is the absence of completion (probe never resolves), not skipped finally.
- (H4) Cookie corruption after first 401. ELIMINATED — no evidence; backend slowness alone is sufficient.

## Root Cause

Two compounding bugs:

1. **PRIMARY — login 401 triggers full-page redirect.** `apiClient.post('/auth/login')` does not pass `suppress401Redirect: true`. Wrong-password → 401 → `redirectTo401()` mutates `window.location.href = '/login?next=/login'` while simultaneously throwing `AuthRequiredError`. The form briefly shows "Login failed" then the browser commits the navigation, full-reloading `/ui/login`. The user perceives this as "I clicked Sign in again." Same hazard on `/auth/register`.

2. **AMPLIFIER — boot probe has no client timeout.** `main.tsx` fires `useAuthStore.getState().refresh()` which awaits `fetchAccountSummary()` indefinitely. With backend `/api/account/me` taking 30s+ (and possibly hanging), `isHydrating=true` forever. The newly-added `RedirectIfAuthed` gate now blocks `/login` itself behind `<AuthHydratingFallback />`, so the user sees "Loading…" with no way out. Hard reload reproduces the same probe → same stuck state.

Compound effect: bug #1 forces a reload on every wrong password; bug #2 makes that reload land on a Loading… screen the user cannot escape from.

## specialist_hint

typescript

## Resolution

- **root_cause:** Login/register POSTs hit the apiClient 401 redirect path (`window.location.href = /login?next=…`), causing a full reload on every wrong password. The reload triggers a slow `/api/account/me` boot probe with no client-side timeout, leaving `isHydrating=true` indefinitely. The new `RedirectIfAuthed` gate then renders `<AuthHydratingFallback />` over `/login` itself with no way out.
- **fix:**
  1. `frontend/src/lib/stores/authStore.ts` — `login()` and `register()` now pass `{ suppress401Redirect: true }` to `apiClient.post`. 401s throw `AuthRequiredError` (caught by the form as `ApiClientError`) without mutating `window.location.href`. Page stays put; inline error renders.
  2. `frontend/src/main.tsx` — boot probe now has an 8s client-side timeout. If `useAuthStore.getState().isHydrating` is still `true` after `BOOT_PROBE_TIMEOUT_MS`, force `isHydrating=false` so the auth gates can render the login form (or redirect home). Late probe responses still settle the user state via the original promise; they just no longer gate the UI.
  3. `frontend/src/tests/lib/stores/authStore.test.ts` — two regression tests assert that login(401) and register(401) do NOT mutate `window.location.href`.
- **verification:**
  - `bun run test` — 138/138 passing (including 2 new regression tests).
  - `bunx tsc --noEmit` — typecheck clean.
  - `bun run lint` — no new errors in changed files (pre-existing lint debt unrelated).
  - Manual: wrong password no longer reloads page; cold-boot Loading… resolves within 8s even when backend is slow.
- **files_changed:**
  - `frontend/src/lib/stores/authStore.ts`
  - `frontend/src/main.tsx`
  - `frontend/src/tests/lib/stores/authStore.test.ts`
