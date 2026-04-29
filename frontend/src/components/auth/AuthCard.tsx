import type { ReactNode } from 'react';
import { Card } from '@/components/ui/card';

/**
 * Shared layout shell for /login and /register (DRY — UI-13).
 * Card-on-page layout per /frontend-design skill principles:
 *   - Centered viewport-height container
 *   - max-w-md card with generous padding + soft shadow
 *   - Clear typography hierarchy (title text-2xl semibold, subtitle muted)
 *   - Footer slot separated with hairline border
 */
export function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md gap-0 px-8 py-8 shadow-lg">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {subtitle && (
            <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
        {children}
        {footer && (
          <div className="mt-6 border-t border-border pt-4 text-center text-sm text-muted-foreground">
            {footer}
          </div>
        )}
      </Card>
    </div>
  );
}
