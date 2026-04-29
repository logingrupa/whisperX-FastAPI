import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../setup';
import { RegisterPage } from '@/routes/RegisterPage';
import { useAuthStore } from '@/lib/stores/authStore';

function renderAt() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <RegisterPage />
    </MemoryRouter>,
  );
}

describe('RegisterPage', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null });
  });

  it('renders email + password + confirm + terms checkbox', () => {
    renderAt();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).toBeInTheDocument();
  });

  it('rejects mismatched password + confirm', async () => {
    const user = userEvent.setup();
    renderAt();
    await user.type(screen.getByLabelText(/email/i), 'bob@example.com');
    await user.type(screen.getByLabelText('Password'), 'Password1!');
    await user.type(screen.getByLabelText(/confirm password/i), 'Different1!');
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it('blocks submit when terms not accepted', async () => {
    const user = userEvent.setup();
    renderAt();
    await user.type(screen.getByLabelText(/email/i), 'bob@example.com');
    await user.type(screen.getByLabelText('Password'), 'Password1!');
    await user.type(screen.getByLabelText(/confirm password/i), 'Password1!');
    await user.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByText(/accept the terms/i)).toBeInTheDocument();
    expect(useAuthStore.getState().user).toBe(null);
  });

  it('strength meter appears once password field has value', async () => {
    const user = userEvent.setup();
    renderAt();
    await user.type(screen.getByLabelText('Password'), 'Pass1!');
    expect(screen.getByTestId('password-strength-meter')).toBeInTheDocument();
  });

  it('happy-path register sets user state', async () => {
    const user = userEvent.setup();
    renderAt();
    await user.type(screen.getByLabelText(/email/i), 'bob@example.com');
    await user.type(screen.getByLabelText('Password'), 'Password1!');
    await user.type(screen.getByLabelText(/confirm password/i), 'Password1!');
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: /create account/i }));
    await waitFor(() => {
      expect(useAuthStore.getState().user?.email).toBe('bob@example.com');
    });
  });

  it('422 surfaces generic registration-failed error', async () => {
    server.use(
      http.post('/auth/register', () =>
        HttpResponse.json(
          { detail: 'Registration failed', code: 'REGISTRATION_FAILED' },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderAt();
    await user.type(screen.getByLabelText(/email/i), 'bob@example.com');
    await user.type(screen.getByLabelText('Password'), 'Password1!');
    await user.type(screen.getByLabelText(/confirm password/i), 'Password1!');
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByText(/registration failed\./i)).toBeInTheDocument();
  });
});
