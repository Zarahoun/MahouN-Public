import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LoginPage from '../components/auth/LoginPage';

const { login } = vi.hoisted(() => ({ login: vi.fn() }));

vi.mock('../store/authStore', () => ({ useAuth: () => ({ login }) }));

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/app/portal/dashboard" element={<p>داشبورد پورتال</p>} />
      </Routes>
    </MemoryRouter>
  );
}

function fillCredentials() {
  fireEvent.change(screen.getByRole('textbox', { name: 'نام کاربری یا ایمیل' }), {
    target: { value: 'lawyer@example.com' },
  });
  fireEvent.change(screen.getByLabelText('رمز عبور'), {
    target: { value: 'correct horse battery staple' },
  });
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('associates labels with inputs and preserves left-to-right credentials', () => {
    renderLogin();

    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'نام کاربری یا ایمیل' })).toHaveAttribute(
      'dir',
      'ltr'
    );
    expect(screen.getByLabelText('رمز عبور')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'ورود به سیستم' })).toBeEnabled();
  });

  it('routes to the portal only after successful authentication', async () => {
    login.mockResolvedValue(undefined);
    renderLogin();
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'ورود به سیستم' }));

    expect(await screen.findByText('داشبورد پورتال')).toBeInTheDocument();
    expect(login).toHaveBeenCalledExactlyOnceWith(
      'lawyer@example.com',
      'correct horse battery staple'
    );
  });

  it('prevents duplicate submissions while authentication is pending', async () => {
    let resolveLogin!: () => void;
    login.mockReturnValue(new Promise<void>((resolve) => (resolveLogin = resolve)));
    renderLogin();
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'ورود به سیستم' }));

    const pendingButton = screen.getByRole('button', { name: 'در حال ورود...' });
    expect(pendingButton).toBeDisabled();
    expect(login).toHaveBeenCalledTimes(1);

    await act(async () => resolveLogin());
    expect(await screen.findByText('داشبورد پورتال')).toBeInTheDocument();
  });

  it('shows authentication failures and allows a subsequent retry', async () => {
    login
      .mockRejectedValueOnce(new Error('اعتبارنامه نامعتبر است'))
      .mockResolvedValueOnce(undefined);
    renderLogin();
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: 'ورود به سیستم' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('اعتبارنامه نامعتبر است');
    expect(screen.getByRole('button', { name: 'ورود به سیستم' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'ورود به سیستم' }));
    expect(await screen.findByText('داشبورد پورتال')).toBeInTheDocument();
    expect(login).toHaveBeenCalledTimes(2);
  });
});
