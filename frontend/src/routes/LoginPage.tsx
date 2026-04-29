import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Form } from '@/components/ui/form';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AuthCard } from '@/components/auth/AuthCard';
import { FormFieldRow } from '@/components/forms/FormField';
import { useAuthStore } from '@/lib/stores/authStore';
import { loginSchema, type LoginInput } from '@/lib/schemas/auth';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';

/**
 * Login page (UI-02). Submit -> authStore.login -> navigate(?next ?? '/').
 *
 * Anti-enumeration policy (T-14-12): one generic error string regardless of
 * backend code/detail. Never echo "user not found" vs "wrong password".
 *
 * /frontend-design: AuthCard + shadcn Form + DRY FormFieldRow.
 */
export function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const login = useAuthStore((s) => s.login);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setSubmitError(null);
    try {
      await login(values.email, values.password);
      const next = params.get('next');
      navigate(next || '/', { replace: true });
    } catch (err) {
      if (err instanceof RateLimitError) {
        setSubmitError(
          `Too many login attempts. Try again in ${err.retryAfterSeconds}s.`,
        );
        return;
      }
      if (err instanceof ApiClientError) {
        setSubmitError('Login failed. Check your credentials.');
        return;
      }
      setSubmitError('Login failed. Please try again.');
    }
  });

  return (
    <AuthCard
      title="Sign in"
      subtitle="Welcome back. Enter your credentials to continue."
      footer={
        <span>
          No account?{' '}
          <Link className="text-foreground underline" to="/register">
            Register
          </Link>
          {' · '}
          <a className="text-foreground underline" href="mailto:hey@logingrupa.lv">
            Forgot password?
          </a>
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
            autoComplete="current-password"
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
            {form.formState.isSubmitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </Form>
    </AuthCard>
  );
}
