# Project Milestones: WhisperX Frontend UI

## v1.2 Multi-User Auth + API Keys + Billing-Ready (Shipped: 2026-05-05)

**Phases completed:** 10 phases, 62 plans, 111 tasks

**Key accomplishments:**

- Alembic 1.17.0 wired to Config.DB_URL with 0001_baseline revision creating the 19-column tasks table — greenfield upgrade head succeeds, brownfield stamp on records.db keeps all 460 rows intact.
- Six new ORM classes (User, ApiKey, Subscription, UsageEvent, RateLimitBucket, DeviceFingerprint) added on Base.metadata, tasks.user_id FK declared, Task.created_at/updated_at swapped to DRY tz-aware factories — Base.metadata now enumerates 7 tables, factories invoked 9 times, zero `if` statements, zero `relationship` imports, all 9 named constraints (1 CK + 1 IX + 1 UQ + 6 FK) verified at module load.
- Alembic 0002_auth_schema revision authored verbatim from plan: 6 new tables (users, api_keys, subscriptions, usage_events, rate_limit_buckets, device_fingerprints) + tasks.user_id FK + tasks tz-aware datetime ALTER — all named constraints in place, greenfield smoke passes (8 tables created, 8 tables expected), CHECK + UNIQUE constraints fire correctly, downgrade reverses cleanly to baseline shape.
- SQLAlchemy Engine connect-listener enforces SQLite PRAGMA foreign_keys=ON on every new connection (with module-load fail-loud assert), Base.metadata.create_all line removed from app/main.py (Alembic is now the sole schema source), and 7 integration tests prove the migration end-to-end via greenfield + brownfield paths plus CHECK + UNIQUE constraint fires — closing Phase 10's schema-foundation milestone.
- Auth foundation: argon2-cffi/pyjwt deps installed, AuthSettings (6 fields, env_prefix=AUTH__) with production-safety validator, single-source _sha256_hex helper, RedactingFilter wired on whisperX logger, and 9 typed auth exceptions ready for Wave 2 services.
- 6 pure-logic auth core modules — password_hasher (Argon2id), jwt_codec (single jwt.decode site), api_key (whsk_<8>_<22>), csrf (double-submit), device_fingerprint (SHA-256 + IP subnet), rate_limit (pure token bucket) — built test-first with 28 passing unit tests and verifier-grade single-site lockdowns on jwt.decode/jwt.encode and DRY _sha256_hex.
- 4 framework-free domain dataclasses, 4 Protocol-based repository interfaces, 4 ORM<->domain mappers, and 4 SQLAlchemy repositories with verifier-grade rollback + DatabaseOperationError discipline. ApiKeyRepository.get_by_prefix uses idx_api_keys_prefix (KEY-08, O(log n)) and filters revoked_at IS NULL (T-11-12). RateLimitRepository.upsert_atomic wraps read+write in BEGIN IMMEDIATE for SQLite worker-safety (T-11-10). Domain layer remains framework-free with zero SQLAlchemy imports.
- 6 thin orchestration services (PasswordService/TokenService/AuthService/KeyService/RateLimitService/CsrfService) on top of Wave-2 core modules and Wave-3 repositories, plus 4 repository providers and 6 service providers wired into the DI Container with locked Singleton-vs-Factory lifecycles. All 22 service unit tests pass via mocked repositories. Generic InvalidCredentialsError on both login-fail legs (no enumeration). create_key returns plaintext exactly once. JWT_SECRET unwrapped at DI provide-time via SecretStr.get_secret_value.call(). Combined Phase 11 unit count: 50 tests (28 core + 22 service).
- 3 integration-test files (15 tests total) close Phase 11: VERIFY-05 Argon2 p99=34.7ms (well under 300ms budget, slow-gated); DI Container resolves all 6 auth services to instances of correct types via .override(MagicMock()) on db_session_factory; RedactingFilter scrubs password/secret/api_key/token attributes + dict args end-to-end and is verified attached to the whisperX logger. Phase 11 success criteria #4 (DI resolution) and #5 (Argon2 p99 gate) are now verifier-checked.
- Wave 1 foundation: `app/cli/` package with Typer singleton and DRY `_resolve_admin`/`_get_container` helpers, `AuthService.register(plan_tier=)` keyword-only kwarg, typer dep declared. `python -m app.cli --help` exits 0 listing both placeholder subcommands; 6/6 AuthService unit tests green; zero nested-ifs across `app/cli/`.
- Wave 2 (parallel-safe with 12-03): `create-admin` Typer subcommand replaces plan-01 stub. Password read via `getpass.getpass()` twice (NEVER as a flag); delegates to `AuthService.register(email, pw, plan_tier='pro')`. Idempotent on re-run. RED→GREEN TDD across 5 unit tests covering help surface, password mismatch, success path, duplicate-email, weak-password — all 5 green; zero nested ifs; password never logged. OPS-01 satisfied.
- Wave 2 (parallel-safe with 12-02): `backfill-tasks` Typer subcommand replaces plan-01 stub. Reassigns every `tasks.user_id IS NULL` row to a named admin user via single `engine.begin()` transaction. `--dry-run` reports without acting; `--yes`/`-y` skips the y/N prompt. Post-update count==0 verified inside the same transaction — non-zero raises typer.Exit(1) (ROLLBACK + fail-loud per CONTEXT §92). RED→GREEN TDD across 7 unit tests covering help surface, missing admin, zero orphans (idempotent), dry-run, decline-prompt, --yes success, post-verify failure — all 7 green; zero nested ifs; reuses `_resolve_admin` + `_get_container` from plan 12-01. OPS-02 satisfied; SCOPE-01 prerequisite met for plan 12-04.
- Wave 3 closure: `0003_tasks_user_id_not_null` Alembic migration tightens `tasks.user_id` to NOT NULL + adds `idx_tasks_user_id`, gated by a pre-flight orphan-row guard that refuses to run if the operator skipped `backfill-tasks`. Two integration tests exercise the full Phase 12 contract: happy path (fresh DB → 0001+0002 → seed 3 orphans → create-admin → backfill → 0003 → assert NOT NULL + index + new NULL insert raises IntegrityError) and negative path (skip backfill → 0003 fails fast with stderr mentioning orphans/backfill-tasks). 2/2 e2e tests green; 7/7 phase 10 alembic regression tests still green; 35/35 phase 11+12 unit tests still green. SCOPE-01 satisfied; Phase 12 milestone closed.
- `app/core/feature_flags.py`
- 1. [Rule 1 - Bug] /auth/logout did not emit Set-Cookie deletion headers
- 1. [Rule 3 - Blocking issue] Added /billing/webhook to PUBLIC_ALLOWLIST
- 1. Domain Task entity surfaces `user_id`
- Unit (`tests/unit/.../test_sqlalchemy_task_repository_scope.py`) — 14 tests:
- 1. DiarizationParams has no `.diarize` field
- Phase 13 atomic flip — DualAuth+CSRF middleware + 5 Phase 13 routers + 6 typed exception handlers wired into app/main.py behind is_auth_v2_enabled(), with locked-down CORS (FRONTEND_URL allowlist + credentials) and W4 legacy BearerAuthMiddleware fallback retained for the V2-OFF else-branch.
- Atomic backend cutover SMOKE gate: 12 end-to-end tests boot a real ``uvicorn`` subprocess (V2 ON + tmp SQLite DB + alembic-migrated schema) and exercise every locked must-have truth from the Phase 13 contract — register/login/create-key/use-key/logout flow, cross-user 404, ANTI-01 rate-limit fires at 4th register, ANTI-04 disposable-email rejected, ANTI-06 CORS allowlist + credentials echo, BILL-05/06 stubs return 501 / 400 on malformed signature, V2_ENABLED feature-flag toggles route registration, MID-04 CSRF required on cookie POST + bearer skips CSRF — all 12 pass in ~233s.
- Vitest 3.2 + jsdom + RTL 16 + MSW 2.13 test runner online with sentinel passing; shadcn form/input/label/dialog/alert primitives + zustand/react-hook-form/zod runtime deps installed — Plans 02-07 unblocked.
- Single fetch() site for all non-WebSocket HTTP — typed error hierarchy (ApiClientError/AuthRequiredError/RateLimitError), automatic CSRF + credentials, locked 401-redirect / 429-RateLimitError policy, and tiger-style boot assertion. Plans 03-07 unblocked.
- Single source of auth state — Zustand authStore with login/register/logout actions, BroadcastChannel('auth') cross-tab sync (UI-12), and one DRY zod schema file owning login + register validation. All HTTP delegated to apiClient. 8/8 tests pass; Plans 04-06 unblocked.
- `<BrowserRouter basename="/ui">` plus 6 routes plus `<RequireAuth>` Outlet HOC, with the existing transcription UI moved verbatim into `<TranscribePage>` (UI-10 zero-regression). All routes wrap in `<RouteErrorBoundary>` via a shared `PageWrap`; dashboards get an `<AppShell>` top-nav while `/` keeps full-bleed.
- Two production-ready auth pages — `<LoginPage>` and `<RegisterPage>` — wired through `react-hook-form` + zod resolver + Zustand `authStore`, layered on a shared `<AuthCard>` Card-on-page shell. Custom 0..4 password strength scorer (pure function) drives a 4-bar visual meter; anti-enumeration error funnel mirrors backend posture. 48/48 tests pass; UI-02 / UI-03 / UI-13 truths verified.
- Two production-ready dashboards — `<KeysDashboardPage>` (UI-05) with show-once + copy + revoke confirmation flow, and `<UsageDashboardPage>` (UI-06) with `plan_tier` Badge + 7-day trial countdown — plus a `<LogoutButton>` mounted into AppShell. All key HTTP funnels through a typed `keysApi` wrapper. 6 new integration tests via MSW (54/54 total green); tsc clean; build clean.
- Three direct-fetch sites in production code eliminated; apiClient.ts is now the SOLE fetch call site in frontend/src (UI-11 invariant locked, CI-grep-enforceable). Added a WS-ticket helper that requests a single-use 60s token via apiClient before opening the WebSocket connection (MID-06 client enforcement). Added TEST-06 regression smoke (3 tests) proving the cutover did not break the existing TranscribePage UploadDropzone + queue + start-affordance UX. 57/57 tests green, build clean, tsc clean.
- Files exist:
- 1. [Rule 1 - Bug] Removed literal `Depends(Response)` from docstring
- GET /api/account/me wired to AccountService.get_account_summary — server-authoritative AccountSummaryResponse hydration source for Plan 15-05 authStore.refresh() and Plan 15-06 AccountPage.
- DELETE /api/account end-to-end with 3-step service-orchestrated cascade (tasks → rate_limit_buckets → user→ORM CASCADE), email-confirm guard (case-insensitive), and cookie clearing — SCOPE-06 closed.
- authStore.refresh() + isHydrating + RequireAuth 3-state gate + main.tsx boot probe — closes Plan 14-03 user-null-on-reload gap; server is authoritative on every page load.
- Three-card account dashboard (Profile / Plan / Danger Zone) with shadcn Dialog primitives for upgrade-interest capture, type-exact-email account deletion, and cross-tab logout-all — closes UI-07 and wires UI-side of AUTH-06/SCOPE-06/BILL-05.
- Single 269-line DRT helper module exporting 7 helpers + ENDPOINT_CATALOG (8 entries) + WS_POLICY_VIOLATION constant — consumed unchanged by plans 16-02..06 to keep verification tests file-disjoint and parallel-safe.
- 17 parametrized integration tests (8 foreign-leg cases, 8 self-leg positive controls, 1 anti-enumeration body-parity assertion) prove that User A's tasks/keys/usage are invisible to User B across every task-touching endpoint — the milestone-gate invariant for VERIFY-01.
- 1. [Rule 1 — Bug] Container settings provider is named `config`, not `settings`
- Locked VERIFY-06 — 4 pytest integration cases prove CsrfMiddleware enforces double-submit on cookie auth and skips bearer-auth surfaces (MID-04), all on `/auth/logout-all` as the single CSRF target.
- VERIFY-07 closed: WS ticket reuse, TTL expiry (mocked clock), and cross-user drift each force a 1008 close — proves WsTicketService atomic single-use + 60s TTL + handler defence-in-depth all enforce.
- Synthetic v1.1 baseline → alembic stamp 0001 → upgrade 0002 → seed admin → upgrade head: 4 brownfield migration smoke tests asserting row preservation, tasks.user_id NOT NULL constraint application, and FK enforcement via deliberate orphan INSERT.
- Operator-followable 9-section migration runbook (`docs/migration-v1.2.md`) mirroring `test_migration_smoke.py` 1:1, delivering OPS-03.
- Operator-facing v1.2 env var schema (15 vars, 5 subsections) appended to `.env.example` delivering OPS-04.
- README.md gains a `## Authentication & API Keys (v1.2)` top-level section (5 subheadings, 3 curl snippets, free-vs-Pro tier matrix, mailto reset link, cross-link to migration runbook) delivering OPS-05.
- 500-node pytest collection inventory pinned to tests/baseline_phase19.txt as the end-of-phase regression diff anchor; Phase 13 atomic-cutover lock waiver entry confirmed in .planning/DEVIATIONS.md.
- Module-level @lru_cache(maxsize=1) factory cluster (`app/core/services.py`) for 9 stateless services — D1 replacement pattern locked, Container coexists, full suite delta zero.
- Phase 19's request-scope Session lifecycle owner (`get_db`) plus 12 chained `_v2` providers (5 repos + 7 services) appended to `app/api/dependencies.py`; legacy `_container.X()` providers untouched (coexistence). Single Session per HTTP request via FastAPI dep cache — D2 architectural lock executed verbatim.
- 1. [Rule 3 - Blocking] Test fixture needed key_router + middleware to seat bearer keys
- 1. [Rule 1 - Bug] Docstring grep-gate tax for `_container`
- 1. [Rule 3 - Blocking] Test fixture get_db override + X-CSRF-Token plumbing
- 5 router families (`auth`, `key`, `billing`, `task`, `ws_ticket`) migrated to the Phase 19 `Depends(authenticated_user)` + router-level `Depends(csrf_protected)` chain. `billing_router` split into auth + webhook variants. `ws_ticket_service` unified on the `app.core.services` lru-cached singleton so HTTP-issue and WS-consume paths share the same in-memory ticket dict.
- WS handler in `app/api/websocket_api.py` migrated to explicit `with SessionLocal() as db:` block (context-manager owns close) + `app.core.services.get_ws_ticket_service` singleton. Zero `_container` references remain.
- `app/services/whisperx_wrapper_service.py` worker rewritten to use a single `with SessionLocal() as db:` context manager. Three `_container.X()` callsites eliminated. New module-scope `_release_slot_if_authed` flat-guard helper replaces the previous nested-if in finally — CLAUDE.md tiger-style restored.
- 14 integration test fixtures + 3 deps tests + 1 fixture stub migrated to `app.dependency_overrides[get_db]` as the sole DB-binding seam — atomic-commit invariant preserved for Plans 11-13 deletions of DualAuthMiddleware / CsrfMiddleware / Container.
- Atomic deletion of 4 source files (DualAuth + BearerAuth modules + 23 obsolete unit tests) + comment cleanup across 7 files; structural invariant `grep -rn 'DualAuthMiddleware|BearerAuthMiddleware|AUTH_V2_ENABLED|is_auth_v2_enabled' app/` collapses from 36 hits to 0.
- 1. [Rule 2 — Preserve coverage] Relocated TestGetAuthenticatedUser before deleting test module
- D1 final closure — single-namespace Depends chain in app/api/dependencies.py; dependency_injector library + Container module + last `Container()` instantiation gone; CLI helpers migrated to a Container-shaped facade backed by lru-cached singletons.
- One-liner:
- Belt-and-suspenders autouse cleanup fixtures + frontend regression gate green: REFACTOR-07 wire-byte equivalence verified end-to-end (138 vitest + 8 Playwright GREEN against Phase-19 refactored backend).
- Single literal session.close() callsite enforced (get_db only); UoW dead-code deleted; CONTEXT.md gate 2 + VALIDATION.md G2 wording aligned with implementation (TWO→ONE match)
- Phase 19 verification ceremony — 21 gates run; 20 PASS, 1 superseded, 2 manual residue; 19-VERIFICATION.md committed; phase status `human_needed` pending 2 browser-only checks.

