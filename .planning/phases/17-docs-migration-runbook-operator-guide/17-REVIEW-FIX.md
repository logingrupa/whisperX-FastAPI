---
phase: 17
date: 2026-05-01
review_path: .planning/phases/17-docs-migration-runbook-operator-guide/17-REVIEW.md
iteration: 1
findings_in_scope: 4
findings_addressed: 4
findings_deferred: 5
fixed: 4
skipped: 0
status: all_fixed
commits:
  - fcadd22 docs(17-fix): correct AUTH__ env var prefix in .env.example (HR-01, MR-01)
  - 44bb405 docs(17-fix): remove dead RATE_LIMIT env vars; document hardcoded limits (HR-02)
  - 1e7469b docs(17-fix): document AUTH__V2_ENABLED master gate (MR-02)
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-05-01
**Source review:** `.planning/phases/17-docs-migration-runbook-operator-guide/17-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (HIGH + MEDIUM): 4
- Fixed: 4
- Skipped: 0
- Deferred (out of scope per directive): 5 (LR-01, LR-02, LR-03, IR-01, IR-02)

All four in-scope findings were addressed. Three atomic commits — one per logical concern — keep the audit trail clean. Acceptance grep gates from the original phase plans (`openssl rand -hex 32` present in `.env.example`, `docs/migration-v1.2.md` cross-link present, no `alembic stamp 0001_baseline` leak into `.env.example` or `README.md`) re-verified passing after every commit.

---

## Fixed Issues

### HR-01: `.env.example` Auth (v1.2) vars use bare names that AuthSettings will ignore

**Files modified:** `.env.example`
**Commit:** `fcadd22`
**Severity:** HIGH

**What was wrong:**
`AuthSettings` (`app/core/config.py:145-151`) declares `env_prefix="AUTH__"` and `case_sensitive=True`. The shipped `.env.example` Auth (v1.2) block declared every var bare (`JWT_SECRET=`, `COOKIE_SECURE=`, etc.). pydantic-settings would silently fall back to in-code defaults in dev (operator believes config landed; doesn't), and raise `ValueError("AUTH__JWT_SECRET must be set in production")` in production — citing a name that didn't appear anywhere in the operator-facing surface.

**What was changed (`.env.example:80-128`):**
1. Renamed every Auth (v1.2) var declaration to its wire form: `JWT_SECRET` -> `AUTH__JWT_SECRET`, `CSRF_SECRET` -> `AUTH__CSRF_SECRET`, `COOKIE_SECURE` -> `AUTH__COOKIE_SECURE`, `COOKIE_DOMAIN` -> `AUTH__COOKIE_DOMAIN`, `FRONTEND_URL` -> `AUTH__FRONTEND_URL`, `TRUST_CF_HEADER` -> `AUTH__TRUST_CF_HEADER`, `HCAPTCHA_ENABLED` -> `AUTH__HCAPTCHA_ENABLED`, `HCAPTCHA_SITE_KEY` -> `AUTH__HCAPTCHA_SITE_KEY`, `HCAPTCHA_SECRET` -> `AUTH__HCAPTCHA_SECRET`.
2. Added a prominent block-header comment (lines 85-90) calling out `env_prefix="AUTH__"` + `case_sensitive=True` semantics, the silent-fallback failure mode, and the line-anchored cross-reference (`app/core/config.py:145-151`).
3. Inline comments (`# COOKIE_SECURE=true forces ...`) updated to use the new prefixed names so the operator sees identical text in the comment and the assignment.

**Code reference cross-check:** every renamed variable corresponds to a `Field(...)` declaration on `AuthSettings` between `app/core/config.py:153` (`JWT_SECRET`) and `app/core/config.py:198` (`HCAPTCHA_SECRET`).

---

### MR-01: Argon2 var names diverge from AuthSettings field names

**Files modified:** `.env.example`
**Commit:** `fcadd22` (folded with HR-01 — same Argon2 lines)
**Severity:** MEDIUM

**What was wrong:**
`.env.example` declared `ARGON2_TIME_COST=2` / `ARGON2_MEMORY_KIB=19456`. `AuthSettings` reads `ARGON2_T_COST` / `ARGON2_M_COST` (`app/core/config.py:158-159`). After HR-01, an operator setting `AUTH__ARGON2_TIME_COST=4` would still see no Argon2 retuning — the var name does not match the field.

