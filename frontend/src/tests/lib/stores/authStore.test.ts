/**
 * authStore tests — verify single source of auth state, HTTP delegation
 * to apiClient, and BroadcastChannel('auth') cross-tab sync (UI-04, UI-12).
 *
 * Phase 15-05 additions: refresh() boot-probe hydration + isHydrating flag.
 *
 * Default MSW handlers (auth.handlers.ts + account.handlers.ts):
 *   POST /auth/login        -> 200 { user_id: 1, plan_tier: 'trial' } (401 when password === 'wrong')
 *   POST /auth/register     -> 201 { user_id: 1, plan_tier: 'trial' }
 *   POST /auth/logout       -> 204 No Content
 *   GET  /api/account/me    -> 200 { user_id, email, plan_tier, trial_started_at, token_version }
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../../setup';
import { useAuthStore } from '@/lib/stores/authStore';

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, isHydrating: true });
  });

  it('initial state has user=null and isHydrating=true', () => {
    expect(useAuthStore.getState().user).toBe(null);
    expect(useAuthStore.getState().isHydrating).toBe(true);
  });

  it('login sets user from /auth/login response', async () => {
    await useAuthStore.getState().login('alice@example.com', 'password123');
    const u = useAuthStore.getState().user;
    expect(u).not.toBe(null);
    expect(u!.id).toBe(1);
    expect(u!.email).toBe('alice@example.com');
    expect(u!.planTier).toBe('trial');
  });

  it('login populates trialStartedAt + tokenVersion with safe defaults', async () => {
    await useAuthStore.getState().login('alice@example.com', 'password123');
    const u = useAuthStore.getState().user;
    expect(u!.trialStartedAt).toBe(null);
    expect(u!.tokenVersion).toBe(0);
  });

  it('login failure (401) leaves user null and propagates error', async () => {
    await expect(
      useAuthStore.getState().login('alice@example.com', 'wrong'),
    ).rejects.toThrow();
    expect(useAuthStore.getState().user).toBe(null);
  });

  it('login 401 does NOT mutate window.location.href (debug fix login-stuck-loading)', async () => {
    // Regression: a 401 from /auth/login (wrong password) MUST NOT trigger
    // apiClient.redirectTo401(). The form is the legitimate auth surface;
    // a redirect-to-/login here causes a full reload-loop and lands on a
    // boot probe that may hang ("stuck at Loading…").
    window.location.href = 'http://localhost/login';
    await expect(
      useAuthStore.getState().login('alice@example.com', 'wrong'),
    ).rejects.toThrow();
    expect(window.location.href).toBe('http://localhost/login');
  });

  it('register 401 does NOT mutate window.location.href (debug fix login-stuck-loading)', async () => {
    server.use(
      http.post('/auth/register', () =>
        HttpResponse.json({ detail: 'Conflict' }, { status: 401 }),
      ),
    );
    window.location.href = 'http://localhost/register';
    await expect(
      useAuthStore.getState().register('bob@example.com', 'password123'),
    ).rejects.toThrow();
    expect(window.location.href).toBe('http://localhost/register');
  });

  it('register sets user from /auth/register response', async () => {
    await useAuthStore.getState().register('bob@example.com', 'password123');
    expect(useAuthStore.getState().user!.email).toBe('bob@example.com');
  });

  it('logout clears user via /auth/logout 204', async () => {
    await useAuthStore.getState().login('alice@example.com', 'password123');
    expect(useAuthStore.getState().user).not.toBe(null);
    await useAuthStore.getState().logout();
    expect(useAuthStore.getState().user).toBe(null);
  });

  it('cross-tab BroadcastChannel logout clears user (UI-12)', async () => {
    await useAuthStore.getState().login('alice@example.com', 'password123');
    expect(useAuthStore.getState().user).not.toBe(null);

    const otherTab = new BroadcastChannel('auth');
    otherTab.postMessage({ type: 'logout' });
    await new Promise((r) => setTimeout(r, 0));
    expect(useAuthStore.getState().user).toBe(null);
    otherTab.close();
  });

  it('login broadcasts a login message on the auth channel', async () => {
    const otherTab = new BroadcastChannel('auth');
    const messages: unknown[] = [];
    otherTab.addEventListener('message', (e) => messages.push(e.data));

    await useAuthStore.getState().login('alice@example.com', 'password123');
    await new Promise((r) => setTimeout(r, 0));

    const loginMsg = messages.find(
      (m) => (m as { type: string }).type === 'login',
    ) as { userId: number; email: string };
    expect(loginMsg).toBeDefined();
    expect(loginMsg.userId).toBe(1);
    expect(loginMsg.email).toBe('alice@example.com');
    otherTab.close();
  });

  it('multiple logins update state idempotently', async () => {
    await useAuthStore.getState().login('alice@example.com', 'password123');
    const first = useAuthStore.getState().user;
    await useAuthStore.getState().login('alice@example.com', 'password123');
    const second = useAuthStore.getState().user;
    expect(first?.email).toBe(second?.email);
  });

  it('refresh() populates user from /api/account/me', async () => {
    await useAuthStore.getState().refresh();
    const u = useAuthStore.getState().user;
    expect(u).not.toBe(null);
    expect(u!.id).toBe(1);
    expect(u!.email).toBe('alice@example.com');
    expect(u!.planTier).toBe('trial');
    expect(u!.trialStartedAt).toBe('2026-04-22T12:00:00Z');
    expect(u!.tokenVersion).toBe(0);
    expect(useAuthStore.getState().isHydrating).toBe(false);
  });

  it('refresh() 401 leaves user null without throwing', async () => {
    server.use(
      http.get('/api/account/me', () =>
        HttpResponse.json({ detail: 'Authentication required' }, { status: 401 }),
      ),
    );
    await expect(useAuthStore.getState().refresh()).resolves.toBeUndefined();
    expect(useAuthStore.getState().user).toBe(null);
    expect(useAuthStore.getState().isHydrating).toBe(false);
  });

  it('refresh() flips isHydrating to false on success', async () => {
    expect(useAuthStore.getState().isHydrating).toBe(true);
    await useAuthStore.getState().refresh();
    expect(useAuthStore.getState().isHydrating).toBe(false);
  });

  it('refresh() flips isHydrating to false on network error', async () => {
    server.use(http.get('/api/account/me', () => HttpResponse.error()));
    await useAuthStore.getState().refresh();
    expect(useAuthStore.getState().isHydrating).toBe(false);
    expect(useAuthStore.getState().user).toBe(null);
  });

  it('logout does not re-hydrate (isHydrating untouched)', async () => {
    await useAuthStore.getState().refresh();
    expect(useAuthStore.getState().isHydrating).toBe(false);
    await useAuthStore.getState().logout();
    expect(useAuthStore.getState().isHydrating).toBe(false);
    expect(useAuthStore.getState().user).toBe(null);
  });
});
