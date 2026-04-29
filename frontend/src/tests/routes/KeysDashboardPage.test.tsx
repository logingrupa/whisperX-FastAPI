import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../setup';
import { KeysDashboardPage } from '@/routes/KeysDashboardPage';
import { useAuthStore } from '@/lib/stores/authStore';

/**
 * Plan 14-06 Task 2 integration tests — KeysDashboardPage end-to-end via MSW.
 *
 * Covers:
 *   - list render (UI-05)
 *   - empty state
 *   - create-key flow show-once + close-refreshes (KEY-04, T-14-15)
 *   - copy-to-clipboard fires navigator.clipboard.writeText
 *   - revoke confirmation -> DELETE /api/keys/:id
 *   - 429 on create surfaces inline retry-after countdown (UI-09)
 */

function renderPage() {
  return render(
    <MemoryRouter>
      <KeysDashboardPage />
    </MemoryRouter>,
  );
}

describe('KeysDashboardPage', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: 1, email: 'alice@example.com', planTier: 'trial' },
    });
  });

  it('renders existing keys from /api/keys', async () => {
    renderPage();
    expect(await screen.findByText('default')).toBeInTheDocument();
    expect(screen.getByText(/whsk_abc1/)).toBeInTheDocument();
  });

  it('shows empty state when no keys', async () => {
    server.use(http.get('/api/keys', () => HttpResponse.json([])));
    renderPage();
    expect(await screen.findByText(/no keys yet/i)).toBeInTheDocument();
  });

  it('create-key flow: opens modal -> submits -> shows plaintext once -> closes refreshes list', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('default');
    const buttons = screen.getAllByRole('button', { name: /create key/i });
    await user.click(buttons[0]);
    const nameInput = await screen.findByLabelText(/name/i);
    await user.type(nameInput, 'my-laptop');
    await user.click(screen.getByRole('button', { name: /^create$/i }));
    // Show-once view
    const plaintext = await screen.findByTestId('created-key-plaintext');
    expect(plaintext.textContent).toContain('whsk_xyz2_');
    // Done -> close + refresh
    await user.click(screen.getByRole('button', { name: /done/i }));
    await waitFor(() => {
      expect(screen.queryByTestId('created-key-plaintext')).not.toBeInTheDocument();
    });
  });

  it('copy-to-clipboard works in show-once view', async () => {
    // userEvent.setup() v14 replaces navigator.clipboard with its own
    // implementation — install a spy on the *resulting* clipboard so we
    // can assert the call regardless of provider (KEY-04 contract).
    const user = userEvent.setup();
    const writeSpy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
    renderPage();
    await screen.findByText('default');
    const createButtons = screen.getAllByRole('button', { name: /create key/i });
    await user.click(createButtons[0]);
    await user.type(await screen.findByLabelText(/name/i), 'my-laptop');
    await user.click(screen.getByRole('button', { name: /^create$/i }));
    await screen.findByTestId('created-key-plaintext');
    const copyBtn = screen.getByRole('button', { name: /copy/i });
    await user.click(copyBtn);
    expect(writeSpy).toHaveBeenCalledWith(expect.stringContaining('whsk_xyz2_'));
  });

  it('revoke flow: clicks revoke -> confirms -> calls DELETE /api/keys/:id', async () => {
    let deleteCalledWith: string | null = null;
    server.use(
      http.delete('/api/keys/:id', ({ params }) => {
        deleteCalledWith = String(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('default');
    await user.click(screen.getByRole('button', { name: /revoke default/i }));
    await user.click(await screen.findByRole('button', { name: /^revoke$/i }));
    await waitFor(() => expect(deleteCalledWith).toBe('1'));
  });

  it('429 on create-key surfaces retry-after countdown (no toast)', async () => {
    server.use(
      http.post('/api/keys', () =>
        HttpResponse.json(
          { detail: 'Too many' },
          { status: 429, headers: { 'Retry-After': '15' } },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('default');
    const createButtons = screen.getAllByRole('button', { name: /create key/i });
    await user.click(createButtons[0]);
    await user.type(await screen.findByLabelText(/name/i), 'my-laptop');
    await user.click(screen.getByRole('button', { name: /^create$/i }));
    expect(await screen.findByText(/15s/)).toBeInTheDocument();
  });
});
