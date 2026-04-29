import { scorePassword, type PasswordStrength } from '@/lib/passwordStrength';
import { cn } from '@/lib/utils';

/**
 * Visual 4-bar password strength meter (UI-03).
 * Colors progress red -> amber -> lime -> green; reads zxcvbn-style score (0..4).
 *
 * SRP: pure rendering — math lives in scorePassword().
 */
export function PasswordStrengthMeter({ password }: { password: string }) {
  const { score, label, hint } = scorePassword(password);
  const segments: PasswordStrength[] = [1, 2, 3, 4];

  return (
    <div className="mt-2" data-testid="password-strength-meter" data-score={score}>
      <div className="flex gap-1" aria-hidden="true">
        {segments.map((seg) => (
          <div
            key={seg}
            className={cn(
              'h-1.5 flex-1 rounded-full transition-colors',
              score >= seg ? colorFor(score) : 'bg-muted',
            )}
          />
        ))}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{label}.</span> {hint}
      </p>
    </div>
  );
}

function colorFor(score: PasswordStrength): string {
  if (score === 1) return 'bg-red-500';
  if (score === 2) return 'bg-amber-500';
  if (score === 3) return 'bg-lime-500';
  return 'bg-green-500';
}
