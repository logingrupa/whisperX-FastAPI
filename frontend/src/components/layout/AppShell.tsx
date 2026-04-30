import { Outlet } from 'react-router-dom';
import { TopNav } from '@/components/layout/TopNav';

/**
 * Dashboard shell — TopNav + main content area.
 * Applied to /dashboard/* routes; / (TranscribePage) renders TopNav as a
 * sibling to preserve full-bleed UploadDropzone layout (UI-10 zero-regression).
 *
 * Header is delegated to <TopNav> so a single nav lives across all pages
 * (DRY). This component owns only the page-content container.
 */
export function AppShell() {
  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <main className="mx-auto max-w-6xl p-6">
        <Outlet />
      </main>
    </div>
  );
}
