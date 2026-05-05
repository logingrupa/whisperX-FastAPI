# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.2 — Multi-User Auth + API Keys + Billing-Ready

**Shipped:** 2026-05-05
**Phases:** 10 (numbered 10-19) | **Plans:** 62 | **Tasks:** 111

### What Was Built
- **Auth core:** Argon2id password hashing (p99 34.7ms), HS256 cookie session (sliding 7d JWT), CSRF double-submit, anti-enumeration login, rate-limited register/login (3/hr + 10/hr per /24)
- **API key system:** `whsk_<8-prefix>_<22-body>` format, SHA-256 hash + indexed prefix lookup, plaintext shown ONCE, soft-delete via `revoked_at`
- **Dual auth:** single `Depends(authenticated_user)` chain accepts cookie OR Bearer; Bearer skips CSRF (stateless API contract)
- **Per-user scoping:** `tasks.user_id` FK + cross-user 404 on every endpoint, `DELETE /api/account` cascade
- **Free-tier gates:** 5 req/hr, 7-day trial from first key, file/duration/model caps, 402/403/429 mappings with `Retry-After`
- **Stripe-ready schema:** `Subscription`, `UsageEvent`, `plan_tier` enum, `stripe_customer_id` nullable — all live, integration deferred to v1.3
- **Alembic migrations:** 0001_baseline + 0002_auth_schema + 0003_tasks_user_id_not_null with brownfield `records.db` smoke tests
- **Frontend auth shell:** LoginPage / RegisterPage / KeysDashboard / UsageDashboard / AccountPage on react-router-dom + Zustand authStore + BroadcastChannel cross-tab sync
- **Single fetch contract (UI-11):** `frontend/src/lib/apiClient.ts` is the SOLE non-WS network entry — auto-CSRF, 401 redirect with `?next=`, 429 → typed `RateLimitError`
- **Test infrastructure:** Vitest + RTL + MSW (138 tests) + Playwright (8 mocked + 3 real-backend Phase-19 specs) + pytest backend with Argon2 p99 slow-gate
- **Phase 19 structural refactor:** dropped `dependency_injector` library entirely, killed `AUTH_V2_ENABLED` + `DualAuthMiddleware` + `BearerAuthMiddleware` + `CsrfMiddleware`, single `Session` per HTTP request via `get_db`, 21/21 verification gates GREEN
- **Operator runbook:** `docs/migration-v1.2.md` (9 sections, 1:1 with `test_migration_smoke.py`), `.env.example` v1.2 schema (15 vars, 5 subsections), README auth section (3 curl snippets, free-vs-Pro matrix)
- **Admin CLI:** `python -m app.cli create-admin` (getpass, idempotent, plan_tier=pro) + `backfill-tasks` (dry-run, post-verify count==0)

### What Worked
- **Atomic-pair shipping (Phase 13 + 14):** building backend + frontend on a branch behind `AUTH_V2_ENABLED` then flipping in a single deploy avoided the 401-storm scenario where backend cuts over without the SPA having login pages
- **Goal-backward planning:** every phase had explicit success criteria + verification gates BEFORE plans were written; 21-gate Phase-19 matrix caught the session-leak class before it could re-emerge
- **Single-source-of-truth invariants enforced via grep:** `jwt.decode` only inside `jwt_codec.py`, `session.close()` only inside `get_db`, `_container.X()` count == 0 by Phase 19 close — these are CI-checkable, not aspirational
- **TDD on auth core (Phase 11):** 28 unit tests written RED→GREEN before integration; rolling back a regression is a `git revert` not a hunt
- **Tiger-style boundary asserts:** `_require_ffmpeg()` pattern (added in close-out) is now the template for every external-binary call
- **Discuss/research before plan:** Phase 19's CONTEXT.md surfaced the D1-D6 architectural decisions BEFORE any code change — execution was almost mechanical because design was locked

### What Was Inefficient
- **Session-leak class shipped twice (commits `0f7bb09` + `61c9d61`)** before Phase 19 structurally fixed it — three sessions of whack-a-mole patching the same DI lifetime bug. Lesson: when the same bug class returns, stop fixing the symptom and look for the structural cause
- **Login-correct-pw-30s-401 debug session sat open** through most of Phase 19 because the symptom (slow login) and the root cause (session pool starvation) lived in different mental models — the debug-session checkpoint loop helped but the initial framing was off
- **Rate limiter had no test bypass** until v1.2 close-out (`RATE_LIMIT_ENABLED` env var added in commit `d966b03`) — meant repeated e2e runs ate the daily login budget. Should have been added in Phase 13
- **OpenAPI YAML drift:** auto-regen creates noise commits whenever `DEVICE` env or extension-set ordering changes. Worth a deterministic ordering pass + dirty-check in CI before v1.3
- **ffmpeg dependency was implicit** until a user actually uploaded audio post-Phase-19; opaque `WinError 2` 500s for everyone. Lesson: if a binary is required at request-time, probe at boot-time

