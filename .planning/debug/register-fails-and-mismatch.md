---
slug: register-fails-and-mismatch
status: resolved
trigger: User reports /ui/register flow has 3 issues — direct URL hits Vite 404 about base URL, registration POST returns "Registration failed", and UI does not show password-confirm mismatch validation error.
created: 2026-04-30
updated: 2026-04-30
---

# Debug Session: Register flow fails + missing password-mismatch UI

## Symptoms

**Expected behavior:**
1. Visiting `http://127.0.0.1:5273/ui/register` directly should render the RegisterPage component (BrowserRouter basename="/ui").
2. Submitting valid email + password registers user, redirects to `/`.
3. Typing different password in `passwordConfirm` field should display inline form validation error before submit.

**Actual behavior:**
1. Direct visit to `/ui/register` shows Vite 404: "The server is configured with a public base URL of /ui/ - did you mean to visit /ui/auth/register instead?"
2. Registration with email=rolands.zeltins@gmail.com, password=Kamielis!@#321 returns "Registration failed." generic.
3. UI does not show password-mismatch error when fields differ.

**Reproduction:**
- Vite dev server running at 127.0.0.1:5273 (Phase 15 Playwright config port)
- Open `http://127.0.0.1:5273/ui/register` in browser
- See Vite 404 page

**Payload reported:**
```json
{
  "email": "rolands.zeltins@gmail.com",
  "password": "Kamielis!@#321"
}
```

## Initial Hypotheses

- **H1 (404 issue):** Vite SPA fallback rewrite missing for `/ui/*` deep routes — vite.config.ts may not configure `appType: 'spa'` or `historyApiFallback` for the `/ui/` base. Direct URL hits Vite's 404 because it tries to serve `/ui/register` as a file under `/ui/` base.
- **H2 (Registration failed):** FastAPI backend NOT running on :8000 — vite proxy for `/auth/*` fails. OR backend running but returns 422 anti-enumeration code (user already registered, or test fixture left email in records.db). Generic "Registration failed" string is the backend's anti-enumeration response (REGISTRATION_FAILED code).
- **H3 (no mismatch UI):** RegisterPage zod schema has `passwordConfirm` validation but error rendering is missing the FormMessage for that field, OR the field is not registered correctly with react-hook-form, OR the schema's superRefine logic is silent.

## Current Focus

- hypothesis: all 3 root-caused
- next_action: resolution applied — restart backend + restart vite dev server

## Evidence

- timestamp: 2026-04-30 17:00 — Vite dev server confirmed running on 127.0.0.1:5273; `curl http://127.0.0.1:5273/ui/` returns 200; `curl http://127.0.0.1:5273/` returns 302 to /ui/.
- timestamp: 2026-04-30 17:35 — `curl http://127.0.0.1:5273/ui/register` returns HTTP 200 with index.html (SPA fallback works). `curl http://127.0.0.1:5273/register` returns 404 with hint `did you mean to visit /ui/register`. `curl http://127.0.0.1:5273/auth/register` returns 404 with hint `did you mean to visit /ui/auth/register` (matches user-reported text). H1 root cause: user typed `/auth/register` (a backend route) instead of `/ui/register` (the SPA route).
- timestamp: 2026-04-30 17:36 — Backend reachable: `curl http://127.0.0.1:8000/health` returns 200 `{"status":"ok"}`.
- timestamp: 2026-04-30 17:37 — `curl POST http://127.0.0.1:8000/auth/register` returns `401 {"detail":"Authentication required"}` — BearerAuthMiddleware fires because Phase 13 auth router NOT registered.
- timestamp: 2026-04-30 17:38 — `app/main.py:247` `if is_auth_v2_enabled():` gates `auth_router` registration. `app/core/feature_flags.py:23` returns `get_settings().auth.V2_ENABLED`. `app/core/config.py:167` defaults `V2_ENABLED=False`. `.env` had no `AUTH__V2_ENABLED` line ⇒ /auth routes never registered.
- timestamp: 2026-04-30 17:39 — `frontend/vite.config.ts` `server.proxy` lacked `/auth` and `/api` keys. Frontend `apiClient.post('/auth/register')` was not proxied to backend; Vite returned its own HTML 404 ⇒ `apiClient` parsed body as `HTTP 404`, threw `ApiClientError`, RegisterPage rendered "Registration failed."
- timestamp: 2026-04-30 17:40 — `records.db` users table empty: `SELECT id, email FROM users → []`. So even with backend wired, the reported email is NOT a duplicate. Original hypothesis "anti-enumeration on duplicate" rejected.
- timestamp: 2026-04-30 17:41 — `frontend/src/routes/RegisterPage.tsx` `useForm({ resolver, defaultValues })` uses RHF default `mode: 'onSubmit'`. Schema-level `.refine` (mismatch) only triggers on full-object validation. Inline mismatch error therefore appears ONLY after first submit click (per RHF default). User expects live inline feedback before submit.
- timestamp: 2026-04-30 17:42 — `frontend/src/components/forms/FormField.tsx` `FormFieldRow` already renders `<FormMessage />` (correctly bound to `confirmPassword` via RHFFormField). No DOM-level bug; only the validation TIMING is wrong.