---

## v1.2 Multi-User Auth + API Keys + Billing-Ready (Shipped: 2026-05-05)

**Phases completed:** 10 phases, 62 plans, 111 tasks

**Key accomplishments:**

- Alembic 1.17.0 wired to Config.DB_URL with 0001_baseline revision creating the 19-column tasks table — greenfield upgrade head succeeds, brownfield stamp on records.db keeps all 460 rows intact.
- Six new ORM classes (User, ApiKey, Subscription, UsageEvent, RateLimitBucket, DeviceFingerprint) added on Base.metadata, tasks.user_id FK declared, Task.created_at/updated_at swapped to DRY tz-aware factories — Base.metadata now enumerates 7 tables, factories invoked 9 times, zero `if` statements, zero `relationship` imports, all 9 named constraints (1 CK + 1 IX + 1 UQ + 6 FK) verified at module load.
- Alembic 0002_auth_schema revision authored verbatim from plan: 6 new tables (users, api_keys, subscriptions, usage_events, rate_limit_buckets, device_fingerprints) + tasks.user_id FK + tasks tz-aware datetime ALTER — all named constraints in place, greenfield smoke passes (8 tables created, 8 tables expected), CHECK + UNIQUE constraints fire correctly, downgrade reverses cleanly to baseline shape.
- SQLAlchemy Engine connect-listener enforces SQLite PRAGMA foreign_keys=ON on every new connection (with module-load fail-loud assert), Base.metadata.create_all line removed from app/main.py (Alembic is now the sole schema source), and 7 integration tests prove the migration end-to-end via greenfield + brownfield paths plus CHECK + UNIQUE constraint fires — closing Phase 10's schema-foundation milestone.
- Auth foundation: argon2-cffi/pyjwt deps installed, AuthSettings (6 fields, env_prefix=AUTH__) with production-safety validator, single-source _sha256_hex helper, RedactingFilter wired on whisperX logger, and 9 typed auth exceptions ready for Wave 2 services.
- 6 pure-logic auth core modules — password_hasher (Argon2id), jwt_codec (single jwt.decode site), api_key (whsk_<8>_<22>), csrf (double-submit), device_fingerprint (SHA-256 + IP subnet), rate_limit (pure token bucket) — built test-first with 28 passing unit tests and verifier-grade single-site lockdowns on jwt.decode/jwt.encode and DRY _sha256_hex.
- 4 framework-free domain dataclasses, 4 Protocol-based repository interfaces, 4 ORM<->domain mappers, and 4 SQLAlchemy repositories with verifier-grade rollback + DatabaseOperationError discipline. ApiKeyRepository.get_by_prefix uses idx_api_keys_prefix (KEY-08, O(log n)) and filters revoked_at IS NULL (T-11-12). RateLimitRepository.upsert_atomic wraps read+write in BEGIN IMMEDIATE for SQLite worker-safety (T-11-10). Domain layer remains framework-free with zero SQLAlchemy imports.
- 6 thin orchestration services (PasswordService/TokenService/AuthService/KeyService/RateLimitService/CsrfService) on top of Wave-2 core modules and Wave-3 repositories, plus 4 repository providers and 6 service providers wired into the DI Container with locked Singleton-vs-Factory lifecycles. All 22 service unit tests pass via mocked repositories. Generic InvalidCredentialsError on both login-fail legs (no enumeration). create_key returns plaintext exactly once. JWT_SECRET unwrapped at DI provide-time via SecretStr.get_secret_value.call(). Combined Phase 11 unit count: 50 tests (28 core + 22 service).
- 3 integration-test files (15 tests total) close Phase 11: VERIFY-05 Argon2 p99=34.7ms (well under 300ms budget, slow-gated); DI Container resolves all 6 auth services to instances of correct types via .override(MagicMock()) on db_session_factory; RedactingFilter scrubs password/secret/api_key/token attributes + dict args end-to-end and is verified attached to the whisperX logger. Phase 11 success criteria #4 (DI resolution) and #5 (Argon2 p99 gate) are now verifier-checked.
- Wave 1 foundation: `app/cli/` package with Typer singleton and DRY `_resolve_admin`/`_get_container` helpers, `AuthService.register(plan_tier=)` keyword-only kwarg, typer dep declared. `python -m app.cli --help` exits 0 listing both placeholder subcommands; 6/6 AuthService unit tests green; zero nested-ifs across `app/cli/`.
- Wave 2 (parallel-safe with 12-03): `create-admin` Typer subcommand replaces plan-01 stub. Password read via `getpass.getpass()` twice (NEVER as a flag); delegates to `AuthService.register(email, pw, plan_tier='pro')`. Idempotent on re-run. RED→GREEN TDD across 5 unit tests covering help surface, password mismatch, success path, duplicate-email, weak-password — all 5 green; zero nested ifs; password never logged. OPS-01 satisfied.
- Wave 2 (parallel-safe with 12-02): `backfill-tasks` Typer subcommand replaces plan-01 stub. Reassigns every `tasks.user_id IS NULL` row to a named admin user via single `engine.begin()` transaction. `--dry-run` reports without acting; `--yes`/`-y` skips the y/N prompt. Post-update count==0 verified inside the same transaction — non-zero raises typer.Exit(1) (ROLLBACK + fail-loud per CONTEXT §92). RED→GREEN TDD across 7 unit tests covering help surface, missing admin, zero orphans (idempotent), dry-run, decline-prompt, --yes success, post-verify failure — all 7 green; zero nested ifs; reuses `_resolve_admin` + `_get_container` from plan 12-01. OPS-02 satisfied; SCOPE-01 prerequisite met for plan 12-04.
- Wave 3 closure: `0003_tasks_user_id_not_null` Alembic migration tightens `tasks.user_id` to NOT NULL + adds `idx_tasks_user_id`, gated by a pre-flight orphan-row guard that refuses to run if the operator skipped `backfill-tasks`. Two integration tests exercise the full Phase 12 contract: happy path (fresh DB → 0001+0002 → seed 3 orphans → create-admin → backfill → 0003 → assert NOT NULL + index + new NULL insert raises IntegrityError) and negative path (skip backfill → 0003 fails fast with stderr mentioning orphans/backfill-tasks). 2/2 e2e tests green; 7/7 phase 10 alembic regression tests still green; 35/35 phase 11+12 unit tests still green. SCOPE-01 satisfied; Phase 12 milestone closed.
- `app/core/feature_flags.py`
- 1. [Rule 1 - Bug] /auth/logout did not emit Set-Cookie deletion headers
- 1. [Rule 3 - Blocking issue] Added /billing/webhook to PUBLIC_ALLOWLIST
- 1. Domain Task entity surfaces `user_id`
- Unit (`tests/unit/.../test_sqlalchemy_task_repository_scope.py`) — 14 tests:
- 1. DiarizationParams has no `.diarize` field
- Phase 13 atomic flip — DualAuth+CSRF middleware + 5 Phase 13 routers + 6 typed exception handlers wired into app/main.py behind is_auth_v2_enabled(), with locked-down CORS (FRONTEND_URL allowlist + credentials) and W4 legacy BearerAuthMiddleware fallback retained for the V2-OFF else-branch.
- Atomic backend cutover SMOKE gate: 12 end-to-end tests boot a real ``uvicorn`` subprocess (V2 ON + tmp SQLite DB + alembic-migrated schema) and exercise every locked must-have truth from the Phase 13 contract — register/login/create-key/use-key/logout flow, cross-user 404, ANTI-01 rate-limit fires at 4th register, ANTI-04 disposable-email rejected, ANTI-06 CORS allowlist + credentials echo, BILL-05/06 stubs return 501 / 400 on malformed signature, V2_ENABLED feature-flag toggles route registration, MID-04 CSRF required on cookie POST + bearer skips CSRF — all 12 pass in ~233s.
- Vitest 3.2 + jsdom + RTL 16 + MSW 2.13 test runner online with sentinel passing; shadcn form/input/label/dialog/alert primitives + zustand/react-hook-form/zod runtime deps installed — Plans 02-07 unblocked.
- Single fetch() site for all non-WebSocket HTTP — typed error hierarchy (ApiClientError/AuthRequiredError/RateLimitError), automatic CSRF + credentials, locked 401-redirect / 429-RateLimitError policy, and tiger-style boot assertion. Plans 03-07 unblocked.
- Single source of auth state — Zustand authStore with login/register/logout actions, BroadcastChannel('auth') cross-tab sync (UI-12), and one DRY zod schema file owning login + register validation. All HTTP delegated to apiClient. 8/8 tests pass; Plans 04-06 unblocked.
- `<BrowserRouter basename="/ui">` plus 6 routes plus `<RequireAuth>` Outlet HOC, with the existing transcription UI moved verbatim into `<TranscribePage>` (UI-10 zero-regression). All routes wrap in `<RouteErrorBoundary>` via a shared `PageWrap`; dashboards get an `<AppShell>` top-nav while `/` keeps full-bleed.
- Two production-ready auth pages — `<LoginPage>` and `<RegisterPage>` — wired through `react-hook-form` + zod resolver + Zustand `authStore`, layered on a shared `<AuthCard>` Card-on-page shell. Custom 0..4 password strength scorer (pure function) drives a 4-bar visual meter; anti-enumeration error funnel mirrors backend posture. 48/48 tests pass; UI-02 / UI-03 / UI-13 truths verified.
- Two production-ready dashboards — `<KeysDashboardPage>` (UI-05) with show-once + copy + revoke confirmation flow, and `<UsageDashboardPage>` (UI-06) with `plan_tier` Badge + 7-day trial countdown — plus a `<LogoutButton>` mounted into AppShell. All key HTTP funnels through a typed `keysApi` wrapper. 6 new integration tests via MSW (54/54 total green); tsc clean; build clean.
- Three direct-fetch sites in production code eliminated; apiClient.ts is now the SOLE fetch call site in frontend/src (UI-11 invariant locked, CI-grep-enforceable). Added a WS-ticket helper that requests a single-use 60s token via apiClient before opening the WebSocket connection (MID-06 client enforcement). Added TEST-06 regression smoke (3 tests) proving the cutover did not break the existing TranscribePage UploadDropzone + queue + start-affordance UX. 57/57 tests green, build clean, tsc clean.
- Files exist:
- 1. [Rule 1 - Bug] Removed literal `Depends(Response)` from docstring
- GET /api/account/me wired to AccountService.get_account_summary — server-authoritative AccountSummaryResponse hydration source for Plan 15-05 authStore.refresh() and Plan 15-06 AccountPage.
- DELETE /api/account end-to-end with 3-step service-orchestrated cascade (tasks → rate_limit_buckets → user→ORM CASCADE), email-confirm guard (case-insensitive), and cookie clearing — SCOPE-06 closed.
- authStore.refresh() + isHydrating + RequireAuth 3-state gate + main.tsx boot probe — closes Plan 14-03 user-null-on-reload gap; server is authoritative on every page load.
- Three-card account dashboard (Profile / Plan / Danger Zone) with shadcn Dialog primitives for upgrade-interest capture, type-exact-email account deletion, and cross-tab logout-all — closes UI-07 and wires UI-side of AUTH-06/SCOPE-06/BILL-05.
- Single 269-line DRT helper module exporting 7 helpers + ENDPOINT_CATALOG (8 entries) + WS_POLICY_VIOLATION constant — consumed unchanged by plans 16-02..06 to keep verification tests file-disjoint and parallel-safe.
- 17 parametrized integration tests (8 foreign-leg cases, 8 self-leg positive controls, 1 anti-enumeration body-parity assertion) prove that User A's tasks/keys/usage are invisible to User B across every task-touching endpoint — the milestone-gate invariant for VERIFY-01.
- 1. [Rule 1 — Bug] Container settings provider is named `config`, not `settings`
- Locked VERIFY-06 — 4 pytest integration cases prove CsrfMiddleware enforces double-submit on cookie auth and skips bearer-auth surfaces (MID-04), all on `/auth/logout-all` as the single CSRF target.
- VERIFY-07 closed: WS ticket reuse, TTL expiry (mocked clock), and cross-user drift each force a 1008 close — proves WsTicketService atomic single-use + 60s TTL + handler defence-in-depth all enforce.
- Synthetic v1.1 baseline → alembic stamp 0001 → upgrade 0002 → seed admin → upgrade head: 4 brownfield migration smoke tests asserting row preservation, tasks.user_id NOT NULL constraint application, and FK enforcement via deliberate orphan INSERT.
- Operator-followable 9-section migration runbook (`docs/migration-v1.2.md`) mirroring `test_migration_smoke.py` 1:1, delivering OPS-03.
- Operator-facing v1.2 env var schema (15 vars, 5 subsections) appended to `.env.example` delivering OPS-04.
- README.md gains a `## Authentication & API Keys (v1.2)` top-level section (5 subheadings, 3 curl snippets, free-vs-Pro tier matrix, mailto reset link, cross-link to migration runbook) delivering OPS-05.
- 500-node pytest collection inventory pinned to tests/baseline_phase19.txt as the end-of-phase regression diff anchor; Phase 13 atomic-cutover lock waiver entry confirmed in .planning/DEVIATIONS.md.
- Module-level @lru_cache(maxsize=1) factory cluster (`app/core/services.py`) for 9 stateless services — D1 replacement pattern locked, Container coexists, full suite delta zero.
- Phase 19's request-scope Session lifecycle owner (`get_db`) plus 12 chained `_v2` providers (5 repos + 7 services) appended to `app/api/dependencies.py`; legacy `_container.X()` providers untouched (coexistence). Single Session per HTTP request via FastAPI dep cache — D2 architectural lock executed verbatim.
- 1. [Rule 3 - Blocking] Test fixture needed key_router + middleware to seat bearer keys
- 1. [Rule 1 - Bug] Docstring grep-gate tax for `_container`
- 1. [Rule 3 - Blocking] Test fixture get_db override + X-CSRF-Token plumbing
- 5 router families (`auth`, `key`, `billing`, `task`, `ws_ticket`) migrated to the Phase 19 `Depends(authenticated_user)` + router-level `Depends(csrf_protected)` chain. `billing_router` split into auth + webhook variants. `ws_ticket_service` unified on the `app.core.services` lru-cached singleton so HTTP-issue and WS-consume paths share the same in-memory ticket dict.
- WS handler in `app/api/websocket_api.py` migrated to explicit `with SessionLocal() as db:` block (context-manager owns close) + `app.core.services.get_ws_ticket_service` singleton. Zero `_container` references remain.
- `app/services/whisperx_wrapper_service.py` worker rewritten to use a single `with SessionLocal() as db:` context manager. Three `_container.X()` callsites eliminated. New module-scope `_release_slot_if_authed` flat-guard helper replaces the previous nested-if in finally — CLAUDE.md tiger-style restored.
- 14 integration test fixtures + 3 deps tests + 1 fixture stub migrated to `app.dependency_overrides[get_db]` as the sole DB-binding seam — atomic-commit invariant preserved for Plans 11-13 deletions of DualAuthMiddleware / CsrfMiddleware / Container.
- Atomic deletion of 4 source files (DualAuth + BearerAuth modules + 23 obsolete unit tests) + comment cleanup across 7 files; structural invariant `grep -rn 'DualAuthMiddleware|BearerAuthMiddleware|AUTH_V2_ENABLED|is_auth_v2_enabled' app/` collapses from 36 hits to 0.
- 1. [Rule 2 — Preserve coverage] Relocated TestGetAuthenticatedUser before deleting test module
- D1 final closure — single-namespace Depends chain in app/api/dependencies.py; dependency_injector library + Container module + last `Container()` instantiation gone; CLI helpers migrated to a Container-shaped facade backed by lru-cached singletons.
- One-liner:
- Belt-and-suspenders autouse cleanup fixtures + frontend regression gate green: REFACTOR-07 wire-byte equivalence verified end-to-end (138 vitest + 8 Playwright GREEN against Phase-19 refactored backend).
- Single literal session.close() callsite enforced (get_db only); UoW dead-code deleted; CONTEXT.md gate 2 + VALIDATION.md G2 wording aligned with implementation (TWO→ONE match)
- Phase 19 verification ceremony — 21 gates run; 20 PASS, 1 superseded, 2 manual residue; 19-VERIFICATION.md committed; phase status `human_needed` pending 2 browser-only checks.

