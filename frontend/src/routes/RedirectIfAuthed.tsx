import { Navigate, Outlet, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '@/lib/stores/authStore';

/**
 * Inverse of RequireAuth — bounces authenticated users away from /login and
 * /register so the cookie session is the source of truth, not the URL.
 *
 * Two-state gate (NOT three — public routes do not block on the boot probe):
 *   user=set   -> Navigate to ?next= or "/"
 *   user=null  -> render Outlet (form is always reachable; probe completion is irrelevant)
 *
 * Why no isHydrating branch: the login form does not depend on knowing whether
 * the user is authed. Rendering it immediately is correct in both branches —
 * if the probe later resolves with a populated user, this gate re-renders and
 * navigates away. Cost: a brief flash of the form for already-authed users.
 * Benefit: zero wait time when the boot probe is slow.
 *
 * Honoring ?next= keeps deep-links working: a logged-in user clicking
 * /login?next=/dashboard/keys lands on /dashboard/keys, not the form.
 */
export function RedirectIfAuthed() {
  const user = useAuthStore((s) => s.user);
  const [params] = useSearchParams();

  if (user !== null) {
    const next = params.get('next');
    return <Navigate to={next || '/'} replace />;
  }

  return <Outlet />;
}
