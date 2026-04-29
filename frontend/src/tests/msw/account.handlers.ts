/**
 * MSW handlers for Phase 15 account/billing endpoints.
 *
 * Mirrors keys.handlers.ts pattern: single named export, plain JSON
 * responses, default-success bodies. Per-test overrides via
 * ``server.use(http.<method>(...))`` cover error/edge cases.
 *
 * Endpoints intercepted:
 *   GET  /api/account/me     -> 200 AccountSummaryResponse (alice@example.com, trial)
 *   DELETE /api/account      -> 204 (void)
 *   POST /auth/logout-all    -> 204 (void)
 *   POST /billing/checkout   -> 501 stub (Stripe arrives in v1.3 — T-15-07)
 */
import { http, HttpResponse } from 'msw';

export const accountHandlers = [
  http.get('/api/account/me', () =>
    HttpResponse.json({
      user_id: 1,
      email: 'alice@example.com',
      plan_tier: 'trial',
      trial_started_at: '2026-04-22T12:00:00Z',
      token_version: 0,
    }),
  ),
  http.delete('/api/account', () => new HttpResponse(null, { status: 204 })),
  http.post('/auth/logout-all', () => new HttpResponse(null, { status: 204 })),
  http.post('/billing/checkout', () =>
    HttpResponse.json(
      {
        detail: 'Not Implemented',
        status: 'stub',
        hint: 'Stripe integration arrives in v1.3',
      },
      { status: 501 },
    ),
  ),
];
