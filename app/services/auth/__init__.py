"""Auth services layer — orchestration on top of pure-logic core modules.

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §160 (locked):
package layout ``app/services/auth/<service>.py``.

Note: full barrel re-exports are wired at the end of plan 11-04 once all 6
service modules exist; this file is intentionally minimal during incremental
TDD construction so RED tests for one service don't drag in not-yet-existing
siblings.
"""
