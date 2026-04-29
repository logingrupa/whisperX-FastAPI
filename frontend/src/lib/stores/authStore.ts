/**
 * Auth store — single source of authentication state (UI-04, UI-12, UI-07).
 *
 * Locked policy (CONTEXT §86-92, Phase 15-05 RESEARCH §621-723):
 *   - Zustand for state (lightweight, no Provider boilerplate)
 *   - BroadcastChannel('auth') for cross-tab sync (UI-12)
 *   - login(): apiClient.post('/auth/login') -> set user -> broadcast 'login'
 *   - register(): apiClient.post('/auth/register') -> set user -> broadcast 'login'
 *   - logout(): apiClient.post('/auth/logout') -> clear user -> broadcast 'logout'
 *   - logoutLocal(): clear user + broadcast 'logout' WITHOUT calling /auth/logout —
 *     used after DELETE /api/account and POST /auth/logout-all where the server
 *     already cleared cookies / invalidated the session. Hitting /auth/logout
 *     again would 401 and trigger a redirect-to-/login race (WR-02).
 *   - refresh(): fetchAccountSummary() -> server-authoritative user; flips isHydrating false
 *
 * Hydration on reload: refresh() called once at module load from main.tsx.
 * isHydrating gates RequireAuth so the boot probe doesn't redirect-flash to /login.
 *
 * SRP: store does state only. Pages do UI only. apiClient does HTTP only.
 */

import { create } from 'zustand';
import { apiClient, ApiClientError, AuthRequiredError } from '@/lib/apiClient';
import { fetchAccountSummary } from '@/lib/api/accountApi';

export interface AuthUser {
  id: number;
  email: string;
  planTier: string;
  trialStartedAt: string | null;
  tokenVersion: number;
}

interface AuthLoginResponse {
  user_id: number;
  plan_tier: string;
}

interface BroadcastLoginMessage {
  type: 'login';
  userId: number;
  planTier: string;
  email: string;
}

interface BroadcastLogoutMessage {
  type: 'logout';
}

type BroadcastAuthMessage = BroadcastLoginMessage | BroadcastLogoutMessage;

interface AuthState {
  user: AuthUser | null;
  isHydrating: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  logoutLocal: () => void;
  refresh: () => Promise<void>;
}

/** Lazily-constructed channel — defers BroadcastChannel construction until first use. */
let _channel: BroadcastChannel | null = null;
function getChannel(): BroadcastChannel {
  if (_channel === null) {
    _channel = new BroadcastChannel('auth');
  }
  return _channel;
}

function broadcast(message: BroadcastAuthMessage): void {
  getChannel().postMessage(message);
}

/**
 * Login/register response -> AuthUser. Server v1.2 omits trial_started_at +
 * token_version on these legs; refresh() (Plan 15-05) overrides with the
 * authoritative /api/account/me payload on next page load.
 */
function toAuthUser(response: AuthLoginResponse, email: string): AuthUser {
  return {
    id: response.user_id,
    email,
    planTier: response.plan_tier,
    trialStartedAt: null,
    tokenVersion: 0,
  };
}

export const useAuthStore = create<AuthState>((set) => {
  // Cross-tab listener: when another tab logs out, clear our user.
  // Login broadcast is informational — the originating tab keeps its own state.
  getChannel().addEventListener('message', (event: MessageEvent) => {
    const data = event.data as BroadcastAuthMessage;
    if (data.type === 'logout') {
      set({ user: null });
    }
  });

  return {
    user: null,
    isHydrating: true,

    login: async (email, password) => {
      const response = await apiClient.post<AuthLoginResponse>('/auth/login', {
        email,
        password,
      });
      const user = toAuthUser(response, email);
      set({ user });
      broadcast({ type: 'login', userId: user.id, planTier: user.planTier, email });
    },

    register: async (email, password) => {
      const response = await apiClient.post<AuthLoginResponse>('/auth/register', {
        email,
        password,
      });
      const user = toAuthUser(response, email);
      set({ user });
      broadcast({ type: 'login', userId: user.id, planTier: user.planTier, email });
    },

    logout: async () => {
      await apiClient.post('/auth/logout');
      set({ user: null });
      broadcast({ type: 'logout' });
    },

    /**
     * Local-only sign-out — clear user + broadcast 'logout', skip the
     * /auth/logout HTTP round-trip. Use AFTER a server call that already
     * cleared the session cookie (DELETE /api/account on success, or
     * POST /auth/logout-all which bumps token_version).
     *
     * Calling logout() in those flows POSTs to /auth/logout with a now-
     * invalid cookie -> 401 -> apiClient.redirectTo401() races with the
     * caller's navigate('/login'), and the cross-tab broadcast is dropped
     * because set({user:null}) never executes (WR-02).
     */
    logoutLocal: () => {
      set({ user: null });
      broadcast({ type: 'logout' });
    },

    refresh: async () => {
      try {
        const summary = await fetchAccountSummary();
        set({
          user: {
            id: summary.user_id,
            email: summary.email,
            planTier: summary.plan_tier,
            trialStartedAt: summary.trial_started_at,
            tokenVersion: summary.token_version,
          },
        });
      } catch (err) {
        // 401 throws AuthRequiredError; leave user null. Other ApiClientErrors
        // (network 0, 500, etc.) — also leave user null. Genuinely unexpected
        // errors re-thrown for visibility (caught by RouteErrorBoundary in dev).
        if (!(err instanceof AuthRequiredError) && !(err instanceof ApiClientError)) {
          throw err;
        }
      } finally {
        set({ isHydrating: false });
      }
    },
  };
});
