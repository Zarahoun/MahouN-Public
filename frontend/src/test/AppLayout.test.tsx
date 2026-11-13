import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AppLayout from '../components/AppLayout';

const { logout } = vi.hoisted(() => ({ logout: vi.fn() }));

vi.mock('../store/authStore', () => ({
  useAuth: () => ({
    logout,
    user: { name: 'کاربر آزمایشی', email: 'user@example.com' },
  }),
}));

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/app/portal/search']}>
      <Routes>
        <Route path="/app/portal" element={<AppLayout />}>
          <Route path="search" element={<p>محتوای جستجو</p>} />
        </Route>
        <Route path="/login" element={<p>صفحه ورود</p>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('AppLayout', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the nested route and marks its navigation item as current', () => {
    renderLayout();

    expect(screen.getByText('محتوای جستجو')).toBeInTheDocument();
    const navigation = screen.getByRole('navigation', { name: 'پیمایش پورتال' });
    expect(within(navigation).getByRole('link', { name: /جستجوی حقوقی/ })).toHaveAttribute(
      'aria-current',
      'page'
    );
    expect(screen.getByText('کاربر آزمایشی')).toBeInTheDocument();
  }, 15000);

  it('offers a horizontally scrollable compact navigation for small screens', () => {
    renderLayout();

    const navigation = screen.getByRole('navigation', { name: 'پیمایش پورتال' });
    expect(navigation).toHaveClass('min-w-max');
    expect(navigation.parentElement).toHaveClass('overflow-x-auto');
  });

  it('logs out and navigates to the login page', () => {
    renderLayout();

    fireEvent.click(screen.getByRole('button', { name: 'خروج' }));

    expect(logout).toHaveBeenCalledOnce();
    expect(screen.getByText('صفحه ورود')).toBeInTheDocument();
  });
});
