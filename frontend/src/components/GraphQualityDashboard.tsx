/**
 * Graph Quality & Semantic Extraction Monitoring Dashboard
 * Enterprise-grade observability for Knowledge Graph extraction,
 * circuit breaker states, anomaly detection, and A/B benchmarking.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Zap,
  AlertTriangle,
  RefreshCw,
  Layers,
  CheckCircle2,
  Clock,
  Sparkles,
  GitCompare,
  TrendingUp,
  AlertOctagon,
  Cpu,
} from 'lucide-react';
import {
  getQualityHealth,
  getExtractors,
  getGraphTopologyMetrics,
  getGraphIntegrityIssues,
  resetCircuitBreaker,
  compareExtractors,
  QualityHealth,
  ExtractorMetrics,
  GraphTopologyMetrics,
  GraphIntegrityIssue,
  ABCompareResponse,
} from '../api/quality';

export default function GraphQualityDashboard() {
  const [activeTab, setActiveTab] = useState<'extractors' | 'topology' | 'ab_test'>('extractors');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Data states
  const [health, setHealth] = useState<QualityHealth | null>(null);
  const [extractors, setExtractors] = useState<ExtractorMetrics[]>([]);
  const [topology, setTopology] = useState<GraphTopologyMetrics | null>(null);
  const [integrityIssues, setIntegrityIssues] = useState<GraphIntegrityIssue[]>([]);

  // A/B Test States
  const [extractorA, setExtractorA] = useState<string>('');
  const [extractorB, setExtractorB] = useState<string>('');
  const [abMetric, setAbMetric] = useState<string>('confidence');
  const [abLoading, setAbLoading] = useState(false);
  const [abResult, setAbResult] = useState<ABCompareResponse | null>(null);

  // Auto-refresh interval
  const [autoRefresh, setAutoRefresh] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(
    async (isSilent = false) => {
      if (!isSilent) setRefreshing(true);
      try {
        const [healthRes, extractorsRes, topologyRes, integrityRes] = await Promise.allSettled([
          getQualityHealth(),
          getExtractors(),
          getGraphTopologyMetrics(),
          getGraphIntegrityIssues(),
        ]);

        if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
        if (extractorsRes.status === 'fulfilled') {
          setExtractors(extractorsRes.value);
          if (extractorsRes.value.length >= 2 && !extractorA && !extractorB) {
            setExtractorA(extractorsRes.value[0].extractor_name);
            setExtractorB(extractorsRes.value[1].extractor_name);
          } else if (extractorsRes.value.length === 1 && !extractorA) {
            setExtractorA(extractorsRes.value[0].extractor_name);
          }
        }
        if (topologyRes.status === 'fulfilled') setTopology(topologyRes.value);
        if (integrityRes.status === 'fulfilled')
          setIntegrityIssues(integrityRes.value.issues || []);

        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'خطا در واکشی داده‌های کیفیت');
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [extractorA, extractorB]
  );

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => {
        fetchData(true);
      }, 10000);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, fetchData]);

  const handleResetBreaker = async (name: string) => {
    try {
      const res = await resetCircuitBreaker(name, true);
      setActionMessage(`فیوز ${name} با موفقیت ریست شد (${res.new_state || 'closed'})`);
      setTimeout(() => setActionMessage(null), 4000);
      fetchData(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطا در ریست کردن فیوز');
      setTimeout(() => setError(null), 4000);
    }
  };

  const handleRunABTest = async () => {
    if (!extractorA || !extractorB) return;
    setAbLoading(true);
    try {
      const res = await compareExtractors({
        extractor_a: extractorA,
        extractor_b: extractorB,
        metric: abMetric,
      });
      setAbResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطا در اجرای آزمون A/B');
    } finally {
      setAbLoading(false);
    }
  };

  const getHealthBadge = (status?: string) => {
    switch (status) {
      case 'healthy':
        return {
          bg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
          dot: 'bg-emerald-400 animate-pulse',
          text: 'سیستم سالم (Healthy)',
          icon: ShieldCheck,
        };
      case 'degraded':
        return {
          bg: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
          dot: 'bg-amber-400 animate-pulse',
          text: 'کاهش کیفیت (Degraded)',
          icon: ShieldAlert,
        };
      case 'critical':
      default:
        return {
          bg: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
          dot: 'bg-rose-400 animate-pulse',
          text: 'نیازمند بررسی (Critical)',
          icon: AlertOctagon,
        };
    }
  };

  const getCircuitStateBadge = (state?: string) => {
    const s = (state || 'unknown').toLowerCase();
    if (s === 'closed') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-sm">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          بسته (عادی - Closed)
        </span>
      );
    }
    if (s === 'half_open' || s === 'half-open') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 border border-amber-500/30 text-amber-400 shadow-sm">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
          نیمه‌باز (در حال آزمون - Half-Open)
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 border border-rose-500/30 text-rose-400 shadow-sm">
        <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-ping"></span>
        قطع شده (باز - Open)
      </span>
    );
  };

  const currentBadge = getHealthBadge(health?.status);
  const StatusIcon = currentBadge.icon;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-10 font-sans" dir="rtl">
      {/* Glow Effects */}
      <div className="fixed top-20 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none -z-10" />
      <div className="fixed bottom-20 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none -z-10" />

      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header Bar */}
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-6 border-b border-slate-800/80">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-gradient-to-tr from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-500/20">
                <Activity className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2">
                  نظارت بر کیفیت گراف دانش
                  <span className="text-xs font-medium px-2 py-0.5 rounded-md bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                    Phase 8 Live
                  </span>
                </h1>
                <p className="text-sm text-slate-400 mt-1">
                  رصد بلادرنگ استخراج‌کننده‌های روابط معنایی، فیوزهای محافظتی (Circuit Breakers) و
                  سلامت توپولوژی
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 self-end md:self-auto">
            {/* Health Pill */}
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-semibold backdrop-blur-md ${currentBadge.bg}`}
            >
              <StatusIcon className="w-4 h-4" />
              <span>{currentBadge.text}</span>
            </div>

            {/* Auto Refresh Toggle */}
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`text-xs px-3 py-1.5 rounded-xl border transition-all ${
                autoRefresh
                  ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-300'
                  : 'bg-slate-900 border-slate-800 text-slate-400'
              }`}
            >
              به‌روزرسانی خودکار: {autoRefresh ? 'فعال' : 'غیرفعال'}
            </button>

            {/* Refresh Button */}
            <button
              onClick={() => fetchData()}
              disabled={refreshing}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-all shadow-sm"
              title="تازه‌سازی دستی"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin text-cyan-400' : ''}`} />
            </button>
          </div>
        </div>

        {/* Notifications / Alerts */}
        {actionMessage && (
          <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 flex items-center gap-3 backdrop-blur-md">
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm font-medium">{actionMessage}</span>
          </div>
        )}

        {error && (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 flex items-center gap-3 backdrop-blur-md">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm font-medium">{error}</span>
          </div>
        )}

        {/* Top KPI Metric Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Overall Quality Score */}
          <div className="relative overflow-hidden p-5 rounded-2xl bg-slate-900/70 border border-slate-800 backdrop-blur-md hover:border-slate-700 transition-all group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-cyan-500/5 rounded-full blur-2xl group-hover:bg-cyan-500/10 transition-all" />
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>امتیاز کلی سلامت گراف</span>
              <Layers className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-white">
                {topology?.quality_score !== undefined
                  ? `${topology.quality_score.toFixed(1)}%`
                  : '۱۰۰٪'}
              </span>
              <span className="text-xs text-emerald-400 font-medium">
                {topology?.quality_level || 'عالی (Optimal)'}
              </span>
            </div>
            <div className="mt-3 w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-gradient-to-r from-cyan-500 to-indigo-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${topology?.quality_score || 100}%` }}
              />
            </div>
          </div>

          {/* Card 2: Extractors & Workloads */}
          <div className="relative overflow-hidden p-5 rounded-2xl bg-slate-900/70 border border-slate-800 backdrop-blur-md hover:border-slate-700 transition-all group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-500/5 rounded-full blur-2xl group-hover:bg-indigo-500/10 transition-all" />
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>استخراج‌کننده‌های ثبت‌شده</span>
              <Cpu className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-white">
                {health?.total_extractors ?? extractors.length}
              </span>
              <span className="text-xs text-slate-400">
                ({health?.active_extractors ?? extractors.length} فعال در رجیستری)
              </span>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              کل فراخوانی‌ها: {health?.total_extractions?.toLocaleString() ?? 0}
            </p>
          </div>

          {/* Card 3: Circuit Breakers */}
          <div className="relative overflow-hidden p-5 rounded-2xl bg-slate-900/70 border border-slate-800 backdrop-blur-md hover:border-slate-700 transition-all group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-2xl group-hover:bg-emerald-500/10 transition-all" />
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>وضعیت فیوزهای محافظتی</span>
              <Shield className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-white">
                {(health?.circuit_breakers_open ?? 0) === 0
                  ? 'امن'
                  : `${health?.circuit_breakers_open} قطع`}
              </span>
              <span
                className={`text-xs font-medium ${(health?.circuit_breakers_open ?? 0) === 0 ? 'text-emerald-400' : 'text-rose-400'}`}
              >
                {(health?.circuit_breakers_open ?? 0) === 0
                  ? 'تمام فیوزها وصل هستند'
                  : 'نیازمند ریست'}
              </span>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              نرخ موفقیت: {health?.avg_success_rate ?? 100}%
            </p>
          </div>

          {/* Card 4: Anomaly Detection Rate */}
          <div className="relative overflow-hidden p-5 rounded-2xl bg-slate-900/70 border border-slate-800 backdrop-blur-md hover:border-slate-700 transition-all group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/5 rounded-full blur-2xl group-hover:bg-amber-500/10 transition-all" />
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>نرخ ناهنجاری (Anomaly Rate)</span>
              <Zap className="w-4 h-4 text-amber-400" />
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-white">
                {health?.anomaly_rate !== undefined ? `${health.anomaly_rate}%` : '۰٪'}
              </span>
              <span className="text-xs text-slate-400 font-medium">Z-Score Monitoring</span>
            </div>
            <p className="mt-2 text-xs text-slate-500">پنجره نمونه‌گیری: ۱۰۰ فراخوانی اخیر</p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-800">
          <button
            onClick={() => setActiveTab('extractors')}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold border-b-2 transition-all ${
              activeTab === 'extractors'
                ? 'border-cyan-500 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Cpu className="w-4 h-4" />
            <span>اکسترکتورها و فیوزها ({extractors.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('topology')}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold border-b-2 transition-all ${
              activeTab === 'topology'
                ? 'border-cyan-500 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Layers className="w-4 h-4" />
            <span>توپولوژی و سلامت ساختار گراف</span>
          </button>

          <button
            onClick={() => setActiveTab('ab_test')}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold border-b-2 transition-all ${
              activeTab === 'ab_test'
                ? 'border-cyan-500 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <GitCompare className="w-4 h-4" />
            <span>آزمون مقایسه‌ای A/B اکسترکتورها</span>
          </button>
        </div>

        {/* TAB 1: Extractors & Circuit Breakers */}
        {activeTab === 'extractors' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">
                  استخراج‌کننده‌های روابط معنایی و فیوزهای محافظتی
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  هر استخراج‌کننده مجهز به فیوز مستقل، ردیاب ناهنجاری و معیارهای آماری
                  F1/Precision/Recall است.
                </p>
              </div>
            </div>

            {loading && extractors.length === 0 ? (
              <div className="py-20 flex flex-col items-center justify-center text-slate-500 gap-3">
                <RefreshCw className="w-8 h-8 animate-spin text-cyan-500" />
                <p className="text-sm">در حال بارگذاری لیست استخراج‌کننده‌ها...</p>
              </div>
            ) : extractors.length === 0 ? (
              <div className="p-8 rounded-2xl bg-slate-900/50 border border-slate-800 text-center">
                <AlertCircleIcon className="w-8 h-8 text-amber-400 mx-auto mb-2" />
                <p className="text-slate-300 font-medium">هیچ استخراج‌کننده‌ای یافت نشد</p>
                <p className="text-xs text-slate-500 mt-1">
                  با بارگذاری اسناد، استخراج‌کننده‌ها به صورت خودکار فعال خواهند شد.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {extractors.map((ext) => (
                  <div
                    key={ext.extractor_name}
                    className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800/80 hover:border-slate-700 backdrop-blur-md transition-all shadow-lg flex flex-col justify-between"
                  >
                    <div>
                      {/* Card Header */}
                      <div className="flex items-start justify-between gap-3 mb-4">
                        <div>
                          <h4 className="font-bold text-base text-white tracking-wide font-mono">
                            {ext.extractor_name}
                          </h4>
                          <span className="text-xs text-slate-500 flex items-center gap-1 mt-1">
                            <Clock className="w-3 h-3" />
                            {ext.total_extractions > 0
                              ? `${ext.total_extractions.toLocaleString()} استخراج`
                              : 'آماده پردازش'}
                          </span>
                        </div>
                        {getCircuitStateBadge(ext.circuit_breaker_state)}
                      </div>

                      {/* Metrics Bars */}
                      <div className="space-y-3.5 my-5 text-xs">
                        <div>
                          <div className="flex justify-between text-slate-400 mb-1">
                            <span>میانگین اطمینان (Confidence):</span>
                            <span className="font-semibold text-cyan-300">
                              {(ext.avg_confidence * 100).toFixed(1)}%
                            </span>
                          </div>
                          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-cyan-500 h-full rounded-full"
                              style={{ width: `${Math.min(ext.avg_confidence * 100, 100)}%` }}
                            />
                          </div>
                        </div>

                        <div>
                          <div className="flex justify-between text-slate-400 mb-1">
                            <span>امتیاز F1 Score:</span>
                            <span className="font-semibold text-indigo-300">
                              {(ext.avg_f1 * 100).toFixed(1)}%
                            </span>
                          </div>
                          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-indigo-500 h-full rounded-full"
                              style={{ width: `${Math.min(ext.avg_f1 * 100, 100)}%` }}
                            />
                          </div>
                        </div>

                        <div className="flex items-center justify-between pt-2 border-t border-slate-800/60 text-slate-400">
                          <span>میانگین تاخیر (Latency):</span>
                          <span className="font-mono text-slate-200">
                            {ext.avg_latency_ms.toFixed(1)} ms
                          </span>
                        </div>

                        <div className="flex items-center justify-between text-slate-400">
                          <span>تعداد ناهنجاری‌های کشف‌شده:</span>
                          <span
                            className={`font-semibold ${ext.anomaly_count > 0 ? 'text-amber-400' : 'text-slate-400'}`}
                          >
                            {ext.anomaly_count} مورد
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Card Actions */}
                    <div className="pt-4 border-t border-slate-800/80 flex items-center justify-between gap-2">
                      <span className="text-[11px] text-slate-500">
                        موفق: {ext.success_count} | ناموفق: {ext.failure_count}
                      </span>
                      <button
                        onClick={() => handleResetBreaker(ext.extractor_name)}
                        className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium transition-all flex items-center gap-1.5 border border-slate-700"
                        title="ریست کردن وضعیت Circuit Breaker به حالت بسته"
                      >
                        <RefreshCw className="w-3 h-3 text-cyan-400" />
                        ریست فیوز
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: Topology & Graph Integrity */}
        {activeTab === 'topology' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 backdrop-blur-md">
                <span className="text-xs text-slate-400 font-medium">تعداد کل نودها</span>
                <p className="text-2xl font-bold text-white mt-2">
                  {topology?.total_nodes?.toLocaleString() ?? 0}
                </p>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 backdrop-blur-md">
                <span className="text-xs text-slate-400 font-medium">تعداد کل یال‌ها (روابط)</span>
                <p className="text-2xl font-bold text-white mt-2">
                  {topology?.total_edges?.toLocaleString() ?? 0}
                </p>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 backdrop-blur-md">
                <span className="text-xs text-slate-400 font-medium">
                  نودهای بدون اتصال (Orphan)
                </span>
                <p
                  className={`text-2xl font-bold mt-2 ${(topology?.orphaned_nodes_count ?? 0) > 0 ? 'text-amber-400' : 'text-emerald-400'}`}
                >
                  {topology?.orphaned_nodes_count ?? 0}
                </p>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 backdrop-blur-md">
                <span className="text-xs text-slate-400 font-medium">تراکم گراف (Density)</span>
                <p className="text-2xl font-bold text-cyan-400 mt-2 font-mono">
                  {topology?.density?.toFixed(4) ?? '۰.۰۰۰۰'}
                </p>
              </div>
            </div>

            {/* Integrity Issues List */}
            <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-md">
              <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-indigo-400" />
                گزارش یکپارچگی ساختار و اعتبارسنجی گراف
              </h3>

              {integrityIssues.length === 0 ? (
                <div className="p-8 text-center text-slate-400 border border-dashed border-slate-800 rounded-xl">
                  <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-2" />
                  <p className="font-medium text-slate-200">
                    هیچ مغایرت ساختاری در گراف شناسایی نشد
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    تمامی وابستگی‌ها، نودها و روابط معنایی در حالت نرمال قرار دارند.
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-slate-800/80">
                  {integrityIssues.map((issue) => (
                    <div
                      key={issue.id}
                      className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-3"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold uppercase ${
                              issue.severity === 'critical'
                                ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                                : issue.severity === 'high'
                                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                  : 'bg-slate-800 text-slate-300'
                            }`}
                          >
                            {issue.severity}
                          </span>
                          <span className="font-semibold text-sm text-white">{issue.type}</span>
                        </div>
                        <p className="text-xs text-slate-400 mt-1.5">{issue.description}</p>
                      </div>

                      <div className="text-left text-xs text-slate-500 font-mono">
                        {issue.affected_nodes?.length
                          ? `${issue.affected_nodes.length} نود متاثر`
                          : ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: Extractor A/B Testing & Causal Benchmarking */}
        {activeTab === 'ab_test' && (
          <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-md space-y-6">
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-cyan-400" />
                آزمون مقایسه‌ای و تحلیل اثر علّی استخراج‌کننده‌ها (A/B Testing & Causal Effect)
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                مقایسه آماری دو الگوریتم استخراج بر روی معیار مشخص، محاسبه P-Value و ارزیابی
                معناداری آماری
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-5 rounded-xl bg-slate-950/60 border border-slate-800/80">
              {/* Extractor A */}
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-2">
                  الگوریتم A (Variant A):
                </label>
                <select
                  value={extractorA}
                  onChange={(e) => setExtractorA(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                >
                  {extractors.map((e) => (
                    <option key={e.extractor_name} value={e.extractor_name}>
                      {e.extractor_name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Extractor B */}
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-2">
                  الگوریتم B (Variant B):
                </label>
                <select
                  value={extractorB}
                  onChange={(e) => setExtractorB(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                >
                  {extractors.map((e) => (
                    <option key={e.extractor_name} value={e.extractor_name}>
                      {e.extractor_name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Metric */}
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-2">
                  معیار ارزیابی (Target Metric):
                </label>
                <select
                  value={abMetric}
                  onChange={(e) => setAbMetric(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                >
                  <option value="confidence">اطمینان (Confidence)</option>
                  <option value="latency_ms">تاخیر پردازش (Latency ms)</option>
                  <option value="precision">دقت (Precision)</option>
                  <option value="recall">فراخوانی (Recall)</option>
                  <option value="f1">امتیاز F1 Score</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={handleRunABTest}
                disabled={abLoading || !extractorA || !extractorB}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-semibold text-sm transition-all shadow-md shadow-cyan-500/20 disabled:opacity-50 flex items-center gap-2"
              >
                {abLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <TrendingUp className="w-4 h-4" />
                )}
                اجرای تحلیل مقایسه‌ای
              </button>
            </div>

            {/* Benchmark Result */}
            {abResult && (
              <div className="p-6 rounded-xl bg-slate-950 border border-slate-800 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <span className="font-bold text-white text-sm">نتیجه آزمون آماری</span>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-semibold ${
                      abResult.is_significant
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {abResult.is_significant
                      ? 'تفاوت معنادار آماری (p < 0.05)'
                      : 'بدون تفاوت معنادار آماری'}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-center">
                  <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                    <span className="text-xs text-slate-400">میانگین {abResult.extractor_a}</span>
                    <p className="text-xl font-bold text-cyan-400 mt-1">
                      {abResult.mean_a.toFixed(3)}
                    </p>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                    <span className="text-xs text-slate-400">میانگین {abResult.extractor_b}</span>
                    <p className="text-xl font-bold text-indigo-400 mt-1">
                      {abResult.mean_b.toFixed(3)}
                    </p>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                    <span className="text-xs text-slate-400">P-Value</span>
                    <p className="text-xl font-bold text-amber-400 mt-1 font-mono">
                      {abResult.p_value.toFixed(4)}
                    </p>
                  </div>
                </div>

                {abResult.recommendation && (
                  <div className="p-4 rounded-xl bg-cyan-950/30 border border-cyan-800/40 text-xs text-cyan-200">
                    <strong>توصیه سامانه: </strong>
                    {abResult.recommendation}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function AlertCircleIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}
