# Phase 18: Stretch (Optional) - Context

**Gathered:** 2026-05-01
**Status:** Closed empty (no observed need)
**Mode:** User decision per autonomous-mode prompt

<domain>
## Phase Boundary

Phase 18 is the explicitly optional v1.2 stretch phase. ROADMAP.md flags it as "gated on observed need; may close empty." Four candidate features were offered (hCaptcha, HaveIBeenPwned k-anonymity, per-key scopes UI, per-key expiration). User declined activation — none of the four trigger conditions surfaced during v1.2 soak.

</domain>

<decisions>
## Implementation Decisions

### Closure
- Phase 18 closes empty. Zero plans, zero summaries.
- All four features remain in the FUTURE-* requirement set; eligible for v1.3+ if observed abuse warrants.
- No code changes. No env-var changes. No doc changes.

</decisions>

<code_context>
## Existing Code Insights

Not applicable — phase closes without execution.

</code_context>

<specifics>
## Specific Ideas

None — phase deferred entirely.

</specifics>

<deferred>
## Deferred Ideas

- hCaptcha activation on `/auth/register` — `AUTH__HCAPTCHA_*` env vars already stubbed in `.env.example`; wiring deferred to v1.3 if abuse observed.
- HaveIBeenPwned k-anonymity check on register — domain rejection only currently; password check deferred.
- Per-key scopes UI (`read-only` scope, KEY-09 family) — deferred.
- Per-key expiration (`expires_at` column, KEY-10 family) — deferred.

</deferred>
