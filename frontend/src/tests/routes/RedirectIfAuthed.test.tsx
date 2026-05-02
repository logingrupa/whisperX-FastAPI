/**
 * RedirectIfAuthed gate tests.
 *
 * Public-route policy: NO wait on the boot probe — the form is reachable
 * immediately regardless of isHydrating. If probe later resolves with a
 * populated user, the gate re-renders and navigates away.
 *
 *   user=null  -> Outlet (form reachable, regardless of isHydrating)
 *   user=set   -> Navigate to ?next= or "/"
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { RedirectIfAuthed } from '@/routes/RedirectIfAuthed';
import { useAuthStore } from '@/lib/stores/authStore';

const authedUser = {
  id: 1,
  email: 'alice@example.com',
  planTier: 'trial' as const,
  trialStartedAt: null,
  tokenVersion: 0,
};

function renderAt(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<div>home-marker</div>} />
        <Route path="/dashboard/keys" element={<div>keys-marker</div>} />
        <Route element={<RedirectIfAuthed />}>
          <Route path="/login" element={<div>login-marker</div>} />
          <Route path="/register" element={<div>register-marker</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('RedirectIfAuthed', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, isHydrating: true });
  });

  it('renders the login form immediately even while isHydrating=true (no probe wait)', () => {
    useAuthStore.setState({ user: null, isHydrating: true });
    renderAt('/login');
    expect(screen.getByText('login-marker')).toBeInTheDocument();
  });

  it('renders the login form when user=null after hydration', () => {
    useAuthStore.setState({ user: null, isHydrating: false });
    renderAt('/login');
    expect(screen.getByText('login-marker')).toBeInTheDocument();
  });

  it('renders the register form when user=null after hydration', () => {
    useAuthStore.setState({ user: null, isHydrating: false });
    renderAt('/register');
    expect(screen.getByText('register-marker')).toBeInTheDocument();
  });

  it('redirects authed user from /login to "/"', () => {
    useAuthStore.setState({ user: authedUser, isHydrating: false });
    renderAt('/login');
    expect(screen.getByText('home-marker')).toBeInTheDocument();
    expect(screen.queryByText('login-marker')).not.toBeInTheDocument();
  });

  it('redirects authed user from /register to "/"', () => {
    useAuthStore.setState({ user: authedUser, isHydrating: false });
    renderAt('/register');
    expect(screen.getByText('home-marker')).toBeInTheDocument();
    expect(screen.queryByText('register-marker')).not.toBeInTheDocument();
  });

  it('honors ?next= deep-link for authed user', () => {
    useAuthStore.setState({ user: authedUser, isHydrating: false });
    renderAt('/login?next=/dashboard/keys');
    expect(screen.getByText('keys-marker')).toBeInTheDocument();
    expect(screen.queryByText('home-marker')).not.toBeInTheDocument();
  });
});
