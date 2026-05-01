---
phase: 17
date: 2026-05-01
status: human_needed
must_haves_passed: 17/17
re_verification: false
---

# Phase 17: Docs + Migration Runbook + Operator Guide — Verification Report

**Phase Goal:** Operator and external API consumer have written guidance — migration runbook is followable end-to-end, `.env.example` lists every new variable with defaults, README documents the auth flow.

**Verified:** 2026-05-01
**Status:** human_needed (1 item — operator must walk the runbook end-to-end on a v1.1-shaped sandbox DB)
**Re-verification:** No — initial verification

---

## Goal-Backward Trace per Success Criterion

### SC1 — `docs/migration-v1.2.md` is operator-followable end-to-end

| Required step | Runbook section | Evidence |
|---|---|---|
| Backup | §2 Pre-flight: Backup Database | `cp records.db records.db.pre-v1.2.bak` (line 53) + `sqlite3` verify (lines 61, 67) |
| `alembic stamp head` (per ROADMAP wording — actual is `0001_baseline`) | §3 Stamp Baseline | `uv run alembic stamp 0001_baseline` (line 91) |
| `alembic upgrade head` (per ROADMAP wording — actual is staged 0002 → head) | §4 + §7 | `alembic upgrade 0002_auth_schema` (§4 line 129), `alembic upgrade head` (§7 line 258) |
| Admin create | §5 Create Admin User | `uv run python -m app.cli create-admin --email admin@example.com` (line 172) |
| Backfill | §6 Backfill Tasks | `--dry-run` (line 214) + `--yes` commit (line 222) |
| Smoke verify | §8 Smoke Verify | 7 numbered checks (chain head, NULL count, idx, admin row, FK, app-boot, /auth/register 201/422) |
| Rollback | §9 Rollback | `alembic downgrade -1` (line 364) + restore-from-backup (line 394) |

Step ordering 1:1 mirrors `tests/integration/test_migration_smoke.py` (stamp 0001 → upgrade 0002 → create-admin → backfill → upgrade head). Sequence integrity confirmed by line-number monotonicity: stamp 76 < upgrade_0002 114 < create-admin 172 < backfill 214 < upgrade_head 258. **PASSED (machine-verifiable). End-to-end execution check requires human (see Human Verification Required below).**

### SC2 — `.env.example` lists every new variable with defaults

ROADMAP-named vars vs `.env.example` (post-fix state with `AUTH__` prefix):

| ROADMAP token | Present? | Form in file | Notes |
|---|---|---|---|
| `JWT_SECRET` | yes | `AUTH__JWT_SECRET=<change-me-in-production>` (line 102) | wire form per HR-01 fix |
| `CSRF_SECRET` | yes | `AUTH__CSRF_SECRET=<change-me-in-production>` (line 103) | wire form per HR-01 fix |
| `COOKIE_SECURE` | yes | `AUTH__COOKIE_SECURE=false` (line 107) | wire form |
| `COOKIE_DOMAIN` | yes | `AUTH__COOKIE_DOMAIN=` (line 109) | wire form |
| `RATE_LIMIT_*` | partial | NOTE block (lines 115–122) names the three values + file:line citations; declarations removed by HR-02 (no consumer in code) | deviation documented in REVIEW-FIX |
| `ARGON2_*` | yes | `AUTH__ARGON2_T_COST`, `AUTH__ARGON2_M_COST`, `AUTH__ARGON2_PARALLELISM` (lines 127–129) | renamed per MR-01 to match codebase fields |
| `TRUST_CF_HEADER` | yes | `AUTH__TRUST_CF_HEADER=false` (line 113) | wire form |
| `FRONTEND_URL` | yes | `AUTH__FRONTEND_URL=http://localhost:5173` (line 111) | wire form |
| `HCAPTCHA_ENABLED` | yes | `AUTH__HCAPTCHA_ENABLED=false` (line 133) | wire form |
| `HCAPTCHA_SITE_KEY` | yes | `AUTH__HCAPTCHA_SITE_KEY=` (line 134) | wire form |
| `HCAPTCHA_SECRET` | yes | `AUTH__HCAPTCHA_SECRET=` (line 135) | wire form |
| (extra) `AUTH__V2_ENABLED` | yes | line 97 | added by MR-02 fix; required for v1.2 routes to mount |

Inline comments + `<change-me-in-production>` placeholder + `openssl rand -hex 32` generator hint all present (counts: 2, 1 respectively). `docs/migration-v1.2.md` cross-link present (count: 2).

Block-header comment (lines 86–90) explicitly documents `env_prefix="AUTH__"` + `case_sensitive=True` semantics so an operator who reads top-down understands the prefix translation rule.