---

## v1.0 Frontend UI (Shipped: 2026-01-29)

**Delivered:** Production-ready web interface for audio/video transcription with real-time progress, speaker diarization, and multi-format export.

**Phases completed:** 1-6 (21 plans total)

**Key accomplishments:**

- WebSocket real-time progress system with stage indicators and reconnection handling
- Streaming upload infrastructure for large files (up to 5GB) with magic byte validation
- React SPA embedded in FastAPI at /ui with client-side routing
- Drag-and-drop upload UI with auto language detection from A03/A04/A05 filename patterns
- Live progress tracking with exponential backoff reconnection and polling fallback
- Transcript viewer with timestamps, speaker labels, and SRT/VTT/TXT/JSON export

**Stats:**

- 83 files created/modified
- 3,075 lines of TypeScript/TSX (frontend)
- 7 phases, 21 plans
- 3 days from start to ship (2026-01-27 → 2026-01-29)

**Git range:** `feat(01-01)` → `docs(05): complete`

**What's next:** v1.1 enhancements (upload progress with speed/ETA, step timing display, persistence on refresh) or new features.

---

## v1.1 Chunked Uploads (Shipped through Phase 9: 2026-02-05)

**Delivered:** TUS-protocol resumable chunked uploads — large files reach the backend through Cloudflare via 50MB chunks; resilient retry/cancel/resume on the frontend.

