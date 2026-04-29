import { describe, it, expect } from 'vitest';
import { scorePassword } from '@/lib/passwordStrength';

/**
 * Boundary-driven tests for the zxcvbn-style scorer (UI-03 / CONTEXT §69).
 * Locked banding (cumulative, capped at 4):
 *   length >= 8     +1
 *   mixed case      +1
 *   digit           +1
 *   symbol          +1
 *   length >= 16    +1
 */
describe('scorePassword', () => {
  it('empty -> 0', () => {
    expect(scorePassword('').score).toBe(0);
  });

  it('short 7 chars -> 0', () => {
    expect(scorePassword('abcdefg').score).toBe(0);
  });

  it('8 chars all lowercase -> 1', () => {
    expect(scorePassword('aaaaaaaa').score).toBe(1);
  });

  it('mixed case + digit 9 chars -> 3 (length+mixed+digit)', () => {
    expect(scorePassword('Password1').score).toBe(3);
  });

  it('mixed + digit + symbol 10 chars -> 4', () => {
    expect(scorePassword('Password1!').score).toBe(4);
  });

  it('long passphrase 18 chars -> 4 (capped)', () => {
    expect(scorePassword('Sup3rL0ngP@ss!w0rd!').score).toBe(4);
  });

  it('returns matching label', () => {
    expect(scorePassword('Password1!').label).toBe('Strong');
  });

  it('empty has very-weak label', () => {
    expect(scorePassword('').label).toBe('Very weak');
  });
});
