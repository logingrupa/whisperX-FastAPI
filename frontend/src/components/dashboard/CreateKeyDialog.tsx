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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { CopyKeyButton } from './CopyKeyButton';
import { createKey, type CreatedApiKey } from '@/lib/api/keysApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';

/**
 * Create-key modal (UI-05).
 *
 * Two-state content:
 *   1. Form: name input + Submit
 *   2. Show-once view: plaintext key + Copy + Done (KEY-04)
 *
 * Show-once UX: plaintext lives only in component state (`created`);
 * `reset()` clears it on close. NEVER persisted to localStorage/sessionStorage
 * (T-14-15 mitigation).
 *
 * Anti-spam: 429 RateLimitError surfaces inline Retry-After countdown,
 * not toast (UI-09).
 */
export function CreateKeyDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);

  const reset = () => {
    setName('');
    setSubmitting(false);
    setError(null);
    setCreated(null);
  };

  const handleClose = () => {
    if (created !== null) onCreated();
    reset();
    onOpenChange(false);
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim().length === 0) {
      setError('Name is required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const apiKey = await createKey(name.trim());
      setCreated(apiKey);
    } catch (err) {
      // RateLimitError extends ApiClientError — handle subtype FIRST
      if (err instanceof RateLimitError) {
        setError(`Too many requests. Try again in ${err.retryAfterSeconds}s.`);
      } else if (err instanceof ApiClientError) {
        setError('Could not create key.');
      } else {
        setError('Could not create key.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : handleClose())}>
      <DialogContent>
        {created === null ? (
          <form onSubmit={onSubmit}>
            <DialogHeader>
              <DialogTitle>Create API key</DialogTitle>
              <DialogDescription>
                Give your key a memorable name. You'll see the raw key once after creation.
              </DialogDescription>
            </DialogHeader>
            <div className="my-6 flex flex-col gap-2">
              <Label htmlFor="key-name">Name</Label>
              <Input
                id="key-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="my-laptop"
                autoFocus
                maxLength={64}
              />
            </div>
            {error !== null && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <DialogFooter className="mt-6">
              <Button type="button" variant="ghost" onClick={handleClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Creating…' : 'Create'}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div>
            <DialogHeader>
              <DialogTitle>Save your API key</DialogTitle>
              <DialogDescription>
                This is the only time the full key is shown. Store it securely.
              </DialogDescription>
            </DialogHeader>
            <Alert className="my-4">
              <AlertDescription>
                The plaintext key is unrecoverable after you close this dialog.
              </AlertDescription>
            </Alert>
            <code
              className="block w-full select-all overflow-x-auto rounded-md border border-border bg-muted p-3 font-mono text-sm"
              data-testid="created-key-plaintext"
            >
              {created.key}
            </code>
            <DialogFooter className="mt-6">
              <CopyKeyButton value={created.key} label="Copy key" />
              <Button type="button" onClick={handleClose}>
                Done
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