**What was changed (`.env.example:117-122`):**
1. Renamed `ARGON2_TIME_COST` -> `AUTH__ARGON2_T_COST` and `ARGON2_MEMORY_KIB` -> `AUTH__ARGON2_M_COST` (matches `app/core/config.py:158-159` verbatim).
2. `AUTH__ARGON2_PARALLELISM` already aligned — only added the `AUTH__` prefix for the same HR-01 reason.
3. Added an inline comment immediately above the block: `# Field names mirror app/core/config.py:158-160 (T_COST/M_COST, NOT TIME_COST/MEMORY_KIB).` — anchors the reader at the codebase truth and pre-empts the descriptive-rename trap (the long-form names read more naturally in English but pydantic doesn't care).

**Numeric defaults preserved:** `t=2`, `m=19456`, `p=1` match `AuthSettings.ARGON2_T_COST`, `ARGON2_M_COST`, `ARGON2_PARALLELISM` defaults exactly.

---

### HR-02: Three RATE_LIMIT_*_PER_HOUR env vars have no consumer in the codebase

**Files modified:** `.env.example`
**Commit:** `44bb405`
**Severity:** HIGH

**What was wrong:**
The block declared `RATE_LIMIT_REGISTER_PER_HOUR=3`, `RATE_LIMIT_LOGIN_PER_HOUR=10`, `RATE_LIMIT_FREE_REQ_PER_HOUR=5`. None of these names appear in `app/`. Actual rate limits are hardcoded as decorator string literals: `@limiter.limit("3/hour")` at `app/api/auth_routes.py:123` (register), `@limiter.limit("10/hour")` at `app/api/auth_routes.py:160` (login), and `FREE_POLICY.max_per_hour=5` at `app/services/free_tier_gate.py:58-65`. An operator tuning `RATE_LIMIT_LOGIN_PER_HOUR=20` for a soak test would see no behaviour change — dead config presented as live config.

**What was changed (`.env.example:108-115`):**
1. Removed the three dead `RATE_LIMIT_*_PER_HOUR=N` declarations.
2. Replaced with a NOTE block listing the three hardcoded values, each with a `<file>:<line>` anchor pointing at the actual decorator / policy constant. This honours the docs-only phase boundary (no code changes), gives operators a one-line breadcrumb to the real source, and prevents the same misleading-config trap if someone re-adds these vars in a later edit.
3. Closing line explicitly states env-wiring is tracked for v1.3, so future operators don't waste cycles tuning a no-op.

**ROADMAP impact:** ROADMAP success criterion 2 lists `RATE_LIMIT_*` by name. The note block keeps the conceptual identifier visible to operators reading top-down through `.env.example` while removing the misleading writeable assignment. If ROADMAP wants live env-driven rate limits, a v1.3 phase must (a) add `RATE_LIMIT_*` fields to `AuthSettings`, (b) replace the decorator literal with a dynamic factory, and (c) re-test the rate-limit suites.

---

### MR-02: AUTH__V2_ENABLED is required for v1.2 routes to mount, but is not documented

**Files modified:** `.env.example`, `docs/migration-v1.2.md`
**Commit:** `1e7469b`
**Severity:** MEDIUM

**What was wrong:**
`app/main.py:247-252` gates v1.2 router mounting on `is_auth_v2_enabled()`, which reads `settings.auth.V2_ENABLED` (`app/core/config.py:167-170`, default `False`). In production, `app/main.py:257` raises `RuntimeError` if `ENVIRONMENT=production` and `V2_ENABLED=False` — fail-loud. In dev/test, `V2_ENABLED=False` boots silently with the v1.2 surface absent. Neither `.env.example` nor `docs/migration-v1.2.md` mentioned `AUTH__V2_ENABLED` anywhere, so an operator following the runbook in staging would complete every step successfully then hit `404 Not Found` on `POST /auth/register` with no documented hint.

**What was changed:**

1. `.env.example:92-97` — new `# --- Feature flag (master gate) ---` subsection placed FIRST in the Auth (v1.2) block (above secrets), reflecting its master-gate role:

   ```
   # AUTH__V2_ENABLED=true mounts the v1.2 auth/keys/account/billing/ws_ticket routers
   # (app/main.py:247-252). Production REFUSES to boot with this set to false
   # (app/main.py:257). Dev/test default is false; smoke verify in
   # docs/migration-v1.2.md Section 8 is meaningless without this set true.
   AUTH__V2_ENABLED=true
   ```

2. `docs/migration-v1.2.md:32` — added a new pre-requisite checklist bullet (Section 1):

   ```
   - `.env` has `AUTH__V2_ENABLED=true` (master gate; without it the v1.2 auth/keys/billing routers never mount — see [`.env.example`](../.env.example) and `app/main.py:247-252`).
   ```

   DRY: links to `.env.example` instead of restating the env-var declaration. SRP: runbook stays prescriptive (do this), `.env.example` stays descriptive (here is the schema).

3. `docs/migration-v1.2.md:341-349` — added Check 7 to Section 8 (Smoke Verify) — the boundary assert that fires only when the gate is set, per tiger-style directive 3:

   ```bash
   curl -i -X POST http://localhost:8000/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"email":"smoke@example.com","password":"smoke-pw-1234"}'
   ```

   Expected: `201 Created`, `400`, or `422` — anything but `404 Not Found`. A 404 maps directly to "operator forgot the master gate; restart with `AUTH__V2_ENABLED=true`."

**Why placed at Section 8 (Smoke Verify), not Section 4 (Upgrade Auth Schema):** the master gate is a runtime concern, not a schema concern. Setting it in Section 4 would fire pre-restart but the binding only takes effect on FastAPI start. Placing the check in Section 8 keeps Section 1's pre-requisite as the prescriptive moment and Section 8 as the post-restart verifier — same pattern as Checks 1-6 (verify after action, not concurrent with it).

---

## Acceptance Grep Gates Re-verified

After every commit, the four phase-success grep gates from the original 17-02 / 17-04 plans were re-run; all pass:

| Gate | Result |
|------|--------|
| `grep -q "openssl rand -hex 32" .env.example` | PASS |
| `grep -q "docs/migration-v1.2.md" .env.example` | PASS |
| `grep -c "alembic stamp 0001_baseline" .env.example` == 0 | PASS |
| `grep -c "alembic stamp 0001_baseline" README.md` == 0 | PASS |

Cross-file SRP/DRY invariants from the review's own verification block (REVIEW.md §261-268) remain intact:

- No migration command body duplicated outside `docs/migration-v1.2.md`.
- No env-var declaration duplicated outside `.env.example`.
- README still contains zero `^JWT_SECRET=` declarations and zero `python -m app.cli backfill-tasks` command bodies.

---

## Deferred Issues (Out of Scope This Pass)

Per the directive's explicit out-of-scope list (LOW + INFO findings — operator can address manually). Each is summarised here so the user has a single tracking surface.

### LR-01: Pro tier "all (incl. large-v3)" overstates allowed_models (LOW)

**File:** `README.md:272`
**Rationale for deferral:** docs-only accuracy nit. Suggested fix: replace `all (incl. large-v3)` with the actual `PRO_POLICY.allowed_models` list (`tiny, base, small, medium, large, large-v2, large-v3`) per `app/services/free_tier_gate.py:71-74`. No silent-failure cost — a 403 from the gate is fail-loud.

### LR-02: README asserts `/dashboard/keys` without `/ui` base prefix (LOW)

**File:** `README.md:215`
**Rationale for deferral:** cosmetic URL drift. Vite `base: '/ui/'` makes the deployed URL `/ui/dashboard/keys`. Suggested fix: replace inline reference with `/ui/dashboard/keys`.

### LR-03: HCAPTCHA_SECRET placeholder lacks "leave blank" callout (LOW)

**File:** `.env.example:124-128` (post-fix line numbers)
**Rationale for deferral:** stylistic. Block-level comment ("Activate only if abuse observed during v1.2 soak") already covers the case; per-var "leave blank while disabled" would be belt-and-suspenders.

### IR-01: README API Keys section omits GET /api/keys (INFO)

**File:** `README.md:213-240`
**Rationale for deferral:** completeness gap, not factual error. Suggested fix: one-line bullet under Issuing referencing `GET /api/keys` (`app/api/key_routes.py:65-72`).

### IR-02: Runbook Section 8 Check 5 admits the check is non-load-bearing (INFO)

**File:** `docs/migration-v1.2.md:324-331`
**Rationale for deferral:** tiger-style polish. Check 5 explains the SQLite CLI quirk but has no fail criterion. Suggested fix: replace with an `engine.connect()` Python snippet that asserts `PRAGMA foreign_keys=1` after the listener attaches.

---

## Notes for the User

1. **Commit message trailing paths:** the `gsd-sdk commit` invocation appended the staged file paths to the commit subject line (e.g., `docs(17-fix): correct AUTH__ env var prefix in .env.example (HR-01, MR-01) .env.example`). This is a quirk of how `gsd-sdk commit <message> <paths...>` was invoked; the file-path positional args ended up in the message rather than driving the commit's pathspec. The commits themselves contain the correct content for the correct files (verified via `git show`); only the cosmetic subject line carries the suffix. No corrective amend was performed (per "create new commits, not amends" directive). If the trailing paths bother you, the cleanest path is `git rebase` or a manual amend with explicit user sign-off.

2. **REVIEW-FIX.md not yet committed:** per `gsd-code-fixer` contract, this report is left uncommitted for the orchestrator workflow to commit as `docs(17-fix): add REVIEW-FIX.md` (the directive's suggested commit 4). The three substantive fix commits are already on `main`.

---

_Fixed: 2026-05-01_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
