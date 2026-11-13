import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  ArrowDownWideNarrow,
  ArrowUpWideNarrow,
  Check,
  Clock3,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useAuth } from '../store/authStore';
import {
  acknowledgeAlert,
  getAlert,
  getAlerts,
  getAlertStatistics,
  resolveAlert,
  type AlertRecord,
  type AlertSeverity,
  type AlertStatus,
} from '../api/alerting';

const severityStyle: Record<AlertSeverity, string> = {
  CRITICAL: 'border-rose-500/40 bg-rose-500/10 text-rose-300',
  ERROR: 'border-orange-500/40 bg-orange-500/10 text-orange-300',
  WARNING: 'border-amber-500/40 bg-amber-500/10 text-amber-200',
  INFO: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-200',
};
const statusLabel: Record<AlertStatus, string> = {
  active: 'فعال',
  acknowledged: 'پذیرفته‌شده',
  resolved: 'رفع‌شده',
  suppressed: 'بی‌صداشده',
};
const statusStyle: Record<AlertStatus, string> = {
  active: 'text-rose-300',
  acknowledged: 'text-teal-300',
  resolved: 'text-emerald-300',
  suppressed: 'text-slate-400',
};
const severityLabel: Record<AlertSeverity, string> = {
  CRITICAL: 'بحرانی',
  ERROR: 'خطا',
  WARNING: 'هشدار',
  INFO: 'اطلاع',
};
const inputClass =
  'w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20';

function formatDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('fa-IR');
}

function formatDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return '—';
  if (seconds < 60) return `${Math.round(seconds)} ثانیه`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} دقیقه`;
  return `${(seconds / 3600).toFixed(1)} ساعت`;
}

function StatTile({ label, value, tone }: { label: string; value: string | number; tone: string }) {
  return (
    <div
      className="border-r-2 border-slate-700 bg-slate-900/70 px-4 py-3 first:border-r-2"
      style={{ borderRightColor: tone }}
    >
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-100">{value}</p>
    </div>
  );
}

function MetricBreakdown({ title, items }: { title: string; items: Array<[string, number]> }) {
  return (
    <div className="min-h-36 border border-slate-800 bg-slate-900/50 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">{title}</h2>
      {items.length ? (
        <ul className="space-y-2">
          {items.slice(0, 5).map(([label, value]) => (
            <li key={label} className="flex items-center justify-between gap-3 text-xs">
              <span className="truncate text-slate-400" title={label}>
                {label}
              </span>
              <span className="tabular-nums text-slate-100">{value}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="py-3 text-xs text-slate-500">داده‌ای در این بازه ثبت نشده</p>
      )}
    </div>
  );
}

export default function AlertManagementPage() {
  const queryClient = useQueryClient();
  const currentUser = useAuth((state) => state.user);
  const actor = currentUser?.username ?? '';
  const [severity, setSeverity] = useState<AlertSeverity | ''>('');
  const [status, setStatus] = useState<AlertStatus | ''>('');
  const [category, setCategory] = useState('');
  const [hours, setHours] = useState(24);
  const [sortBy, setSortBy] = useState<'triggered_at' | 'severity' | 'status'>('triggered_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notes, setNotes] = useState('');
  const [incidentId, setIncidentId] = useState('');
  const [suppressNotifications, setSuppressNotifications] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!selectedId) return;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSelectedId(null);
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('keydown', closeOnEscape);
      previouslyFocused?.focus();
    };
  }, [selectedId]);

  const listQuery = useQuery({
    queryKey: [
      'monitoring',
      'alerts',
      { severity, status, category, hours, sortBy, sortOrder, limit, offset },
    ],
    queryFn: () =>
      getAlerts({
        severity,
        status,
        category,
        hours,
        sort_by: sortBy,
        sort_order: sortOrder,
        limit,
        offset,
      }),
    refetchInterval: 30_000,
  });
  const statsQuery = useQuery({
    queryKey: ['monitoring', 'alerts', 'stats', hours],
    queryFn: () => getAlertStatistics(hours),
    refetchInterval: 30_000,
  });
  const detailQuery = useQuery({
    queryKey: ['monitoring', 'alerts', 'detail', selectedId],
    queryFn: () => getAlert(selectedId as string),
    enabled: Boolean(selectedId),
  });
  const invalidate = async () => {
    await Promise.all([queryClient.invalidateQueries({ queryKey: ['monitoring', 'alerts'] })]);
    if (selectedId)
      await queryClient.invalidateQueries({
        queryKey: ['monitoring', 'alerts', 'detail', selectedId],
      });
  };
  const acknowledgeMutation = useMutation({
    mutationFn: (input: { alert: AlertRecord; actor: string; notes: string; suppress: boolean }) =>
      acknowledgeAlert(input.alert.alert_id, {
        acknowledged_by: input.actor,
        notes: input.notes || undefined,
        suppress_notifications: input.suppress,
      }),
    onSuccess: invalidate,
  });
  const resolveMutation = useMutation({
    mutationFn: (input: { alert: AlertRecord; actor: string; notes: string; incidentId: string }) =>
      resolveAlert(input.alert.alert_id, {
        resolved_by: input.actor,
        resolution_notes: input.notes,
        incident_id: input.incidentId || undefined,
      }),
    onSuccess: invalidate,
  });

  const alerts = listQuery.data?.alerts ?? [];
  const detail = detailQuery.data;
  const stats = statsQuery.data;
  const isActionPending = acknowledgeMutation.isPending || resolveMutation.isPending;
  const queryError = listQuery.error ?? statsQuery.error;
  const bySeverity = stats?.by_severity ?? {};
  const categories = Object.keys(stats?.by_category ?? {}).sort();
  const totalSeverity = Object.values(bySeverity).reduce((sum, count) => sum + count, 0);
  const severityRows = useMemo(
    () =>
      [
        ['CRITICAL', severityLabel.CRITICAL, 'bg-rose-400'],
        ['ERROR', severityLabel.ERROR, 'bg-orange-400'],
        ['WARNING', severityLabel.WARNING, 'bg-amber-300'],
        ['INFO', severityLabel.INFO, 'bg-cyan-300'],
      ] as const,
    []
  );
  const refresh = () => {
    void Promise.all([listQuery.refetch(), statsQuery.refetch()]);
  };
  const openDetail = (alert: AlertRecord) => {
    setSelectedId(alert.alert_id);
    setNotes('');
    setIncidentId('');
    setActionError(null);
    setSuppressNotifications(false);
  };
  const runAction = async (kind: 'acknowledge' | 'resolve') => {
    if (!detail || !actor.trim() || (kind === 'resolve' && !notes.trim())) return;
    setActionError(null);
    try {
      if (kind === 'acknowledge')
        await acknowledgeMutation.mutateAsync({
          alert: detail,
          actor: actor.trim(),
          notes: notes.trim(),
          suppress: suppressNotifications,
        });
      else
        await resolveMutation.mutateAsync({
          alert: detail,
          actor: actor.trim(),
          notes: notes.trim(),
          incidentId: incidentId.trim(),
        });
      setActionError(null);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : 'عملیات انجام نشد. دوباره تلاش کنید.'
      );
    }
  };

  return (
    <div dir="rtl" className="min-h-full bg-[#080d17] px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1500px]">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-5">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-medium tracking-[0.18em] text-teal-300">
              <Activity size={14} /> عملیات پایش
            </div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">مرکز مدیریت هشدارها</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              بررسی رخدادها، ثبت پذیرش و مستندسازی رفع مشکل بر پایه دادهٔ زندهٔ سامانه.
            </p>
          </div>
          <button
            type="button"
            onClick={refresh}
            disabled={listQuery.isFetching || statsQuery.isFetching}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-teal-500/60 hover:bg-slate-800 disabled:cursor-wait disabled:opacity-50"
          >
            <RefreshCw
              size={15}
              className={listQuery.isFetching || statsQuery.isFetching ? 'animate-spin' : ''}
            />{' '}
            به‌روزرسانی
          </button>
        </header>

        {queryError && (
          <div
            role="alert"
            className="mb-5 flex flex-wrap items-center justify-between gap-3 border border-rose-500/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-200"
          >
            <span>دریافت داده‌های هشدار ناموفق بود: {queryError.message}</span>
            <button onClick={refresh} className="font-semibold underline underline-offset-4">
              تلاش دوباره
            </button>
          </div>
        )}

        <section
          aria-label="خلاصه آمار هشدارها"
          className="mb-6 grid grid-cols-2 overflow-hidden border border-slate-800 bg-slate-900/40 sm:grid-cols-4"
        >
          <StatTile
            label={`کل هشدارها · ${hours} ساعت`}
            value={stats?.total_triggered ?? '—'}
            tone="#38bdf8"
          />
          <StatTile label="فعال" value={stats?.by_status.active ?? '—'} tone="#fb7185" />
          <StatTile label="پذیرفته‌شده" value={stats?.total_acknowledged ?? '—'} tone="#2dd4bf" />
          <StatTile label="رفع‌شده" value={stats?.total_resolved ?? '—'} tone="#34d399" />
        </section>

        <section className="mb-6 grid gap-4 lg:grid-cols-[1.1fr_1fr]">
          <div className="border border-slate-800 bg-slate-900/50 p-4 sm:p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold">توزیع شدت · {hours} ساعت</h2>
              <span className="text-xs text-slate-500">
                {stats?.time_window_hours ?? hours} ساعت اخیر
              </span>
            </div>
            <div className="space-y-3">
              {severityRows.map(([key, label, color]) => {
                const count = bySeverity[key] ?? 0;
                const width = totalSeverity ? (count / totalSeverity) * 100 : 0;
                return (
                  <div
                    key={key}
                    className="grid grid-cols-[70px_1fr_36px] items-center gap-3 text-xs"
                  >
                    <span className="text-slate-400">{label}</span>
                    <div className="h-2 overflow-hidden bg-slate-800">
                      <div
                        className={`h-full ${color} transition-[width] duration-500`}
                        style={{ width: `${width}%` }}
                      />
                    </div>
                    <span className="text-left tabular-nums text-slate-300">{count}</span>
                  </div>
                );
              })}
              {!stats && statsQuery.isLoading && (
                <div className="h-20 animate-pulse bg-slate-800/50" />
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-px border border-slate-800 bg-slate-800">
            <div className="bg-slate-900/70 p-4 sm:p-5">
              <p className="text-xs text-slate-400">روند در مقایسه با بازهٔ قبل</p>
              <div className="mt-3 flex items-center gap-2">
                <span className="text-xl font-semibold">
                  {stats?.trend_direction === 'increasing'
                    ? 'افزایشی'
                    : stats?.trend_direction === 'decreasing'
                      ? 'کاهشی'
                      : stats
                        ? 'پایدار'
                        : '—'}
                </span>
                <span
                  className={`text-sm tabular-nums ${(stats?.trend_percentage ?? 0) > 0 ? 'text-rose-300' : 'text-teal-300'}`}
                >
                  {stats
                    ? `${stats.trend_percentage > 0 ? '+' : ''}${stats.trend_percentage}%`
                    : ''}
                </span>
              </div>
            </div>
            <div className="bg-slate-900/70 p-4 sm:p-5">
              <p className="text-xs text-slate-400">میانگین زمان پذیرش</p>
              <p className="mt-3 text-xl font-semibold">
                {stats ? formatDuration(stats.avg_acknowledgement_time_seconds) : '—'}
              </p>
            </div>
            <div className="bg-slate-900/70 p-4 sm:p-5">
              <p className="text-xs text-slate-400">میانگین زمان رفع</p>
              <p className="mt-3 text-xl font-semibold">
                {stats ? formatDuration(stats.avg_resolution_time_seconds) : '—'}
              </p>
            </div>
            <div className="bg-slate-900/70 p-4 sm:p-5">
              <p className="text-xs text-slate-400">آخرین محاسبه</p>
              <p className="mt-3 text-sm font-medium">
                {stats ? formatDate(stats.timestamp) : '—'}
              </p>
            </div>
          </div>
        </section>

        <section
          aria-label="جزئیات آماری"
          className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4"
        >
          <MetricBreakdown
            title="بر اساس دسته"
            items={Object.entries(stats?.by_category ?? {}).sort(
              (left, right) => right[1] - left[1]
            )}
          />
          <MetricBreakdown
            title="بر اساس کانال اعلان"
            items={Object.entries(stats?.by_channel ?? {}).sort(
              (left, right) => right[1] - left[1]
            )}
          />
          <MetricBreakdown
            title="پرتکرارترین هشدارها"
            items={(stats?.top_alert_names ?? []).map(({ name, count }) => [name, count])}
          />
          <MetricBreakdown
            title="نمونه‌های پرتکرار"
            items={(stats?.top_instances ?? []).map(({ instance, count }) => [instance, count])}
          />
        </section>

        <section className="border border-slate-800 bg-slate-900/40">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-4 sm:px-5">
            <div>
              <h2 className="font-semibold">فهرست هشدارها</h2>
              <p className="mt-1 text-xs text-slate-500">
                {listQuery.data ? `${listQuery.data.total} مورد مطابق فیلترها` : 'دریافت از سامانه'}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="sr-only" htmlFor="alert-severity">
                شدت هشدار
              </label>
              <select
                id="alert-severity"
                value={severity}
                onChange={(event) => {
                  setSeverity(event.target.value as AlertSeverity | '');
                  setOffset(0);
                }}
                className={inputClass + ' w-auto'}
              >
                <option value="">همه شدت‌ها</option>
                <option value="CRITICAL">بحرانی</option>
                <option value="ERROR">خطا</option>
                <option value="WARNING">هشدار</option>
                <option value="INFO">اطلاع</option>
              </select>
              <label className="sr-only" htmlFor="alert-status">
                وضعیت
              </label>
              <select
                id="alert-status"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value as AlertStatus | '');
                  setOffset(0);
                }}
                className={inputClass + ' w-auto'}
              >
                <option value="">همه وضعیت‌ها</option>
                <option value="active">فعال</option>
                <option value="acknowledged">پذیرفته‌شده</option>
                <option value="resolved">رفع‌شده</option>
                <option value="suppressed">بی‌صداشده</option>
              </select>
              <label className="sr-only" htmlFor="alert-category">
                دسته
              </label>
              <select
                id="alert-category"
                value={category}
                onChange={(event) => {
                  setCategory(event.target.value);
                  setOffset(0);
                }}
                className={inputClass + ' w-auto'}
              >
                <option value="">همه دسته‌ها</option>
                {categories.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <label className="sr-only" htmlFor="alert-hours">
                بازه زمانی
              </label>
              <select
                id="alert-hours"
                value={hours}
                onChange={(event) => {
                  setHours(Number(event.target.value));
                  setOffset(0);
                }}
                className={inputClass + ' w-auto'}
              >
                <option value={1}>۱ ساعت</option>
                <option value={6}>۶ ساعت</option>
                <option value={24}>۲۴ ساعت</option>
                <option value={168}>۷ روز</option>
                <option value={720}>۳۰ روز</option>
              </select>
              <label className="sr-only" htmlFor="alert-sort">
                مرتب‌سازی بر اساس
              </label>
              <select
                id="alert-sort"
                value={sortBy}
                onChange={(event) => setSortBy(event.target.value as typeof sortBy)}
                className={inputClass + ' w-auto'}
              >
                <option value="triggered_at">زمان ایجاد</option>
                <option value="severity">شدت</option>
                <option value="status">وضعیت</option>
              </select>
              <button
                type="button"
                aria-label={sortOrder === 'desc' ? 'نزولی' : 'صعودی'}
                onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
                className="rounded-lg border border-slate-700 p-2 text-slate-300 hover:border-teal-500/60 hover:text-white"
              >
                {sortOrder === 'desc' ? (
                  <ArrowDownWideNarrow size={17} />
                ) : (
                  <ArrowUpWideNarrow size={17} />
                )}
              </button>
            </div>
          </div>
          {listQuery.isLoading ? (
            <div className="space-y-2 p-4" aria-label="در حال بارگذاری">
              {[0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="h-20 animate-pulse border border-slate-800 bg-slate-800/40"
                />
              ))}
            </div>
          ) : alerts.length === 0 ? (
            <div className="px-4 py-14 text-center">
              <Search className="mx-auto mb-3 text-slate-600" size={26} />
              <p className="font-medium text-slate-300">هشداری برای نمایش وجود ندارد</p>
              <p className="mt-1 text-sm text-slate-500">
                فیلترها را تغییر دهید یا بعداً دوباره بررسی کنید.
              </p>
            </div>
          ) : (
            <>
              <div className="hidden grid-cols-[minmax(220px,2fr)_110px_110px_minmax(160px,1.4fr)_130px] gap-4 border-b border-slate-800 px-5 py-2 text-[11px] font-medium text-slate-500 lg:grid">
                <span>هشدار</span>
                <span>شدت</span>
                <span>وضعیت</span>
                <span>منبع / نمونه</span>
                <span>زمان ایجاد</span>
              </div>
              <div className="divide-y divide-slate-800/80">
                {alerts.map((alert) => (
                  <button
                    type="button"
                    key={alert.alert_id}
                    onClick={() => openDetail(alert)}
                    className="grid w-full gap-3 px-4 py-4 text-right transition hover:bg-slate-800/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500 lg:grid-cols-[minmax(220px,2fr)_110px_110px_minmax(160px,1.4fr)_130px] lg:items-center lg:gap-4 lg:px-5"
                  >
                    <span className="min-w-0">
                      <span className="flex items-start gap-2">
                        <AlertTriangle
                          size={16}
                          className={`mt-0.5 shrink-0 ${alert.severity === 'CRITICAL' ? 'text-rose-300' : 'text-amber-300'}`}
                        />
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-slate-100">
                            {alert.alert_name}
                          </span>
                          <span className="mt-1 block line-clamp-2 text-xs leading-5 text-slate-400">
                            {alert.message}
                          </span>
                        </span>
                      </span>
                    </span>
                    <span>
                      <span
                        className={`inline-flex rounded border px-2 py-1 text-xs ${severityStyle[alert.severity]}`}
                      >
                        {severityLabel[alert.severity]}
                      </span>
                    </span>
                    <span className={`text-sm ${statusStyle[alert.status]}`}>
                      {statusLabel[alert.status]}
                    </span>
                    <span className="text-xs text-slate-400">
                      {alert.metadata.source}
                      {alert.metadata.instance ? ` · ${alert.metadata.instance}` : ''}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-slate-400">
                      <Clock3 size={13} />
                      {formatDate(alert.triggered_at)}
                    </span>
                  </button>
                ))}
              </div>
              <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 px-4 py-3 text-sm text-slate-400 sm:px-5">
                <span>
                  نمایش {listQuery.data?.total ? offset + 1 : 0} تا{' '}
                  {Math.min(offset + (listQuery.data?.returned ?? 0), listQuery.data?.total ?? 0)}{' '}
                  از {listQuery.data?.total ?? 0}
                </span>
                <div className="flex items-center gap-2">
                  <label htmlFor="alert-page-size" className="text-xs">
                    تعداد در صفحه
                  </label>
                  <select
                    id="alert-page-size"
                    value={limit}
                    onChange={(event) => {
                      setLimit(Number(event.target.value));
                      setOffset(0);
                    }}
                    className={inputClass + ' w-auto py-1.5'}
                  >
                    <option value={10}>۱۰</option>
                    <option value={25}>۲۵</option>
                    <option value={50}>۵۰</option>
                    <option value={100}>۱۰۰</option>
                  </select>
                  <button
                    type="button"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - limit))}
                    className="rounded border border-slate-700 px-3 py-1.5 hover:bg-slate-800 disabled:opacity-40"
                  >
                    قبلی
                  </button>
                  <button
                    type="button"
                    disabled={offset + limit >= (listQuery.data?.total ?? 0)}
                    onClick={() => setOffset(offset + limit)}
                    className="rounded border border-slate-700 px-3 py-1.5 hover:bg-slate-800 disabled:opacity-40"
                  >
                    بعدی
                  </button>
                </div>
              </footer>
            </>
          )}
        </section>
      </div>

      {selectedId && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/70"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedId(null);
          }}
        >
          <aside
            role="dialog"
            aria-modal="true"
            aria-labelledby="alert-detail-title"
            onKeyDown={(event) => {
              if (event.key !== 'Tab') return;
              const focusable = Array.from(
                event.currentTarget.querySelectorAll<HTMLElement>(
                  'button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
                )
              );
              if (!focusable.length) {
                event.preventDefault();
                return;
              }
              const first = focusable[0];
              const last = focusable[focusable.length - 1];
              if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
              } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
              }
            }}
            className="flex h-full w-full max-w-2xl flex-col overflow-y-auto border-r border-slate-700 bg-[#0b1220] shadow-2xl"
          >
            <header className="sticky top-0 z-10 flex items-start justify-between border-b border-slate-800 bg-[#0b1220]/95 px-5 py-4 backdrop-blur">
              <div>
                <p className="text-xs text-teal-300">جزئیات رخداد</p>
                <h2 id="alert-detail-title" className="mt-1 text-lg font-semibold">
                  {detail?.alert_name ?? 'در حال دریافت…'}
                </h2>
              </div>
              <button
                ref={closeButtonRef}
                onClick={() => setSelectedId(null)}
                aria-label="بستن"
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X size={18} />
              </button>
            </header>
            {detailQuery.isLoading ? (
              <div className="m-5 h-48 animate-pulse bg-slate-800/50" />
            ) : detailQuery.error ? (
              <div role="alert" className="m-5 border border-rose-500/30 p-4 text-sm text-rose-200">
                دریافت جزئیات ناموفق بود: {detailQuery.error.message}
              </div>
            ) : (
              detail && (
                <div className="space-y-6 p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded border px-2 py-1 text-xs ${severityStyle[detail.severity]}`}
                    >
                      {severityLabel[detail.severity]}
                    </span>
                    <span className={`text-sm ${statusStyle[detail.status]}`}>
                      {statusLabel[detail.status]}
                    </span>
                    <span className="mr-auto font-mono text-[11px] text-slate-500">
                      {detail.alert_id}
                    </span>
                  </div>
                  <p className="border-r-2 border-amber-400 px-3 text-sm leading-7 text-slate-200">
                    {detail.message}
                  </p>
                  <section>
                    <h3 className="mb-3 text-sm font-semibold text-slate-300">چرخهٔ عمر</h3>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        ['ایجاد', detail.triggered_at],
                        ['آخرین تغییر', detail.updated_at],
                        ['پذیرش', detail.acknowledged_at],
                        ['رفع', detail.resolved_at],
                      ].map(([label, date]) => (
                        <div key={label} className="border border-slate-800 bg-slate-900/60 p-3">
                          <p className="text-xs text-slate-500">{label}</p>
                          <p className="mt-1 text-xs text-slate-200">{formatDate(date)}</p>
                        </div>
                      ))}
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                      <p className="text-slate-400">
                        پذیرفته‌شده توسط:{' '}
                        <span className="text-slate-200">{detail.acknowledged_by ?? '—'}</span>
                      </p>
                      <p className="text-slate-400">
                        رفع‌شده توسط:{' '}
                        <span className="text-slate-200">{detail.resolved_by ?? '—'}</span>
                      </p>
                    </div>
                  </section>
                  <section>
                    <h3 className="mb-3 text-sm font-semibold text-slate-300">زمینه و اعلان</h3>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-3 border border-slate-800 bg-slate-900/40 p-4 text-xs">
                      <span className="text-slate-500">منبع</span>
                      <span>{detail.metadata.source}</span>
                      <span className="text-slate-500">دسته</span>
                      <span>{detail.metadata.category}</span>
                      <span className="text-slate-500">نمونه</span>
                      <span>{detail.metadata.instance ?? '—'}</span>
                      <span className="text-slate-500">منطقه</span>
                      <span>{detail.metadata.region ?? '—'}</span>
                      <span className="text-slate-500">کانال‌ها</span>
                      <span>{detail.channels.length ? detail.channels.join('، ') : '—'}</span>
                      <span className="text-slate-500">تعداد اعلان</span>
                      <span>{detail.notification_count}</span>
                      <span className="text-slate-500">آخرین اعلان</span>
                      <span>{formatDate(detail.last_notification_at)}</span>
                      <span className="text-slate-500">شناسه رخداد</span>
                      <span>{detail.incident_id ?? '—'}</span>
                    </div>
                  </section>
                  {Object.keys(detail.metadata.labels).length > 0 && (
                    <section>
                      <h3 className="mb-2 text-sm font-semibold text-slate-300">برچسب‌ها</h3>
                      <dl className="grid grid-cols-2 gap-2 border border-slate-800 bg-slate-900/40 p-3 text-xs">
                        {Object.entries(detail.metadata.labels).map(([key, value]) => (
                          <div key={key} className="contents">
                            <dt className="text-slate-500">{key}</dt>
                            <dd className="break-all text-slate-200">{value}</dd>
                          </div>
                        ))}
                      </dl>
                    </section>
                  )}
                  {Object.keys(detail.metadata.annotations).length > 0 && (
                    <section>
                      <h3 className="mb-2 text-sm font-semibold text-slate-300">توضیحات فراداده</h3>
                      <dl className="grid grid-cols-2 gap-2 border border-slate-800 bg-slate-900/40 p-3 text-xs">
                        {Object.entries(detail.metadata.annotations).map(([key, value]) => (
                          <div key={key} className="contents">
                            <dt className="text-slate-500">{key}</dt>
                            <dd className="break-all text-slate-200">{value}</dd>
                          </div>
                        ))}
                      </dl>
                    </section>
                  )}
                  {detail.related_alerts.length > 0 && (
                    <section>
                      <h3 className="mb-2 text-sm font-semibold text-slate-300">هشدارهای مرتبط</h3>
                      <div className="flex flex-wrap gap-2">
                        {detail.related_alerts.map((alertId) => (
                          <button
                            key={alertId}
                            type="button"
                            onClick={() => setSelectedId(alertId)}
                            className="rounded border border-slate-700 px-2 py-1 font-mono text-xs text-teal-300 hover:border-teal-500"
                          >
                            {alertId}
                          </button>
                        ))}
                      </div>
                    </section>
                  )}
                  {detail.suggested_actions.length > 0 && (
                    <section>
                      <h3 className="mb-2 text-sm font-semibold text-slate-300">
                        اقدام‌های پیشنهادی
                      </h3>
                      <ul className="space-y-2">
                        {detail.suggested_actions.map((action, index) => (
                          <li
                            key={`${index}-${action}`}
                            className="flex gap-2 text-sm text-slate-300"
                          >
                            <Check size={15} className="mt-0.5 shrink-0 text-teal-300" />
                            {action}
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {detail.runbook_url && (
                    <a
                      href={detail.runbook_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex text-sm text-teal-300 underline underline-offset-4"
                    >
                      باز کردن راهنمای عملیات
                    </a>
                  )}
                  {detail.status !== 'resolved' && (
                    <section className="border-t border-slate-800 pt-5">
                      <div className="mb-3 flex items-center gap-2">
                        <ShieldCheck className="text-teal-300" size={17} />
                        <h3 className="text-sm font-semibold">ثبت اقدام اپراتور</h3>
                      </div>
                      <div className="space-y-3">
                        <p className="text-xs text-slate-400">
                          اپراتور:{' '}
                          <span className="text-slate-200">
                            {actor || 'حساب کاربری شناسایی نشد'}
                          </span>
                        </p>
                        <label className="block text-xs text-slate-400">
                          یادداشت
                          <textarea
                            className={inputClass + ' mt-1.5 min-h-20 resize-y'}
                            value={notes}
                            onChange={(event) => setNotes(event.target.value)}
                            placeholder={
                              detail.status === 'active'
                                ? 'یادداشت پذیرش (اختیاری)؛ برای رفع، شرح الزامی است'
                                : 'شرح اقدام و علت ریشه‌ای برای رفع'
                            }
                          />
                        </label>
                        {detail.status === 'active' && (
                          <label className="flex items-center gap-2 text-xs text-slate-400">
                            <input
                              type="checkbox"
                              checked={suppressNotifications}
                              onChange={(event) => setSuppressNotifications(event.target.checked)}
                              className="accent-teal-500"
                            />
                            توقف موقت اعلان‌های بعدی
                          </label>
                        )}
                        <label className="block text-xs text-slate-400">
                          شناسه رخداد مرتبط · اختیاری
                          <input
                            className={inputClass + ' mt-1.5'}
                            value={incidentId}
                            onChange={(event) => setIncidentId(event.target.value)}
                            placeholder="INC-…"
                          />
                        </label>
                      </div>
                      {actionError && (
                        <p role="alert" className="mt-3 text-sm text-rose-300">
                          {actionError}
                        </p>
                      )}
                      <div className="mt-4 flex flex-wrap gap-2">
                        {detail.status === 'active' && (
                          <button
                            type="button"
                            disabled={!actor.trim() || isActionPending}
                            onClick={() => void runAction('acknowledge')}
                            className="rounded-lg border border-teal-500/40 bg-teal-500/10 px-4 py-2 text-sm font-medium text-teal-200 hover:bg-teal-500/20 disabled:opacity-40"
                          >
                            {acknowledgeMutation.isPending ? 'در حال ثبت…' : 'پذیرش هشدار'}
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={!actor.trim() || !notes.trim() || isActionPending}
                          onClick={() => void runAction('resolve')}
                          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {resolveMutation.isPending ? 'در حال ثبت رفع…' : 'ثبت رفع مشکل'}
                        </button>
                      </div>
                    </section>
                  )}
                </div>
              )
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
