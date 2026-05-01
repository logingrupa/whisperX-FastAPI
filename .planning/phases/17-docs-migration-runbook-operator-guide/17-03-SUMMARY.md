---
phase: 17-docs-migration-runbook-operator-guide
plan: 03
subsystem: docs
tags: [docs, readme, auth-flow, ops]

requires:
  - phase: 13-atomic-backend-cutover
    provides: register/login/logout routes; /api/keys + show-once UX; bearer auth contract; CSRF double-submit; /speech-to-text bearer path; rate limit semantics; Stripe stubs
  - phase: 17-docs-migration-runbook-operator-guide-plan-01
    provides: docs/migration-v1.2.md (link target referenced from README's Migrating from v1.1 subsection)
  - phase: 17-docs-migration-runbook-operator-guide-plan-02
    provides: .env.example v1.2 secrets schema (referenced by name in Migrating subsection — JWT_SECRET, CSRF_SECRET)
provides:
  - External API consumer entrypoint to v1.2 auth surface (OPS-05)
  - Single README section covering registration/login/logout flow, key issuance, bearer usage, free-vs-Pro tier matrix, mailto password reset
  - Cross-link to operator runbook (docs/migration-v1.2.md) for v1.1 -> v1.2 upgrade path — no step bodies duplicated
affects: []

tech-stack:
  added: []
  patterns:
    - "Insert-only README edits — pre-existing content preserved byte-for-byte; new top-level section spliced between stable anchor lines (`In production, the frontend is served...` + `---` + `The whisperX API is a tool...`)"
    - "Curl-snippet contract literal verbatim — every snippet shows EXACT header form (`Authorization: Bearer whsk_<prefix>_<random>`), EXACT endpoint paths (`/auth/register`, `/api/keys`, `/speech-to-text`, `/task/<uuid>`), EXACT response shape one-liner — verifier-grep asserts the literal token strings"
    - "Free vs Pro = markdown table (not nested bullets) — flat 5-row matrix; nested-if invariant zero; column header pattern matches sibling Tech Stack table at the top of the README"
    - "DRY enforcement at file boundary — README's Migrating from v1.1 subsection contains ONE link to `docs/migration-v1.2.md` and zero migration command bodies; verifier-grep asserts `alembic stamp 0001_baseline` + `python -m app.cli backfill-tasks` + `alembic upgrade 0002_auth_schema` + `python -m app.cli create-admin` all == 0 in README"
    - "SRP boundary — README owns API-consumer entrypoint narrative; `.env.example` owns env-var schema; `docs/migration-v1.2.md` owns migration step bodies; each surface non-overlapping"

key-files:
  created:
    - .planning/phases/17-docs-migration-runbook-operator-guide/17-03-SUMMARY.md
  modified:
    - README.md

key-decisions:
  - "PLAN-prescribed locked block honored verbatim (lines 179-289 of 17-03-PLAN.md) — text flow diagram + 7 bullet items in Registration section + 3-step curl in Issuing + 2-curl bearer in Using + 5-row table in Free/Pro + locked Migrating prose; the in-prompt `<readme_section_locked_structure>` block was a simpler alternative — PLAN.md was chosen as authoritative source per the plan's verbatim directive (line 178: 'do NOT paraphrase headings, table values, or curl snippets')"
  - "Insertion anchor: the `In production, the frontend is served directly by FastAPI at /ui` line + `---` + `The whisperX API is a tool...` line — single Edit splice with no other byte changes; preserves existing badges/Fork Information/Web UI block + Documentation/Getting Started/Troubleshooting trailing structure"
  - "Free vs Pro values locked from PLAN.md decisions block + REQUIREMENTS.md RATE-03..RATE-10 + PROJECT.md (5 req/hr, <=5 min, 30 min/day, tiny+small, 1 concurrent for free; 100/hr, <=60 min, 600 min/day, all models, 3 concurrent for Pro €5/mo) — values are locked invariants, not subject to Claude discretion"
  - "Trial mention added — PLAN block notes 'Default tier is `trial`. The trial counter starts at first key creation (RATE-08).' before the table; preserves Phase 13-04 AuthService.start_trial_if_first_key invariant in operator-facing surface"
  - "Bullet form `Endpoint: POST /api/keys (cookie session + matching X-CSRF-Token) -> 201 + show-once plaintext key` added under the Issuing curl block — original PLAN block had `POST /api/keys` only inside the curl URL (`-X POST https://your-host/api/keys`), which the acceptance grep `grep -c 'POST /api/keys' README.md >= 1` does not match (POST is followed by ` https://`, not ` /api/keys`); inline bullet preserves the verbatim PLAN block while satisfying the literal-token grep gate"
  - "501 stubs (BILL-05/BILL-06) flagged inline under Free vs Pro — operator/consumer reads the limit table THEN immediately sees the v1.2 stub status without backtracking; eliminates a follow-up Q&A loop"
  - "Migrating subsection deliberately short — single link sentence + paragraph describing what the runbook covers + new-deployment fallback (copy .env.example, openssl rand -hex 32, alembic upgrade head against empty DB); zero step bodies; zero alembic CLI invocations beyond the empty-DB sentence"

patterns-established:
  - "README docs-phase verifier-grep gate set — existence + 5 subheadings + 5 routes + bearer header literal + mailto + cross-link + 5-row tier table + DRY zero-occurrence on migration command tokens + DRY zero-occurrence on env-var declarations + ordering invariant via awk monotonic line numbers + insertion-position invariant via awk Web-UI-< Auth < Documentation"
  - "Insert-only README workflow — Read README.md fully -> identify stable 3-line anchor (last line of preceding section + `---` + first line of following section) -> single Edit replacing the 3-line anchor with anchor-prefix + new section + `---` + anchor-suffix -> verify via grep before commit -> never use Write for README edits"
  - "DRY split between README + .env.example + docs/migration-v1.2.md — README references each by relative path; cross-file grep gates verify zero overlap of migration commands or env-var declarations"

requirements-completed: [OPS-05]

duration: 4min
completed: 2026-05-01
---

# Phase 17 Plan 03: Docs — README v1.2 Auth Section Summary

**README.md gains a `## Authentication & API Keys (v1.2)` top-level section (5 subheadings, 3 curl snippets, free-vs-Pro tier matrix, mailto reset link, cross-link to migration runbook) delivering OPS-05.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-01T16:41:42Z
- **Completed:** 2026-05-01T16:43:30Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- README.md gains a new `## Authentication & API Keys (v1.2)` top-level section (110 insertion lines, zero deletions) inserted between the existing Web UI (v1.0) block and the v1.0 API prose introduction.
- Five anchored subheadings present in locked order: Registration & Login Flow, Issuing API Keys, Using an API Key, Free vs Pro Tiers, Migrating from v1.1.
- Three curl snippets: (1) cookie login + csrf_token read + `POST /api/keys` show-once issuance, (2) bearer transcribe submit (`POST /speech-to-text`), (3) bearer task poll (`GET /task/<uuid>`).
- ASCII text flow diagram for register/login/logout cookie session lifecycle.
- Free vs Pro markdown table — 5 limit rows: Requests/hour, File size, Duration cap, Models, Concurrent slots; concrete v1.2 values for free + v1.3-stub Pro tier.
- Limit-hit response taxonomy (429+Retry-After, 402, 403) and 501-stub status (POST /billing/checkout, POST /billing/webhook) noted under Free vs Pro.
- mailto:hey@logingrupa.lv password reset link present in Registration & Login Flow bullet list (AUTH-07 — no SMTP in v1.2).
- Migrating subsection cross-links to `docs/migration-v1.2.md` (single link, no step bodies duplicated — DRY enforced cross-file) plus a 1-paragraph new-deployment fallback (copy .env.example, generate secrets, run `alembic upgrade head` against empty DB).
- Pre-existing README content preserved byte-for-byte: Fork Information, Web UI (v1.0) block + all subsections, Documentation block, Getting Started, Troubleshooting, Related — verified via `awk` line-number invariant (Web UI at line 45 < Auth section at line 184 < Documentation at line 296).

## Task Commits

1. **Task 1: Insert `## Authentication & API Keys (v1.2)` section into README.md** — `674fb3e` (docs)

**Plan metadata commit:** pending (final-commit step below).

## Files Created/Modified

- `README.md` — 110-line insertion of `## Authentication & API Keys (v1.2)` section between the closing of the Web UI (v1.0) block and the opening of the v1.0 API prose; existing top-level structure (`# whisperX REST API`, badges, `## Fork Information`, `## Web UI (v1.0)`, `## Documentation`, `## System Requirements`, `## Getting Started`, `## Troubleshooting`, `## Related`) preserved byte-for-byte.
- `.planning/phases/17-docs-migration-runbook-operator-guide/17-03-SUMMARY.md` — this file.

## Decisions Made

- **PLAN-prescribed locked block as authoritative source.** Plan 17-03-PLAN.md `<action>` block (lines 179-289) and the in-prompt `<readme_section_locked_structure>` block describe two slightly different layouts — the PLAN's is more comprehensive (text flow diagram, RATE-08 trial note, 4 bullet items in Registration with explicit ANTI-01/02 citations). The PLAN explicitly directs "verbatim — do NOT paraphrase headings, table values, or curl snippets" (line 178). PLAN block chosen; verifier-grep set from BOTH layouts satisfied because the PLAN block is a strict superset of the prompt block's required tokens.
- **Insertion anchor.** Single 3-line splice: `In production, the frontend is served directly by FastAPI at /ui, so no proxy is needed.` + blank + `---` + blank + `The whisperX API is a tool...`. The `---` horizontal rule pattern matches Phase 17's existing rule-separator style elsewhere in the README.
- **Free vs Pro values locked.** Free tier (5 req/hr, <=5 min, 30 min/day, tiny+small, 1 concurrent slot) sourced from REQUIREMENTS.md RATE-03..RATE-10 and PROJECT.md key-decisions. Pro tier (100 req/hr, <=60 min, 600 min/day, all models incl. large-v3, 3 concurrent slots, €5/mo) is the v1.3-stub placeholder; v1.2 Pro routes return 501 (BILL-05/06).
- **`POST /api/keys` literal added as bullet** outside the curl block. The original PLAN block embeds the route only inside `-X POST https://your-host/api/keys`, which doesn't match the acceptance-grep token `POST /api/keys` (POST is followed by space then `https`, not space then `/api/keys`). Added a one-line bullet `Endpoint: POST /api/keys (cookie session + matching X-CSRF-Token) -> 201 + show-once plaintext key` above the existing detail bullets — preserves the verbatim PLAN block and satisfies the literal-token grep gate.
- **Trial mention preserved.** PLAN block opens Free vs Pro with `Default tier is trial. The trial counter starts at first key creation (RATE-08).` — kept verbatim. Operator-facing surface for the Phase 13-04 `AuthService.start_trial_if_first_key` invariant.
- **501 stub status flagged inline.** PLAN block closes Free vs Pro with `Pro checkout (POST /billing/checkout) and the Stripe webhook (POST /billing/webhook) return 501 Not Implemented in v1.2 — schema is in place; live Stripe ships in v1.3 (BILL-05, BILL-06).` — kept verbatim. Operator/consumer reads the limit table THEN immediately sees the v1.2 stub status; no follow-up loop.
- **Migrating subsection short by design.** Single link sentence + 1 paragraph describing runbook scope + new-deployment fallback (copy .env.example, `openssl rand -hex 32` for JWT_SECRET/CSRF_SECRET, `alembic upgrade head` against empty DB). DRY: zero migration command bodies; verifier-grep `grep -c 'alembic stamp 0001_baseline' README.md` == 0.

## Deviations from Plan

**[Rule 1 - Bug] Added `Endpoint: POST /api/keys` bullet above Issuing API Keys detail bullets.**
- **Found during:** Task 1 verification (acceptance grep gate `grep -c "POST /api/keys" README.md >= 1`).
- **Issue:** PLAN-prescribed block had `POST /api/keys` only inside the curl URL form `-X POST https://your-host/api/keys` — the literal token `POST /api/keys` (with `/api` immediately after the space) is not present in the curl URL because the host segment intervenes (`POST https://your-host/api/keys`).
- **Fix:** Added a single bullet `Endpoint: POST /api/keys (cookie session + matching X-CSRF-Token) -> 201 + show-once plaintext key` above the existing 3 detail bullets. Mirrors the bullet form already used in Registration & Login Flow (e.g., `Endpoint: POST /auth/register {email, password} -> 201`).
- **Files modified:** README.md (+1 bullet line, no other touches).
- **Commit:** `674fb3e` (same task commit; the bullet was added before the commit).

**Notable plan/prompt reconciliation (not a deviation):** Plan 17-03-PLAN.md `<action>` block (lines 179-289) and the in-prompt `<readme_section_locked_structure>` block are two slightly different layouts. The PLAN block is the comprehensive form (text flow diagram + 7-bullet Registration list with ANTI-01/02 citations + RATE-08 trial note + 501-stub mention) and the prompt block is the simpler form (4-bullet Registration + table-only Free/Pro). The PLAN.md explicit directive "verbatim — do NOT paraphrase headings, table values, or curl snippets" + the PLAN block satisfying BOTH grep sets (it is a strict superset of the prompt block's required tokens) makes the PLAN block the operative authority. Verifier-grep gates from BOTH layouts pass.

## Issues Encountered

None — single-task docs plan, no auth/runtime/build dependencies. The single Rule-1 fix above was applied inline before commit.

## User Setup Required

None — pure documentation, no external service configuration.

## Threat Flags

None — README documents existing auth surface (Phase 13 already shipped). No new network endpoints, auth paths, or trust-boundary changes introduced.

Threat register entries from PLAN `<threat_model>` (T-17-08 wrong header form, T-17-09 real-key exposure, T-17-10 wrong reset address, T-17-11 docs/runbook drift) all mitigated:
- T-17-08: literal `Authorization: Bearer whsk_PREFIX01_<22charbase64random>` form present in 2 curl snippets — verifier-grep == 2.
- T-17-09: placeholder `whsk_PREFIX01_<22charbase64random>` (literal "PREFIX01") used throughout — clearly fake, no real key shape.
- T-17-10: `mailto:hey@logingrupa.lv` matches PROJECT.md and `app/api/auth_routes.py` 403 detail — verifier-grep == 1.
- T-17-11: Migrating subsection contains zero migration command bodies — verifier-grep `grep -c 'alembic stamp 0001_baseline' README.md` == 0; `grep -c 'python -m app.cli backfill-tasks' README.md` == 0; `grep -c 'alembic upgrade 0002_auth_schema' README.md` == 0; `grep -c 'python -m app.cli create-admin' README.md` == 0.

## Next Phase Readiness

- Phase 17 closes — all 3 success criteria delivered: (1) docs/migration-v1.2.md operator runbook (Plan 17-01, OPS-03); (2) .env.example v1.2 schema (Plan 17-02, OPS-04); (3) README v1.2 auth section (this plan, OPS-05).
- v1.2 milestone OPS-* requirement set fully closed (OPS-01..OPS-05).
- Phase 18 (stretch, optional) is the only remaining v1.2 phase — gated on observed need; no blockers.

## Self-Check

- [x] `README.md` exists (FILE_EXISTS).
- [x] Pre-existing top-level heading preserved: `^# whisperX REST API` count == 1.
- [x] New top-level section: `^## Authentication & API Keys (v1.2)$` count == 1.
- [x] All 5 subheadings present exactly once: Registration & Login Flow, Issuing API Keys, Using an API Key, Free vs Pro Tiers, Migrating from v1.1.
- [x] Routes present: POST /auth/register == 2; POST /auth/login == 2; POST /auth/logout == 3; POST /api/keys == 1; POST /speech-to-text == 1.
- [x] Bearer header literal: `Authorization: Bearer whsk_` count == 2 (transcribe + task-poll snippets); X-CSRF-Token count == 3.
- [x] Placeholder key: `whsk_PREFIX01` count == 3.
- [x] mailto reset link: `mailto:hey@logingrupa.lv` count == 1.
- [x] Cross-link to runbook: `docs/migration-v1.2.md` count == 1.
- [x] Free vs Pro table rows (5): Requests/hour == 1; File size == 1; Duration cap == 1; Models == 1; Concurrent slots == 1.
- [x] DRY: zero migration command bodies in README — alembic stamp 0001_baseline == 0; alembic upgrade 0002_auth_schema == 0; python -m app.cli create-admin == 0; python -m app.cli backfill-tasks == 0.
- [x] DRY: zero env-var declarations in README — `^JWT_SECRET=` == 0; `^CSRF_SECRET=` == 0.
- [x] Subsection ordering invariant (awk monotonic): Registration (188) < Issuing (213) < Using (242) < Free/Pro (263) < Migrating (282).
- [x] Top-level position invariant (awk): Web UI (45) < Auth (184) < Documentation (296).
- [x] Pre-existing structure preserved: Web UI == 1; Documentation == 1; Getting Started == 1; Troubleshooting == 1.
- [x] Commit `674fb3e` exists in git log.
- [x] No accidental file deletions in commit (`git diff --diff-filter=D HEAD~1 HEAD` empty).

## Self-Check: PASSED

---
*Phase: 17-docs-migration-runbook-operator-guide*
*Completed: 2026-05-01*
