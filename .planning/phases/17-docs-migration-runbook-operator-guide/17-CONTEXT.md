# Phase 17: Docs + Migration Runbook + Operator Guide - Context

**Gathered:** 2026-05-01
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, all areas accepted)

<domain>
## Phase Boundary

Operator and external API consumer have written guidance. Three deliverables — `docs/migration-v1.2.md`, expanded `.env.example`, and a v1.2 auth section in `README.md` — let an operator unfamiliar with the source migrate from v1.1 to v1.2 end-to-end and let an external user understand how to register, issue keys, and transcribe via API. No code changes — pure documentation.

</domain>

<decisions>
## Implementation Decisions

### Migration Runbook Structure
- Path: `docs/migration-v1.2.md` — matches Phase 17 success criterion verbatim.
- Eight sections: Overview, Pre-flight backup, Stamp baseline, Upgrade 0002 auth schema, Create admin user, Backfill tasks, Upgrade head (0003 NOT NULL), Smoke verify, Rollback.
- Every step shows copy-pasteable bash command blocks. Operator follows commands without consulting source code.
- Explicit rollback section: `alembic downgrade -1` per migration, plus DB-restore-from-backup steps for the unrecoverable case.

### README Auth Section
- Placement: new top-level `## Authentication & API Keys (v1.2)` section after Web UI, before Tech Stack.
- Depth: concise — text flow diagram for register/login, API key issuance via cookie, bearer usage, free vs Pro table, mailto reset link.
- Code samples: three curl snippets — register, list keys via cookie session, transcribe via bearer.
- Free vs Pro: markdown table with Limit / Free / Pro columns covering req/hr, file size, duration, models, concurrency.

### .env.example Layout
- Strategy: append a new `# === Auth (v1.2) ===` block after the Logging section. Existing var order preserved.
- Secrets: placeholder `<change-me-in-production>` plus an inline comment showing the `openssl rand -hex 32` generator command.
- Comment density: one-line purpose comment per var with a cross-reference to the runbook section that uses it.
- Grouping: five subsections — Auth secrets, Cookie & CORS, Rate limit, Argon2, hCaptcha.

### Claude's Discretion
- Exact prose, table formatting, and intra-section ordering at Claude's discretion as long as the locked structure above holds.
- Section length — be concise; the success criterion is followability, not page count.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docs/CONFIGURATION_MIGRATION.md` exists — sibling doc style anchor.
- `tests/integration/test_migration_smoke.py` (Phase 16) is the executable mirror of the runbook — use it as the source of truth for migration step ordering.
- `alembic/versions/0001_baseline.py`, `0002_auth_schema.py`, `0003_tasks_user_id_not_null.py` define the migration sequence.
- `app/cli/` admin-create + backfill-tasks commands documented in their own SUMMARYs (Phase 12) — runbook references them.
- `.env.example` already has Environment / Database / WhisperX / Logging sections — append, do not rewrite.

### Established Patterns
- Code-fenced bash blocks with `$` prompts and explicit comments per command.
- Tables for limit / option matrices (precedent: README Tech Stack table, PROJECT.md Key Decisions).
- Cross-references via relative links (e.g., `[backfill](#5-backfill-tasks)`).

### Integration Points
- `docs/migration-v1.2.md` (new) — referenced from README "Migrating from v1.1".
- `.env.example` (modified) — referenced from runbook step "Pre-flight: configure .env".
- `README.md` (modified) — links to runbook for operators, exposes auth flow to API consumers.

</code_context>

<specifics>
## Specific Ideas

- Runbook step 5 (admin create): `python -m app.cli create-admin --email <op@example.com>` — getpass-based password prompt; warn that Windows pipes won't work with getpass.
- Runbook step 6 (backfill): `python -m app.cli backfill-tasks --admin-email <op@example.com>` — non-interactive `--assume-yes` available for CI.
- Free vs Pro table values pulled from `app/core/free_tier_gate.py` and PROJECT.md decision row "Free tier: 5 req/hr + file <5min + 30min/day + tiny/small models only + 1 concurrent slot".
- Bearer curl example uses `whsk_*` prefix and `Authorization: Bearer whsk_...` header form per Phase 13-04 contract.
- Mailto reset link: `mailto:hey@logingrupa.lv` — matches PROJECT.md and `app/api/auth_routes.py` 403 detail.

</specifics>

<deferred>
## Deferred Ideas

- Sequence diagrams for auth flow — defer to v1.3 when SMTP password reset replaces mailto.
- Postman collection for auth endpoints — backlog.
- Multi-language README translations — backlog.

</deferred>
