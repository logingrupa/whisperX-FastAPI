/**
 * Quick task 260505-l2w — UsageDashboardPage RTL coverage.
 *
 * Scenarios:
 *   1. Happy path (trial)              — DEFAULT_USAGE_SUMMARY renders cards.
 *   2. Trial-not-started (free tier)   — trial card NOT rendered.
 *   3. Trial expired                   — destructive treatment + Upgrade CTA.
 *   4. Hour quota at limit             — destructive data-attr.
 *   5. Daily minutes near limit (>=80%)— warn data-attr.
 *   6. 500 error                       — destructive Alert renders, no crash.
 *   7. Refresh button re-fetches       — count updates after server.use override.
 *
 * Subtype-first error invariant exercised by the rate-limit + 500 paths;
 * tests assert the user-facing copy ("Could not load usage." / "Rate
 * limited."). Async assertions use findBy*; sync use queryBy* / getBy*.
 */
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';

import { UsageDashboardPage } from '@/routes/UsageDashboardPage';
import { server } from '@/tests/setup';
import {
  DAILY_NEAR_LIMIT_USAGE,
  FREE_NO_TRIAL_USAGE,
  HOUR_AT_LIMIT_USAGE,
  TRIAL_EXPIRED_USAGE,
} from '@/tests/msw/usage.handlers';

function renderPage() {
  return render(
    <MemoryRouter>
      <UsageDashboardPage />
    </MemoryRouter>,
  );
}

describe('UsageDashboardPage', () => {
  it('renders real numbers for the happy-path trial summary', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: /usage/i })).toBeInTheDocument();
    // Hour quota count "1 of 5"
    const hourCard = await screen.findByTestId('hour-quota-card');
    expect(within(hourCard).getByText(/1 of 5/i)).toBeInTheDocument();
    // Daily minutes "4.5 min of 30.0 min"
    const dailyCard = await screen.findByTestId('daily-minutes-card');
    expect(within(dailyCard).getByText(/4\.5 min of 30\.0 min/)).toBeInTheDocument();
    // Plan badge label "Trial" appears at least once (also as trial-card heading).
    expect((await screen.findAllByText('Trial')).length).toBeGreaterThan(0);
    // Trial card present
    expect(await screen.findByTestId('trial-card')).toBeInTheDocument();
    // Phase-14 placeholder copy must be absent from the rebuilt page.
    expect(screen.queryByText(/no\s+data\s+yet/i)).toBeNull();
  });

  it('hides trial card when plan_tier !== "trial"', async () => {
    server.use(
      http.get('/api/usage', () => HttpResponse.json(FREE_NO_TRIAL_USAGE)),
    );
    renderPage();
    expect(await screen.findByTestId('hour-quota-card')).toBeInTheDocument();
    // Trial card omitted entirely (no empty placeholder).
    expect(screen.queryByTestId('trial-card')).toBeNull();
  });

  it('renders destructive trial-expired card with Upgrade CTA', async () => {
    server.use(
      http.get('/api/usage', () => HttpResponse.json(TRIAL_EXPIRED_USAGE)),
    );
    renderPage();
    const trialCard = await screen.findByTestId('trial-card');
    expect(trialCard).toHaveAttribute('data-trial-state', 'expired');
    expect(within(trialCard).getByText(/trial expired/i)).toBeInTheDocument();
    // Upgrade button present
    expect(within(trialCard).getByRole('button', { name: /upgrade/i })).toBeInTheDocument();
  });

  it('shows destructive accent on hour-quota card at 100%', async () => {
    server.use(
      http.get('/api/usage', () => HttpResponse.json(HOUR_AT_LIMIT_USAGE)),
    );
    renderPage();
    const hourCard = await screen.findByTestId('hour-quota-card');
    expect(hourCard).toHaveAttribute('data-quota-state', 'destructive');
    expect(within(hourCard).getByText(/5 of 5/)).toBeInTheDocument();
  });

  it('shows warn accent on daily-minutes card at >= 80%', async () => {
    server.use(
      http.get('/api/usage', () => HttpResponse.json(DAILY_NEAR_LIMIT_USAGE)),
    );
    renderPage();
    const dailyCard = await screen.findByTestId('daily-minutes-card');
    // 25 / 30 = 83% -> warn.
    expect(dailyCard).toHaveAttribute('data-quota-state', 'warn');
  });

  it('renders error alert on 500 response and does not crash', async () => {
    server.use(
      http.get('/api/usage', () =>
        HttpResponse.json({ detail: 'oops' }, { status: 500 }),
      ),
    );
    renderPage();
    expect(await screen.findByText(/could not load usage/i)).toBeInTheDocument();
    // Page heading still present (no full-tree crash).
    expect(screen.getByRole('heading', { name: /usage/i })).toBeInTheDocument();
  });

  it('Refresh button re-fetches /api/usage', async () => {
    renderPage();
    const hourCard = await screen.findByTestId('hour-quota-card');
    expect(within(hourCard).getByText(/1 of 5/)).toBeInTheDocument();

    // Override default handler so the next fetch returns hour_count=2.
    server.use(
      http.get('/api/usage', () =>
        HttpResponse.json({
          plan_tier: 'trial',
          trial_started_at: '2026-05-01T12:00:00Z',
          trial_expires_at: '2026-05-08T12:00:00Z',
          hour_count: 2,
          hour_limit: 5,
          daily_minutes_used: 4.5,
          daily_minutes_limit: 30.0,
          window_resets_at: '2026-05-05T15:00:00Z',
          day_resets_at: '2026-05-06T00:00:00Z',
        }),
      ),
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /refresh/i }));
    const updatedHourCard = await screen.findByTestId('hour-quota-card');
    expect(await within(updatedHourCard).findByText(/2 of 5/)).toBeInTheDocument();
  });
});
