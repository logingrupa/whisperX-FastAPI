/**
 * Usage dashboard page (quick-260505-l2w) — real data from GET /api/usage.
 *
 * Layout / design variant chosen via /frontend-design (inline executor pass):
 *
 *   @design-variant: horizontal-bar-quota-cards
 *
 * Single-column-friendly card stack inside the AccountPage shell idiom
 * (`max-w-2xl mx-auto flex flex-col gap-4 md:gap-6`). Three to four cards:
 *
 *   1. Plan — pill Badge with tier-specific variant + tier copy line built
 *      entirely from summary.hour_limit + summary.daily_minutes_limit
 *      (no hardcoded numbers; data-driven for free / trial / pro / team).
 *   2. Trial countdown — rendered ONLY when plan_tier === 'trial' AND
 *      trial_started_at !== null. Days-remaining label colored by
 *      threshold (<=2d destructive, <=4d warn, >4d default); when expired
 *      the card border + accent flips destructive and surfaces an
 *      "Upgrade" button → /pricing. When NOT trial: card omitted entirely
 *      (no empty placeholder).
 *   3. Hour quota — horizontal Progress bar with semantic color via
 *      wrapping div data-attr (warn at high-fill threshold, destructive
 *      at full). Count "N of N" above the bar, "Resets at HH:MM UTC"
 *      sub-line below.
 *   4. Daily minutes — same horizontal-bar pattern; minutes formatted
 *      with one-decimal precision plus "min" suffix; "Resets at midnight
 *      UTC" sub-line.
 *
 * Refresh affordance: small icon-button in the page header re-fires
 * fetchUsageSummary once on click. No polling, no setInterval. CONTEXT D
 * lock: one-shot fetch on mount + manual Refresh.
 *
 * Engineering posture (CONTEXT meta lock — "best practices, don't
 * overcomplicate"): re-uses existing <Card>, <Badge>, <Button>,
 * <Progress>, <Alert> primitives — zero new deps, no chart library, no
 * shadcn skeleton install. Inline `bg-muted h-N rounded` pulses for the
 * loading state mirror the AccountPage pattern.
 *
 * Error handling — subtype-first per CLAUDE.md:
 *   RateLimitError -> inline countdown copy
 *   ApiClientError -> generic error alert
 *   else           -> generic error alert
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  fetchUsageSummary,
  type PlanTier,
  type UsageSummary,
} from '@/lib/api/usageApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';

const PLAN_BADGE_VARIANT: Record<PlanTier, 'default' | 'secondary' | 'outline'> = {
  free: 'secondary',
  trial: 'outline',
  pro: 'default',
  team: 'default',
};

const PLAN_BADGE_LABEL: Record<PlanTier, string> = {
  free: 'Free',
  trial: 'Trial',
  pro: 'Pro',
  team: 'Team',
};

const PRICING_ROUTE = '/pricing';
const QUOTA_WARN_THRESHOLD = 0.8;
const QUOTA_FULL_THRESHOLD = 1.0;
const TRIAL_WARN_DAYS = 4;
const TRIAL_DESTRUCTIVE_DAYS = 2;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

type SemanticAccent = 'default' | 'warn' | 'destructive';

function resolveQuotaAccent(used: number, limit: number): SemanticAccent {
  if (limit <= 0) return 'default';
  const percent = used / limit;
  if (percent >= QUOTA_FULL_THRESHOLD) return 'destructive';
  if (percent >= QUOTA_WARN_THRESHOLD) return 'warn';
  return 'default';
}

function resolveTrialAccent(daysLeft: number): SemanticAccent {
  if (daysLeft <= TRIAL_DESTRUCTIVE_DAYS) return 'destructive';
  if (daysLeft <= TRIAL_WARN_DAYS) return 'warn';
  return 'default';
}

function quotaIndicatorClass(accent: SemanticAccent): string {
  if (accent === 'destructive') return 'bg-destructive/15';
  if (accent === 'warn') return 'bg-amber-500/20';
  return '';
}

function quotaCountClass(accent: SemanticAccent): string {
  if (accent === 'destructive') return 'text-destructive';
  if (accent === 'warn') return 'text-amber-600 dark:text-amber-400';
  return 'text-foreground';
}

function trialAccentClass(accent: SemanticAccent): string {
  if (accent === 'destructive') return 'text-destructive';
  if (accent === 'warn') return 'text-amber-600 dark:text-amber-400';
  return 'text-foreground';
}

function formatHourMinUTC(iso: string): string {
  const date = new Date(iso);
  const hours = String(date.getUTCHours()).padStart(2, '0');
  const minutes = String(date.getUTCMinutes()).padStart(2, '0');
  return `${hours}:${minutes} UTC`;
}

function formatMinutes(value: number): string {
  return `${value.toFixed(1)} min`;
}

function clampPercent(value: number): number {
  if (Number.isNaN(value)) return 0;
  if (value < 0) return 0;
  if (value > 100) return 100;
  return value;
}

function daysLeftFrom(expiresIso: string, now: Date): number {
  const expires = new Date(expiresIso).getTime();
  const remaining = expires - now.getTime();
  return Math.ceil(remaining / MS_PER_DAY);
}

function SkeletonLine({ className = '' }: { className?: string }) {
  return <div className={`h-4 rounded bg-muted animate-pulse ${className}`} />;
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

export function UsageDashboardPage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refresh = async (): Promise<void> => {
    setError(null);
    setIsLoading(true);
    try {
      const data = await fetchUsageSummary();
      setSummary(data);
    } catch (err) {
      // RateLimitError BEFORE ApiClientError — RateLimitError extends ApiClientError.
      if (err instanceof RateLimitError) {
        setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
        setSummary(null);
        return;
      }
      if (err instanceof ApiClientError) {
        setError('Could not load usage.');
        setSummary(null);
        return;
      }
      setError('Could not load usage.');
      setSummary(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchUsageSummary()
      .then((data) => {
        setSummary(data);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof RateLimitError) {
          setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
        } else if (err instanceof ApiClientError) {
          setError('Could not load usage.');
        } else {
          setError('Could not load usage.');
        }
        setIsLoading(false);
      });
  }, []);

  if (error !== null) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4 md:gap-6">
        <PageHeader onRefresh={refresh} disabled={isLoading} />
        <Card className="gap-4 p-6">
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <div>
            <Button variant="outline" size="sm" onClick={refresh}>
              Retry
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (summary === null) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4 md:gap-6">
        <PageHeader onRefresh={refresh} disabled />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  const planVariant = PLAN_BADGE_VARIANT[summary.plan_tier];
  const planLabel = PLAN_BADGE_LABEL[summary.plan_tier];
  const planLine =
    `Your plan: ${summary.hour_limit} transcribes/hour, ` +
    `${summary.daily_minutes_limit} min/day.`;

  const showTrialCard =
    summary.plan_tier === 'trial' && summary.trial_started_at !== null;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 md:gap-6">
      <PageHeader onRefresh={refresh} disabled={isLoading} />

      {/* Plan card */}
      <Card className="gap-4 p-6">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold">Plan</h2>
          <Badge variant={planVariant} className="capitalize">
            {planLabel}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{planLine}</p>
      </Card>

      {showTrialCard && summary.trial_expires_at !== null && (
        <TrialCountdownCard
          trialExpiresAtIso={summary.trial_expires_at}
          onUpgrade={() => navigate(PRICING_ROUTE)}
        />
      )}

      {/* Hour quota card */}
      <QuotaCard
        title="Hour quota"
        used={summary.hour_count}
        limit={summary.hour_limit}
        valueLabel={`${summary.hour_count} of ${summary.hour_limit}`}
        subLine={`Resets at ${formatHourMinUTC(summary.window_resets_at)}`}
        testIdPrefix="hour-quota"
      />

      {/* Daily minutes card */}
      <QuotaCard
        title="Daily minutes"
        used={summary.daily_minutes_used}
        limit={summary.daily_minutes_limit}
        valueLabel={`${formatMinutes(summary.daily_minutes_used)} of ${formatMinutes(summary.daily_minutes_limit)}`}
        subLine="Resets at midnight UTC"
        testIdPrefix="daily-minutes"
      />
    </div>
  );
}

