---
phase: 17
status: findings_found
date: 2026-05-01
findings_count: 9
critical: 0
high: 2
medium: 2
low: 3
info: 2
---

# Phase 17 Code Review: Docs + Migration Runbook + Operator Guide

**Reviewed:** 2026-05-01
**Depth:** standard (docs-appropriate)
**Files Reviewed:** 3
**Files Reviewed List:**
- docs/migration-v1.2.md (NEW)
- .env.example (MODIFIED — Auth (v1.2) block appended)
- README.md (MODIFIED — Authentication & API Keys (v1.2) section inserted)

**Status:** findings_found

## Summary

Phase 17 ships three documentation deliverables (OPS-03, OPS-04, OPS-05). Structural conformance is excellent — every locked heading, sequence, and verifier-grep gate from the three plans passes. Tiger-style boundary asserts are present in the runbook (every command shows expected output). DRY across files holds (no migration command body duplicated outside `docs/migration-v1.2.md`; no env-var declaration duplicated outside `.env.example`).

The substantive issues are about **factual accuracy of the operator-facing surface vs codebase ground truth**, primarily concentrated in `.env.example`:

- **Two HIGH** findings: bare env-var names that the runtime will silently ignore (because AuthSettings uses `env_prefix="AUTH__"` with `case_sensitive=True`), and three rate-limit env vars that have no consumer in code at all (decorator literals are hardcoded).
- **Two MEDIUM** findings: Argon2 var-name drift (`ARGON2_TIME_COST` / `ARGON2_MEMORY_KIB` documented; codebase reads `ARGON2_T_COST` / `ARGON2_M_COST`), and missing `AUTH__V2_ENABLED=true` documentation (without it, the v1.2 auth/key/billing routes never mount in dev/test environments).
- **Three LOW** findings: minor wording / accuracy gaps that won't break operator flow but reduce precision.
- **Two INFO** findings: stylistic / completeness suggestions.

The 17-02 SUMMARY documents the bare-name vs `AUTH__`-prefixed divergence as "documented, not fixed" with rationale "ROADMAP success criterion 2 names the bare form." This review classifies it as HIGH because the cost is operator-facing silent-failure in development plus a confusing fail-loud error message in production (the var name in the error never appears in any doc). Production safety holds (validator catches it), but UX cost is real and the `.env.example` file is the very surface this phase is meant to clarify.

---

## High

### HR-01: `.env.example` Auth (v1.2) vars use bare names that AuthSettings will ignore

**File:** `.env.example:86-119` (entire `# === Auth (v1.2) ===` block)
**Category:** factual accuracy / silent-failure config

**Issue:**
`AuthSettings` in `app/core/config.py:145-151` is configured with `env_prefix="AUTH__"` and `case_sensitive=True`. Every field on the model — `JWT_SECRET`, `CSRF_SECRET`, `COOKIE_SECURE`, `COOKIE_DOMAIN`, `FRONTEND_URL`, `TRUST_CF_HEADER`, `HCAPTCHA_*`, `ARGON2_*`, `V2_ENABLED`, `JWT_TTL_DAYS` — is read from the env namespace `AUTH__<FIELD_NAME>` only.

The `.env.example` block declares these as bare names (`JWT_SECRET=`, `CSRF_SECRET=`, `COOKIE_SECURE=`, etc.). When an operator copies `.env.example` to `.env` verbatim and starts the app:

1. `JWT_SECRET=<change-me-in-production>` is silently ignored by `AuthSettings`.
2. `AuthSettings.JWT_SECRET` falls back to its in-code default `SecretStr("change-me-dev-only")`.
3. In development, the app boots; the operator believes their config was applied; behavior diverges from intent.
4. In production, `_reject_dev_defaults_in_production` raises `ValueError("AUTH__JWT_SECRET must be set in production")` — the variable name in the error message (`AUTH__JWT_SECRET`) never appears in `.env.example`, leaving the operator to guess the prefix translation.

The existing Notes block (`.env.example:126-129`) shows lowercase `database__DB_URL`, `whisper__WHISPER_MODEL`, `logging__LOG_LEVEL` examples — which would also fail for AuthSettings because `case_sensitive=True` requires the exact uppercase `AUTH__` form.

