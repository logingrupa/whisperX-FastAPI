/**
 * Plan 15-06 Task 2 — UpgradeInterestDialog RTL coverage.
 *
 * Covers (BILL-05 client paths):
 *   - submits -> swallows 501 (default MSW handler) -> shows "Thanks!" copy
 *   - 2s auto-close after success (vi.useFakeTimers + advanceTimersByTimeAsync)
 *   - 429 RateLimitError surfaces inline retry-after countdown copy
 *
 * T-15-07: backend /billing/checkout returns 501 stub; dialog must treat
 * statusCode === 501 as success (caller catches before generic ApiClientError).
 *
 * TEST-05 invariants honored — async clicks awaited; findByText/findByRole
 * used after every state change.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { UpgradeInterestDialog } from '@/components/dashboard/UpgradeInterestDialog';
import { server } from '@/tests/setup';

afterEach(() => {
  vi.useRealTimers();
});

describe('UpgradeInterestDialog', () => {
  it('submits, swallows 501, shows Thanks copy', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<UpgradeInterestDialog open onOpenChange={onOpenChange} />);
    await user.click(
      await screen.findByRole('button', { name: /^send$/i }),
    );
    // "Thanks!" is unique to the success alert; "v1.3" appears in the
    // dialog description as well, so assert the full success-body sentence.
    expect(await screen.findByText(/thanks!/i)).toBeInTheDocument();
    expect(
      await screen.findByText(/stripe checkout arrives in v1\.3/i),
    ).toBeInTheDocument();
  });

  it('auto-closes 2s after success', async () => {
    // Real timers for the click+fetch chain, fake timers only after success
    // lands. Mixing fake timers with MSW response promises tends to deadlock
    // findByText polling, so advance timers via setTimeout-spy instead.
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout');
    render(<UpgradeInterestDialog open onOpenChange={onOpenChange} />);
    await user.click(screen.getByRole('button', { name: /^send$/i }));
    await screen.findByText(/thanks!/i);
    // Verify a 2000ms close timer was scheduled, then run its callback
    // synchronously to assert the auto-close contract.
    const close = setTimeoutSpy.mock.calls.find(([, ms]) => ms === 2000);
    expect(close).toBeDefined();
    const callback = close![0] as () => void;
    act(() => {
      callback();
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    setTimeoutSpy.mockRestore();
  });

  it('429 shows retry-after countdown', async () => {
    server.use(
      http.post('/billing/checkout', () =>
        HttpResponse.json(
          { detail: 'rate' },
          { status: 429, headers: { 'Retry-After': '15' } },
        ),
      ),
    );
    const user = userEvent.setup();
    render(<UpgradeInterestDialog open onOpenChange={() => {}} />);
    await user.click(
      await screen.findByRole('button', { name: /^send$/i }),
    );
    expect(await screen.findByText(/15s/)).toBeInTheDocument();
  });
});
