---
phase: 16
slug: verification-cross-user-matrix-e2e
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-30
---

# Phase 16 — Validation Strategy

> Verification-only phase. Tests ARE the deliverable. Quick command runs each test file in isolation; full suite gates milestone close.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + httpx TestClient + alembic subprocess |
| **Config files** | `pyproject.toml`, `tests/conftest.py`, `tests/integration/conftest.py` |
| **Quick run command** | `pytest tests/integration/test_security_matrix.py tests/integration/test_jwt_attacks.py tests/integration/test_csrf_enforcement.py tests/integration/test_ws_ticket_safety.py tests/integration/test_migration_smoke.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~45–60 seconds (matrix subprocess alembic dominates) |

---

## Sampling Rate

- **After every task commit:** Run that task's specific test file
- **After every plan wave:** Quick run command (5 files)
- **Before milestone close:** Full suite green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 0 | — | T-16-04 | _phase16_helpers exports ENDPOINT_CATALOG, _seed_two_users, _forge_jwt, _issue_csrf_pair, _run_alembic, WS_POLICY_VIOLATION | unit | `python -c "from tests.integration import _phase16_helpers; assert hasattr(_phase16_helpers, 'ENDPOINT_CATALOG')"` | ❌ W0 | ⬜ pending |
| 16-02-01 | 02 | 1 | VERIFY-01 | T-16-01 | Cross-user matrix: 8 endpoints × {self/foreign} produce expected status | integration | `pytest tests/integration/test_security_matrix.py -x -q` | ❌ W0 | ⬜ pending |
| 16-03-01 | 03 | 1 | VERIFY-02 | T-16-04 | alg=none JWT → 401 | integration | `pytest tests/integration/test_jwt_attacks.py -k alg_none -q` | ❌ W0 | ⬜ pending |
| 16-03-02 | 03 | 1 | VERIFY-03 | T-16-04 | Tampered signature → 401 | integration | `pytest tests/integration/test_jwt_attacks.py -k tampered -q` | ❌ W0 | ⬜ pending |
| 16-03-03 | 03 | 1 | VERIFY-04 | T-16-04 | Expired JWT → 401 | integration | `pytest tests/integration/test_jwt_attacks.py -k expired -q` | ❌ W0 | ⬜ pending |
| 16-04-01 | 04 | 1 | VERIFY-06 | T-16-05 | Missing CSRF → 403; mismatched → 403; matching → 200/204 | integration | `pytest tests/integration/test_csrf_enforcement.py -x -q` | ❌ W0 | ⬜ pending |
| 16-04-02 | 04 | 1 | VERIFY-06 | T-16-05 | Bearer auth bypasses CSRF check | integration | `pytest tests/integration/test_csrf_enforcement.py -k bearer_skips -q` | ❌ W0 | ⬜ pending |
| 16-05-01 | 05 | 1 | VERIFY-07 | T-16-02 | Ticket reuse → 1008 close | integration | `pytest tests/integration/test_ws_ticket_safety.py -k reuse -q` | ❌ W0 | ⬜ pending |
| 16-05-02 | 05 | 1 | VERIFY-07 | T-16-02 | Expired ticket (>60s mocked clock) → 1008 | integration | `pytest tests/integration/test_ws_ticket_safety.py -k expired -q` | ❌ W0 | ⬜ pending |
| 16-05-03 | 05 | 1 | VERIFY-07 | T-16-02 | Cross-user ticket → 1008 | integration | `pytest tests/integration/test_ws_ticket_safety.py -k cross_user -q` | ❌ W0 | ⬜ pending |
| 16-06-01 | 06 | 1 | VERIFY-08 | T-16-03 | Migration smoke baseline → upgrade head; tasks.user_id NOT NULL preserved; FK enforce; row count preserved | integration | `pytest tests/integration/test_migration_smoke.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/integration/_phase16_helpers.py` — DRY shared module (ENDPOINT_CATALOG, fixtures, JWT forge, CSRF pair, alembic subprocess wrapper, WS_POLICY_VIOLATION constant)
- [ ] `tests/fixtures/migration/` — synthetic baseline schema generator (in-test, no committed binary DB)

---

## Manual-Only Verifications

*None — Phase 16 is 100% automated. If a manual verification is needed, it indicates a verification-strategy bug to fix here.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers shared helpers + migration fixture
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