The 17-02 SUMMARY's "Decisions Made" paragraph rationalises this as a ROADMAP-success-criterion-driven naming (the criterion lists bare names) and notes the divergence is "cosmetic." The runtime behaviour above is not cosmetic — it is silent default-fallback in dev and a cryptic-but-correct fail-loud in production. Phase 17's stated purpose is to let an operator unfamiliar with the source configure v1.2 from `.env.example` without consulting code; the current block does not meet that bar.

**Fix:**
Add an explicit, prominent header comment to the Auth (v1.2) block documenting the prefix translation rule, OR rename the declared variables to their wire form. Concrete option (least-invasive):

```bash
# ============================================
# === Auth (v1.2) ===
# ============================================
# v1.2 introduces multi-user auth + API keys + Stripe-ready billing.
# See docs/migration-v1.2.md for the operator runbook.
#
# IMPORTANT: every variable in this block is read by AuthSettings, which
# uses env_prefix="AUTH__" with case-sensitive matching. In your real .env,
# prefix every name below with AUTH__ (uppercase, double underscore):
#     JWT_SECRET=...     -> AUTH__JWT_SECRET=...
#     COOKIE_SECURE=...  -> AUTH__COOKIE_SECURE=...
# The bare names below are the operator-facing identifier; the AUTH__ form
# is the wire format pydantic-settings reads. Without the prefix the values
# are silently ignored and AuthSettings falls back to its in-code defaults.
```

Alternative (cleaner): rename the declared lines to `AUTH__JWT_SECRET=`, `AUTH__CSRF_SECRET=`, etc. — the file then becomes copy-paste-and-run correct. The ROADMAP success criterion text can be reconciled by treating the bare name as the conceptual identifier and the AUTH__ form as its concrete env-var spelling.

---

### HR-02: Three RATE_LIMIT_*_PER_HOUR env vars have no consumer in the codebase

**File:** `.env.example:103-107`
**Category:** factual accuracy / dead config

**Issue:**
The block declares three rate-limit env vars:
- `RATE_LIMIT_REGISTER_PER_HOUR=3`
- `RATE_LIMIT_LOGIN_PER_HOUR=10`
- `RATE_LIMIT_FREE_REQ_PER_HOUR=5`

`grep -rn "RATE_LIMIT_REGISTER\|RATE_LIMIT_LOGIN\|RATE_LIMIT_FREE" app/` returns zero matches. The actual rate limits are hardcoded as decorator string literals in `app/api/auth_routes.py:123` (`@limiter.limit("3/hour")`) and `:160` (`@limiter.limit("10/hour")`). The free-tier per-hour limit is hardcoded as `max_per_hour=5` in `app/services/free_tier_gate.py:59` (`FREE_POLICY` named tuple).

An operator who edits `RATE_LIMIT_LOGIN_PER_HOUR=20` to relax login throttling during a soak test will see no behaviour change; the slowapi decorator still says `"10/hour"`. This is dead config presented as live config.

The inline comment ("Per /24 IPv4 subnet (or /64 IPv6). Anti-spam (ANTI-01/02).") asserts a contract that the runtime does not honour.

**Fix:**
Two options, pick one:

A) Remove the three vars from `.env.example` (and adjust the surrounding subsection — possibly drop the `# --- Rate limit ---` heading entirely if no live var remains). Update the 17-02-PLAN's `<artifacts>` block accordingly. This honours the cap-as-code reality.

B) Wire the vars in code: read `settings.auth.RATE_LIMIT_*` into the decorator/policy values and re-test rate-limit suites. This is the larger fix; it converts dead config into live config consistent with the doc.

Option A is the minimal correctness fix consistent with the docs-only phase boundary. Option B would belong in a follow-up code phase.

Note: ROADMAP success criterion 2 lists `RATE_LIMIT_*` by name. If those names are kept in `.env.example` for ROADMAP conformance without wiring, add a one-line comment explicitly flagging "documented for v1.3 — currently hardcoded at decorator site" so future operators do not waste cycles tuning a no-op.

---

## Medium

### MR-01: Argon2 var names diverge from AuthSettings field names

