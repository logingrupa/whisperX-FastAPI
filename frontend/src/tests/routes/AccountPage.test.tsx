/**
 * Plan 15-06 Task 2 — AccountPage RTL coverage.
 *
 * Covers:
 *   - hydration success: email + plan_tier badge render after /me lands
 *   - hydration error: /me 500 surfaces "Could not load account." copy
 *   - reload retry: error -> click "Reload account" -> success
 *   - upgrade gating: planTier='pro' hides "Upgrade to Pro" CTA
 *
 * TEST-05 invariants honored — every async assertion uses findByRole /
 * findByText (not getByRole/getByText after a state change).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';

import { AccountPage } from '@/routes/AccountPage';
import { useAuthStore } from '@/lib/stores/authStore';
import { server } from '@/tests/setup';

function renderPage() {
  return render(
    <MemoryRouter>
      <AccountPage />
    </MemoryRouter>,
  );
}

describe('AccountPage', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: 1,
        email: 'alice@example.com',
        planTier: 'trial',
        trialStartedAt: '2026-04-22T12:00:00Z',
        tokenVersion: 0,
      },
      isHydrating: false,
    });
  });

  it('renders email + plan_tier badge after hydration', async () => {
    renderPage();
    expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
    // Badge label "Trial" — case-sensitive copy from PLAN_BADGE_LABEL map
    expect(await screen.findByText('Trial')).toBeInTheDocument();
  });

  it('renders error card on /me 500', async () => {
    server.use(
      http.get('/api/account/me', () =>
        HttpResponse.json({ detail: 'oops' }, { status: 500 }),
      ),
    );
    renderPage();
    expect(
      await screen.findByText(/could not load account/i),
    ).toBeInTheDocument();
  });

  it('"Reload account" button retries fetch', async () => {
    server.use(
      http.get('/api/account/me', () =>
        HttpResponse.json({ detail: 'oops' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/could not load account/i);
    // Restore default handler before clicking reload — server.resetHandlers()
    // clears the override stack so the default 200 alice handler kicks back in.
    server.resetHandlers();
    await user.click(
      await screen.findByRole('button', { name: /reload account/i }),
    );
    expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
  });

  it('hides Upgrade button when plan_tier="pro"', async () => {
    server.use(
      http.get('/api/account/me', () =>
        HttpResponse.json({
          user_id: 1,
          email: 'alice@example.com',
          plan_tier: 'pro',
          trial_started_at: null,
          token_version: 0,
        }),
      ),
    );
    renderPage();
    await screen.findByText('alice@example.com');
    expect(
      screen.queryByRole('button', { name: /upgrade to pro/i }),
    ).not.toBeInTheDocument();
  });
});