**Phases completed:** 7-9 (8 plans). Phase 10 (Cloudflare e2e) deferred to v1.3 because v1.2 auth retrofit blocks the frontend NOW.

**Key accomplishments:**

- TUS protocol resumable upload backend with tuspyserver
- Server-side chunk reassembly + transcription trigger hook
- 10-minute incomplete-session cleanup scheduler
- TUS frontend client with file size routing (≥80MB → TUS)
- Single smooth progress bar with speed (MB/s) + ETA
- Exponential backoff retry [1s, 2s, 4s] + permanent-error classifier
- Cancel button + retrying indicator + classified error UI
- localStorage-backed resume on page refresh

**Stats:**

- 8 plans across 3 phases
- Average plan duration: 2.9 minutes
- v1.1 phase 10 deferred → v1.3 (3 INTEG-* requirements)

**Git range:** `feat(07-01)` → `feat(09-02)`

**What's next:** v1.2 — multi-user auth retrofit (the deferred phase 10 follows in v1.3 once auth lands).

---

## v1.2 Multi-User Auth + API Keys + Billing-Ready (In progress — Started 2026-04-29)

**Target:** Convert trusted-deploy single-user app into multi-tenant SaaS with self-serve registration, per-user API keys, free-tier rate limits, and Stripe-ready billing schema.

