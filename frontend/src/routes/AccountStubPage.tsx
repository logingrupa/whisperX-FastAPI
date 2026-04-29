import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

/**
 * Placeholder — Phase 15 (UI-07) fills in plan_tier card, upgrade-to-pro CTA,
 * delete-account flow.
 */
export function AccountStubPage() {
  return (
    <Card className="mx-auto max-w-2xl p-8">
      <div className="flex items-start justify-between">
        <h1 className="text-2xl font-semibold">Account</h1>
        <Badge variant="secondary">Coming in Phase 15</Badge>
      </div>
      <p className="mt-4 text-sm text-muted-foreground">
        Account management — plan tier, upgrade to Pro, delete account — ships in
        the next polish phase. For password reset, email{' '}
        <a className="underline" href="mailto:hey@logingrupa.lv">
          hey@logingrupa.lv
        </a>
        .
      </p>
    </Card>
  );
}