**File:** `.env.example:111-113`
**Category:** factual accuracy

**Issue:**
The block declares `ARGON2_TIME_COST=2` and `ARGON2_MEMORY_KIB=19456`. `AuthSettings` (`app/core/config.py:158-159`) declares the corresponding fields as `ARGON2_M_COST` and `ARGON2_T_COST`. Even after the `AUTH__` prefix fix from HR-01, an operator who sets `AUTH__ARGON2_TIME_COST=4` will see no Argon2 retuning at runtime — `AuthSettings.ARGON2_T_COST` keeps its default `2`.

`ARGON2_PARALLELISM` matches the codebase field name; only the two cost vars drift.

The 17-02 SUMMARY documents the divergence with rationale "ROADMAP success criterion 2 lists these names explicitly." The numeric defaults match (19456 / 2 / 1) so dev/test boots succeed with no change observed; the silent-no-op only bites operators who try to tune cost upward in response to slow Argon2 benchmarks (the inline comment explicitly invites tuning: "Tune up if Argon2 benchmark p99 < 100ms").

**Fix:**
Pick one:

A) Rename in `.env.example` to match the codebase: `ARGON2_T_COST=2` / `ARGON2_M_COST=19456` (and update the AUTH__ prefix per HR-01: `AUTH__ARGON2_T_COST=2`, `AUTH__ARGON2_M_COST=19456`).
B) Rename in `app/core/config.py` AuthSettings fields to the descriptive form `ARGON2_TIME_COST` / `ARGON2_MEMORY_KIB`, audit consumers (token_service, password hasher), and re-run the Argon2 benchmark gate.

Option A is the docs-only fix; option B is the code fix that aligns the names operators see with the names already in widespread use.

---

### MR-02: AUTH__V2_ENABLED is required for v1.2 routes to mount, but is not documented in .env.example

**File:** `.env.example:80-119` (Auth (v1.2) block) and `docs/migration-v1.2.md:27-33` (Pre-requisite checklist)
**Category:** missing config / operator runbook gap

**Issue:**
`app/main.py:247-252` gates inclusion of the Phase 13 routers (auth, keys, account, billing, ws_ticket) on `is_auth_v2_enabled()`, which reads `settings.auth.V2_ENABLED` (`app/core/feature_flags.py:23`). The default is `False` (`app/core/config.py:167-170`).

In production, `app/main.py:257` raises `RuntimeError` if `ENVIRONMENT=production` and `V2_ENABLED=False` — fail-loud, fine. In dev/test, `V2_ENABLED=False` boots silently with the v1.2 auth surface absent.

An operator following the runbook in a staging/dev environment, who does not set `AUTH__V2_ENABLED=true`, will:
1. Complete the migration successfully (alembic stamp/upgrade chain works regardless of V2_ENABLED).
2. Run smoke verify (Section 8) successfully — `uvicorn app.main:app` boots with Phase 13 routers omitted.
3. Try to test `POST /auth/register` per README — receive `404 Not Found` because the route never mounted.
4. Have no documented hint about the missing flag.

`.env.example:80-119` does not declare `AUTH__V2_ENABLED` (or `V2_ENABLED`) anywhere. `docs/migration-v1.2.md` does not mention it in the Pre-requisite checklist or Smoke Verify section.

**Fix:**
Two changes, both small:

A) Add to `.env.example` Auth (v1.2) block (e.g., as a new subsection or inline near Auth secrets):
```bash
# --- Feature flag ---
# AUTH__V2_ENABLED=true mounts the v1.2 auth/keys/billing routers.
# Production REFUSES to boot with this set to false (app/main.py:257).
# Dev/test default is false — set true to exercise v1.2 routes locally.
V2_ENABLED=true
```
(Apply the AUTH__ prefix-comment fix from HR-01.)

B) Update `docs/migration-v1.2.md` Section 1 Pre-requisite checklist to include "`AUTH__V2_ENABLED=true` is set in `.env` (otherwise the v1.2 routes are not mounted)" and Section 8 Smoke Verify to add a curl that hits `/auth/register` and asserts 422 (registration disabled stub) or 201 (registration succeeds), proving the router is mounted.

---

## Low

