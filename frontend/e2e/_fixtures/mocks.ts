import type { Page, Route } from '@playwright/test';

/**
 * Backend route mocks for e2e suite.
 *
 * SRP: each helper installs ONE endpoint mock. Specs compose only what they
 * need — DRY without coupling specs together.
 *
 * Contract mirrors `frontend/src/lib/api/accountApi.ts` and Phase 15-VERIFICATION:
 *   GET    /api/account/me     -> AccountSummaryResponse (200)
 *   POST   /auth/logout-all    -> 204 no-body
 *   DELETE /api/account        -> 204 no-body (or 400 EMAIL_CONFIRM_MISMATCH)
 *   POST   /billing/checkout   -> 501 stub (UI swallows as success)
 */

export const SIGNED_IN_EMAIL = 'uat@whisperx.local';
export const SIGNED_IN_USER_ID = 4242;

export interface AccountSummaryFixture {
  user_id: number;
  email: string;
  plan_tier: 'free' | 'trial' | 'pro' | 'team';
  trial_started_at: string | null;
  token_version: number;
}

export const DEFAULT_ACCOUNT_SUMMARY: AccountSummaryFixture = {
  user_id: SIGNED_IN_USER_ID,
  email: SIGNED_IN_EMAIL,
  plan_tier: 'free',
  trial_started_at: null,
  token_version: 1,
};

/** Match backend paths regardless of querystring; relative -> absolute glob. */
const ACCOUNT_ME = '**/api/account/me';
const ACCOUNT_DELETE = '**/api/account';
const LOGOUT_ALL = '**/auth/logout-all';
const BILLING_CHECKOUT = '**/billing/checkout';
const KEYS_LIST = '**/api/keys';

function fulfillJson(route: Route, status: number, body: unknown): Promise<void> {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function fulfillNoContent(route: Route): Promise<void> {
  return route.fulfill({ status: 204, body: '' });
}

/** Mock GET /api/account/me with the given summary (default = free tier). */
export async function mockAccountSummary(
  page: Page,
  summary: AccountSummaryFixture = DEFAULT_ACCOUNT_SUMMARY,
): Promise<void> {
  await page.route(ACCOUNT_ME, (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    return fulfillJson(route, 200, summary);
  });
}

/** Mock POST /auth/logout-all -> 204. */
export async function mockLogoutAll(page: Page): Promise<void> {
  await page.route(LOGOUT_ALL, (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    return fulfillNoContent(route);
  });
}

/**
 * Mock DELETE /api/account.
 *  - default 204 success
 *  - pass `{ status: 400 }` for EMAIL_CONFIRM_MISMATCH
 */
export async function mockDeleteAccount(
  page: Page,
  opts: { status?: 204 | 400 } = {},
): Promise<void> {
  const status = opts.status ?? 204;
  await page.route(ACCOUNT_DELETE, (route) => {
    if (route.request().method() !== 'DELETE') return route.fallback();
    if (status === 400) {
      return fulfillJson(route, 400, {
        error: { code: 'EMAIL_CONFIRM_MISMATCH', message: 'mismatch' },
      });
    }
    return fulfillNoContent(route);
  });
}

/**
 * Mock POST /billing/checkout -> 501 stub. UI's UpgradeInterestDialog
 * swallows 501 as success (T-15-07).
 */
export async function mockBillingCheckout501(page: Page): Promise<void> {
  await page.route(BILLING_CHECKOUT, (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    return fulfillJson(route, 501, {
      error: { code: 'NOT_IMPLEMENTED', message: 'Stripe ships in v1.3' },
    });
  });
}

/**
 * Mock GET /api/keys -> empty array. Backend contract returns
 * `ApiKeyListItem[]` (not wrapped) — see `keysApi.ts:fetchKeys`.
 */
export async function mockKeysEmpty(page: Page): Promise<void> {
  await page.route(KEYS_LIST, (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    return fulfillJson(route, 200, []);
  });
}

/** Convenience bundle for "signed in, no upgrade flow yet" specs. */
export async function installAccountMocks(
  page: Page,
  summary?: AccountSummaryFixture,
): Promise<void> {
  await mockAccountSummary(page, summary);
}