### Patterns Established
- **`@lru_cache(maxsize=1)` factories** for stateless services + binary probes — pattern locked in `app/core/services.py` AND `app/audio.py:_ffmpeg_path()`
- **Boundary guardrails raising `InfrastructureError`** for external-system failures → 503 + `code` field + correlation_id (instead of opaque 500s). `FFMPEG_MISSING` is the template
- **Single-fetch-site frontend pattern:** `apiClient.ts` is grep-enforceable as the only fetch entry; specs that violate it fail CI
- **Real-backend Playwright project (`phase19-real-backend`)** alongside the mocked `chromium` project — separates UAT-style mocked specs from regression specs that exercise the actual cookie/JWT/CSRF stack end-to-end
- **Atomic-pair labels in ROADMAP:** when two phases MUST ship together (13+14), label them so future-you doesn't half-ship
- **Debug-session-as-artifact:** every non-trivial bug gets a `.planning/debug/<slug>.md` file with hypothesis ladder, evidence log, eliminated branches, and resolution. Resolved sessions move to `.planning/debug/resolved/` for cross-milestone search

### Key Lessons
1. **When a bug class returns, fix the structure, not the symptom.** Two consecutive session-leak commits were the signal that the DI library's lifetime contract was wrong for the codebase; Phase 19 deleted the library rather than patching one more callsite.
2. **External binaries need boot-time probes.** Any `subprocess.run([bare_name, ...])` is an opaque 500 waiting to happen on the first deploy where the binary is missing. Probe at boot, raise typed `InfrastructureError` at request-time, return 503 + a code field — never let `WinError 2` reach the user as `INTERNAL_ERROR`.
3. **Rate limits need a test bypass from day one.** Slowapi without `enabled=False` makes repeated e2e runs eat the per-IP budget for an hour. Cost: a 30-second env-var check at design time saved a full restart cycle at close-out.
4. **Atomic-pair shipping works when the contract is locked first.** Phase 13+14's atomic pair would have been a nightmare without `AUTH_V2_ENABLED` as a single-bit kill switch + identical end-to-end smoke tests on both sides of the flag.
5. **Verification gates must be greppable.** "21 gates" only worked because every gate had a shell command that returns 0 or 1. Soft gates ("does it feel right") would have shipped the leak class for a third time.

### Cost Observations
- Model mix: ~100% Opus 4.7 (quality profile, 1M context); occasional Haiku for trivial reads
- Sessions: ~30+ across the v1.2 timeframe (2026-04-29 → 2026-05-05, ~7 calendar days)
- Notable: Phase 19's discuss → research → plan → execute pipeline kept context per-task under ~50% — much cheaper than the long single-context Phase 13 atomic-pair execution which approached compaction

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 6 | ~30 | Initial GSD adoption, manual phase tracking |
| v1.1 | 3 | ~9 | Chunked uploads layered on existing patterns |
| v1.2 | 10 | 62 | Atomic-pair phases, 21-gate verification matrix, structural refactor as its own phase (19) |

### Cumulative Quality

| Milestone | Backend Tests | Frontend Tests | E2E Specs |
|-----------|---------------|----------------|-----------|
| v1.0 | (limited) | — | — |
| v1.1 | (added TUS smoke) | — | — |
| v1.2 | 500+ pytest nodes (baselined in `tests/baseline_phase19.txt`) | 138 vitest | 8 mocked Playwright + 3 real-backend |

### Top Lessons (Verified Across Milestones)

1. **Lock the contract before writing the code.** v1.0's `ApiResult<T>` discriminated union, v1.1's TUS protocol choice, v1.2's `AUTH_V2_ENABLED` flag — every phase that decided design first executed faster than phases that shipped first and rationalized later.
2. **Single-source-of-truth invariants beat coding conventions.** "Always use the apiClient" is a guideline; `grep -rn 'fetch(' frontend/src/ → 1 hit` is enforcement.
3. **Phase numbering is cheap; phase boundaries are valuable.** Splitting Phase 19 into 17 plans across 7 waves let parallelism emerge naturally and made re-execution after deviations a fraction of the original cost.
