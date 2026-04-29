import { Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import { TranscribePage } from './TranscribePage';
import { RequireAuth } from './RequireAuth';
import { RouteErrorBoundary } from './RouteErrorBoundary';
import { AccountStubPage } from './AccountStubPage';
import { AppShell } from '@/components/layout/AppShell';

// Lazy-loaded pages (Plans 05/06 ship the real implementations).
// Each lazy module is wrapped in a default export by its plan.
const LoginPage = lazy(() =>
  import('./LoginPage').then((m) => ({ default: m.LoginPage })),
);
const RegisterPage = lazy(() =>
  import('./RegisterPage').then((m) => ({ default: m.RegisterPage })),
);
const KeysDashboardPage = lazy(() =>
  import('./KeysDashboardPage').then((m) => ({ default: m.KeysDashboardPage })),
);
const UsageDashboardPage = lazy(() =>
  import('./UsageDashboardPage').then((m) => ({ default: m.UsageDashboardPage })),
);

function PageWrap({ children }: { children: ReactNode }) {
  return (
    <RouteErrorBoundary>
      <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Loading…</div>}>
        {children}
      </Suspense>
    </RouteErrorBoundary>
  );
}

export function AppRouter() {
  return (
    <Routes>
      {/* Public routes — no AppShell, no auth */}
      <Route path="/login" element={<PageWrap><LoginPage /></PageWrap>} />
      <Route path="/register" element={<PageWrap><RegisterPage /></PageWrap>} />

      {/* Root — TranscribePage (UI-10) — auth-required, full-bleed (no AppShell) */}
      <Route element={<RequireAuth />}>
        <Route path="/" element={<PageWrap><TranscribePage /></PageWrap>} />
      </Route>

      {/* Dashboard routes — auth-required, wrapped in AppShell */}
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/dashboard/keys" element={<PageWrap><KeysDashboardPage /></PageWrap>} />
          <Route path="/dashboard/usage" element={<PageWrap><UsageDashboardPage /></PageWrap>} />
          <Route path="/dashboard/account" element={<PageWrap><AccountStubPage /></PageWrap>} />
        </Route>
      </Route>

      {/* Catch-all -> /login (the redirect to /login?next= is handled by RequireAuth) */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
