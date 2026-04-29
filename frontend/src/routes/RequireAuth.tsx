import { useLocation, Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/lib/stores/authStore';

/**
 * Auth gate (UI-04) — wraps protected routes.
 * Anonymous users are redirected to /login?next=<currentPath>.
 *
 * Note: authStore.user starts null on every page load (Phase 14 has no
 * /api/account/me hydration — Phase 15). The cookie session itself
 * remains valid 7 days; user just re-lands at /login briefly.
 */
export function RequireAuth() {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  if (user === null) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return <Outlet />;
}
