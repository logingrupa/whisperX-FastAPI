import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { TranscribePage } from '@/routes/TranscribePage';
import { useAuthStore } from '@/lib/stores/authStore';

/**
 * TEST-06 — regression smoke for the existing transcription flow.
 *
 * Goal: prove Phase 14 cutover (apiClient + WS-ticket + router shell) did NOT
 * break the upload/transcribe/progress/export UX. We render TranscribePage
 * inside MemoryRouter + TooltipProvider, drop a file, and assert the queue
 * accepts it and exposes a Start affordance. Deeper E2E lives in Phase 16.
 */

// jsdom has no WebSocket; react-use-websocket will try to construct one as
// soon as socketUrl flips to a string. Stub a minimal compliant implementation.
class MockWebSocket {
  readyState = 0;
  onopen: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.(new Event('open'));
    }, 0);
  }
  send(): void {}
  close(): void {
    this.readyState = 3;
    this.onclose?.(new CloseEvent('close', { code: 1000 }));
  }
  addEventListener(): void {}
  removeEventListener(): void {}
}

function renderTranscribe() {
  return render(
    <MemoryRouter>
      <TooltipProvider>
        <TranscribePage />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

describe('TEST-06 regression smoke — TranscribePage existing flow', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: 1, email: 'alice@example.com', planTier: 'trial' },
    });
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  it('renders the dropzone CTA', () => {
    renderTranscribe();
    expect(screen.getByText(/upload files/i)).toBeInTheDocument();
  });

  it('accepts a file via the input and adds it to the queue', async () => {
    const user = userEvent.setup();
    renderTranscribe();
    const input = document.querySelector('input[type="file"]');
    expect(input).not.toBe(null);
    const file = new File(['test audio bytes'], 'sample.mp3', { type: 'audio/mpeg' });
    await user.upload(input as HTMLInputElement, file);
    expect(await screen.findByText(/sample\.mp3/)).toBeInTheDocument();
  });

  it('exposes a Start affordance once a file is queued (apiClient cutover did not regress UI-10)', async () => {
    const user = userEvent.setup();
    renderTranscribe();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['short audio'], 'short.mp3', { type: 'audio/mpeg' });
    await user.upload(input, file);
    await screen.findByText(/short\.mp3/);
    // FileQueueItem's per-file start button uses the `title` attribute as
    // its accessible name; pending state renders either "Start processing"
    // (language selected) or "Select language first" (default). Both shapes
    // prove the queue UI is alive after the cutover.
    const startOrLangButtons = await screen.findAllByRole('button', {
      name: /start processing|select language first/i,
    });
    expect(startOrLangButtons.length).toBeGreaterThan(0);
  });
});
