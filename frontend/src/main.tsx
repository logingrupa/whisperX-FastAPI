import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import { useAuthStore } from '@/lib/stores/authStore'
import './index.css'
import App from './App.tsx'

// Boot probe (Plan 15-05) — hydrate auth from server cookie session before
// first render. Fire-and-forget; isHydrating flips false in refresh's finally.
// Module-scope call (not useEffect) avoids StrictMode double-hydration.
void useAuthStore.getState().refresh();

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
