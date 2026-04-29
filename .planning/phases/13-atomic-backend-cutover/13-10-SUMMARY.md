---
phase: 13-atomic-backend-cutover
plan: 10
subsystem: backend-atomic-cutover
tags: [e2e-smoke, integration-test, subprocess-test, phase13-close, atomic-deploy-gate, csrf, dual-auth, cors-allowlist, rate-limit, disposable-email, billing-stubs, feature-flag]
requires:
  - phase: 13-09
    provides: app/main.py atomic-flip wiring (DualAuth+CSRF / 5 routers / 6 handlers / locked CORS / W4 fallback)
  - phase: 13-08
    provides: free-tier gate + concurrency release wiring (referenced via /api/keys flow)
  - phase: 13-07
    provides: per-user task scoping (referenced via cross-user 404 mental model)
  - phase: 13-04
    provides: /api/keys CRUD with show-once + cross-user 404
  - phase: 13-05
    provides: /billing/checkout (501) + /billing/webhook (400/501)
  - phase: 13-03
    provides: /auth/register, /auth/login, /auth/logout + slowapi limiter + disposable-email gate
  - phase: 13-02
    provides: DualAuthMiddleware + CsrfMiddleware
  - phase: 13-01
    provides: AuthSettings.V2_ENABLED + FRONTEND_URL + COOKIE_SECURE
  - phase: 12
    provides: alembic upgrade head pipeline (0001+0002+0003 migrations) - tmp DB seed
provides:
  - tests/integration/test_phase13_e2e_smoke.py - 12 e2e tests booting real uvicorn subprocess against tmp SQLite DB; gates Phase 13 atomic deploy with Phase 14 frontend
  - app/docs.py - UTF-8-safe writers (encoding="utf-8" + ensure_ascii=False + allow_unicode=True) so subprocess lifespan does not crash on Windows cp1252
  - regenerated app/docs/openapi.json + openapi.yaml + db_schema.md - now reflect Phase 13 routes (auth/keys/account/billing/ws_ticket) via utf-8 writer
affects:
  - phase 14 (frontend cutover) - smoke gate green = atomic backend deploy is ready to pair with /login + /register frontend pages
  - phase 16 (verification) - this is the SMOKE pre-flight; cross-user matrix + JWT attack matrix + WS ticket reuse tests are Phase 16 territory
  - operator runbook (Phase 17) - subprocess+tmp-DB+alembic-upgrade-head pattern documented here for staging dry-runs

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Subprocess-per-scenario test pattern: each fixture spawns a fresh uvicorn worker (clean module state, fresh slowapi bucket, fresh settings.lru_cache, fresh tmp SQLite DB, fresh JWT/CSRF secrets) so test cross-pollination is impossible"
    - "Boot-readiness probe: poll /health every 0.5s with 1s timeout; bail early if proc.poll() returns; 90s ceiling kills child + drains stderr (tiger-style fail-loud)"
    - "_free_port() socket trick (bind 127.0.0.1:0; OS-allocates) for parallel-safe port acquisition on Windows"
    - "_register() DRY helper clears httpx cookie jar BEFORE and AFTER the register call so subsequent state-mutating requests in the same client are not auto-attached with stale session+csrf cookies (which would trip CsrfMiddleware on cookie-auth state-mutating routes)"
    - "Per-test env override: alembic upgrade head runs in same env block as uvicorn so engine bind URLs match (no separate test-fixture vs runtime gap)"
    - "API_BEARER_TOKEN passed in V2_OFF fixture so legacy BearerAuthMiddleware passes the request through and we observe the 404 (route not registered) instead of 401 (auth missing) - the must-have signal we're testing"
    - "Authentication gates collapsed: every test uses the same {register, optional logout, optional cookies-clear} preamble + the route-under-test - SRP per test class"
