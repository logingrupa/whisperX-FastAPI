/**
 * Phase 15 — typed HTTP wrappers for /api/account/* and /auth/logout-all.
 *
 * Single fetch site for account-related endpoints (UI-11 invariant). Mirrors
 * keysApi.ts: dumb DTO + thin apiClient wrappers, no business logic.
 *
 * Backend contract (locked from Phase 15 RESEARCH §551-572 + CONTEXT D-04):
 *   GET    /api/account/me          -> 200 AccountSummaryResponse
 *   POST   /auth/logout-all         -> 204 (void) — bumps token_version + clears cookies
 *   DELETE /api/account             -> 204 (void) — body {email_confirm: string}; 400 on mismatch
 *   POST   /billing/checkout        -> 501 stub — caller treats as success (v1.3 ships Stripe)
 */

import { apiClient } from '@/lib/apiClient';

export interface AccountSummaryResponse {
  user_id: number;
  email: string;
  plan_tier: 'free' | 'trial' | 'pro' | 'team';
  trial_started_at: string | null;
  token_version: number;
}

/**
 * Probe-style boot fetch — uses suppress401Redirect so a 401 throws
 * AuthRequiredError without forcing redirect. RequireAuth handles
 * unauth navigation; authStore.refresh() needs the silent failure path
 * for cold-boot hydration.
 */
export function fetchAccountSummary(): Promise<AccountSummaryResponse> {
  return apiClient.get<AccountSummaryResponse>(
    '/api/account/me',
    { suppress401Redirect: true },
  );
}

/**
 * Sign out of all devices (AUTH-06). Bumps users.token_version which
 * invalidates every issued JWT, then clears the caller's session+csrf
 * cookies. Caller MUST follow up with authStore.logout() + redirect.
 */
export function logoutAllDevices(): Promise<void> {
  return apiClient.post<void>('/auth/logout-all');
}

/**
 * Permanently delete the caller's account (SCOPE-06). Body
 * ``{email_confirm}`` must equal user.email exactly (case-insensitive at
 * the service boundary). Backend cascades user row + tasks + api_keys +
 * subscriptions + usage_events + device_fingerprints + rate_limit_buckets
 * inside a single transaction.
 */
export function deleteAccount(emailConfirm: string): Promise<void> {
  return apiClient.delete<void>('/api/account', { email_confirm: emailConfirm });
}

/**
 * Upgrade-interest probe (BILL-05). Hits /billing/checkout which is a
 * 501 stub in v1.2 — caller catches ApiClientError with ``statusCode === 501``
 * and treats it as success (T-15-07). v1.3 wires real Stripe Checkout.
 */
export function submitUpgradeInterest(message: string): Promise<void> {
  return apiClient.post<void>('/billing/checkout', { plan: 'pro', message });
}
