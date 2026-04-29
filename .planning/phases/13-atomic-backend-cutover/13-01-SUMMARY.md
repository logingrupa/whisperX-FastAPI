---
phase: 13-atomic-backend-cutover
plan: 01
subsystem: backend-foundation
tags: [auth, config, feature-flag, anti-spam, blocklist, deps]
requires:
  - Phase 11 AuthSettings + JWT/CSRF SecretStr scaffold (11-01)
  - Phase 12 admin CLI complete (12-04)
provides:
  - slowapi 0.1.9 import surface (Phase 13 / RATE-01)
  - stripe 15.1.0 boot-only import (Phase 13 / BILL-07)
  - AuthSettings.V2_ENABLED feature flag (atomic cutover gate)
  - AuthSettings.FRONTEND_URL (CORS allowlist; ANTI-06)
  - AuthSettings.COOKIE_SECURE / COOKIE_DOMAIN (cookie attrs; AUTH-04)
  - AuthSettings.TRUST_CF_HEADER (slowapi key_func; RATE-01)
  - AuthSettings.HCAPTCHA_ENABLED / SITE_KEY / SECRET (ANTI-05)
  - app.core.feature_flags.is_auth_v2_enabled() / is_hcaptcha_enabled()
  - data/disposable-emails.txt (5413-entry blocklist; ANTI-04)
  - Production-safety boot guards: V2 + localhost FRONTEND_URL OR insecure cookies → ValueError
affects:
  - pyproject.toml [project].dependencies (+2 deps)
  - app/core/config.py AuthSettings (+8 fields, +2 validator branches)
tech-stack:
  added:
    - slowapi==0.1.9
    - stripe==15.1.0
    - limits==5.8.0 (transitive)
    - deprecated==1.3.1 (transitive)
  patterns:
    - Feature flag isolation via app.core.feature_flags single source
    - Tiger-style fail-loud production guards in pydantic model_validator
    - Bundled static blocklist over runtime API call (deterministic boot)
key-files:
  created:
    - app/core/feature_flags.py
    - data/disposable-emails.txt
  modified:
    - pyproject.toml
    - app/core/config.py
decisions:
  - Bundle 5413-entry disposable-email list at repo root (data/disposable-emails.txt) sourced from disposable-email-domains/disposable-email-domains GitHub master branch — deterministic, network-free boot
  - Production safety guard fires inside AuthSettings model_validator (not main.py) — fails at config construction; cannot reach FastAPI startup with broken config
  - V2_ENABLED defaults False — dev environment continues legacy BearerAuthMiddleware until paired Phase 14 frontend ships
  - COOKIE_SECURE defaults False (dev convenience); production guard forces True when V2_ENABLED=true
  - Stripe imported as module-level only (no runtime calls in v1.2 per BILL-07 / D-Stripe-stub)
metrics:
  duration: "3m 39s"
  completed: "2026-04-29"
  tasks: 3
  commits: 3
  files_changed: 4
  lines_added: 5486
---

# Phase 13 Plan 01: Foundation Setup Summary

Wave 1 foundation: deps (slowapi+stripe), AuthSettings extension (8 envs + 2 prod safety guards), feature-flag helper, and disposable-email blocklist data file ship — every downstream Phase 13 plan can now import these primitives.

## What Was Built

### Task 1: Deps (commit `f71a7dd`)

Added two production deps to `pyproject.toml [project].dependencies`:
- `slowapi>=0.1.9` (resolved 0.1.9) — token-bucket per-IP rate limiting
- `stripe==15.1.0` — pinned exactly; imported at boot only

Both packages installed into `.venv` and importable:
```
slowapi 0.1.9
stripe 15.1.0 (api_version 2026-04-22.dahlia)
```

### Task 2: AuthSettings extension (commit `588f5c4`)

Added 8 fields to `app/core/config.py:AuthSettings` between `CSRF_SECRET` and the `_reject_dev_defaults_in_production` validator:

| Field             | Type      | Default                     | Purpose                                       |
| ----------------- | --------- | --------------------------- | --------------------------------------------- |
| V2_ENABLED        | bool      | False                       | Phase 13 atomic-cutover gate                  |
| FRONTEND_URL      | str       | http://localhost:5173       | CORS single-origin allowlist (ANTI-06)        |
| COOKIE_SECURE     | bool      | False                       | Cookie Secure attribute (prod must be true)   |
| COOKIE_DOMAIN     | str       | "" (browser default)        | Cookie Domain attribute                       |
| TRUST_CF_HEADER   | bool      | False                       | Trust CF-Connecting-IP for slowapi (RATE-01)  |
| HCAPTCHA_ENABLED  | bool      | False                       | Enable hCaptcha (ANTI-05)                     |
| HCAPTCHA_SITE_KEY | str       | ""                          | hCaptcha public site key                      |
| HCAPTCHA_SECRET   | SecretStr | ""                          | hCaptcha verify endpoint secret               |

Extended `_reject_dev_defaults_in_production` validator with two new branches that raise `ValueError` at construction time:
1. `V2_ENABLED=true` AND `FRONTEND_URL == "http://localhost:5173"` → "AUTH__FRONTEND_URL must be set when AUTH__V2_ENABLED=true in production"
2. `V2_ENABLED=true` AND `COOKIE_SECURE=false` → "AUTH__COOKIE_SECURE must be true when AUTH__V2_ENABLED=true in production"

