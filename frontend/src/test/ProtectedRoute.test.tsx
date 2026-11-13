import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';
import ProtectedRoute from '../components/auth/ProtectedRoute';
import { Permission, Role, useAuth } from '../store/authStore';
import type { User } from '../store/authStore';

const baseUser: User = {
  id: 'user-1',
  username: 'test-user',
  email: 'test@example.com',
  name: 'Test User',
  role: Role.ANALYST,
  permissions: [Permission.READ],
};

function renderProtectedRoute(
  user: User | null,
  routeOptions: {
    requiredPermissions?: Permission[];
    requiredRoles?: Role[];
  } = {}
) {
  useAuth.setState({ user, isAuthenticated: user !== null });

  return render(
    <MemoryRouter initialEntries={['/private']}>
      <Routes>
        <Route
          path="/private"
          element={
            <ProtectedRoute {...routeOptions}>
              <p>محتوای محافظت‌شده</p>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<p>صفحه ورود</p>} />
        <Route path="/" element={<p>دسترسی رد شد</p>} />
      </Routes>
    </MemoryRouter>
  );
}

afterEach(() => {
  useAuth.setState({ user: null, isAuthenticated: false });
});

describe('ProtectedRoute authorization', () => {
  it('redirects unauthenticated users to login without rendering protected content', () => {
    renderProtectedRoute(null);

    expect(screen.getByText('صفحه ورود')).toBeInTheDocument();
    expect(screen.queryByText('محتوای محافظت‌شده')).not.toBeInTheDocument();
  });

  it('requires every requested permission', () => {
    renderProtectedRoute(baseUser, {
      requiredPermissions: [Permission.READ, Permission.WRITE],
    });

    expect(screen.getByText('دسترسی رد شد')).toBeInTheDocument();
    expect(screen.queryByText('محتوای محافظت‌شده')).not.toBeInTheDocument();
  });

  it('allows a user whose role and permissions satisfy the route', () => {
    renderProtectedRoute(baseUser, {
      requiredPermissions: [Permission.READ],
      requiredRoles: [Role.ANALYST],
    });

    expect(screen.getByText('محتوای محافظت‌شده')).toBeInTheDocument();
  });

  it('applies the canonical admin role and permission overrides', () => {
    renderProtectedRoute(
      { ...baseUser, role: Role.ADMIN, permissions: [] },
      {
        requiredPermissions: [Permission.WRITE, Permission.DELETE],
        requiredRoles: [Role.ANALYST],
      }
    );

    expect(screen.getByText('محتوای محافظت‌شده')).toBeInTheDocument();
  });
});
