---
phase: 15
slug: account-dashboard-hardening-billing-stubs
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-29
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest 8.x + httpx TestClient |
| **Framework (frontend)** | Vitest 3.2 + RTL 16 + MSW 2.13 |
| **Config files** | `pytest.ini`, `frontend/vitest.config.ts`, `frontend/src/tests/setup.ts` |
| **Quick run command (backend)** | `pytest tests/integration/test_account_routes.py -x -q` |
| **Quick run command (frontend)** | `cd frontend && bun run vitest run src/tests/AccountPage.test.tsx` |
| **Full suite (backend)** | `pytest tests/ -q` |
| **Full suite (frontend)** | `cd frontend && bun run vitest run` |
| **Estimated runtime** | ~25 seconds backend / ~12 seconds frontend |

---

## Sampling Rate

- **After every task commit:** Run quick command for the affected layer
- **After every plan wave:** Run full suite for the affected layer
- **Before `/gsd-verify-work`:** Both suites green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 0 | UI-07 | — | apiClient.get accepts suppress401Redirect; delete accepts body | unit | `cd frontend && bun run vitest run src/tests/apiClient.test.ts` | ❌ W0 | ⬜ pending |
| 15-01-02 | 01 | 0 | UI-07 | — | _clear_auth_cookies importable from shared module | unit | `pytest tests/unit/api/test_cookie_helpers.py -x -q` | ❌ W0 | ⬜ pending |
| 15-02-01 | 02 | 1 | AUTH-06 | T-15-03 | POST /auth/logout-all bumps token_version + clears cookies, returns 204 | integration | `pytest tests/integration/test_logout_all.py -x -q` | ❌ W0 | ⬜ pending |
| 15-02-02 | 02 | 1 | AUTH-06 | T-15-03 | Old JWT 401s after logout-all | integration | `pytest tests/integration/test_logout_all.py -k invalidates_existing -q` | ❌ W0 | ⬜ pending |
| 15-03-01 | 03 | 1 | UI-07 | — | GET /api/account/me returns AccountSummaryResponse for authed user | integration | `pytest tests/integration/test_account_me.py -x -q` | ❌ W0 | ⬜ pending |
| 15-03-02 | 03 | 1 | UI-07 | T-15-04 | GET /api/account/me 401s without auth | integration | `pytest tests/integration/test_account_me.py -k no_auth -q` | ❌ W0 | ⬜ pending |
| 15-04-01 | 04 | 1 | SCOPE-06 | T-15-01 | DELETE /api/account cascades all 6 child tables | integration | `pytest tests/integration/test_delete_account.py -k cascade -q` | ❌ W0 | ⬜ pending |
| 15-04-02 | 04 | 1 | SCOPE-06 | T-15-02 | DELETE /api/account 400s on email_confirm mismatch | integration | `pytest tests/integration/test_delete_account.py -k mismatch -q` | ❌ W0 | ⬜ pending |
| 15-04-03 | 04 | 1 | SCOPE-06 | T-15-02 | DELETE /api/account clears cookies + 204 on success | integration | `pytest tests/integration/test_delete_account.py -k clears -q` | ❌ W0 | ⬜ pending |
| 15-04-04 | 04 | 1 | SCOPE-06 | T-15-01 | rate_limit_buckets pre-deleted (no FK; LIKE 'user:<uid>:%') | integration | `pytest tests/integration/test_delete_account.py -k rate_limit -q` | ❌ W0 | ⬜ pending |
| 15-05-01 | 05 | 2 | UI-07 | — | authStore.refresh() hydrates from /me; isHydrating gates RequireAuth | unit | `cd frontend && bun run vitest run src/tests/authStore.refresh.test.ts` | ❌ W0 | ⬜ pending |
| 15-06-01 | 06 | 3 | UI-07 | — | AccountPage renders email + plan tier badge | unit | `cd frontend && bun run vitest run src/tests/AccountPage.test.tsx -t renders` | ❌ W0 | ⬜ pending |
| 15-06-02 | 06 | 3 | UI-07 | — | UpgradeInterestDialog 501-swallow success path | unit | `cd frontend && bun run vitest run src/tests/UpgradeInterestDialog.test.tsx` | ❌ W0 | ⬜ pending |
| 15-06-03 | 06 | 3 | UI-07 / SCOPE-06 | T-15-02 | DeleteAccountDialog disables submit until type-email matches (case-insensitive) | unit | `cd frontend && bun run vitest run src/tests/DeleteAccountDialog.test.tsx` | ❌ W0 | ⬜ pending |
| 15-06-04 | 06 | 3 | UI-07 / AUTH-06 | T-15-03 | LogoutAllDialog confirm flow → authStore.logout() + redirect | unit | `cd frontend && bun run vitest run src/tests/LogoutAllDialog.test.tsx` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `frontend/src/lib/apiClient.ts` — extend `get` with `suppress401Redirect`; extend `delete` to accept body
- [ ] `frontend/src/tests/apiClient.test.ts` — assertion stubs for both extensions
- [ ] `app/api/_cookie_helpers.py` — extract `_clear_auth_cookies` (DRY across auth_routes + account_routes)
- [ ] `app/api/schemas/account_schemas.py` — `AccountSummaryResponse` + `DeleteAccountRequest` Pydantic models
- [ ] `frontend/src/lib/api/accountApi.ts` — skeleton + types
- [ ] `frontend/src/tests/msw/account.handlers.ts` — MSW handlers for /me + /auth/logout-all + DELETE /api/account + /billing/checkout 501
- [ ] `tests/integration/test_logout_all.py`, `test_account_me.py`, `test_delete_account.py` — RED test stubs (file scaffolding + first assertion)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| AccountPage visual polish on `< sm`, `sm-md`, `≥ md` breakpoints | UI-07 | Pixel-perfect mobile drawer + card stacking is best confirmed in browser | Open `/dashboard/account` at viewport 375 / 768 / 1280 and confirm cards stack, dialogs adapt, danger row layout flips |
| `/frontend-design` polish bar | UI-07 | Subjective design quality | Side-by-side compare with KeysDashboardPage; verify gap-6, rounded-xl, destructive border tone match |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
