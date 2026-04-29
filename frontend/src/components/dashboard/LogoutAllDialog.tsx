import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { logoutAllDevices } from '@/lib/api/accountApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';
import { useAuthStore } from '@/lib/stores/authStore';

/**
 * Sign-out-of-all-devices confirmation dialog (AUTH-06).
 *
 * Single-confirm pattern (UI-SPEC §229-237) — mirrors RevokeKeyDialog.
 * On success: bumps users.token_version (server-side), clears cookies,
 * then calls authStore.logout() (broadcasts via BroadcastChannel('auth')
 * for cross-tab sync — T-15-09 mitigation), then redirects /login.
 *
 * Rate-limit: RateLimitError caught BEFORE ApiClientError (subtype-first).
 */
export function LogoutAllDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onConfirm = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await logoutAllDevices();
      await logout();
      navigate('/login', { replace: true });
    } catch (err) {
      // RateLimitError extends ApiClientError — handle subtype FIRST
      if (err instanceof RateLimitError) {
        setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
      } else if (err instanceof ApiClientError) {
        setError('Could not sign out. Try again.');
      } else {
        setError('Could not sign out. Try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) setError(null);
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Sign out of all devices?</DialogTitle>
          <DialogDescription>
            Every active session — including this one — will be ended. You'll need
            to sign in again on every device.
          </DialogDescription>
        </DialogHeader>
        {error !== null && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <DialogFooter className="mt-4">
          <Button type="button" variant="ghost" onClick={() => handleOpenChange(false)}>
            Stay signed in
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting ? 'Signing out…' : 'Sign out everywhere'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
