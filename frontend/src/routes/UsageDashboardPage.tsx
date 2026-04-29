import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useAuthStore } from '@/lib/stores/authStore';
import { fetchKeys, type ApiKeyListItem } from '@/lib/api/keysApi';

/**
 * Usage dashboard (UI-06).
 *
 * Phase 14 best-effort:
 *   - Plan tier:        from authStore.user.planTier (set on login)
 *   - Trial countdown:  derived from earliest active key's created_at + 7d
 *                       (RATE-08: trial starts at first key creation; backend
 *                        writes trial_started_at on first key, but no /me
 *                        endpoint to read it back in Phase 14 — earliest key
 *                        is the closest client-side proxy).
 *   - Hour quota / daily minutes: render "No data yet" placeholder until
 *                                 Phase 15 ships a /api/usage endpoint.
 *
 * Threat note (T-14-17): trial countdown manipulation accepted at the UI
 * layer — backend RATE-09 enforces actual trial expiry on every transcribe.
 */
export function UsageDashboardPage() {
  const user = useAuthStore((s) => s.user);
  const [keys, setKeys] = useState<ApiKeyListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchKeys()
      .then(setKeys)
      .catch(() => setError('Could not load usage info.'));
  }, []);

  const trialInfo = computeTrialInfo(keys);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Usage</h1>
        <p className="text-sm text-muted-foreground">
          Free-tier limits: 5 transcribes/hour, 30 minutes/day, files up to 5 minutes, tiny &amp; small models.
        </p>
      </div>

      {error !== null && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <MetricCard label="Plan">
          <Badge variant="default" className="text-base capitalize">
            {user?.planTier ?? 'unknown'}
          </Badge>
        </MetricCard>

        <MetricCard label="Trial">
          <Badge variant={trialInfo.variant}>{trialInfo.label}</Badge>
        </MetricCard>

        <MetricCard label="Hour quota">
          <span className="text-sm text-muted-foreground" data-testid="hour-quota">
            No data yet
          </span>
        </MetricCard>

        <MetricCard label="Daily minutes">
          <span className="text-sm text-muted-foreground" data-testid="daily-minutes">
            No data yet
          </span>
        </MetricCard>
      </div>
    </div>
  );
}

function MetricCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Card className="p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="mt-2">{children}</div>
    </Card>
  );
}

type TrialVariant = 'default' | 'secondary' | 'destructive' | 'outline';

function computeTrialInfo(keys: ApiKeyListItem[] | null): {
  label: string;
  variant: TrialVariant;
} {
  if (keys === null) return { label: 'Loading…', variant: 'outline' };
  const active = keys.filter((k) => k.status === 'active');
  if (active.length === 0) return { label: 'Trial not started', variant: 'secondary' };
  const earliest = active.reduce((acc, k) =>
    k.created_at < acc.created_at ? k : acc,
  );
  const start = new Date(earliest.created_at).getTime();
  const expires = start + 7 * 24 * 60 * 60 * 1000;
  const remainingMs = expires - Date.now();
  const days = Math.ceil(remainingMs / (24 * 60 * 60 * 1000));
  if (days <= 0) return { label: 'Trial expired', variant: 'destructive' };
  const variant: TrialVariant = days <= 2 ? 'destructive' : days <= 4 ? 'secondary' : 'default';
  return { label: `Trial: ${days} ${days === 1 ? 'day' : 'days'} left`, variant };
}