function PageHeader({ onRefresh, disabled }: { onRefresh: () => void; disabled: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <h1 className="text-2xl font-semibold">Usage</h1>
      <Button
        variant="outline"
        size="sm"
        onClick={onRefresh}
        disabled={disabled}
        aria-label="Refresh usage"
      >
        Refresh
      </Button>
    </div>
  );
}

function TrialCountdownCard({
  trialExpiresAtIso,
  onUpgrade,
}: {
  trialExpiresAtIso: string;
  onUpgrade: () => void;
}) {
  const now = new Date();
  const daysLeft = daysLeftFrom(trialExpiresAtIso, now);
  const isExpired = daysLeft <= 0;

  if (isExpired) {
    const daysAgo = Math.abs(daysLeft);
    return (
      <Card
        className="gap-4 border-destructive/40 p-6"
        data-testid="trial-card"
        data-trial-state="expired"
      >
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-semibold text-destructive">
              Trial expired {daysAgo} day{daysAgo === 1 ? '' : 's'} ago
            </h2>
            <p className="text-sm text-muted-foreground">
              Upgrade to keep transcribing without interruption.
            </p>
          </div>
          <Button variant="destructive" onClick={onUpgrade} className="md:self-center">
            Upgrade
          </Button>
        </div>
      </Card>
    );
  }

  const accent = resolveTrialAccent(daysLeft);
  const accentClass = trialAccentClass(accent);
  return (
    <Card className="gap-2 p-6" data-testid="trial-card" data-trial-state={accent}>
      <h2 className="text-lg font-semibold">Trial</h2>
      <p className={`text-sm font-medium ${accentClass}`}>
        {daysLeft} day{daysLeft === 1 ? '' : 's'} left
      </p>
    </Card>
  );
}

function QuotaCard({
  title,
  used,
  limit,
  valueLabel,
  subLine,
  testIdPrefix,
}: {
  title: string;
  used: number;
  limit: number;
  valueLabel: string;
  subLine: string;
  testIdPrefix: string;
}) {
  const accent = resolveQuotaAccent(used, limit);
  const percent = clampPercent(limit > 0 ? (used / limit) * 100 : 0);
  return (
    <Card
      className="gap-3 p-6"
      data-testid={`${testIdPrefix}-card`}
      data-quota-state={accent}
    >
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        <span
          className={`text-sm font-medium ${quotaCountClass(accent)}`}
          data-testid={`${testIdPrefix}-count`}
        >
          {valueLabel}
        </span>
      </div>
      <div className={`rounded-full ${quotaIndicatorClass(accent)}`}>
        <Progress value={percent} aria-label={`${title} progress`} />
      </div>
      <p className="text-xs text-muted-foreground">{subLine}</p>
    </Card>
  );
}
