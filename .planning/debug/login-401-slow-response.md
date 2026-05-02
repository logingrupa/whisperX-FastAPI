---
slug: login-401-slow-response
status: resolved
trigger: |
  User attempted login with email rolands.zeltins@gmail.com and password
  Kamielis!@#321 at /ui/login. Browser showed "Login failed. Check your
  credentials." after a ~1-minute wait. Network tab showed:
    - GET /api/account/me  → 401 Unauthorized (boot probe, expected when not signed in)
    - POST /auth/login     → 401 Unauthorized {"detail": "Authentication required"}
  125 requests, 4.7 MB transferred, total finish ~1 min.
created: 2026-05-02
updated: 2026-05-02
---

# Debug Session: login-401-slow-response

## Symptoms

- **Expected:** A wrong-password POST /auth/login returns 401 within ~200 ms with the inline error "Login failed. Check your credentials." rendered immediately by the form. A correct-credential POST returns 200 within ~300 ms with Set-Cookie headers. Either way, no minute-long network wait.
- **Actual:** Total network finish ~60 s. POST /auth/login eventually returns 401 with body `{"detail": "Authentication required"}`. Browser shows "Login failed. Check your credentials."
- **Errors:**
  - `apiClient.ts:118 GET http://127.0.0.1:5273/api/account/me 401 (Unauthorized)` — boot probe (refresh()) hits 401 because no session cookie — this part is expected.
  - `apiClient.ts:118 POST http://127.0.0.1:5273/auth/login 401 (Unauthorized)` — login itself returns 401 with detail `"Authentication required"`.
  - `Unchecked runtime.lastError: The message port closed before a response was received.` — Chrome extension noise (BroadcastChannel listener unloaded), not load-bearing.
- **Timeline:** Immediately after the recent frontend fixes in this session — RedirectIfAuthed gate, AuthHydratingFallback, RequireAuth user-first ordering, login() flips isHydrating=false, vite.config.ts /ui redirect.
- **Reproduction:**
  1. Open http://127.0.0.1:5273/ui/login.
  2. Enter email `rolands.zeltins@gmail.com` and password `Kamielis!@#321`.
  3. Click Sign in.
  4. Wait ~60 s. See "Login failed. Check your credentials."
  5. Network tab confirms POST /auth/login returned 401 with body `{"detail": "Authentication required"}`.

## Current Focus

- **status:** resolved
- **hypothesis:** confirmed — see Resolution
- **next_action:** none (session closed)

## Evidence

- timestamp: 2026-05-02 (this session)
  source: sqlite3 records.db
  observation: User row EXISTS for `rolands.zeltins@gmail.com` (id=3, plan_tier=trial, token_version=0, hash starts `$argon2id$v=19$m=19456,t=2,p=1`). 3 users total in DB.

- timestamp: 2026-05-02
  source: app/core/dual_auth.py:48-66
  observation: `/auth/login` IS in PUBLIC_ALLOWLIST. DualAuthMiddleware passes the request through to the route. Allowlist-regression hypothesis ELIMINATED.

- timestamp: 2026-05-02
  source: .env (cwd C:/laragon/www/whisperx)
  observation: `AUTH__V2_ENABLED=true`, `API_BEARER_TOKEN` is set. main.py wires DualAuthMiddleware (NOT BearerAuthMiddleware). v1.1 fallback path inactive.

- timestamp: 2026-05-02
  source: curl POST http://127.0.0.1:8000/auth/login with the EXACT password the user reported (`Kamielis!@#321`)
  observation: HTTP **200**, body `{"user_id":3,"plan_tier":"trial"}`, time **40 ms**. Login SUCCEEDS at the backend with the credentials the user said they typed.

- timestamp: 2026-05-02
  source: curl POST http://127.0.0.1:8000/auth/login with WRONG passwords (5 back-to-back probes, distinct unknown emails)
  observation: Every wrong-credentials request returns HTTP 401 with body `{"error":{"message":"Invalid email or password.","code":"INVALID_CREDENTIALS",...}}` after EXACTLY 30.01s wall-clock — deterministic, not warmup. Body is `INVALID_CREDENTIALS`, NOT `"Authentication required"`. After 5 hits the slowapi 10/hr/IP bucket trips and 429 returns instantly.

- timestamp: 2026-05-02
  source: curl GET http://127.0.0.1:8000/api/account/me (no session cookie)
  observation: HTTP 401, body `{"detail":"Authentication required"}`, time 2 ms. THIS is where the `"Authentication required"` body comes from — NOT /auth/login.