key-files:
  created:
    - tests/integration/test_phase13_e2e_smoke.py - 12 e2e smoke tests (~470 LoC; covers all locked must-have truths from PLAN frontmatter)
  modified:
    - app/docs.py - UTF-8 explicit on all three writers (save_openapi_json + write_markdown_to_file); ensure_ascii=False / allow_unicode=True so non-ASCII docstring/comment chars survive on Windows
    - app/docs/openapi.json - regenerated under utf-8 writer; now includes Phase 13 routes (auth/keys/account/billing/ws_ticket)
    - app/docs/openapi.yaml - regenerated under utf-8 writer; allow_unicode=True
    - app/docs/db_schema.md - regenerated under utf-8 writer (column comments survive cp1252 collisions)

key-decisions:
  - "[13-10]: Subprocess-per-test (not in-process TestClient) chosen because (a) app/main.py engine binding happens at module load against DB_URL env (we need a fresh DB per scenario), (b) slowapi's leaky bucket is process-local (we need fresh ANTI-01 counters per test), (c) settings.lru_cache caches the V2_ENABLED flag (we need to flip it). Pattern mirrors test_phase12_cli_backfill_e2e.py."
  - "[13-10]: V2_OFF fixture sets API_BEARER_TOKEN=smoke-legacy-token + test sends Authorization: Bearer header so the legacy BearerAuthMiddleware passes through to the FastAPI router. Without bearer the middleware short-circuits at 401 and we cannot distinguish 'auth missing' from 'route absent' - which is the must-have signal."
  - "[13-10]: _register() helper wipes the httpx cookie jar both BEFORE and AFTER the POST. cookies= per-request is httpx-deprecated (warns) but acceptable here because tests pass them explicitly per route to avoid jar persistence between distinct user identities (cross-user 404 test uses two cookie dicts on one client)."
  - "[13-10]: Rule 3 deviation - app/docs.py utf-8 fix was a hard blocker: subprocess uvicorn lifespan hung indefinitely on Windows because cp1252 default text mode could not encode non-ASCII chars (`->` in route docstrings) in save_openapi_json/write_markdown_to_file. Standalone python -c 'from app.main import app' worked because that test never reached lifespan. Fix essential to unblock smoke gate."
  - "[13-10]: 4th register returns 429 not 4th registration attempt - the limit is 3/hour so iterations 0,1,2 succeed then iteration 3 (4th call) returns 429. Retry-After header asserted as int > 0 (slowapi emits seconds value derived from window)."
  - "[13-10]: /billing/webhook is in PUBLIC_ALLOWLIST in DualAuthMiddleware (Stripe calls server-to-server; HMAC verify is v1.3) but DualAuth still flips to cookie-auth mode if a session cookie is present in the request, which then trips CsrfMiddleware. Test wipes cookie jar before each /billing/webhook POST so the path resolves anonymous and the 501/400 signals are not masked by 403 CSRF errors. Documented as inline comment in test."

patterns-established:
  - "E2E smoke gate via uvicorn subprocess: each fixture spawns a fresh worker with overridden env (DB_URL, AUTH__JWT_SECRET, AUTH__CSRF_SECRET, AUTH__FRONTEND_URL, AUTH__COOKIE_SECURE, ENVIRONMENT, AUTH__V2_ENABLED) and runs alembic upgrade head before boot - this is the deployment dry-run pattern Phase 17 will document for production rollout"
  - "Cookie-jar discipline pattern: when an httpx.Client is reused across multiple identities (cross-user tests), wipe the jar via client.cookies.clear() between identities AND pass cookies=identity_cookies + headers={X-CSRF-Token: identity_csrf} explicitly per request - keeps DualAuth resolution legs deterministic"
  - "UTF-8-safe ASGI artifact writer pattern: any function that serializes user-facing or schema text to disk MUST pass encoding=\"utf-8\" + the format-specific ensure-unicode flag (ensure_ascii=False for json, allow_unicode=True for yaml) - default text mode on Windows is cp1252 and will crash on non-ASCII chars in docstrings/comments"
  - "Atomic-flip verification pattern: single must-have - V2_OFF returns 404 / V2_ON returns 422 on empty body - this distinguishes 'route NOT registered' from 'route registered + body invalid' which is the contract semantic of the feature flag"

