import { Link, NavLink, Outlet } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { useAuthStore } from '@/lib/stores/authStore';

/**
 * Dashboard shell — top nav + main content area.
 * Applied to /dashboard/* routes; / (TranscribePage) renders without it
 * to preserve full-bleed UploadDropzone layout (UI-10 zero-regression).
 *
 * `/frontend-design` principles: density via spacing-4 nav, hierarchy via
 * font-semibold brand + ghost links, modern via neutral palette.
 */
export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    isActive
      ? 'text-sm font-medium text-foreground'
      : 'text-sm font-medium text-muted-foreground hover:text-foreground';

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-6xl items-center justify-between p-4">
          <Link to="/" className="text-lg font-semibold">
            WhisperX
          </Link>
          <nav className="flex items-center gap-6">
            <NavLink to="/dashboard/keys" className={navLinkClass}>
              API Keys
            </NavLink>
            <NavLink to="/dashboard/usage" className={navLinkClass}>
              Usage
            </NavLink>
            <NavLink to="/dashboard/account" className={navLinkClass}>
              Account
            </NavLink>
            {user !== null && (
              <Badge variant="outline" className="ml-2">
                {user.email}
              </Badge>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl p-6">
        <Outlet />
      </main>
    </div>
  );
}
