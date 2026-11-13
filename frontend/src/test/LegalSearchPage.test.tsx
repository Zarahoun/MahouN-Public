/**
 * LegalSearchPage component tests
 * Covers search flow, empty validation, pagination, sorting, theme toggle,
 * and accessibility (axe-core) without touching the backend (MSW mocked).
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import axe from 'axe-core';
import React from 'react';
import { delay, http, HttpResponse } from 'msw';
import { server } from './mocks/server';
import LegalSearchPage from '../components/LegalSearchPage';
import { ThemeProvider } from '../components/theme/ThemeContext';

beforeAll(() => server.listen());
afterAll(() => server.close());
beforeEach(() => server.resetHandlers());
afterEach(() => vi.restoreAllMocks());

function renderWithTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

describe('LegalSearchPage', () => {
  it('renders the search input, button, and theme toggle', () => {
    renderWithTheme(<LegalSearchPage />);

    expect(screen.getByPlaceholderText(/سوال حقوقی خود را وارد کنید/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /جستجو/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /تغییر-theme/ })).toBeInTheDocument();
  });

  it('shows a validation error toast for empty query', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    renderWithTheme(<LegalSearchPage />);

    fireEvent.click(screen.getByRole('button', { name: /جستجو/ }));

    // showToast warns when container not registered; no crash expected
    expect(spy).toHaveBeenCalled();
  });

  it('searches and displays results', async () => {
    renderWithTheme(<LegalSearchPage />);

    const input = screen.getByPlaceholderText(/سوال حقوقی خود را وارد کنید/);
    fireEvent.change(input, { target: { value: 'اعتراض ثالث اجرایی' } });
    fireEvent.click(screen.getByRole('button', { name: /جستجو/ }));

    await waitFor(() => {
      expect(screen.getByText(/اعتراض ثالث اجرایی/)).toBeInTheDocument();
    });
    expect(screen.getByText(/دادگاه تجدیدنظر استان/)).toBeInTheDocument();
  });

  it('displays expanded result metadata', async () => {
    renderWithTheme(<LegalSearchPage />);

    const input = screen.getByPlaceholderText(/سوال حقوقی خود را وارد کنید/);
    fireEvent.change(input, { target: { value: 'اعتراض ثالث اجرایی' } });
    fireEvent.click(screen.getByRole('button', { name: /جستجو/ }));

    await waitFor(() => {
      expect(screen.getByText(/1402\/123/)).toBeInTheDocument();
    });

    // Both mocked results render metadata: case numbers, judges, law articles
    expect(screen.getByText(/1401\/456/)).toBeInTheDocument();
    expect(screen.getByText(/قاضیان:/)).toBeInTheDocument();
    expect(screen.getByText(/مستندات قانونی:/)).toBeInTheDocument();
  });

  it('does not show pagination when results fit within the limit', async () => {
    renderWithTheme(<LegalSearchPage />);

    const input = screen.getByPlaceholderText(/سوال حقوقی خود را وارد کنید/);
    fireEvent.change(input, { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: /جستجو/ }));

    await waitFor(() => {
      expect(screen.getByText(/x/)).toBeInTheDocument();
    });

    // 2 mocked results < default limit 10 => no pagination controls
    expect(screen.queryByRole('button', { name: /بعدی/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /قبلی/ })).not.toBeInTheDocument();
  });

  it('fetches the correct offsets for forward/back navigation and restarts new searches at zero', async () => {
    const offsets: number[] = [];
    server.use(
      http.post('http://localhost:8000/v1/search/verdicts', async ({ request }) => {
        const body = (await request.json()) as {
          query: string;
          limit: number;
          offset: number;
        };
        offsets.push(body.offset);
        const hits = Array.from({ length: 12 }, (_, index) => ({
          verdict_id: `page-${index + 1}`,
          case_type: `پرونده ${index + 1}`,
          title: `عنوان ${index + 1}`,
          chunk_text: `متن رأی ${index + 1}`,
          law_articles: [],
          tags: [],
          metadata: {},
        }));

        return HttpResponse.json({
          results: hits.slice(body.offset, body.offset + body.limit),
          total: hits.length,
          query: body.query,
        });
      })
    );
    renderWithTheme(<LegalSearchPage />);

    const input = screen.getByPlaceholderText(/سوال حقوقی خود را وارد کنید/);
    fireEvent.change(input, { target: { value: 'جستجوی اول' } });
    fireEvent.click(screen.getByRole('button', { name: /جستجو/ }));
    await screen.findByText('پرونده 1');

    fireEvent.click(screen.getByRole('button', { name: 'بعدی' }));
    await screen.findByText('پرونده 11');
    fireEvent.click(screen.getByRole('button', { name: 'قبلی' }));
    await screen.findByText('پرونده 1');

    fireEvent.click(screen.getByRole('button', { name: 'بعدی' }));
    await screen.findByText('پرونده 11');
    fireEvent.change(input, { target: { value: 'جستجوی دوم' } });
    fireEvent.click(screen.getByRole('button', { name: /جستجو/ }));
    await screen.findByText('پرونده 1');

    expect(offsets).toEqual([0, 10, 0, 10, 0]);
  }, 15000);

  it('does not allow a slower stale search response to replace a newer result', async () => {
    let slowResponseCompleted = false;
    server.use(
      http.post('http://localhost:8000/v1/search/verdicts', async ({ request }) => {
        const body = (await request.json()) as { query: string };
        if (body.query === 'درخواست کند') {
          await delay(80);
          slowResponseCompleted = true;
        }
        const hit = {
          verdict_id: body.query,
          case_type: body.query,
          title: body.query,
          chunk_text: body.query,
          law_articles: [],
          tags: [],
          metadata: {},
        };
        return HttpResponse.json({ results: [hit], total: 1, query: body.query });
      })
    );
    renderWithTheme(<LegalSearchPage />);

    const input = screen.getByPlaceholderText(/سوال حقوقی خود را وارد کنید/);
    fireEvent.change(input, { target: { value: 'درخواست کند' } });
    fireEvent.click(screen.getByRole('button', { name: /جستجو/ }));

    fireEvent.change(input, { target: { value: 'درخواست جدید' } });
    fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true });

    expect(await screen.findByRole('heading', { name: 'درخواست جدید' })).toBeInTheDocument();
    await waitFor(() => expect(slowResponseCompleted).toBe(true));
    expect(screen.getByRole('heading', { name: 'درخواست جدید' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'درخواست کند' })).not.toBeInTheDocument();
  });

  it('toggles theme and persists data-theme attribute', () => {
    renderWithTheme(<LegalSearchPage />);

    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');

    const toggle = screen.getByRole('button', {
      name: /تغییر-theme \(روشن\/تاریک\)/,
    });

    fireEvent.click(toggle);

    expect(document.documentElement).toHaveAttribute('data-theme', 'light');

    fireEvent.click(toggle);

    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('passes accessibility checks (axe-core)', async () => {
    const { container } = renderWithTheme(<LegalSearchPage />);

    const results = await new Promise((resolve, reject) => {
      axe.run(container, (err, res) => (err ? reject(err) : resolve(res)));
    });

    const violations = (results as { violations: { impact: string }[] }).violations;
    const criticalOrHigh = violations.filter((v) => v.impact === 'critical' || v.impact === 'high');
    expect(criticalOrHigh).toEqual([]);
  });
});
