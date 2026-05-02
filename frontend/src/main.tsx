import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import { useAuthStore } from '@/lib/stores/authStore'
import './index.css'
import App from './App.tsx'

/**
 * Boot probe (Plan 15-05) — hydrate auth from server cookie session before
 * first render. Fire-and-forget; isHydrating flips false in refresh's finally.
 * Module-scope call (not useEffect) avoids StrictMode double-hydration.
 *
 * Timeout safety net (debug fix login-stuck-loading):
 *   If the probe doesn't settle within BOOT_PROBE_TIMEOUT_MS we force
 *   isHydrating=false so the auth gates can render (login form or
 *   redirect-to-/login). Without this, a slow /api/account/me deadlocks
 *   <AuthHydratingFallback /> and the user sees "Loading…" forever with
 *   no way out — including on /login itself, which is gated by
 *   RedirectIfAuthed. Late probe responses (after timeout) still update
 *   user state via the original promise; they just no longer gate the UI.
 */
const BOOT_PROBE_TIMEOUT_MS = 8000;

void useAuthStore.getState().refresh();
setTimeout(() => {
  if (useAuthStore.getState().isHydrating) {
    useAuthStore.setState({ isHydrating: false });
  }
}, BOOT_PROBE_TIMEOUT_MS);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename="/ui">
      <TooltipProvider>
        <App />
        <Toaster />
      </TooltipProvider>
    </BrowserRouter>
  </StrictMode>,
)
