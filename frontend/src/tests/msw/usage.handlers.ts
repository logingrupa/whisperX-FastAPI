/**
 * MSW handlers for GET /api/usage (quick-260505-l2w).
 *
 * Default body: trial user, low usage. Per-test overrides via
 * ``server.use(http.get(...))`` for trial-expired / near-limit / 500 cases.
 * Override-factory fixtures exported for ergonomic test setup.
 *
 * File-name convention: ``*.handlers.ts`` (plural, dot-separated) — matches
 * the existing barrel imports (auth.handlers / keys.handlers / ws.handlers /
 * transcribe.handlers / account.handlers).
 */
import { http, HttpResponse } from 'msw';

export interface UsageSummaryFixture {
  plan_tier: 'free' | 'trial' | 'pro' | 'team';
  trial_started_at: string | null;
  trial_expires_at: string | null;
  hour_count: number;
  hour_limit: number;
  daily_minutes_used: number;
  daily_minutes_limit: number;
  window_resets_at: string;
  day_resets_at: string;
}

export const DEFAULT_USAGE_SUMMARY: UsageSummaryFixture = {
  plan_tier: 'trial',
  trial_started_at: '2026-05-01T12:00:00Z',
  trial_expires_at: '2026-05-08T12:00:00Z',
  hour_count: 1,
  hour_limit: 5,
  daily_minutes_used: 4.5,
  daily_minutes_limit: 30.0,
  window_resets_at: '2026-05-05T15:00:00Z',
  day_resets_at: '2026-05-06T00:00:00Z',
};

export const TRIAL_EXPIRED_USAGE: UsageSummaryFixture = {
  ...DEFAULT_USAGE_SUMMARY,
  trial_started_at: '2026-04-20T12:00:00Z',
  trial_expires_at: '2026-04-27T12:00:00Z',
};

export const FREE_NO_TRIAL_USAGE: UsageSummaryFixture = {
  ...DEFAULT_USAGE_SUMMARY,
  plan_tier: 'free',
  trial_started_at: null,
  trial_expires_at: null,
};

export const HOUR_AT_LIMIT_USAGE: UsageSummaryFixture = {
  ...DEFAULT_USAGE_SUMMARY,
  hour_count: 5,
};

export const DAILY_NEAR_LIMIT_USAGE: UsageSummaryFixture = {
  ...DEFAULT_USAGE_SUMMARY,
  daily_minutes_used: 25.0,
};

export const usageHandlers = [
  http.get('/api/usage', () => HttpResponse.json(DEFAULT_USAGE_SUMMARY)),
];
