/**
 * Roll-our-own zxcvbn-style password strength heuristic (UI-03 / CONTEXT §69).
 * No external library — score 0..4 from regex/length checks.
 *
 * Pure function — easy to unit-test, no side effects, no React imports.
 *
 * Bands (cumulative, capped at 4):
 *   length >= 8     +1
 *   mixed case      +1
 *   digit           +1
 *   symbol          +1
 *   length >= 16    +1
 */

export type PasswordStrength = 0 | 1 | 2 | 3 | 4;

export interface PasswordStrengthResult {
  score: PasswordStrength;
  label: string;
  hint: string;
}

const LABELS: Record<PasswordStrength, string> = {
  0: 'Very weak',
  1: 'Weak',
  2: 'Fair',
  3: 'Good',
  4: 'Strong',
};

const HINTS: Record<PasswordStrength, string> = {
  0: 'Use at least 8 characters.',
  1: 'Add mixed case or digits.',
  2: 'Add a symbol or more length.',
  3: 'Almost there — a bit longer is great.',
  4: 'Strong password.',
};

export function scorePassword(password: string): PasswordStrengthResult {
  if (password.length === 0) {
    return { score: 0, label: LABELS[0], hint: HINTS[0] };
  }
  let raw = 0;
  if (password.length >= 8) raw += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) raw += 1;
  if (/\d/.test(password)) raw += 1;
  if (/[^A-Za-z0-9]/.test(password)) raw += 1;
  if (password.length >= 16) raw += 1;
  const score = Math.min(raw, 4) as PasswordStrength;
  return { score, label: LABELS[score], hint: HINTS[score] };
}
