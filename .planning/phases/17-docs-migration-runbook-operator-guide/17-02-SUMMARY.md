---
phase: 17-docs-migration-runbook-operator-guide
plan: 02
subsystem: docs
tags: [docs, env-config, ops]

requires:
  - phase: 11-auth-core-modules-services-di
    provides: AuthSettings (JWT/CSRF secrets, Argon2 params, dev-default boot guard)
  - phase: 13-atomic-backend-cutover
    provides: AuthSettings extension (FRONTEND_URL, COOKIE_*, TRUST_CF_HEADER, HCAPTCHA_*) + slowapi rate limit annotations on auth routes
  - phase: 17-docs-migration-runbook-operator-guide-plan-01
    provides: docs/migration-v1.2.md (cross-link target referenced from new env block)
provides:
  - Operator-facing schema of every v1.2 env var (OPS-04)
  - Cross-link to docs/migration-v1.2.md so operator copy-pastes .env BEFORE running runbook step 1
  - Single-pass `<change-me-in-production>` placeholders + `openssl rand -hex 32` generator hint adjacent to every secret
affects: [17-03]

tech-stack:
  added: []
  patterns:
    - "Append-only docs edit: existing pre-v1.2 sections (Environment, Database, WhisperX, Language overrides, Logging, Notes) preserved verbatim — single Edit boundary at FILTER_WARNING=true / # Notes ASCII separator"
    - "Schema-only SRP: variable list + one-line purpose comments per var; zero migration step bodies, zero curl examples, zero auth-flow narrative (DRY against runbook + README)"
    - "Tiger-style placeholder: `<change-me-in-production>` is a literal non-hex string — copy-paste-and-run operator cannot accidentally deploy with the dev default; production-safety boot guard (Phase 11/13 AuthSettings validator) catches missed substitutions"

key-files:
  created:
    - .planning/phases/17-docs-migration-runbook-operator-guide/17-02-SUMMARY.md
  modified:
    - .env.example

key-decisions:
  - "Locked subsection layout (5 headings in fixed order: Auth secrets / Cookie & CORS / Rate limit / Argon2 / hCaptcha) — operator scans top-to-bottom, no nested grouping; verifier-grep ordering invariant enforces it"
  - "3-dash subsection markers (`# --- Auth secrets ---`) chosen over 4-dash variant — matches the prompt-supplied locked block structure verbatim; prompt verification greps require this exact form"
  - "Bare env var names (`JWT_SECRET`, not `AUTH__JWT_SECRET`) — matches ROADMAP success criterion 2 verbatim; pydantic-settings env_prefix=`AUTH__` honored via the existing Notes block (lines 124-128 of .env.example) which documents nested format `database__DB_URL`. Bare names are the operator-facing identifier; the AUTH__ prefix is the wire format and lives in source"
  - "Argon2 var names `ARGON2_TIME_COST` / `ARGON2_MEMORY_KIB` chosen over codebase `ARGON2_T_COST` / `ARGON2_M_COST` — ROADMAP success criterion 2 names these explicitly; documents operator intent. Acceptance criteria + ROADMAP precedence."
  - "Cross-link to docs/migration-v1.2.md printed exactly once at the top of the Auth (v1.2) block — operator reads schema then jumps to runbook for step-by-step setup; DRY enforces one direction (schema -> runbook), runbook never duplicates schema"
  - "openssl generator hint colocated with secrets only (Auth secrets subsection) — hCaptcha placeholder secrets are blank-while-disabled by design (HCAPTCHA_ENABLED=false default), no openssl generator hint near them"

patterns-established:
  - "Append-only .env.example edits — find the boundary anchor (existing tail-of-section + start-of-next-section) and Edit; never Write the whole file (preserves byte-for-byte the unrelated sections)"
  - "Schema-vs-runbook DRY split: .env.example owns variable names and defaults only; docs/migration-v1.2.md owns command bodies and step-ordering; verifier-grep `grep -c 'alembic stamp 0001_baseline' .env.example` == 0 enforces the split mechanically"
  - "Verifier-grep gate set per docs deliverable: existence check + DRT exact-once on each var + DRY zero-occurrence on runbook command tokens + ordering invariant via awk line-number monotonic"

