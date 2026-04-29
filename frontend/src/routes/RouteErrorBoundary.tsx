import { ErrorBoundary } from 'react-error-boundary';
import type { ReactNode } from 'react';
import { Card } from '@/components/ui/card';

/**
 * Per-route error boundary (CONTEXT §147 Claude's Discretion locked).
 * Renders a recoverable error card; user can reload to recover.
 */
function FallbackUI({ error }: { error: Error }) {
  return (
    <Card className="mx-auto mt-12 max-w-lg p-6">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <p className="mt-2 text-sm text-muted-foreground">{error.message}</p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="mt-4 inline-flex items-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
      >
        Reload page
      </button>
    </Card>
  );
}

export function RouteErrorBoundary({ children }: { children: ReactNode }) {
  return <ErrorBoundary FallbackComponent={FallbackUI}>{children}</ErrorBoundary>;
}