requirements-completed: [AUTH-01, AUTH-03, AUTH-05, KEY-01, KEY-04, KEY-05, KEY-07, MID-01, MID-04, ANTI-01, ANTI-02, ANTI-04, ANTI-06, RATE-03, RATE-04, RATE-12, BILL-05, BILL-06]

# Metrics
duration: 26min
completed: 2026-04-29
---

# Phase 13 Plan 10: Phase 13 E2E Smoke Gate Summary

**Atomic backend cutover SMOKE gate: 12 end-to-end tests boot a real ``uvicorn`` subprocess (V2 ON + tmp SQLite DB + alembic-migrated schema) and exercise every locked must-have truth from the Phase 13 contract — register/login/create-key/use-key/logout flow, cross-user 404, ANTI-01 rate-limit fires at 4th register, ANTI-04 disposable-email rejected, ANTI-06 CORS allowlist + credentials echo, BILL-05/06 stubs return 501 / 400 on malformed signature, V2_ENABLED feature-flag toggles route registration, MID-04 CSRF required on cookie POST + bearer skips CSRF — all 12 pass in ~233s.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-04-29T12:06:53Z
- **Completed:** 2026-04-29T12:32:54Z
- **Tasks:** 1 (single e2e smoke gate per plan)
- **Files created:** 1 (tests/integration/test_phase13_e2e_smoke.py — 12 tests, ~480 LoC)
- **Files modified:** 4 (app/docs.py + 3 regenerated docs artifacts)
- **Test runtime:** 233s e2e smoke alone (12/12 pass); 255s wider Phase 13 integration suite (112/112 pass excluding pre-existing factory-import-broken test_task_lifecycle.py)
- **Commits:** 1 (`b9de900` — atomic feat commit)

## Accomplishments

- **12/12 e2e smoke tests pass** booting a fresh uvicorn subprocess per scenario against a tmp SQLite DB:
  1. `test_full_register_login_create_key_use_key_logout_flow` — happy path: register → cookie set → POST /api/keys (cookie+CSRF) → GET /api/keys (bearer-auth) → DELETE /api/keys/{id} → logout → Set-Cookie Max-Age=0 / expires=Thu, 01 Jan 1970
  2. `test_login_after_register_succeeds` — credentials persist across logout: register → logout → login round-trip → 200 + new cookies
  3. `test_cross_user_404_isolation` — User B's DELETE on User A's key returns 404 opaque (not 403; SCOPE-02 anti-enumeration)
  4. `test_register_rate_limit_3_per_hour` — 3 successful registers + 4th returns 429 with Retry-After header > 0 (ANTI-01)
  5. `test_disposable_email_rejected` — 10minutemail.com domain → 422 generic "Registration failed" (ANTI-04)
  6. `test_cors_preflight_allowed_origin` — Origin: http://localhost:5173 → ACAO=http://localhost:5173 + ACAC=true (ANTI-06)
  7. `test_cors_preflight_disallowed_origin` — Origin: https://evil.example.com → ACAO != evil.example.com (CORSMiddleware does not echo non-allowlisted origins)
  8. `test_billing_stubs_return_501` — /billing/checkout (auth required) → 501 with `{status: stub, hint: ...v1.3...}`; /billing/webhook valid Stripe-Signature schema → 501; malformed → 400 (BILL-05/06)
  9. `test_v2_disabled_routes_not_registered` — V2_OFF + valid legacy bearer → /auth/register returns 404 (route NOT registered when V2 off); /health → 200 (public allowlist active in both branches)
  10. `test_v2_enabled_routes_registered` — V2_ON + empty body POST /auth/register → 422 (route IS registered + body invalid; distinguishes 422 from 404)
  11. `test_csrf_required_on_cookie_post` — cookie-auth POST /api/keys without X-CSRF-Token → 403 "CSRF token missing" (MID-04)
  12. `test_bearer_auth_skips_csrf` — Authorization: Bearer whsk_* on POST /api/keys → 201 (bearer wins; CsrfMiddleware bypasses bearer-authenticated routes)