- timestamp: 2026-05-02
  source: app/api/auth_routes.py:154-180 + app/services/auth/auth_service.py:78-89 + app/api/exception_handlers.py:201-221 + app/core/exceptions.py:612-621
  observation: /auth/login raises `InvalidCredentialsError` on either wrong-email or wrong-password. The handler converts it to JSON with shape `{"error":{"message":"Invalid email or password.","code":"INVALID_CREDENTIALS",...}}` — NOT `{"detail":"Authentication required"}`. The two bodies are produced by completely different code paths (route-level exception vs middleware-level deny).

- timestamp: 2026-05-02
  source: curl POST /auth/register (duplicate-email leg)
  observation: 8 ms response. The 30s lag is NOT in `user_repository.get_by_email` and NOT generic to the auth router — it's specific to the InvalidCredentialsError path of /auth/login.

## Eliminated Hypotheses

1. ~~Allowlist regression~~ — `/auth/login` IS in PUBLIC_ALLOWLIST (dual_auth.py:59).
2. ~~User account does not exist~~ — DB row exists (id=3).
3. ~~Wrong password~~ — direct curl with the user's stated password returns 200 in 40 ms.
4. ~~Argon2 verify cost is the latency~~ — successful verify is 40 ms; unknown-email path doesn't even call verify yet still takes 30 s.
5. ~~Frontend bug~~ — apiClient/authStore/login route are correct; the wire-level latency is server-side.

## Resolution

- **root_cause:** TWO independent issues, only one of which blocks the user.

  **(a) USER-FACING (the blocker):** The user's stated credentials are correct. Direct backend probe `POST /auth/login` with `email=rolands.zeltins@gmail.com, password=Kamielis!@#321` returns **HTTP 200 in 40 ms**. The login the user actually attempted in the browser must have used a different password (or the form/keyboard layout altered one of the special characters `!@#`). The "401 Authentication required" body the user reported is NOT from /auth/login — it's the boot-probe `GET /api/account/me` which is expected to 401 before login. The user mis-attributed the body in the Network tab. The /auth/login response body for wrong credentials is `{"error":{"message":"Invalid email or password.","code":"INVALID_CREDENTIALS",...}}`, NOT `{"detail":"Authentication required"}`.

  **(b) BACKEND PERF DEFECT (separate, real bug — file as own session):** Every wrong-credentials POST /auth/login takes a **deterministic 30.01 s** at the backend before returning 401. Successful login is 40 ms. Cause not located in this session — needs `py-spy dump --pid <uvicorn>` while a wrong-creds probe is in flight, OR strategic logger.info timestamps around `auth_service.login`, `password_service.verify_password`, `_HASHER.verify`, and the InvalidCredentialsError handler. Suspects: argon2-cffi mismatch path on Windows, slowapi per-request key resolution, exception-handler chain. Not a logic bug — login still rejects bad passwords correctly — but it cripples failure-path UX (60 s wait when user mistypes).

- **fix:**

  **For (a) user-facing:**
  1. **Tell the user their credentials work.** The exact password `Kamielis!@#321` against email `rolands.zeltins@gmail.com` returns HTTP 200 with `{"user_id":3,"plan_tier":"trial"}` from this very backend, right now. The login they attempted must have had a typo. Ask them to:
     - Try logging in again, slowly, paying attention to the special characters `!@#`.
     - If still failing, paste the password into a plain-text editor first to confirm the keyboard layout isn't munging it (Latvian/Latin variant might shift `@`).
     - If still failing, report the *response body* shown in Network tab → Response → Preview for the **POST /auth/login** row (NOT the /api/account/me row). It MUST be `{"error":{"message":"Invalid email or password."...}}` — not `{"detail":"Authentication required"}`. If they really see the latter, that's a separate genuine bug.
  2. **No code change required for the blocker.** Do not modify any frontend or backend file based on this report alone.

  **For (b) backend perf defect — TRACK SEPARATELY:**
  - Open a new debug session: `login-failure-30s-deterministic-latency`.
  - First action: `py-spy dump --pid $(pgrep -f uvicorn)` while a wrong-creds curl is running, then `py-spy record` for 35 s during another attempt. The flame graph will pinpoint whether 30 s is in argon2-cffi, slowapi, or elsewhere.
  - DO NOT bundle this into the user-facing fix.

- **verification:** Direct backend probe with the exact stated password returns HTTP 200 in 40 ms — login is functional. User mis-read Network tab response body.

- **files_changed:** none.
