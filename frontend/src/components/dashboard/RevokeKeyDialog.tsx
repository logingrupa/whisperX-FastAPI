import { useState } from 'react';
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
import { revokeKey } from '@/lib/api/keysApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';

/**
 * Revoke-key confirmation modal (UI-05).
 *
 * Single-confirm-click — backend soft-deletes (Phase 13). Cross-user
 * spoofing mitigated server-side (T-14-16): unknown id -> 404.
 */
export function RevokeKeyDialog({
  keyId,
  keyName,
  open,
  onOpenChange,
  onRevoked,
}: {
  keyId: number | null;
  keyName: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRevoked: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onConfirm = async () => {
    if (keyId === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await revokeKey(keyId);
      onRevoked();
      onOpenChange(false);
    } catch (err) {
      // RateLimitError BEFORE ApiClientError — RateLimitError extends ApiClientError
      if (err instanceof RateLimitError) {
        setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
      } else if (err instanceof ApiClientError) {
        setError('Could not revoke key.');
      } else {
        setError('Could not revoke key.');
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
          <DialogTitle>Revoke key?</DialogTitle>
          <DialogDescription>
            {keyName !== null
              ? `"${keyName}" will be revoked immediately.`
              : 'This key will be revoked immediately.'}
            {' '}Existing requests using it will fail.
          </DialogDescription>
        </DialogHeader>
        {error !== null && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <DialogFooter className="mt-4">
          <Button type="button" variant="ghost" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting ? 'Revoking…' : 'Revoke'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
