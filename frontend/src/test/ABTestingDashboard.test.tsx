import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ABTestingDashboard from '../components/ABTestingDashboard';

const experiments = [
  {
    id: 'experiment-running',
    name: 'مقایسه مدل یک و دو',
    description: 'بررسی پاسخ‌گویی',
    status: 'running',
    variant_a: 'model-a',
    variant_b: 'model-b',
    traffic_split: 50,
    started_at: '2026-10-01T10:00:00Z',
    metrics: {
      impressions_a: 1250,
      impressions_b: 1200,
      conversions_a: 975,
      conversions_b: 900,
      conversion_rate_a: 0.78,
      conversion_rate_b: 0.75,
      statistical_significance: 0.95,
    },
  },
  {
    id: 'experiment-completed',
    name: 'مقایسه تکمیل‌شده',
    description: 'نتایج نهایی',
    status: 'completed',
    variant_a: 'model-c',
    variant_b: 'model-d',
    traffic_split: 50,
    started_at: '2026-09-01T10:00:00Z',
    ended_at: '2026-09-02T10:00:00Z',
    metrics: {
      impressions_a: 500,
      impressions_b: 500,
      conversions_a: 350,
      conversions_b: 400,
      conversion_rate_a: 0.7,
      conversion_rate_b: 0.8,
      statistical_significance: 0.97,
      winner: 'B',
    },
  },
];

function respond(body: unknown, ok = true, status = 200) {
  return Promise.resolve({
    ok,
    status,
    json: async () => body,
  });
}

describe('ABTestingDashboard', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => respond({ experiments }))
    );
  });

  it('shows a loading status until the API request resolves', async () => {
    let resolveRequest!: (response: Awaited<ReturnType<typeof respond>>) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Awaited<ReturnType<typeof respond>>>((resolve) => {
            resolveRequest = resolve;
          })
      )
    );

    render(<ABTestingDashboard />);
    expect(screen.getByRole('status', { name: 'در حال بارگذاری آزمایش‌ها' })).toBeInTheDocument();

    resolveRequest(await respond({ experiments }));
    expect(await screen.findByText('مقایسه مدل یک و دو')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('renders server-provided variants, computed rates, and winner data', async () => {
    render(<ABTestingDashboard />);

    expect(await screen.findByText('مقایسه مدل یک و دو')).toBeInTheDocument();
    expect(screen.getByText('model-a')).toBeInTheDocument();
    expect(screen.getByText('model-b')).toBeInTheDocument();
    expect(screen.getByText('برنده: B')).toBeInTheDocument();
    expect(screen.getByText('78.00%')).toBeInTheDocument();
    expect(screen.getByText(/95.0%/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('/api/v1/experiments');
  });

  it('filters visible experiments without changing summary totals', async () => {
    render(<ABTestingDashboard />);
    await screen.findByText('مقایسه مدل یک و دو');

    fireEvent.change(screen.getByRole('combobox', { name: 'فیلتر وضعیت:' }), {
      target: { value: 'running' },
    });

    expect(screen.getByText('مقایسه مدل یک و دو')).toBeInTheDocument();
    expect(screen.queryByText('مقایسه تکمیل‌شده')).not.toBeInTheDocument();
    expect(screen.getByText('کل آزمایش‌ها').nextElementSibling).toHaveTextContent('2');
  });

  it('surfaces HTTP failures instead of rendering them as empty data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => respond({ detail: 'service unavailable' }, false, 503))
    );

    render(<ABTestingDashboard />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to fetch experiments');
    expect(screen.queryByText('هیچ آزمایشی یافت نشد')).not.toBeInTheDocument();
  });

  it('surfaces network failures and provides a useful empty filter state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    const { unmount } = render(<ABTestingDashboard />);

    expect(await screen.findByRole('alert')).toHaveTextContent('offline');
    unmount();

    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => respond({ experiments: [] }))
    );
    render(<ABTestingDashboard />);
    expect(await screen.findByText('هیچ آزمایشی یافت نشد')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /آزمایش جدید/ })).not.toBeInTheDocument();
  });
});