### LR-01: Pro tier "all (incl. large-v3)" overstates the codebase's allowed_models set

**File:** `README.md:272`
**Category:** accuracy

**Issue:**
The Free vs Pro tier table says: `Models | tiny, small | all (incl. large-v3)`.

`app/services/free_tier_gate.py:71-74` defines the Pro `allowed_models` frozenset as `{"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}`. The Whisper model catalogue from README.md:374-380 includes `large-v3-turbo`, `distil-large-v2`, `distil-large-v3`, `distil-medium.en`, `distil-small.en`, the `.en` variants, and `nyrahealth/faster_CrisperWhisper` — none of which are in the Pro allowlist.

A Pro user requesting `large-v3-turbo` or any `distil-*` model would receive `403 Forbidden` (per RATE-06 messaging), contradicting the README claim of "all".

**Fix:**
Replace `all (incl. large-v3)` with the actual allowlist or its accurate range, e.g.:
```
| Models | `tiny`, `small` | `tiny`, `base`, `small`, `medium`, `large`, `large-v2`, `large-v3` |
```
Or, if the intent is for Pro to receive the full catalogue and the gate is the bug, file a follow-up to widen `PRO_POLICY.allowed_models`. For docs-only fix, narrow the README claim to match `free_tier_gate.py`.

---

### LR-02: README asserts /dashboard/keys without the /ui base prefix

**File:** `README.md:215`
**Category:** accuracy / link target

**Issue:**
"Authenticated browser users issue keys via `/dashboard/keys`."

The frontend is mounted under `/ui/` (`frontend/vite.config.ts:101` `base: '/ui/'`; CLAUDE.md "Vite dev server (port 5173, base `/ui`)"). The actual user-visible URL on the deployed app is `/ui/dashboard/keys`. A bare `/dashboard/keys` request to FastAPI would be redirected by the dev-only middleware (`vite.config.ts:34` `Location: /ui${pathname}`) but in production behaviour depends on the FastAPI mount config.

**Fix:**
Replace with `/ui/dashboard/keys` to match the deployed URL.

---

### LR-03: HCAPTCHA_SECRET placeholder lacks the "leave blank" callout the threat model required

**File:** `.env.example:117-119`
**Category:** missing safety guidance / threat model misalignment

**Issue:**
17-02-PLAN T-17-07 ("hCaptcha secret committed to .env.example as a placeholder appears legitimate") prescribes a placeholder `<change-me-in-production-or-leave-blank-while-disabled>`. The shipped block uses bare empty values (`HCAPTCHA_SITE_KEY=` and `HCAPTCHA_SECRET=`) without the explicit "leave blank while disabled" guidance per variable. The block-level comment ("Activate only if abuse observed during v1.2 soak") covers the case but does not telegraph that empty is the correct dev/test value.

**Fix:**
Either add an inline comment per var (`# Leave blank while HCAPTCHA_ENABLED=false`) or accept the block-level comment as sufficient. This is a minor presentation issue.

---

## Info

### IR-01: README API Keys section omits GET /api/keys

**File:** `README.md:213-240`
**Category:** completeness

**Issue:**
The `### Issuing API Keys` section documents `POST /api/keys` and `DELETE /api/keys/{id}` but never mentions `GET /api/keys` (list-keys). The endpoint exists (`app/api/key_routes.py:65-72`) and is the only way for an external bearer client to discover its own key prefixes.

**Fix:**
Optional. Add a one-line bullet under Issuing or a separate `### Listing API Keys` mini-section, e.g.:
```
- List your keys (cookie or bearer): `GET /api/keys` -> 200 + array of `{id, name, prefix, created_at, last_used_at, status}`
```

---

### IR-02: Runbook Section 8 Check 5 admits the check is non-load-bearing

**File:** `docs/migration-v1.2.md:324-330`
**Category:** tiger-style boundary clarity

**Issue:**
Check 5 ("Foreign-key enforcement is active") explains that `sqlite3 records.db "PRAGMA foreign_keys;"` may legitimately return `0` because the SQLite CLI does not invoke the engine listener. The narrative correctly explains why, but the check then has no fail criterion: the operator runs the command, sees `0`, and is told "this is fine." In tiger-style boundary terms, a check that always passes is not a check.

