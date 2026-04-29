import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { setupServer } from 'msw/node';
import { handlers } from './msw/handlers';

// BroadcastChannel polyfill — jsdom 25 lacks BroadcastChannel (CONTEXT §146).
// Locked decision: vi.stubGlobal with a working implementation backed by an
// in-memory channel registry so cross-tab sync tests pass deterministically.
type BcListener = (event: MessageEvent) => void;
const channelInstances: Map<string, Set<MockBroadcastChannel>> = new Map();

class MockBroadcastChannel {
  private listeners = new Set<BcListener>();
  public name: string;

  constructor(name: string) {
    this.name = name;
    const peers = channelInstances.get(name) ?? new Set<MockBroadcastChannel>();
    peers.add(this);
    channelInstances.set(name, peers);
  }

  postMessage(data: unknown): void {
    const peers = channelInstances.get(this.name);
    if (!peers) return;
    const event = new MessageEvent('message', { data });
    for (const peer of peers) {
      if (peer === this) continue;
      for (const listener of peer.listeners) listener(event);
    }
  }

  addEventListener(_type: string, listener: BcListener): void {
    this.listeners.add(listener);
  }

  removeEventListener(_type: string, listener: BcListener): void {
    this.listeners.delete(listener);
  }

  close(): void {
    this.listeners.clear();
    channelInstances.get(this.name)?.delete(this);
  }
}
vi.stubGlobal('BroadcastChannel', MockBroadcastChannel);

// window.location: jsdom provides — but tests that assert redirects need
// a settable href. Replace with a writable mock.
const locationMock = {
  href: 'http://localhost/',
  pathname: '/',
  search: '',
  assign: vi.fn(),
  replace: vi.fn(),
};
Object.defineProperty(window, 'location', {
  writable: true,
  value: locationMock,
});

// navigator.clipboard polyfill for copy-to-clipboard tests
Object.assign(navigator, {
  clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
});

// MSW Node server (used by Vitest)
export const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
  locationMock.href = 'http://localhost/';
  locationMock.pathname = '/';
  locationMock.search = '';
});
afterAll(() => server.close());
