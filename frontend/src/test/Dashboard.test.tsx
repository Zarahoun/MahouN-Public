import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Dashboard from '../../shared/components/Dashboard';

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>
  );
}

function jsonResponse(body: unknown, ok = true, status = 200) {
  return Promise.resolve({
    ok,
    status,
    json: async () => body,
  });
}

describe('Dashboard statistics', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => jsonResponse({ total_documents: 12, total_queries: 34 }))
    );
  });

  it('renders values returned by the health endpoint', async () => {
    renderDashboard();

    expect(await screen.findByText('12')).toBeInTheDocument();
    expect(screen.getByText('34')).toBeInTheDocument();
    expect(screen.getByText('مدارک آپلود شده')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/system/health');
  });

  it('does not present failed statistics requests as real zero values', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => jsonResponse({}, false, 503))
    );
    vi.spyOn(console, 'error').mockImplementation(() => {});
    renderDashboard();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'آمار داشبورد بارگذاری نشد و در دسترس نیست.'
    );
    expect(screen.getAllByText('—')).toHaveLength(4);
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('retries a failed statistics request and replaces unavailable values on success', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => jsonResponse({}, false, 503))
      .mockImplementationOnce(() => jsonResponse({ total_documents: 3, total_queries: 9 }));
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'error').mockImplementation(() => {});
    renderDashboard();
    await screen.findByRole('alert');

    fireEvent.click(screen.getByRole('button', { name: 'تلاش دوباره' }));

    expect(await screen.findByText('3')).toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  }, 15000);
});