All 15 existing config tests pass with no regressions.

### Task 3: feature_flags + blocklist (commit `c7482d1`)

**`app/core/feature_flags.py`** (29 lines): two flat-return helpers reading `get_settings().auth.*`:
- `is_auth_v2_enabled() -> bool` — wraps V2_ENABLED
- `is_hcaptcha_enabled() -> bool` — wraps HCAPTCHA_ENABLED

DRY: single import surface for downstream middleware/route registration code (no direct AuthSettings imports). SRP: pure config accessors, zero business logic. `grep -cE "^\s+if .*\bif\b"` returns 0 (no nested-if).

**`data/disposable-emails.txt`** (5413 lines): canonical disposable-domain blocklist fetched from `https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf`. Sorted lowercase ASCII, LF line endings, trailing newline at EOF, no comments or blank lines. All 5413 entries match `^[a-z0-9.-]+\.[a-z]+$`. Sample entries: `mailinator.com`, `yopmail.com`, `10minutemail.com` confirmed present.

Loader (consumer) ships in Plan 13-03 (auth_routes); this plan delivers the data file only.

## Verification

Final automated gates — all green:

```
$ pytest tests/unit/core/test_config.py -q
15 passed

$ python -c "import slowapi, stripe; from app.core.feature_flags import is_auth_v2_enabled; assert is_auth_v2_enabled() is False"
[ok]

$ python -c "from app.core.disposable_emails import is_disposable_email"
# Note: loader scheduled for Plan 13-03 — data file shipped this plan
# Manual verify: 'mailinator.com' in data/disposable-emails.txt → True
[ok]
```

Acceptance grep counts (all match plan expectations):

| Pattern                                   | Expected | Actual |
| ----------------------------------------- | -------- | ------ |
| `slowapi` in pyproject.toml               | ≥1       | 1      |
| `stripe==15.1.0` in pyproject.toml        | 1        | 1      |
| `V2_ENABLED: bool` in config.py           | 1        | 1      |
| `FRONTEND_URL: str` in config.py          | 1        | 1      |
| `COOKIE_SECURE: bool` in config.py        | 1        | 1      |
| `TRUST_CF_HEADER: bool` in config.py      | 1        | 1      |
| `HCAPTCHA_ENABLED: bool` in config.py     | 1        | 1      |
| `HCAPTCHA_SECRET: SecretStr` in config.py | 1        | 1      |
| `AUTH__V2_ENABLED=true` in config.py      | ≥1       | 2      |
| `JWT_SECRET: SecretStr` in config.py      | 1        | 1      |
| `def is_auth_v2_enabled` in feature_flags | 1        | 1      |
| `def is_hcaptcha_enabled` in feature_flags| 1        | 1      |
| nested-if pattern in feature_flags        | 0        | 0      |
| `wc -l data/disposable-emails.txt`        | ≥1500    | 5413   |

Production-safety guard manually exercised:
- `ENVIRONMENT=production` + `V2_ENABLED=true` + `COOKIE_SECURE=false` → ValueError raised (verified)
- `ENVIRONMENT=production` + `V2_ENABLED=true` + `FRONTEND_URL=http://localhost:5173` → ValueError raised (verified)
- Both pre-existing JWT/CSRF dev-default guards still fire (no regression)

## Deviations from Plan

None — plan executed exactly as written. The plan recommended ≥1500 entries; actual fetch returned 5413 (full canonical list), exceeding the floor by ~3.6×. No architectural deviations, no auto-fixes triggered, no auth gates encountered.

## Commits

| # | Hash       | Type  | Message                                                              |
| - | ---------- | ----- | -------------------------------------------------------------------- |
| 1 | `f71a7dd`  | chore | add slowapi + stripe deps for Phase 13 cutover                       |
| 2 | `588f5c4`  | feat  | extend AuthSettings with Phase 13 envs + V2 production safety        |
| 3 | `c7482d1`  | feat  | add feature_flags helper + disposable-email blocklist                |

## Requirements Marked Complete

- ANTI-04 (disposable-email blocklist data file shipped — loader in 13-03)
- ANTI-05 (hCaptcha config envs scaffolded — middleware in 13-02/03)
- ANTI-06 (FRONTEND_URL CORS env scaffolded — wired in 13-09)
- BILL-07 (stripe imported at module-load; never called at runtime in v1.2)
- MID-03 (V2_ENABLED feature flag + helper — gate primitive ready for 13-09)

Note: ANTI-04/05/06 and MID-03 are marked complete at the **scaffold/data layer**; their HTTP enforcement lands in subsequent Wave 1-4 plans. The PLAN frontmatter declared this plan delivers the foundation for them.

## Self-Check

Files created exist:
- `app/core/feature_flags.py` → FOUND
- `data/disposable-emails.txt` → FOUND (5413 lines)

Files modified:
- `pyproject.toml` → MODIFIED (slowapi + stripe added)
- `app/core/config.py` → MODIFIED (8 fields + 2 guard branches)

Commits exist:
- `f71a7dd` → FOUND
- `588f5c4` → FOUND
- `c7482d1` → FOUND

## Self-Check: PASSED
