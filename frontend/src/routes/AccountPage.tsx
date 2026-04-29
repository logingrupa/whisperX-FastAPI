import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  fetchAccountSummary,
  type AccountSummaryResponse,
} from '@/lib/api/accountApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';
import { UpgradeInterestDialog } from '@/components/dashboard/UpgradeInterestDialog';
import { DeleteAccountDialog } from '@/components/dashboard/DeleteAccountDialog';
import { LogoutAllDialog } from '@/components/dashboard/LogoutAllDialog';

/**
 * Account dashboard page (UI-07) — three-card layout: Profile / Plan / Danger Zone.
 *
 * Dumb orchestrator (SRP):
 *   - accountApi    -> HTTP via apiClient (DRY single fetch site)
 *   - 3 dialogs     -> own their own form/confirm state machines
 *   - this page     -> fetches /api/account/me, renders cards, opens dialogs
 *
 * Layout per UI-SPEC §116-160 (locked):
 *   gap-4 mobile / gap-6 md+; max-w-2xl mx-auto wrapper; Cards p-6 internal;
 *   Profile + Plan are read-only; Danger Zone has destructive border tint.
 *   Plan card primary CTA "Upgrade to Pro" is the focal point (sole bg-primary
 *   action on the page).
 *
 * Error chain (subtype-first invariant — Phase 14):
 *   RateLimitError BEFORE ApiClientError BEFORE generic catch — all set
 *   `error` (not throwing). Reload button re-runs refresh().
 */

const PLAN_BADGE_VARIANT: Record<
  AccountSummaryResponse['plan_tier'],
  'default' | 'secondary' | 'outline'
> = {
  free: 'secondary',
  trial: 'outline',
  pro: 'default',
  team: 'default',
};

const PLAN_BADGE_LABEL: Record<AccountSummaryResponse['plan_tier'], string> = {
  free: 'Free',
  trial: 'Trial',
  pro: 'Pro',
  team: 'Team',
};

const PLAN_COPY: Record<AccountSummaryResponse['plan_tier'], string> = {
  free:
    "You're on the Free plan. 5 transcribes per hour, files up to 5 minutes, 30 min/day, tiny + small models only.",
  trial:
    "You're on the 7-day Free trial. Upgrade to Pro to keep diarization, large-v3, and 100 req/hr after it ends.",
  pro:
    "You're on Pro. 100 req/hr, files up to 60 min, 600 min/day, all models, diarization enabled. Thanks for the support.",
  team:
    "You're on Team. All Pro features, plus shared workspace primitives shipping post-v1.2.",
};

const PLAN_FALLBACK_COPY = 'Plan details unavailable.';

function isUpgradeable(tier: AccountSummaryResponse['plan_tier']): boolean {
  return tier !== 'pro' && tier !== 'team';
}

function SkeletonLine({ className = '' }: { className?: string }) {
  return <div className={`h-4 rounded bg-muted ${className}`} />;
}

function SkeletonCard() {
  return (
    <Card className="gap-4 p-6">
      <SkeletonLine className="w-32" />
      <SkeletonLine className="w-48" />
      <SkeletonLine className="w-40" />
    </Card>
  );
}

export function AccountPage() {
  const [summary, setSummary] = useState<AccountSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [logoutAllOpen, setLogoutAllOpen] = useState(false);

  const refresh = async () => {
    setError(null);
    setSummary(null);
    try {
      const data = await fetchAccountSummary();
      setSummary(data);
    } catch (err) {
      // RateLimitError BEFORE ApiClientError — RateLimitError extends ApiClientError
      if (err instanceof RateLimitError) {
        setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
        return;
      }
      if (err instanceof ApiClientError) {
        setError('Could not load account.');
        return;
      }
      setError('Could not load account.');
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  if (error !== null) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4 md:gap-6">
        <h1 className="text-2xl font-semibold">Account</h1>
        <Card className="gap-4 p-6">
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <div>
            <Button variant="outline" size="sm" onClick={refresh}>
              Reload account
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (summary === null) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4 md:gap-6">
        <h1 className="text-2xl font-semibold">Account</h1>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  const planBadgeVariant = PLAN_BADGE_VARIANT[summary.plan_tier];
  const planBadgeLabel = PLAN_BADGE_LABEL[summary.plan_tier];
  const planCopy = PLAN_COPY[summary.plan_tier] ?? PLAN_FALLBACK_COPY;
  const showUpgradeCta = isUpgradeable(summary.plan_tier);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 md:gap-6">
      <h1 className="text-2xl font-semibold">Account</h1>

      {/* Profile card */}
      <Card className="gap-4 p-6">
        <h2 className="text-lg font-semibold">Profile</h2>
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-[6rem_1fr]">
          <dt className="text-sm font-medium text-muted-foreground">Email</dt>
          <dd className="text-sm">{summary.email}</dd>
          <dt className="text-sm font-medium text-muted-foreground">Plan</dt>
          <dd>
            <Badge variant={planBadgeVariant}>{planBadgeLabel}</Badge>
          </dd>
        </dl>
        <p className="text-sm text-muted-foreground">
          For password reset, email{' '}
          <a className="underline" href="mailto:hey@logingrupa.lv">
            hey@logingrupa.lv
          </a>
          .
        </p>
      </Card>

      {/* Plan card */}
      <Card className="gap-4 p-6">
        <h2 className="text-lg font-semibold">Plan</h2>
        <p className="text-sm text-muted-foreground">{planCopy}</p>
        {showUpgradeCta && (
          <div>
            <Button onClick={() => setUpgradeOpen(true)}>Upgrade to Pro</Button>
          </div>
        )}
      </Card>

      {/* Danger Zone card */}
      <Card className="gap-4 border-destructive/40 p-6">
        <h2 className="text-lg font-semibold text-destructive">Danger zone</h2>

        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between md:gap-4">
          <p className="text-sm text-muted-foreground md:max-w-md">
            End every active session, including this one. Useful if you suspect a
            leaked cookie or want to log out a forgotten device.
          </p>
          <Button
            variant="destructive"
            className="w-full md:w-auto"
            onClick={() => setLogoutAllOpen(true)}
          >
            Sign out of all devices
          </Button>
        </div>

        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between md:gap-4">
          <p className="text-sm text-muted-foreground md:max-w-md">
            Permanently delete your account and every task, API key, subscription,
            and usage record. This cannot be undone.
          </p>
          <Button
            variant="destructive"
            className="w-full md:w-auto"
            onClick={() => setDeleteOpen(true)}
          >
            Delete account
          </Button>
        </div>
      </Card>

      <UpgradeInterestDialog open={upgradeOpen} onOpenChange={setUpgradeOpen} />
      <DeleteAccountDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        userEmail={summary.email}
      />
      <LogoutAllDialog open={logoutAllOpen} onOpenChange={setLogoutAllOpen} />
    </div>
  );
}