- **Subprocess pattern locked**: each test fixture spawns a fresh uvicorn worker with overridden env (DB_URL, AUTH__JWT_SECRET, AUTH__CSRF_SECRET, AUTH__FRONTEND_URL, AUTH__COOKIE_SECURE, ENVIRONMENT, AUTH__V2_ENABLED) AND runs `alembic upgrade head` before boot — clean module state, fresh slowapi bucket, fresh settings.lru_cache, fresh tmp SQLite DB.
- **Rule 3 blocker fix**: app/docs.py lifespan-hang on Windows cp1252 (subprocess uvicorn could not encode non-ASCII chars in route docstrings) — fixed by adding `encoding="utf-8"` + `ensure_ascii=False` (json) / `allow_unicode=True` (yaml) to all three writers. Regenerated artifacts now include the full Phase 13 surface (auth/keys/account/billing/ws_ticket).
- **Wider Phase 13 integration suite green**: 112/112 tests pass (excluding pre-existing factory-import-broken `test_task_lifecycle.py` already in deferred-items.md from Phase 13-06).

## Self-Verified 11 Verification Scenarios

| # | Scenario | Result | Evidence |
|---|----------|--------|----------|
| 1 | Full register→login→create-key→use-key→logout flow | PASS | `test_full_register_login_create_key_use_key_logout_flow` — 7-step assertion chain incl. show-once contract (`key not in items[0]`) + soft-delete (`status == "revoked"`) + Max-Age=0 cookie deletion |
| 2 | Cross-user 404 (anti-enumeration) | PASS | `test_cross_user_404_isolation` — User B's DELETE on User A's key_id → 404 opaque |
| 3 | ANTI-01 register rate-limit fires at 4th | PASS | `test_register_rate_limit_3_per_hour` — 3 × 201 + 1 × 429 + Retry-After > 0 |
| 4 | ANTI-04 disposable-email rejected | PASS | `test_disposable_email_rejected` — trash@10minutemail.com → 422 + "Registration failed" body |
| 5 | ANTI-06 CORS allowlist (credentials echo) | PASS | `test_cors_preflight_allowed_origin` — Origin: localhost:5173 → ACAO=localhost:5173 + ACAC=true |
| 6 | ANTI-06 CORS rejects disallowed origin | PASS | `test_cors_preflight_disallowed_origin` — Origin: evil.example.com → ACAO != echo |
| 7 | BILL-05/06 stubs return 501 | PASS | `test_billing_stubs_return_501` — /billing/checkout → 501 stub + valid Stripe-Sig → 501 + malformed Stripe-Sig → 400 |
| 8 | V2_ENABLED=false → /auth/register NOT registered | PASS | `test_v2_disabled_routes_not_registered` — V2_OFF + legacy bearer → 404 (FastAPI route absent); /health → 200 (allowlist) |
| 9 | V2_ENABLED=true → /auth/register registered | PASS | `test_v2_enabled_routes_registered` — V2_ON + empty body → 422 (route IS registered + body invalid) |
| 10 | MID-04 CSRF required on cookie POST | PASS | `test_csrf_required_on_cookie_post` — cookie-auth POST /api/keys without X-CSRF-Token → 403 "CSRF token missing" |
| 11 | MID-04 Bearer auth skips CSRF | PASS | `test_bearer_auth_skips_csrf` — POST /api/keys with `Authorization: Bearer whsk_*` (no CSRF, no cookie) → 201 |

## Grep Acceptance Gate Results

