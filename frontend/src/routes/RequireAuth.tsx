import { useLocation, Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/lib/stores/authStore';
import { AuthHydratingFallback } from '@/components/layout/AuthHydratingFallback';

/**
 * Auth gate (UI-04, UI-07) — wraps protected routes.
 *
 * Order of checks (matters):
 *   user=set                       -> render Outlet (already authed; don't wait for probe)
 *   user=null AND isHydrating      -> Loading (don't know yet — fail-closed)
 *   user=null AND !isHydrating     -> Navigate to /login?next=<currentPath>
 *
 * Why user-first: a successful login() populates `user` immediately while the
 * boot probe (`/api/account/me`) may still be in flight. Checking isHydrating
 * first would render Loading even though we already know the user is authed,
 * trapping them on the spinner until probe timeout fires.
 */
export function RequireAuth() {
  const user = useAuthStore((s) => s.user);
  const isHydrating = useAuthStore((s) => s.isHydrating);
  const location = useLocation();

  if (user !== null) {
    return <Outlet />;
  }

  if (isHydrating) {
    return <AuthHydratingFallback />;
  }

  const next = encodeURIComponent(location.pathname + location.search);
  return <Navigate to={`/login?next=${next}`} replace />;
}