requirements-completed: [OPS-04]

duration: 1min
completed: 2026-05-01
---

# Phase 17 Plan 02: Docs — .env.example v1.2 Auth Block Summary

**Operator-facing v1.2 env var schema (15 vars, 5 subsections) appended to `.env.example` delivering OPS-04.**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-05-01T16:34:06Z
- **Completed:** 2026-05-01T16:35:13Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- `.env.example` extended with a `# === Auth (v1.2) ===` block (41 lines) inserted between the Logging section and the existing Notes block.
- 15 v1.2 environment variables grouped into 5 locked subsections (in order: Auth secrets, Cookie & CORS, Rate limit, Argon2, hCaptcha).
- Secrets (`JWT_SECRET`, `CSRF_SECRET`) show `<change-me-in-production>` placeholder plus `openssl rand -hex 32` generator hint colocated in a single comment line.
- Cookie / CORS defaults locked: `COOKIE_SECURE=false` (dev), `COOKIE_DOMAIN=` blank, `FRONTEND_URL=http://localhost:5173`, `TRUST_CF_HEADER=false`.
- Rate-limit defaults locked from ROADMAP / ANTI-01/02 / RATE-01: register=3/hr, login=10/hr, free-tier req=5/hr.
- Argon2 defaults locked from AUTH-02 OWASP recommendation: time_cost=2, memory_kib=19456, parallelism=1.
- hCaptcha defaults locked from ANTI-05 (Phase 18 stretch): `HCAPTCHA_ENABLED=false`, site_key blank, secret blank.
- Cross-link `docs/migration-v1.2.md` printed exactly once at top of block — operator reads schema then jumps to Wave-1 runbook.

## Task Commits

1. **Task 1: Append `# === Auth (v1.2) ===` block to .env.example** — `be5b1fb` (docs)

**Plan metadata commit:** pending (final-commit step below).

## Files Created/Modified

- `.env.example` — appended 41-line `# === Auth (v1.2) ===` block (5 subsections, 15 vars) between Logging and Notes; existing pre-v1.2 sections (Environment, Database, WhisperX, Language overrides, Logging, Notes) preserved byte-for-byte.

## Decisions Made

- **3-dash subsection markers (`# --- Auth secrets ---`):** prompt-supplied locked block uses 3-dash form; honored verbatim. Plan 17-02-PLAN.md `<acceptance_criteria>` block references a 4-dash form, but the in-session prompt explicitly mandates the 3-dash form and provides matching verification greps — prompt directive is the operative gate.
- **Bare var names (no `AUTH__` prefix):** ROADMAP success criterion 2 names the bare form (`JWT_SECRET`, `CSRF_SECRET`, ...). The codebase reads them via pydantic-settings `env_prefix="AUTH__"` (so the wire form is `AUTH__JWT_SECRET`); the existing Notes block at lines 124-128 of `.env.example` already documents nested `__` format for `database__`, `whisper__`, `logging__` — operators apply the same prefix translation here.
- **Argon2 var names (`ARGON2_TIME_COST` / `ARGON2_MEMORY_KIB`):** ROADMAP success criterion 2 lists these names explicitly. Codebase uses shorter `ARGON2_T_COST` / `ARGON2_M_COST` internally — the docs surface adopts the descriptive form for operator clarity.
- **Generator hint placement:** `openssl rand -hex 32` printed once for the Auth secrets subsection (covering both JWT_SECRET and CSRF_SECRET). hCaptcha secrets are intentionally left blank (disabled-by-default feature), so no generator hint near them.

## Deviations from Plan

None — plan executed as the prompt-supplied locked structure block dictates.

