---
phase: 19
slug: auth-di-refactor
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-02
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source of truth: 19-RESEARCH.md `## Validation Architecture` section (Dimension 8).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest 8.x via `.venv/Scripts/python.exe -m pytest` |
| **Framework (frontend)** | vitest 2.x + Playwright (chromium) |
| **Backend config** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Frontend config** | `frontend/vitest.config.ts`, `frontend/playwright.config.ts` |
| **Quick run command (backend)** | `.venv/Scripts/python.exe -m pytest tests/ -x --tb=short` |
| **Quick run command (frontend)** | `cd frontend && bun run test` |
| **Full suite command** | `.venv/Scripts/python.exe -m pytest tests/ --tb=short && cd frontend && bun run test && bun run test:e2e` |
| **Estimated runtime** | ~90s backend + ~30s vitest + ~120s playwright = ~4 min full |

---

## Sampling Rate

- **After every task commit:** Run quick backend suite (~90s).
- **After every plan wave:** Run full backend suite + greppable invariants.
- **Before phase verification:** Full suite (backend + frontend + e2e) must be green.
- **Max feedback latency:** 90s per commit.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|--------|
| 19-01 | 01 | 0 | REFACTOR-06 | Pin baseline test inventory | manual + commit | `pytest --collect-only -q > tests/baseline_phase19.txt` | ⬜ |
| 19-02 | 02 | 1 | REFACTOR-05 | Module-level singletons via @lru_cache | unit | `pytest tests/unit/test_services_module.py` | ⬜ |
| 19-03 | 03 | 1 | REFACTOR-02 | get_db yields Session, closes finally | unit | `pytest tests/unit/test_dependencies_get_db.py` | ⬜ |
| 19-04 | 04 | 2 | REFACTOR-03 | authenticated_user resolves bearer-then-cookie | integration | `pytest tests/integration/test_authenticated_user_dep.py` | ⬜ |
| 19-05 | 05 | 2 | REFACTOR-03 | csrf_protected dep enforces header pair | integration | `pytest tests/integration/test_csrf_protected_dep.py` | ⬜ |
| 19-06 | 06 | 3 | REFACTOR-03 | /api/account/me uses Depends, suite green | integration | `pytest tests/integration/test_account_routes.py` | ⬜ |
| 19-07 | 07 | 3 | REFACTOR-03 | All routers migrated to Depends | integration | `pytest tests/integration/test_*_routes.py` | ⬜ |
| 19-08 | 08 | 4 | REFACTOR-03 | WS uses explicit SessionLocal block | integration | `pytest tests/integration/test_websocket_*.py` | ⬜ |
| 19-09 | 09 | 4 | REFACTOR-02 | Background task uses with SessionLocal() | integration | `pytest tests/integration/test_whisperx_wrapper.py` | ⬜ |
| 19-10 | 10 | 5 | REFACTOR-04 | DualAuth + BearerAuth + AUTH_V2 deleted | grep + integration | `grep -rn 'DualAuthMiddleware\|BearerAuthMiddleware\|AUTH_V2_ENABLED' app/` → 0 | ⬜ |
| 19-11 | 11 | 5 | REFACTOR-03 | CsrfMiddleware class deleted | grep | `grep -rn 'class CsrfMiddleware' app/` → 0 | ⬜ |
| 19-12 | 12 | 6 | REFACTOR-01 + 05 | container.py deleted | grep | `grep -rn '_container\.\|dependency_injector' app/` → 0 | ⬜ |
| 19-13 | 13 | 6 | REFACTOR-06 | No-leak regression test added | integration | `pytest tests/integration/test_no_session_leak.py` | ⬜ |
| 19-14 | 14 | 7 | REFACTOR-07 | Frontend e2e green (Set-Cookie byte-identical) | e2e | `cd frontend && bun run test && bun run test:e2e` | ⬜ |
| 19-15 | 15 | 7 | DRY/SRP | Dead code sweep | grep | `grep -rn 'session\.close()\|PUBLIC_ALLOWLIST\|set_container' app/` → expected exact set | ⬜ |
| 19-16 | 16 | 7 | All | Final 21-gate verification | manual + suite | All gates from 19-CONTEXT.md `## Verification gates` pass | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Greppable Invariants (CI-enforceable)

After T-19-12 these MUST hold (run as a CI gate in T-19-16):

| # | Invariant | Command | Expected |
|---|-----------|---------|----------|
| G1 | No container callsites | `grep -rn '_container\.' app/` | 0 |
| G2 | Single session.close site | `grep -rn 'session\.close()' app/` | exactly 2 (get_db + WhisperX background) |
| G3 | dependency_injector deleted | `grep -rn 'dependency_injector' app/` | 0 |
| G4 | AUTH_V2 + legacy middleware deleted | `grep -rn 'AUTH_V2_ENABLED\|is_auth_v2_enabled\|BearerAuthMiddleware\|DualAuthMiddleware' app/` | 0 |
| G5 | No nested if-in-if-in-if | `grep -rn '            if ' app/api/dependencies.py` | 0 (tiger-style) |

---

## Wave 0 Requirements

- [ ] `tests/baseline_phase19.txt` — frozen pytest inventory pre-refactor (T-19-01)
- [ ] `.planning/DEVIATIONS.md` — Phase 13 architectural lock waiver entry (T-19-01)
- [ ] No new framework install — pytest + vitest + playwright already wired

---

## Behavior Preservation Gates (each test must stay green per task)

- POST `/auth/register` → 201 + `Set-Cookie: session` + `Set-Cookie: csrf_token`
- POST `/auth/login` correct creds → 200 (< 100ms after T-19-13)
- POST `/auth/login` wrong creds → 401 INVALID_CREDENTIALS body
- GET `/api/account/me` with valid cookie → 200 (boot probe — fixes "reload asks login")
- POST `/auth/logout-all` without `X-CSRF-Token` → 403
- Bearer GET `/api/account/me` → 200 (Authorization wins over cookie)
- Tampered JWT → 401
- Stale cookie + POST `/auth/login` → reaches route, returns INVALID_CREDENTIALS (recovery flow not blocked)
- WebSocket: valid ticket → upgraded; expired ticket → 4001 close

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hard-reload signed-in user lands on `/` (not `/ui/login`) | REFACTOR-03 | Browser-only behavior; backend session leak indirectly causes boot probe to time out | After T-19-13 green: login → wait for redirect → Ctrl+Shift+R → must remain on `/` |
| Network panel: login responds < 1s | User-stated bug | Wall-clock perf, browser observed | After T-19-12 green: 20 sequential logins all complete < 1s in DevTools Network |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All 16 tasks have automated verification command OR Wave 0 dependency
- [ ] Sampling continuity: every task has command, no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers baseline pytest inventory + DEVIATIONS waiver
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s per commit
- [ ] `nyquist_compliant: true` set in frontmatter (after Wave 0 in T-19-01)

**Approval:** pending
