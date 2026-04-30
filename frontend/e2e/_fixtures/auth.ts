import { test as base, expect, type BrowserContext, type Page } from '@playwright/test';
import {
  installAccountMocks,
  type AccountSummaryFixture,
  DEFAULT_ACCOUNT_SUMMARY,
} from './mocks';

/**
 * Shared auth fixture — gives every spec a "signed-in" page.
 *
 * Server cookie auth runs through the same-origin Vite dev server.
 * The auth gate (`RequireAuth.tsx`) only checks `useAuthStore().user !== null`,
 * which the boot probe (`main.tsx` -> `authStore.refresh()`) hydrates from
 * `GET /api/account/me`. So: mock that one endpoint, the gate passes.
 *
 * No real session/csrf cookies needed — the mock fulfills the request before
 * it ever leaves the page. We still seed a `csrf_token` cookie so apiClient's
 * state-mutating calls attach the X-CSRF-Token header (DRY with backend
 * contract, even though all mutations are also mocked).
 */
async function seedCsrfCookie(context: BrowserContext): Promise<void> {
  await context.addCookies([
    {
      name: 'csrf_token',
      value: 'e2e-csrf-token',
      url: 'http://localhost:5173',
      httpOnly: false,
      sameSite: 'Lax',
    },
  ]);
}

interface AuthFixtures {
  signedInPage: Page;
  accountSummary: AccountSummaryFixture;
}

export const test = base.extend<AuthFixtures>({
  accountSummary: async ({}, use) => {
    await use(DEFAULT_ACCOUNT_SUMMARY);
  },

  signedInPage: async ({ page, context, accountSummary }, use) => {
    await seedCsrfCookie(context);
    await installAccountMocks(page, accountSummary);
    await use(page);
  },
});

export { expect };