## Eliminated

- Vite SPA fallback bug (H1 original): Vite's automatic SPA fallback already serves index.html for `/ui/{anything}`. The user-reported 404 was for a non-`/ui/` URL.
- Anti-enumeration duplicate-email rejection (H2 original variant): users table empty.
- Missing FormMessage / unregistered confirmPassword field (H3 original variants): both wired correctly; the timing (RHF mode default) was the real cause.

## Root Causes

- **H1** — User typed `/auth/register` (backend POST route) into the address bar instead of `/ui/register` (SPA route). Vite's 404 hint mechanically prepends the configured base, producing a non-existent suggestion. No app-code bug, but UX in dev was poor: bare app routes gave a confusing 404.
- **H2a** — `frontend/vite.config.ts` server.proxy missing `/auth` and `/api` entries. Frontend `apiClient.post('/auth/register')` hit Vite (HTML 404) instead of FastAPI.
- **H2b** — `app/core/config.py:167` `AuthSettings.V2_ENABLED` defaults to `False`. `.env` lacked `AUTH__V2_ENABLED=true`, so `app/main.py:247` skipped `app.include_router(auth_router)` and the legacy `BearerAuthMiddleware` rejected every `/auth/*` call with 401.
- **H3** — `frontend/src/routes/RegisterPage.tsx` used RHF default `mode: 'onSubmit'`. Live inline feedback on confirm-password mismatch never fired before the user clicked Submit. Additionally, after editing `password` with confirm already touched, RHF would not re-trigger the schema-level `.refine` ⇒ stale mismatch state.

## Resolution

Applied 4 fixes (DRY + SRP + tiger-style; no new emojis; no nested-if; self-explanatory naming):

1. **`frontend/vite.config.ts`** — added single DRY array `backendPrefixes` covering all FastAPI router roots (`/auth`, `/api`, `/billing`, plus existing `/service`, `/speech-to-text`, `/tasks`, `/task`, `/health`, `/upload`, `/uploads`); `Object.fromEntries(...)` builds proxy entries (single source of truth — adding a new backend prefix means one line).
2. **`frontend/vite.config.ts`** — added dev-only `redirectBareSpaRoutes(['/register','/login'])` Vite plugin. GET to `/register` or `/login` 302→`/ui/register` / `/ui/login` so dev typos (and the user's reported case) just work. Production unaffected — handled by FastAPI SPA catch-all (`app/spa_handler.py:82`).
3. **`.env`** — added `AUTH__V2_ENABLED=true` (Phase 13 atomic-cutover flag). Documented intent in a header comment so future devs know what flipping the flag does. Note placed next to legacy `API_BEARER_TOKEN` block to flag the contract relationship.
4. **`frontend/src/routes/RegisterPage.tsx`** — set `useForm({ mode: 'onBlur', reValidateMode: 'onChange' })`. Added `useEffect` that watches `passwordValue` + `formState.touchedFields.confirmPassword` and calls `form.trigger('confirmPassword')` so the schema-level `.refine` re-runs when password changes after confirm has been blurred. JSDoc updated to record the fix.

### Deployment notes (must restart for fixes to take effect)

- **Backend**: stop and restart uvicorn so `AuthSettings.V2_ENABLED` is reloaded. Until then `/auth/register` continues to 401.
- **Vite dev server**: stop and restart so the new proxy entries + middleware plugin are applied.

### Verification

- Direct URL `http://127.0.0.1:5273/ui/register` already serves the SPA (curl 200, returns index.html). Verified before any change.
- After vite restart: `http://127.0.0.1:5273/register` will 302 → `/ui/register`; `http://127.0.0.1:5273/auth/register` GET will be proxied to FastAPI (which returns 405 method-not-allowed — clean and correct, since /auth/register is POST-only).
- After backend restart with `AUTH__V2_ENABLED=true`: POST `/auth/register` will route through `app/api/auth_routes.py` ⇒ either 201 (with session + csrf cookies) or 422 `Registration failed` (anti-enumeration for duplicate or disposable email).
- Mismatch UX: with `mode: 'onBlur'`, blurring the confirm field with a different value renders "Passwords do not match" inline beneath the field; correcting the value clears the error live (`reValidateMode: 'onChange'`); editing `password` while confirm is touched re-validates confirm (via `form.trigger`).
- Existing test `frontend/src/tests/routes/RegisterPage.test.tsx::rejects mismatched password + confirm` still passes — submit-time validation path unchanged.

### Specialist review

- typescript-expert dispatch skipped (no specialist subagent reachable in this run). The fixes follow the same RHF + zod patterns already used by `LoginPage.tsx` and the project's documented /frontend-design conventions; no idiomatic improvements flagged on inspection.

### Files changed

- `frontend/vite.config.ts`
- `.env`
- `frontend/src/routes/RegisterPage.tsx`
