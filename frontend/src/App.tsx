import { AppRouter } from '@/routes/AppRouter';

/**
 * Root application — delegates to the AppRouter.
 * Existing transcription UI lives at frontend/src/routes/TranscribePage.tsx (UI-10).
 */
function App() {
  return <AppRouter />;
}

export default App;
