# Project Deviations Log

Records explicit user-authorized waivers of prior locked decisions. Each
entry pins the date, the original lock, the new direction, and the
phase that carries the implementation.

---

## 2026-05-02 — Phase 13 atomic-cutover lock waived

**Original lock**: `.planning/phases/13-atomic-backend-cutover/13-CONTEXT.md`
locked the auth + DI architecture (`DualAuthMiddleware` +
`dependency_injector` Factory providers + `AUTH_V2_ENABLED` flag) as
an atomic-pair cutover with Phase 14. The lock was intended to prevent
mid-flight architectural drift during the v1.0 → v1.2 multi-tenant
conversion.

**Trigger**: Two consecutive production-impacting bugs root-caused to
the locked architecture:

- `0f7bb09` — `fix(api/deps): close DB session in every Factory-DI
  provider — root cause of login 30s/401 stall`
- `61c9d61` — `fix(middleware/background): close DB sessions in every
  direct container.X() call`

Both bugs were SQLAlchemy session leaks. Both required inline
`try/finally` patches because the codebase chose `Factory` providers
(no lifecycle owner) + middleware-direct `_container.X()` calls
(bypass the FastAPI `Depends` lifecycle that owns session cleanup).
The pattern will keep regenerating leaks on every new endpoint until
the structure changes.

**User direction (verbatim)**: "clean fast working code, fresh code,
best practices, industry".

**Waiver granted**: Phase 13's "atomic cutover lock" is treated as
delivered — V2 is THE auth path; the cutover is past. The architectural
decisions captured by the lock (Factory + middleware-direct + flag) are
released for restructuring.

**Carry phase**: Phase 19 — Auth + DI Structural Refactor.
See `.planning/phases/19-auth-di-refactor/19-CONTEXT.md` for the
self-contained mission, six locked architectural decisions (D1-D6),
21-gate verification matrix, and 16-step execution order.

**Constraints preserved through the deviation**:

- Frontend HTTP contract: byte-identical pre/post (cookie names, CSRF
  header, 401 redirect target, Set-Cookie attributes, all endpoint
  shapes). Verified via Playwright e2e gate.
- Production safety: refactor lands behind one PR with each commit
  atomically green; rollback is `git reset --hard origin/main` on the
  branch — no partial state lands on `main`.
- Test inventory: phase-start `pytest --collect-only` snapshot pinned
  in `tests/baseline_phase19.txt`; phase-end count must be ≥ baseline.
- Behavioral invariants from Phase 13 (bearer-wins-when-both,
  cookie-sliding-refresh, `token_version` invalidation,
  bad-cookie-on-public-falls-through, CSRF only on cookie-auth
  state-mutating, single 401 shape, per-user task scoping, slowapi
  rate limits, `usage_events` writes, W1 concurrency-slot release):
  enumerated in 19-CONTEXT.md as preserved-exactly contracts.

**Authorization trail**: User invocation `/gsd-quick --full ...` on
2026-05-02 explicitly directed: "you made plan, I need you to read
it, ... save fix the plan and save to file so I can start with
/gsd-autonomous". Critique + fixed CONTEXT.md committed; Phase 19
added to ROADMAP.md via `/gsd-add-phase`.