**Fix:**
Optional. Either (a) remove Check 5 and let the runtime listener be the implicit guarantor, or (b) replace it with a check that actually fires under a real connection — e.g., spawn a brief Python `engine.connect()` snippet that asserts `PRAGMA foreign_keys` is `1` after the listener attaches:
```bash
uv run python -c "from app.infrastructure.database.connection import engine; \
  print(engine.connect().exec_driver_sql('PRAGMA foreign_keys').scalar())"
# Expected: 1
```

---

## Cross-File DRY / SRP / Tiger-Style Verification

All cross-file invariants from the three plans hold:

- **DRY**: `grep -c "alembic stamp 0001_baseline" .env.example` == 0; `grep -c "alembic stamp 0001_baseline" README.md` == 0; `grep -c "python -m app.cli backfill-tasks" README.md` == 0; `grep -c "^JWT_SECRET=" README.md` == 0. Migration commands and env-var declarations live in exactly one file each.
- **SRP**: runbook contains migration procedure only (no auth-flow narrative, no env-var schema). `.env.example` contains config schema only (no curl, no migration steps). README contains API-consumer entrypoint only (no env-var declarations, no migration command bodies).
- **Tiger-style**: every fenced bash block in `docs/migration-v1.2.md` shows an explicit "Expected output" comment. Every curl snippet in `README.md` shows the response shape (e.g., `# Response: {"task_id": "<uuid>"}`).
- **Step ordering**: 1:1 mirror of `tests/integration/test_migration_smoke.py:119-122` (stamp → upgrade 0002 → admin/backfill → upgrade head) confirmed.

## Codebase Truth Cross-Checks

| Claim in docs                                         | Codebase truth                                                                  | Match |
|-------------------------------------------------------|----------------------------------------------------------------------------------|-------|
| `python -m app.cli create-admin --email <e>`          | `@app.command(name="create-admin")` with `--email/-e` Option                     | yes   |
| `python -m app.cli backfill-tasks --admin-email <e> --dry-run --yes` | `@app.command(name="backfill-tasks")` with `--admin-email`, `--dry-run`, `--yes/-y` | yes |
| Alembic revisions `0001_baseline`, `0002_auth_schema`, `0003_tasks_user_id_not_null` | Verbatim revision IDs in `alembic/versions/` | yes |
| 0003 pre-flight RuntimeError text                      | `alembic/versions/0003_tasks_user_id_not_null.py:52-56` (verbatim)              | yes   |
| `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `POST /auth/logout-all` | `app/api/auth_routes.py:117,154,183,198` (verbatim) | yes |
| `POST /api/keys`, `DELETE /api/keys/{id}`              | `app/api/key_routes.py:29,43,75` (router prefix `/api/keys`)                    | yes   |
| `POST /api/ws/ticket`                                  | `app/api/ws_ticket_routes.py:40,60` (router prefix `/api/ws`, route `/ticket`)  | yes   |
| `POST /speech-to-text`                                 | `app/api/audio_api.py:58` (route on stt_router, no prefix)                      | yes   |
| `POST /billing/checkout`, `POST /billing/webhook` -> 501 | `app/api/billing_routes.py:46,63` with `status_code=501`                       | yes   |
| `mailto:hey@logingrupa.lv`                             | `app/api/auth_routes.py:59` (`PASSWORD_RESET_HINT`)                              | yes   |
| Free tier: 5 req/hr, 5min file, 30min/day, 1 concurrent | `app/services/free_tier_gate.py:58-65`                                          | yes   |
| `whsk_<8-char-prefix>_<22-char-base64-random>` (~128 bits) | `app/api/key_routes.py` + KEY-02 spec                                       | yes   |
| Argon2 OWASP params m=19456 KiB, t=2, p=1              | `app/core/config.py:158-160` (numeric values match; field NAMES drift — see MR-01) | values yes / names no |
| `JWT_SECRET` env var                                   | `AUTH__JWT_SECRET` (env_prefix=`AUTH__`, case_sensitive=True) — see HR-01       | name no |

---

_Reviewed: 2026-05-01_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (docs-appropriate)_
