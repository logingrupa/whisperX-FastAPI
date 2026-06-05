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

const usageByKeyEntrySchema = z.object({
  api_key_id: z.number().int().nullable(),
  name: z.string().nullable(),
  prefix: z.string().nullable(),
  revoked: z.boolean(),
  transcription_count: z.number().int().nonnegative(),
  minutes_used: z.number().nonnegative(),
  last_used_at: z.string().datetime({ offset: true }).nullable(),
});

const usageByKeyResponseSchema = z.object({
  keys: z.array(usageByKeyEntrySchema),
});

export type UsageByKeyEntry = z.infer<typeof usageByKeyEntrySchema>;
export type UsageByKeyResponse = z.infer<typeof usageByKeyResponseSchema>;

/**
 * Fetch the caller's usage summary. Throws RateLimitError on 429 (rate
 * limited) or ApiClientError on other 4xx/5xx; subtype-first catch order
 * is mandatory at call sites.
 */
export async function fetchUsageSummary(): Promise<UsageSummary> {
  const raw = await apiClient.get<unknown>('/api/usage');
  return usageSummarySchema.parse(raw);
}

/**
 * Fetch per-API-key usage totals (busiest key first). The api_key_id=null
 * entry is the "unattributed" bucket (pre-attribution history + cookie/
 * session transcriptions). Same subtype-first error contract as above.
 */
export async function fetchUsageByKey(): Promise<UsageByKeyEntry[]> {
  const raw = await apiClient.get<unknown>('/api/usage/by-key');
  return usageByKeyResponseSchema.parse(raw).keys;
}

// Re-export error classes for caller convenience (DRY with accountApi style).
export { ApiClientError, RateLimitError };
