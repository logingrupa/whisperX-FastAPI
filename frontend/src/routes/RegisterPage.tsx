import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Form,
  FormField,
  FormItem,
  FormControl,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AuthCard } from '@/components/auth/AuthCard';
import { FormFieldRow } from '@/components/forms/FormField';
import { PasswordStrengthMeter } from '@/components/auth/PasswordStrengthMeter';
import { useAuthStore } from '@/lib/stores/authStore';
import { registerSchema, type RegisterInput } from '@/lib/schemas/auth';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';

/**
 * Register page (UI-03). Submit -> authStore.register -> navigate(?next ?? '/').
 *
 * Anti-enumeration: 422/4xx surfaces as a single generic "Registration failed."
 * Strength meter renders only once the password field has any value.
 *
 * /frontend-design: AuthCard + shadcn Form + DRY FormFieldRow + PasswordStrengthMeter.
 */
export function RegisterPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const register = useAuthStore((s) => s.register);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<RegisterInput>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      email: '',
      password: '',
      confirmPassword: '',
      termsAccepted: false,
    },
  });

  const passwordValue = form.watch('password') ?? '';

  const onSubmit = form.handleSubmit(async (values) => {
    setSubmitError(null);
    try {
      await register(values.email, values.password);
      const next = params.get('next');
      navigate(next || '/', { replace: true });
    } catch (err) {
      if (err instanceof RateLimitError) {
        setSubmitError(`Too many sign-ups. Try again in ${err.retryAfterSeconds}s.`);
        return;
      }
      if (err instanceof ApiClientError) {
        setSubmitError('Registration failed.');
        return;
      }
      setSubmitError('Registration failed. Please try again.');
    }
  });

  return (
    <AuthCard
      title="Create account"
      subtitle="Free trial starts when you create your first API key."
      footer={
        <span>
          Already have an account?{' '}
          <Link className="text-foreground underline" to="/login">
            Sign in
          </Link>
        </span>
      }
    >
      <Form {...form}>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <FormFieldRow
            control={form.control}
            name="email"
            label="Email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
          />
          <FormFieldRow
            control={form.control}
            name="password"
            label="Password"
            type="password"
            autoComplete="new-password"
            rightSlot={
              passwordValue.length > 0 ? (
                <PasswordStrengthMeter password={passwordValue} />
              ) : null
            }
          />
          <FormFieldRow
            control={form.control}
            name="confirmPassword"
            label="Confirm password"
            type="password"
            autoComplete="new-password"
          />
          <FormField
            control={form.control}
            name="termsAccepted"
            render={({ field }) => (
              <FormItem className="flex items-start gap-2 space-y-0">
                <FormControl>
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 rounded border-input"
                    checked={Boolean(field.value)}
                    onChange={(e) => field.onChange(e.target.checked)}
                  />
                </FormControl>
                <div className="space-y-1">
                  <FormLabel className="text-sm font-normal">
                    I accept the terms of service.
                  </FormLabel>
                  <FormMessage />
                </div>
              </FormItem>
            )}
          />
          {submitError !== null && (
            <Alert variant="destructive">
              <AlertDescription>{submitError}</AlertDescription>
            </Alert>
          )}
          <Button
            type="submit"
            disabled={form.formState.isSubmitting}
            className="mt-2"
          >
            {form.formState.isSubmitting ? 'Creating account…' : 'Create account'}
          </Button>
        </form>
      </Form>
    </AuthCard>
  );
}
