import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/lib/stores/authStore';
import { Button } from '@/components/ui/button';
import { LogOut } from 'lucide-react';

/**
 * Logout button (UI-04).
 *
 * Calls authStore.logout (apiClient.post('/auth/logout') + state clear +
 * BroadcastChannel sync), then navigates to /login. RequireAuth would
 * redirect anyway on the next render — explicit navigate makes the
 * post-logout location deterministic.
 */
export function LogoutButton() {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);

  const onClick = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <Button type="button" variant="ghost" size="sm" onClick={onClick}>
      <LogOut className="h-4 w-4" />
      <span className="ml-1">Log out</span>
    </Button>
  );
}
