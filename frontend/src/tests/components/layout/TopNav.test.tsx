/**
 * TopNav unit tests.
 *
 * Covers:
 *   - renders email + avatar initial when user authenticated
 *   - dropdown exposes API Keys / Usage / Account links + Sign out
 *   - Sign out flow calls authStore.logout + navigates to /login
 *
 * Conventions match existing dialog tests (RTL + MSW + MemoryRouter +
 * findBy* after every async transition).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { TopNav } from '@/components/layout/TopNav';
import { useAuthStore } from '@/lib/stores/authStore';

function renderTopNav() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<TopNav />} />
        <Route path="/login" element={<div>login-marker</div>} />
        <Route path="/dashboard/keys" element={<div>keys-marker</div>} />
        <Route path="/dashboard/usage" element={<div>usage-marker</div>} />
        <Route path="/dashboard/account" element={<div>account-marker</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('TopNav', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: 1,
        email: 'alice@example.com',
        planTier: 'trial',
        trialStartedAt: null,
        tokenVersion: 0,
      },
      isHydrating: false,
    });
  });

  it('renders brand link + avatar initial + email', async () => {
    renderTopNav();
    expect(
      await screen.findByRole('link', { name: /whisperx/i }),
    ).toBeInTheDocument();
    // First letter of email, uppercased, in avatar circle
    expect(screen.getByText('A')).toBeInTheDocument();
    // Email visible at >=md (jsdom has no media queries; element is in DOM
    // regardless — we assert presence, not visibility)
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
  });

  it('opens user menu and renders all nav items', async () => {
    const user = userEvent.setup();
    renderTopNav();
    await user.click(
      await screen.findByRole('button', { name: /open user menu/i }),
    );
    expect(
      await screen.findByRole('menuitem', { name: /api keys/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /usage/i })).toBeInTheDocument();
    expect(
      screen.getByRole('menuitem', { name: /account/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('menuitem', { name: /sign out/i }),
    ).toBeInTheDocument();
  });

  it('Sign out calls authStore.logout and navigates /login', async () => {
    const logoutSpy = vi.fn().mockResolvedValue(undefined);
    useAuthStore.setState({ logout: logoutSpy });

    const user = userEvent.setup();
    renderTopNav();
    await user.click(
      await screen.findByRole('button', { name: /open user menu/i }),
    );
    await user.click(
      await screen.findByRole('menuitem', { name: /sign out/i }),
    );

    expect(await screen.findByText('login-marker')).toBeInTheDocument();
    expect(logoutSpy).toHaveBeenCalledTimes(1);
  });

  it('falls back to "?" initial when user has empty email', async () => {
    useAuthStore.setState({
      user: {
        id: 2,
        email: '',
        planTier: 'free',
        trialStartedAt: null,
        tokenVersion: 0,
      },
    });
    renderTopNav();
    expect(await screen.findByText('?')).toBeInTheDocument();
  });
});