| Gate | Required | Actual | Pass |
|------|----------|--------|------|
| `@pytest.mark.integration` count | ≥10 | 12 | ✓ |
| Test functions count | ≥10 | 12 | ✓ |
| Named must-have tests count | ≥10 | 11 | ✓ |
| `AUTH__V2_ENABLED` references | ≥2 | 5 | ✓ |
| `subprocess.Popen` / `subprocess.run` | ≥2 | 4 | ✓ |
| `alembic` references | ≥1 | 2 | ✓ |
| `Retry-After` / `retry-after` | ≥1 | 4 | ✓ |
| `pytest tests/integration/test_phase13_e2e_smoke.py -v -m integration` | ≥10 pass | 12/12 pass | ✓ |

## Task Commits

1. **Task 1: Phase 13 e2e smoke test gate** — `b9de900` (feat)

## Files Created/Modified

- `tests/integration/test_phase13_e2e_smoke.py` — **CREATED** — 12 e2e tests (~480 LoC) covering every Phase 13 locked must-have truth via fresh-uvicorn-subprocess pattern + tmp SQLite DB + per-scenario alembic upgrade head
- `app/docs.py` — **MODIFIED** — UTF-8 explicit on `save_openapi_json` (json) + `write_markdown_to_file` (md); `ensure_ascii=False` (json), `allow_unicode=True` (yaml) — Rule 3 blocker fix
- `app/docs/openapi.json` — **REGENERATED** — now reflects Phase 13 routes (auth/keys/account/billing/ws_ticket) via utf-8 writer
- `app/docs/openapi.yaml` — **REGENERATED** — same as above with allow_unicode=True
- `app/docs/db_schema.md` — **REGENERATED** — column comments now survive cp1252 collisions via utf-8 writer

## Decisions Made

- **Subprocess-per-test pattern (mirrors `test_phase12_cli_backfill_e2e.py`):** in-process TestClient was rejected because (a) `app/main.py` binds the SQLAlchemy engine to `DB_URL` at module load — we need a fresh tmp DB per scenario, (b) slowapi's leaky bucket is process-local — we need fresh ANTI-01 counters per test, (c) `settings.lru_cache` caches the `V2_ENABLED` flag — we need to flip it between V2-ON and V2-OFF fixtures. The subprocess pattern gives us all three for free, at the cost of ~10s boot per test (~233s total wall-time).
- **V2_OFF fixture sets `API_BEARER_TOKEN`:** without a real bearer token in env, the legacy `BearerAuthMiddleware` short-circuits with 401 on every non-public route, masking the actual signal we want to test (route NOT registered → 404). With a valid bearer token in env AND in the request header, the middleware passes through to the FastAPI router, which then returns 404 because `/auth/register` is registered ONLY when `V2_ENABLED=true` per the `app/main.py` 13-09 wiring.
- **Cookie-jar discipline via `_register()` helper + per-test `client.cookies.clear()` calls:** httpx persists cookies in the client jar across requests, AND the `cookies=` kwarg merges into the jar (it does not replace). The tests need:
  1. Multi-user identities on one client (cross-user 404 test) → wipe between registers + pass `cookies=identity_dict` per request
  2. Anonymous follow-up requests after a register (login round-trip, billing webhook test) → wipe jar between the auth'd call and the public-allowlist call so DualAuth resolves anonymous (otherwise cookie-auth mode trips CsrfMiddleware on the next state-mutating POST)
  Without this discipline, the second POST in any sequence trips CsrfMiddleware with 403 "CSRF token missing" because the auto-attached session cookie flips DualAuth into cookie-auth mode while the test's headers carry no `X-CSRF-Token`.
