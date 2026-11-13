import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MonitoringDashboard from '../components/MonitoringDashboard';

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../api/client', () => ({
  apiClient: { get, post },
}));

const realtimeMetrics = {
  timestamp: '2026-10-27T01:00:00Z',
  cpu_usage: 42.5,
  memory_usage: 61.2,
  disk_usage: 70.1,
  network_in: 1.2,
  network_out: 2.3,
  active_connections: 17,
  queries_per_second: 8.25,
  cache_hit_rate: 0.875,
};

const overview = {
  health_metrics: [
    {
      component: 'Neo4j',
      status: 'healthy',
      value: 12.5,
      unit: 'ms',
      threshold: 100,
    },
  ],
  alerts: [
    {
      id: 'alert-1',
      severity: 'warning',
      title: 'مصرف حافظه',
      message: 'مصرف حافظه از آستانه عبور کرده است.',
      timestamp: '2026-10-27T01:00:00Z',
      component: 'worker',
      acknowledged: false,
    },
  ],
  metrics: {
    total_queries_today: 240,
    avg_response_time: 0.125,
    error_rate: 0.02,
    active_users: 7,
  },
  system_info: {
    version: '1.2.0',
    uptime_hours: 28.5,
    environment: 'test',
  },
};

describe('MonitoringDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockImplementation((path: string) =>
      Promise.resolve(path.endsWith('/metrics/realtime') ? realtimeMetrics : overview)
    );
    post.mockResolvedValue(undefined);
  });

  it('renders the loading state before either initial request settles', async () => {
    let resolveOverview!: (value: typeof overview) => void;
    let resolveMetrics!: (value: typeof realtimeMetrics) => void;
    get.mockImplementation(
      (path: string) =>
        new Promise((resolve) => {
          if (path.endsWith('/metrics/realtime')) resolveMetrics = resolve;
          else resolveOverview = resolve;
        })
    );

    render(<MonitoringDashboard />);
    expect(screen.getByRole('heading', { name: 'مانیتورینگ' })).toBeInTheDocument();
    expect(
      screen.getByRole('status', { name: 'در حال بارگذاری داده‌های مانیتورینگ' })
    ).toBeInTheDocument();

    await act(async () => {
      resolveMetrics(realtimeMetrics);
      resolveOverview(overview);
    });
    expect(await screen.findByText('42.5%')).toBeInTheDocument();
    expect(screen.getByText('مصرف حافظه')).toBeInTheDocument();
  });

  it('renders measured values and health information from the API', async () => {
    render(<MonitoringDashboard />);

    expect(await screen.findByText('42.5%')).toBeInTheDocument();
    expect(screen.getByText('61.2%')).toBeInTheDocument();
    expect(screen.getByText('87.5%')).toBeInTheDocument();
    expect(screen.getByText('Neo4j')).toBeInTheDocument();
    expect(screen.getByText(/240|۲۴۰/)).toBeInTheDocument();
    expect(screen.getByText('1.2.0')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/api/v1/dashboard/studio/metrics/realtime');
    expect(get).toHaveBeenCalledWith('/api/v1/dashboard/studio/overview');
  });

  it('surfaces realtime failures while retaining independently loaded overview data', async () => {
    get.mockImplementation((path: string) =>
      path.endsWith('/metrics/realtime')
        ? Promise.reject(new Error('metrics offline'))
        : Promise.resolve(overview)
    );
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<MonitoringDashboard />);

    expect(await screen.findByRole('alert')).toHaveTextContent('metrics offline');
    expect(screen.getByText('Neo4j')).toBeInTheDocument();
    errorSpy.mockRestore();
  });

  it('retries the realtime endpoint when the refresh control is activated', async () => {
    render(<MonitoringDashboard />);
    await screen.findByText('42.5%');

    fireEvent.click(screen.getByRole('button', { name: 'به‌روزرسانی' }));

    await waitFor(() => {
      expect(get.mock.calls.filter(([path]) => path.endsWith('/metrics/realtime'))).toHaveLength(2);
    });
  });

  it('acknowledges an alert only after the backend request succeeds', async () => {
    let resolvePost!: () => void;
    post.mockReturnValue(
      new Promise<void>((resolve) => {
        resolvePost = resolve;
      })
    );
    render(<MonitoringDashboard />);

    const acknowledgeButton = await screen.findByRole('button', { name: 'تأیید' });
    fireEvent.click(acknowledgeButton);

    expect(post).toHaveBeenCalledWith('/api/v1/dashboard/studio/alerts/alert-1/acknowledge');
    expect(acknowledgeButton).toBeInTheDocument();

    resolvePost();
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'تأیید' })).not.toBeInTheDocument();
    });
  });
});
