import { Link, useNavigate } from 'react-router-dom';
import { ChevronDown, Key, Activity, UserCog, LogOut } from 'lucide-react';
import { useAuthStore } from '@/lib/stores/authStore';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

/**
 * Shared top navigation — single source of truth across TranscribePage (`/`)
 * and AppShell-wrapped dashboard routes (`/dashboard/*`).
 *
 * SRP: nav chrome only. Reads `authStore.user` for display + `logout` action.
 * DRY: replaces ad-hoc header in `AppShell` and gives `/` a matching nav.
 *
 * Layout: `sticky top-0` + `backdrop-blur` so content scrolls under translucent
 * header. `h-14 border-b` for slim, scannable bar. `gap-3 items-center` aligns
 * brand + menu trigger on a single baseline.
 *
 * Full-bleed safe: NO max-width container — TranscribePage's UploadDropzone
 * remains edge-to-edge. Inner padding is `px-4` only (matches body gutter).
 */
export function TopNav() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const onSignOut = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const email = user?.email ?? '';
  const initial = email.charAt(0).toUpperCase() || '?';

  return (
    <header className="sticky top-0 z-40 h-14 w-full border-b border-border bg-background/80 backdrop-blur">
      <div className="flex h-full items-center justify-between gap-3 px-4">
        <Link to="/" className="text-lg font-semibold">
          WhisperX
        </Link>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="gap-2"
              aria-label="Open user menu"
            >
              <span
                aria-hidden="true"
                className="flex h-7 w-7 items-center justify-center rounded-full bg-muted text-sm font-medium"
              >
                {initial}
              </span>
              <span className="hidden text-sm md:inline">{email}</span>
              <ChevronDown className="h-4 w-4 opacity-70" />
            </Button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem asChild>
              <Link to="/dashboard/keys">
                <Key className="h-4 w-4" />
                <span>API Keys</span>
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/dashboard/usage">
                <Activity className="h-4 w-4" />
                <span>Usage</span>
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/dashboard/account">
                <UserCog className="h-4 w-4" />
                <span>Account</span>
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onSignOut} variant="destructive">
              <LogOut className="h-4 w-4" />
              <span>Sign out</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