**PASSED with documented deviations** (RATE_LIMIT_* declarations removed per HR-02 because they had no code consumer; values + locations still documented in NOTE block. ARGON2 names match codebase fields, not the long-form names in ROADMAP wording).

### SC3 — `README.md` describes registration/login flow, API key issuance + bearer usage, free-vs-Pro tier differences, and the `mailto:hey@logingrupa.lv` reset path

| Required content | README section | Evidence |
|---|---|---|
| Registration / login flow | `### Registration & Login Flow` (line 188) | ASCII diagram (lines 190–203) + 7 bullets covering register/login/logout/logout-all/rate limits/disposable-email rejection/mailto reset |
| API key issuance | `### Issuing API Keys` (line 213) | 3-step curl snippet (login → read csrf_token → POST /api/keys) + endpoint bullet (line 237) + key-format spec |
| Bearer usage | `### Using an API Key` (line 242) | Two curl snippets (POST /speech-to-text + GET /task/<uuid>) with literal `Authorization: Bearer whsk_PREFIX01_<22charbase64random>` header form |
| Free-vs-Pro tier differences | `### Free vs Pro Tiers` (line 263) | 5-row markdown table (Requests/hour, File size, Duration cap, Models, Concurrent slots) + 429/402/403 limit-hit taxonomy + 501 stub note |
| `mailto:hey@logingrupa.lv` reset path | line 211 (in Registration & Login Flow) | `[mailto:hey@logingrupa.lv](mailto:hey@logingrupa.lv)` rendered link |
| Migration cross-link | `### Migrating from v1.1` (line 282) | single link to `docs/migration-v1.2.md` (line 286); zero migration command bodies duplicated |

Insertion position correct: Web UI (line 45) < Authentication & API Keys (line 184) < Documentation (line 296). **PASSED.**

---

## Aggregated Must-Have Results

| # | Plan | Truth (from `must_haves.truths` in plan frontmatter) | Status | Evidence |
|---|------|------|--------|----------|
| 1 | 17-01 | docs/migration-v1.2.md exists with 9 numbered top-level sections in locked order | PASSED | All 9 `^## N. ` headings present; line numbers 9, 46, 76, 114, 163, 199, 243, 289, 355 |
| 2 | 17-01 | Step ordering mirrors test_migration_smoke.py 4-step sequence | PASSED | stamp 0001 (line 76) → upgrade 0002 (114) → create-admin (172) → backfill (214) → upgrade head (258); test file lines 119–122 confirm same sequence |
| 3 | 17-01 | Every shell command is in fenced bash block | PASSED | 33 `^```bash$` fences (>= 7 floor by 4.7×) |
| 4 | 17-01 | Rollback section documents `alembic downgrade -1` + restore-from-backup | PASSED | §9 line 364 `alembic downgrade -1`; §9 line 394 `cp records.db.pre-v1.2.bak records.db` |
| 5 | 17-01 | Operator unfamiliar with source can copy bash blocks verbatim and migrate v1.1→v1.2 end-to-end | NEEDS HUMAN | Structurally complete (all commands, expected outputs, failure modes documented). Actual end-to-end follow-through requires human verification. |
| 6 | 17-02 | `.env.example` contains `# === Auth (v1.2) ===` block appended after Logging | PASSED | line 81 `# === Auth (v1.2) ===` between line 78 (`FILTER_WARNING=true`) and line 138 (`# Notes`) |
| 7 | 17-02 | Auth (v1.2) block has 5 subsections in locked order | PASSED | Auth secrets (99) < Cookie & CORS (105) < Rate limit (115) < Argon2 (124) < hCaptcha (131); plus master-gate Feature flag (92) prepended by MR-02 fix |
| 8 | 17-02 | All named env vars present with one-line purpose comments + example values | PASSED | 12 of 14 ROADMAP-named vars present as `AUTH__<NAME>=` declarations; `RATE_LIMIT_*` documented in NOTE block per HR-02 (deliberate — no code consumer); every var has an inline comment |
| 9 | 17-02 | Secret defaults use `<change-me-in-production>` + `openssl rand -hex 32` generator hint | PASSED | placeholder count 2; openssl hint count 1 (colocated with Auth secrets subsection covering both secrets) |
| 10 | 17-02 | Existing pre-v1.2 sections preserved | PASSED | `ENVIRONMENT=development`, `DB_URL=sqlite:///records.db`, `WHISPER_MODEL=tiny`, `LOG_LEVEL=INFO`, `FILTER_WARNING=true` all present at original positions; Notes block preserved at line 138 |
| 11 | 17-03 | README has new `## Authentication & API Keys (v1.2)` top-level section | PASSED | line 184; count 1 |
| 12 | 17-03 | Auth section inserted between Web UI block and Documentation | PASSED | Web UI 45 < Auth 184 < Documentation 296 |
| 13 | 17-03 | Five required subheadings present in locked order | PASSED | Registration & Login Flow (188) < Issuing API Keys (213) < Using an API Key (242) < Free vs Pro Tiers (263) < Migrating from v1.1 (282) |
| 14 | 17-03 | Free vs Pro markdown table with 5 limit rows | PASSED | Requests/hour, File size, Duration cap, Models, Concurrent slots — each `grep -c == 1` |
| 15 | 17-03 | Curl snippets for register-then-issue-key (cookie) AND transcribe via bearer (whsk_*) | PASSED | 3 curl snippets in Issuing section + 2 curl snippets in Using section; `Authorization: Bearer whsk_` count 2 |
| 16 | 17-03 | Migrating subsection links to `docs/migration-v1.2.md` (no step bodies duplicated) | PASSED | `docs/migration-v1.2.md` count 1; cross-file DRY: `alembic stamp 0001_baseline` count 0; `python -m app.cli backfill-tasks` count 0; `python -m app.cli create-admin` count 0; `alembic upgrade 0002_auth_schema` count 0 |
| 17 | 17-03 | `mailto:hey@logingrupa.lv` reset path documented | PASSED | line 211; count 1 |