- **`pytest-timeout` not installed (deferred):** plan suggested `--timeout=180`, which `pytest-timeout` plugin gates. The plugin is not in `pyproject.toml`. Tests pass without it (subprocess boot+drain is the natural ceiling); plan acceptance criteria do not mandate the timeout flag. Deferred — adding the plugin is a Phase 18 polish item if needed.
- **Wider integration suite excluded `test_task_lifecycle.py`:** that file imports `factory` (the factory-boy package), which is not installed. Pre-existing problem documented in `.planning/phases/13-atomic-backend-cutover/deferred-items.md` since Phase 13-06. Out of scope for plan 13-10.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed `app/docs.py` Windows cp1252 hang in subprocess lifespan**
- **Found during:** Task 1 first test run
- **Issue:** Smoke test fixtures could not boot uvicorn — server hung at "Application lifespan started" indefinitely. Root cause: `save_openapi_json` (writes openapi.json + openapi.yaml) and `write_markdown_to_file` (writes db_schema.md) used Python's default text-mode encoding which is cp1252 on Windows. Route docstrings contain non-ASCII chars (e.g. `→`); `cp1252.encode()` raised `UnicodeEncodeError` mid-lifespan. Standalone `python -c "from app.main import app"` test passed because that path never reaches lifespan; uvicorn-launched subprocess hangs because the lifespan exception is swallowed by ASGI machinery and the worker stays in "Waiting for application startup" forever.
- **Fix:** Added `encoding="utf-8"` to all three `open()` calls in `app/docs.py`; added `ensure_ascii=False` to `json.dump` and `allow_unicode=True` to `yaml.dump` so the on-disk artifacts preserve the unicode chars instead of escaping them to ASCII. Also regenerated the three on-disk artifacts (`openapi.json`, `openapi.yaml`, `db_schema.md`) which now reflect the Phase 13 routes.
- **Files modified:** `app/docs.py`, `app/docs/openapi.json`, `app/docs/openapi.yaml`, `app/docs/db_schema.md`
- **Verification:** Lifespan completes cleanly via `python -c "from app.main import app, lifespan; import asyncio; asyncio.run(lifespan(app).__aenter__())"`; subprocess uvicorn boots in ~13s (was hanging indefinitely); all 12 smoke tests pass against the booted subprocess.
- **Committed in:** `b9de900` (Task 1 atomic commit)
- **Why Rule 3, not out-of-scope pre-existing:** the bug was latent before Phase 13 (no non-ASCII chars in docstrings) and surfaced when Phase 13 routes added `→` style arrows to summary text. The fix is a hard precondition for the smoke tests to run at all — without it, no test can boot the app via subprocess, blocking the entire plan deliverable.

**2. [Rule 1 - Bug] CSRF middleware false-positives in tests due to httpx cookie-jar persistence**
- **Found during:** Task 1 mid-flight (4 tests failing on 2nd-and-later POSTs)
- **Issue:** httpx.Client persists cookies across requests in its jar. When tests passed `cookies=` per request, httpx **merged** them into the jar (not replaced). Subsequent state-mutating POSTs in the same client auto-attached the persisted session+csrf cookies, flipping DualAuth into cookie-auth mode, which then tripped CsrfMiddleware with 403 "CSRF token missing" because no `X-CSRF-Token` header was present on those follow-up calls. This was masking the actual signals we wanted to test (rate-limit 429, billing 501, cross-user 201, login 200).
- **Fix:** Added `client.cookies.clear()` calls (a) in `_register()` both before and after the register call, (b) between iterations in the rate-limit loop, (c) before the login POST in the round-trip test, (d) before each /billing/webhook POST in the billing-stubs test. Pattern documented inline as "Cookie-jar discipline pattern" in patterns-established.
- **Files modified:** `tests/integration/test_phase13_e2e_smoke.py`
- **Verification:** All 4 previously-failing tests now pass; no spurious 403 CSRF errors anywhere in the suite.
- **Committed in:** `b9de900` (Task 1 atomic commit)
- **Why test-bug not production-bug:** CsrfMiddleware behavior is correct — auto-attached cookie + cookie-auth + state-mutating POST without CSRF header SHOULD return 403. The test was inadvertently triggering this path; the fix is in test setup, not production code.

