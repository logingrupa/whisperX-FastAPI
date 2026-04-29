import { useLocation, Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/lib/stores/authStore';

/**
 * Auth gate (UI-04, UI-07) — wraps protected routes.
 *
 * Three-state gate (Phase 15-05):
 *   isHydrating=true              -> render null (suppress redirect-flash on boot)
 *   isHydrating=false, user=null  -> Navigate to /login?next=<currentPath>
 *   isHydrating=false, user=set   -> render Outlet
 *
 * Boot probe in main.tsx kicks authStore.refresh() before first render. While
 * the /api/account/me probe is in-flight we render nothing — RequireAuth waits
 * one tick rather than redirecting immediately and re-rendering on the success
 * path. Eliminates the double-redirect race documented in RESEARCH §658-666.
 */
export function RequireAuth() {
  const user = useAuthStore((s) => s.user);
  const isHydrating = useAuthStore((s) => s.isHydrating);
  const location = useLocation();

  // Suppress redirect-flash during boot probe — fail-closed (hide UI rather
  // than risk leaking authed routes during hydration).
  if (isHydrating) {
    return null;
  }

  if (user === null) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return <Outlet />;
}