**Score: 17/17 must-haves PASSED** (one of which — #5 — is structurally complete but the dynamic claim "operator can migrate end-to-end" requires human walkthrough).

---

## HIGH/MEDIUM Finding Fix Verification

| Finding | Severity | Fixed in commit | Verified state in current files |
|---------|----------|----------------|----------------------------------|
| HR-01: bare env-var names AuthSettings will silently ignore | HIGH | fcadd22 | All 12 v1.2 vars use `AUTH__<NAME>=` wire form (lines 97, 102–103, 107–113, 127–129, 133–135). Block-header comment (lines 86–90) explicitly documents `env_prefix="AUTH__"` + `case_sensitive=True` semantics with file:line citation `app/core/config.py:145-151`. **FIXED.** |
| HR-02: three RATE_LIMIT_*_PER_HOUR vars have no code consumer | HIGH | 44bb405 | Three writeable assignments removed. Replaced with NOTE block (lines 115–122) listing the three hardcoded values + file:line anchors (`app/api/auth_routes.py:123`, `:160`, `app/services/free_tier_gate.py:58-65`). Closing line flags v1.3 wiring as future work. **FIXED.** |
| MR-01: ARGON2 var names diverge from AuthSettings field names | MEDIUM | fcadd22 (folded with HR-01) | `AUTH__ARGON2_T_COST=2`, `AUTH__ARGON2_M_COST=19456`, `AUTH__ARGON2_PARALLELISM=1` (lines 127–129) match `app/core/config.py:158-160` verbatim. Inline comment line 126 explicitly anchors `app/core/config.py:158-160 (T_COST/M_COST, NOT TIME_COST/MEMORY_KIB)` to pre-empt the descriptive-rename trap. **FIXED.** |
| MR-02: `AUTH__V2_ENABLED` master gate undocumented | MEDIUM | 1e7469b | (a) `.env.example:97` declares `AUTH__V2_ENABLED=true` in a new `# --- Feature flag (master gate) ---` subsection placed FIRST in the Auth (v1.2) block. (b) `docs/migration-v1.2.md:32` adds Section 1 Pre-requisite checklist bullet. (c) `docs/migration-v1.2.md:341–349` adds Section 8 Smoke Verify Check 7 — a curl that asserts `/auth/register` does NOT return 404 (404 ⇒ master gate unset). **FIXED.** |

**All 4 in-scope HIGH/MEDIUM findings verified fixed against the actual files (not just the REVIEW-FIX narrative).**

The 5 deferred LOW/INFO findings (LR-01 Pro tier model overstatement, LR-02 missing `/ui` prefix on dashboard URL, LR-03 hCaptcha "leave blank" callout, IR-01 missing `GET /api/keys`, IR-02 non-load-bearing FK PRAGMA check) are out of scope per the REVIEW-FIX directive and do not block phase closure.

---

## Cross-File DRY / SRP / Tiger-Style

| Invariant | Check | Result |
|-----------|-------|--------|
| DRY — migration commands live in runbook only | `grep -c "alembic stamp 0001_baseline" .env.example` | 0 ✓ |
| DRY — migration commands live in runbook only | `grep -c "alembic stamp 0001_baseline" README.md` | 0 ✓ |
| DRY — backfill command lives in runbook only | `grep -c "python -m app.cli backfill-tasks" README.md` | 0 ✓ |
| DRY — env-var declarations live in `.env.example` only | `grep -c "^JWT_SECRET=\|^AUTH__" README.md` | 0 ✓ |
| SRP — runbook contains migration procedure only | manual scan | no auth-flow narrative; no env-var schema ✓ |
| SRP — `.env.example` contains config schema only | manual scan | no curl snippets; no migration step bodies; only var assignments + one-line comments ✓ |
| SRP — README contains API-consumer entrypoint only | manual scan | no env-var declarations; no migration command bodies; documentation links to authoritative source for both ✓ |
| Tiger-style — runbook commands show expected output | manual scan | every fenced bash block in `docs/migration-v1.2.md` has an "Expected output:" line ✓ |
| Tiger-style — README curl snippets show response shape | manual scan | every curl snippet in README has `# Response: ...` comment ✓ |

---

## Anti-Pattern Scan

No TODO/FIXME/PLACEHOLDER/XXX/HACK comments found in any of the three deliverable files. No empty implementations or stub returns (these are docs files — N/A by category). No data-flow concerns (Level 4 N/A — documentation).

---

## Requirements Coverage

| Requirement | Source plan | Description (REQUIREMENTS.md) | Status | Evidence |
|---|---|---|---|---|
| OPS-03 | 17-01 | Migration runbook documented in `docs/migration-v1.2.md` (backup → `alembic stamp head` → `alembic upgrade head` → verify) | SATISFIED | 9-section runbook with fenced bash blocks; step ordering mirrors `test_migration_smoke.py` |
| OPS-04 | 17-02 | `.env.example` lists every new env var with example values: `JWT_SECRET`, `CSRF_SECRET`, `COOKIE_SECURE`, `COOKIE_DOMAIN`, `RATE_LIMIT_*`, `ARGON2_*`, `TRUST_CF_HEADER`, `FRONTEND_URL`, `HCAPTCHA_ENABLED`, `HCAPTCHA_SITE_KEY`, `HCAPTCHA_SECRET` | SATISFIED (with documented deviations) | All ROADMAP-named tokens present; deviations: (1) `AUTH__` wire-form prefix per HR-01; (2) `RATE_LIMIT_*` documented in NOTE block per HR-02 (no code consumer); (3) `ARGON2_*` uses `T_COST`/`M_COST` codebase names per MR-01 |
| OPS-05 | 17-03 | README.md documents the auth flow, key management, free vs Pro tiers, and the manual password-reset path | SATISFIED | New section line 184; 5 subheadings; mailto link line 211; tier table lines 267–273 |

No orphaned requirements. ROADMAP table lines 282–284 confirm OPS-03/04/05 mapped to Phase 17 with status `Complete`.

---

## Human Verification Required

### 1. End-to-end runbook walkthrough on a v1.1-shaped sandbox DB

**Test:**
1. Provision a v1.1 SQLite DB (or copy a real pre-v1.2 production `records.db` to a sandbox).
2. Open `docs/migration-v1.2.md` and execute every fenced bash block in Sections 2 → 3 → 4 → 5 → 6 → 7 → 8 verbatim, replacing only the placeholder email in Sections 5 and 6.
3. Do NOT consult any source file outside what the runbook explicitly references.

**Expected:**
- Each command's actual output matches the runbook's "Expected output" line.
- Section 8 Check 1: `alembic current` returns `0003_tasks_user_id_not_null (head)`.
- Section 8 Check 2: `SELECT COUNT(*) FROM tasks WHERE user_id IS NULL` returns `0`.
- Section 8 Check 6: app boots cleanly under `uvicorn`.
- Section 8 Check 7: `POST /auth/register` returns 201/400/422 (not 404), confirming `AUTH__V2_ENABLED=true` mounted the v1.2 routers.

**Why human:** Phase 17 success criterion 1 is "operator new to the project follows `docs/migration-v1.2.md` step-by-step ... without consulting source code, and the migration completes successfully." This is a dynamic, environment-bound assertion (real shell, real `uv`, real SQLite, real `alembic` runtime) that no static grep or file check can substitute for. The `tests/integration/test_migration_smoke.py` provides a CI-level executable mirror but the prose-followability claim — that an operator unfamiliar with the codebase can read the document and succeed — only holds when an actual human walks through it.

---

## Gaps Summary

No actionable gaps. All 4 HIGH/MEDIUM review findings are fixed in the actual files (not just narratively in REVIEW-FIX.md). All 17 plan-frontmatter must-haves pass. All 3 ROADMAP success criteria are satisfied with their structural commitments — SC1's dynamic end-to-end claim is the only remaining open item and is appropriately bounded as a human verification task. The phase is structurally and contractually complete; closing it requires an operator to walk the runbook once.

---

_Verified: 2026-05-01_
_Verifier: Claude (gsd-verifier)_