---

**Total deviations:** 2 auto-fixed (1 Rule 3 blocking + 1 Rule 1 test-side bug; both committed atomically with the test file).
**Impact on plan:** Both fixes essential. Without #1 the smoke tests cannot boot the app at all. Without #2 the smoke tests cannot exercise the contract correctly. No scope creep — both fixes are within the plan's smoke-gate boundary.

## Issues Encountered

- **Pre-existing pytest-timeout absent:** plan suggested `--timeout=180` flag but `pytest-timeout` plugin not in pyproject.toml. Tests pass without it (subprocess boot+drain is the natural ceiling). Logged as decision; deferred as Phase 18 polish.
- **Pre-existing `test_task_lifecycle.py` factory-import error:** module imports `factory` (factory-boy) which is not installed. Already in `.planning/phases/13-atomic-backend-cutover/deferred-items.md` from Phase 13-06. Out of scope for plan 13-10; explicitly ignored when running the wider Phase 13 integration suite (112/112 pass with this exclusion).
- **httpx deprecation warning** about per-request `cookies=<...>` (recommends setting on client): cosmetic; does not affect correctness; would be addressed in Phase 18 polish (refactor to client.cookies.update() per identity context).

## TDD Gate Compliance

Plan type is `execute` (not `tdd`), so RED/GREEN gates do not apply. Single commit uses `feat:` type — correct for new test file + new module-level dependency (utf-8 writers in app/docs.py).

## Next Phase Readiness

- **Phase 14 (frontend cutover):** READY. The atomic backend cutover is now smoke-gated:
  - all 11 must-have truths from the plan frontmatter verified end-to-end against a real subprocess-booted app
  - V2_ENABLED feature flag toggles route registration as designed (404 vs 422 distinction)
  - CORS allowlist correctly echoes FRONTEND_URL with credentials=true and rejects disallowed origins
  - CSRF + bearer auth resolution + rate-limit + disposable-email + billing stubs all behave per contract
  - frontend can ship `/login` + `/register` pages targeting `http://${BACKEND}/auth/{register,login,logout}` with `credentials: 'include'`
- **Phase 15 (polish UI/auth):** unchanged; AUTH-06 logout-all-devices, SCOPE-06 full-account-delete, BILL-05/06 UI, UI-07 dashboard land in Phase 15 against the now-stable Phase 13 stack.
- **Phase 16 (verification):** READY for cross-user matrix tests, JWT attack matrix tests, WS ticket reuse tests, migration smoke tests against the wired stack — those are the FULL test suite while this plan delivered the SMOKE pre-flight.
- **Operational note:** when deploying with `AUTH__V2_ENABLED=true`, ensure `AUTH__JWT_SECRET`, `AUTH__CSRF_SECRET`, `AUTH__FRONTEND_URL`, and `AUTH__COOKIE_SECURE=true` are all set (the AuthSettings model_validator from Phase 13-01 enforces these in production). The smoke-fixture `_build_env` function documents the canonical env-var contract for staging dry-runs.

## Self-Check: PASSED

All files exist on disk; all commit hashes resolved in `git log --all --oneline`:

- `tests/integration/test_phase13_e2e_smoke.py` ✓ (480 LoC, 12 tests)
- `app/docs.py` ✓ (modified — utf-8 writers)
- `app/docs/openapi.json` ✓ (regenerated)
- `app/docs/openapi.yaml` ✓ (regenerated)
- `app/docs/db_schema.md` ✓ (regenerated)
- `.planning/phases/13-atomic-backend-cutover/13-10-SUMMARY.md` ✓ (this file)
- Commit `b9de900` (Task 1 — feat: add Phase 13 e2e smoke test gate) ✓

---

*Phase: 13-atomic-backend-cutover*
*Plan: 10 (e2e smoke gate — Phase 13 close)*
*Completed: 2026-04-29*
