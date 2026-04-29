import { describe, it, expect } from 'vitest';

describe('vitest infra sentinel', () => {
  it('jest-dom matchers available', () => {
    const el = document.createElement('div');
    el.textContent = 'hello';
    expect(el).toHaveTextContent('hello');
  });
  it('BroadcastChannel polyfill installed', () => {
    const bc = new BroadcastChannel('test');
    expect(bc.name).toBe('test');
    bc.close();
  });
});