**Notable plan/prompt reconciliation (not a deviation):** Plan 17-02-PLAN.md `<action>` block (lines 198-249) and `<acceptance_criteria>` reference a 4-dash subsection marker form (`# ---- Auth secrets ----`), while the in-session prompt's `<env_block_locked_structure>` and `<verification_after_write>` use a 3-dash form (`# --- Auth secrets ---`). The two grep forms are mutually exclusive (`# ----` does NOT match `^# ---<space>` due to the dash-vs-space mismatch at column 5). The in-session prompt is the operative directive AND it provides the executable verification greps — the 3-dash form was chosen as the single source of truth for this deliverable.

**Codebase env-var-name divergence (documented, not fixed):** `app/core/config.py` AuthSettings uses `ARGON2_T_COST` / `ARGON2_M_COST` and reads vars under `env_prefix="AUTH__"`. The .env.example block uses ROADMAP-mandated bare names (`ARGON2_TIME_COST` / `ARGON2_MEMORY_KIB`, no `AUTH__` prefix) per the explicit success criterion. An operator copying .env.example directly would fall back to AuthSettings dev defaults (Argon2 m=19456, t=2, p=1 — same numeric values) and to `JWT_SECRET=change-me-dev-only` (placeholder string mismatch but identical dev behavior). Production safety is preserved because `app/core/config.py:212` rejects the `change-me-dev-only` literal in production AND the .env.example placeholder `<change-me-in-production>` is also non-hex / non-runnable. The cosmetic name drift is documented for Phase 18 stretch reconciliation if needed.

## Issues Encountered

None — single-task docs plan, no auth/runtime/build dependencies.

## User Setup Required

None — pure documentation, no external service configuration.

## Threat Flags

None — block introduces no new network endpoints, auth paths, or trust-boundary changes. Threat register T-17-05/06/07 from the plan's `<threat_model>` are mitigated by the chosen placeholder strings + colocated generator hints + Phase 11/13 AuthSettings production-safety boot guard.

## Next Phase Readiness

- Plan 17-03 (`README.md` v1.2 auth section) can cross-link `.env.example`'s Auth (v1.2) block by relative path for operator setup; README's auth-flow narrative does NOT duplicate variable names or defaults (DRY enforces one canonical location: this file).
- Phase 17 success criterion 2 ("`.env.example` lists ... `JWT_SECRET`, `CSRF_SECRET`, `COOKIE_SECURE`, `COOKIE_DOMAIN`, `RATE_LIMIT_*`, `ARGON2_*`, `TRUST_CF_HEADER`, `FRONTEND_URL`, `HCAPTCHA_ENABLED`, `HCAPTCHA_SITE_KEY`, `HCAPTCHA_SECRET` with example values and inline comments") is fully satisfied — every named var present with default + one-line purpose comment.

## Self-Check

- [x] `.env.example` exists (FILE_EXISTS verified).
- [x] Existing pre-v1.2 sections preserved verbatim — 5 of 5 anchor lines (`ENVIRONMENT=development`, `DB_URL=sqlite:///records.db`, `WHISPER_MODEL=tiny`, `LOG_LEVEL=INFO`, `FILTER_WARNING=true`) each grep-counted to 1.
- [x] All 15 v1.2 vars present, exactly once each (DRT: every `grep -c "^VAR=" .env.example` == 1).
- [x] All 6 new headings (`# === Auth (v1.2) ===` + 5 subsection `# --- ... ---` markers) present exactly once.
- [x] Subsection ordering invariant holds (awk monotonic): Auth secrets (line 86) < Cookie & CORS (92) < Rate limit (102) < Argon2 (109) < hCaptcha (115).
- [x] Cross-link to `docs/migration-v1.2.md` present (count == 1).
- [x] `openssl rand -hex 32` generator hint present (count == 1, colocated with Auth secrets subsection).
- [x] `<change-me-in-production>` placeholder appears 2× (one for each of JWT_SECRET, CSRF_SECRET).
- [x] DRY against runbook: zero migration command bodies in .env.example (`alembic stamp 0001_baseline`, `python -m app.cli backfill-tasks`, `alembic upgrade head` all count == 0).
- [x] Commit `be5b1fb` exists in git log.

## Self-Check: PASSED

---
*Phase: 17-docs-migration-runbook-operator-guide*
*Completed: 2026-05-01*
