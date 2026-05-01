---
phase: 18
status: closed_empty
date: 2026-05-01
plans_executed: 0
plans_total: 0
requirements_addressed: []
---

# Phase 18 — Stretch (Optional): Closed Empty

## Outcome

Phase 18 closed without execution. Per ROADMAP.md, this phase was "gated on observed need; may close empty." During the autonomous walkthrough on 2026-05-01, the user reviewed the four candidate features (hCaptcha, HaveIBeenPwned, per-key scopes, per-key expiration) and declined activation — no abuse signal surfaced during v1.2 soak.

## What changed

Nothing. No code, no docs, no schema, no env vars.

## What deferred

All four candidate features remain in the FUTURE-* requirement set:
- **FUTURE-HCAPTCHA**: hCaptcha on `/auth/register`. Env vars stubbed at `.env.example:133-135` (`AUTH__HCAPTCHA_ENABLED=false`).
- **FUTURE-HIBP**: HaveIBeenPwned k-anonymity password check on register.
- **FUTURE-KEY-SCOPES**: Per-key scopes UI (read-only flow + 403 on transcribe).
- **FUTURE-KEY-EXP**: Per-key `expires_at` column + 401 on expired keys before manual revocation.

Each is independently activatable in v1.3+ if abuse observed.

## Closure rationale

The four success criteria in ROADMAP §Phase 18 are conditional ("If hCaptcha activated: ..."). With zero activations, all conditions trivially hold. No verification needed.

## v1.2 milestone status

Phase 18 closure terminates v1.2 active scope. Phases 10–17 deliver the milestone. Phase 18 is the documented opt-out signal.
