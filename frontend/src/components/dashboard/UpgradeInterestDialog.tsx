import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { submitUpgradeInterest } from '@/lib/api/accountApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';

/**
 * Upgrade-to-Pro interest capture dialog (BILL-05).
 *
 * Two-state machine (UI-SPEC §239-247):
 *   1. idle/error  -> textarea + Send/No-thanks buttons
 *   2. success     -> Alert "Thanks! Stripe arrives in v1.3" + auto-close 2s
 *
 * Backend `/billing/checkout` returns 501 in v1.2 — caller catches
 * ApiClientError with `status === 501` (statusCode === 501 contract — T-15-07)
 * and treats it as success. v1.3 will wire real Stripe checkout.
 *
 * Rate-limit: RateLimitError caught BEFORE ApiClientError (subtype-first
 * invariant — Phase 14). Inline countdown copy `Too many requests. Try
 * again in {n}s.` (UI-SPEC §305).
 */
const SUCCESS_AUTO_CLOSE_MS = 2000;
const TEXTAREA_MAX_LENGTH = 500;

const TEXTAREA_CLASS =
  'flex min-h-24 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm ' +
  'shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground ' +
  'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] ' +
  'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50';

export function UpgradeInterestDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const reset = () => {
    setMessage('');
    setSubmitting(false);
    setError(null);
    setSuccess(false);
  };

  const handleClose = () => {
    reset();
    onOpenChange(false);
  };

  // Auto-close 2s after success — UI-SPEC §174 / §245
  useEffect(() => {
    if (!success) return;
    const timer = setTimeout(() => {
      handleClose();
    }, SUCCESS_AUTO_CLOSE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [success]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await submitUpgradeInterest(message.trim());
      setSuccess(true);
    } catch (err) {
      // Subtype-first: RateLimitError (extends ApiClientError) BEFORE the
      // generic ApiClientError branch. Then 501 -> success swallow (T-15-07,
      // statusCode === 501 contract); other ApiClientError -> generic copy.
      if (err instanceof RateLimitError) {
        setError(`Too many requests. Try again in ${err.retryAfterSeconds}s.`);
      } else if (err instanceof ApiClientError && err.status === 501) {
        // statusCode === 501 (mapped via err.status) — T-15-07 swallow as success
        setSuccess(true);
      } else if (err instanceof ApiClientError) {
        setError('Could not send. Try again.');
      } else {
        setError('Could not send. Try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) handleClose();
    else onOpenChange(true);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upgrade to Pro</DialogTitle>
          <DialogDescription>
            Tell us what you need from Pro. Real Stripe checkout ships in v1.3.
          </DialogDescription>
        </DialogHeader>

        {success ? (
          <Alert className="my-2">
            <AlertDescription>
              <p className="font-medium text-foreground">Thanks!</p>
              <p>Stripe checkout arrives in v1.3. We'll email you when it goes live.</p>
            </AlertDescription>
          </Alert>
        ) : (
          <form onSubmit={onSubmit}>
            <div className="my-4 flex flex-col gap-2">
              <Label htmlFor="upgrade-message">
                What do you want from Pro? — optional
              </Label>
              <textarea
                id="upgrade-message"
                className={TEXTAREA_CLASS}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Diarization on long files, faster turnaround, larger uploads…"
                maxLength={TEXTAREA_MAX_LENGTH}
                disabled={submitting}
                autoFocus
              />
            </div>
            {error !== null && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={handleClose}>
                No thanks
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Sending…' : 'Send'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
