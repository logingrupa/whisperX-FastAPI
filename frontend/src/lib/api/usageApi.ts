/**
 * Quick task 260505-l2w — typed wrapper for GET /api/usage.
 *
 * Single fetch site for usage-related endpoints (UI-11 invariant). Mirrors
 * accountApi.ts: zod parse at the wrapper boundary so contract drift is
 * caught here, not at render time.
 *
 * Backend contract (locked from RESEARCH + UsageSummaryResponse schema):
 *   GET /api/usage -> 200 UsageSummary
 *   401 -> apiClient redirects to /login?next=... (this route is gated by
 *          RequireAuth already; no suppress401Redirect needed).
 *
 * Subtype-first error handling MUST be applied at call sites:
 *   catch RateLimitError BEFORE ApiClientError (CLAUDE.md locked policy).
 */
import { z } from 'zod';

import { apiClient, ApiClientError, RateLimitError } from '@/lib/apiClient';

export const planTierSchema = z.enum(['free', 'trial', 'pro', 'team']);
export type PlanTier = z.infer<typeof planTierSchema>;

const usageSummarySchema = z.object({
  plan_tier: planTierSchema,
  trial_started_at: z.string().datetime({ offset: true }).nullable(),
  trial_expires_at: z.string().datetime({ offset: true }).nullable(),
  hour_count: z.number().int().nonnegative(),
  hour_limit: z.number().int().nonnegative(),
  daily_minutes_used: z.number().nonnegative(),
  daily_minutes_limit: z.number().nonnegative(),
  window_resets_at: z.string().datetime({ offset: true }),
  day_resets_at: z.string().datetime({ offset: true }),
});

export type UsageSummary = z.infer<typeof usageSummarySchema>;

/**
 * Fetch the caller's usage summary. Throws RateLimitError on 429 (rate
 * limited) or ApiClientError on other 4xx/5xx; subtype-first catch order
 * is mandatory at call sites.
 */
export async function fetchUsageSummary(): Promise<UsageSummary> {
  const raw = await apiClient.get<unknown>('/api/usage');
  return usageSummarySchema.parse(raw);
}

// Re-export error classes for caller convenience (DRY with accountApi style).
export { ApiClientError, RateLimitError };