**Target date:** TBD

**Status:** In progress — Roadmap created 2026-04-29; Phase 10 plan-phase next.

**Phases planned:** 10-18 (9 phases). Phases 13 + 14 deploy as **atomic pair**.

- Phase 10: Alembic Baseline + Auth Schema (silent infra)
- Phase 11: Auth Core Modules + Services + DI (silent infra)
- Phase 12: Admin CLI + Task Backfill (silent infra, pre-cutover)
- Phase 13: Atomic Backend Cutover **(ATOMIC PAIR with 14)**
- Phase 14: Atomic Frontend Cutover + Test Infra **(ATOMIC PAIR with 13)**
- Phase 15: Account Dashboard Hardening + Billing Stubs
- Phase 16: Verification + Cross-User Matrix + E2E
- Phase 17: Docs + Migration Runbook + Operator Guide
- Phase 18: Stretch (Optional)

**Requirements coverage:** 95/95 mapped (100%)

**Headline features:**

- Email/password registration + login (cookie session HS256 JWT, 7d sliding, CSRF-protected)
- Argon2id password hashing (OWASP `m=19456 KiB, t=2, p=1`)
- Per-user API keys (`whsk_<prefix>_<random>`, sha256-hashed, prefix-indexed)
- Dual-auth middleware (cookie session + bearer API key)
- Per-user task scoping (`tasks.user_id` FK + repository-layer WHERE filter)
- IP-locked register/login throttling (3/hr + 10/hr per /24)
- Device fingerprint logging
- Free-tier gates (5 req/hr, 5min file, 30min/day, tiny/small models only, 7d trial)
- Stripe-ready schema (Subscription, UsageEvent, plan_tier enum) — €5/mo Pro stub
- Alembic migrations replace `Base.metadata.create_all()`
- Auth UI pages (login, register, dashboard/keys, dashboard/usage, dashboard/account)
- Vitest + RTL + MSW frontend test infra
- Bootstrap admin CLI (`python -m app.cli create-admin`)

**Git range:** TBD

**What's next (post-v1.2 → v1.3):** Real Stripe integration (FUTURE-01), single-GPU concurrency queue (FUTURE-02), Cloudflare e2e validation (FUTURE-03 — was v1.1 phase 10), SMTP email (FUTURE-04).

---
*Last updated: 2026-04-29 — v1.2 roadmap appended (Multi-User Auth + API Keys + Billing-Ready, 9 phases 10-18)*
