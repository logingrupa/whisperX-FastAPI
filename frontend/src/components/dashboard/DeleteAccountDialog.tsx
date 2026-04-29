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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { deleteAccount } from '@/lib/api/accountApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';
import { useAuthStore } from '@/lib/stores/authStore';

/**
 * Delete-account confirmation dialog (SCOPE-06).
 *
 * Type-exact-email match gate (UI-SPEC §214-227):
 *   isMatched = confirmEmail.trim().toLowerCase() === userEmail.toLowerCase()
 *   submit disabled until isMatched (forgiving case, type-exact otherwise).
 *
 * On success: cascade-deletes account server-side (Plan 15-04), clears
 * cookies, then calls authStore.logout() (broadcasts cross-tab — UI-12)
 * then redirects /login.
 *
 * Error branches:
 *   - 429 RateLimitError    -> rate-limit copy
 *   - 400 ApiClientError    -> "Confirmation email does not match." (server gate)
 *   - other ApiClientError  -> generic "Could not delete account."
 *
 * Tiger-style: UI gate is defence-in-depth; backend re-validates email
 * (Plan 15-04 service-level guard) — T-15-02 mitigation.
 */
export function DeleteAccountDialog({
  open,
  onOpenChange,
  userEmail,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userEmail: string;
}) {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const [confirmEmail, setConfirmEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isMatched =
    confirmEmail.trim().toLowerCase() === userEmail.toLowerCase() &&
    userEmail.length > 0;

  const reset = () => {
    setConfirmEmail('');
    setSubmitting(false);
    setError(null);
  };

  const handleClose = () => {
    reset();
    onOpenChange(false);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) handleClose();
    else onOpenChange(true);
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isMatched) return; // defence — button is disabled
    setSubmitting(true);
    setError(null);
    try {
      await deleteAccount(confirmEmail);
      await logout();
      navigate('/login', { replace: true });
    } catch (err) {
      // RateLimitError extends ApiClientError — handle subtype FIRST
      if (err instanceof RateLimitError) {
        setError(`Too many requests. Try again in ${err.retryAfterSeconds}s.`);
      } else if (err instanceof ApiClientError) {
        setError(
          err.status === 400
            ? 'Confirmation email does not match.'
            : 'Could not delete account. Try again.',
        );
      } else {
        setError('Could not delete account. Try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Delete account?</DialogTitle>
            <DialogDescription>
              This permanently deletes your account, API keys, tasks, and usage
              history. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="my-6 flex flex-col gap-2">
            <Label htmlFor="confirm-email">
              Type your email to confirm: {userEmail}
            </Label>
            <Input
              id="confirm-email"
              type="email"
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
              placeholder="you@example.com"
              autoFocus
              autoComplete="off"
              spellCheck={false}
              disabled={submitting}
            />
          </div>
          {error !== null && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={handleClose}>
              Keep account
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={!isMatched || submitting}
            >
              {submitting ? 'Deleting…' : 'Delete account'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
