/**
 * Graph Quality & Semantic Extraction Quality API Client
 * Connects to canonical backend routers:
 * - /api/v1/quality/*
 * - /api/v1/graph/quality/metrics, /integrity/issues, /completeness/report
 */

import { apiClient } from './client';

export interface QualityHealth {
  status: 'healthy' | 'degraded' | 'critical';
  total_extractors: number;
  active_extractors: number;
  total_extractions: number;
  anomaly_rate: number;
  avg_success_rate: number;
  circuit_breakers_open: number;
  timestamp: string;
}

export interface ExtractorMetrics {
  extractor_name: string;
  total_extractions: number;
  success_count: number;
  failure_count: number;
  avg_latency_ms: number;
  avg_confidence: number;
  avg_precision: number;
  avg_recall: number;
  avg_f1: number;
  anomaly_count: number;
  circuit_breaker_state: 'closed' | 'open' | 'half_open' | string;
  last_extraction?: string | null;
}

export interface AnomalyRecord {
  timestamp: string;
  metric_name: string;
  value: number;
  expected_value: number;
  z_score: number;
  severity: 'low' | 'medium' | 'high';
}

export interface CircuitBreakerStatus {
  state: 'closed' | 'open' | 'half_open' | string;
  failure_count: number;
  last_failure_time?: string | null;
  last_state_change: string;
}

export interface QualityStats {
  total_extractors: number;
  total_extractions: number;
  total_successes: number;
  total_failures: number;
  avg_latency_ms: number;
  avg_confidence: number;
  avg_precision: number;
  avg_recall: number;
  avg_f1: number;
  per_extractor: Record<string, unknown>;
  timestamp: string;
}

export interface GraphTopologyMetrics {
  quality_score: number;
  quality_level: string;
  total_nodes: number;
  total_edges: number;
  density: number;
  orphaned_nodes_count: number;
  duplicate_nodes_count: number;
  missing_properties_count: number;
  broken_relationships_count: number;
  consistency_issues_count: number;
  timestamp: string;
}

export interface GraphIntegrityIssue {
  id: string;
  type: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  description: string;
  affected_nodes: string[];
  affected_edges: string[];
}

export interface GraphCompletenessReport {
  overall_score: number;
  node_coverage: number;
  edge_coverage: number;
  property_coverage: number;
  missing_nodes: string[];
  missing_edges: string[];
  missing_properties: Record<string, string[]>;
}

export interface ABCompareRequest {
  extractor_a: string;
  extractor_b: string;
  metric?: string;
}

export interface ABCompareResponse {
  extractor_a: string;
  extractor_b: string;
  metric: string;
  mean_a: number;
  mean_b: number;
  difference: number;
  p_value: number;
  is_significant: boolean;
  recommendation?: string;
  winner?: string;
  timestamp: string;
}

// API functions
export async function getQualityHealth(): Promise<QualityHealth> {
  return apiClient.get<QualityHealth>('/api/v1/quality/health');
}

export async function getQualityStats(): Promise<QualityStats> {
  return apiClient.get<QualityStats>('/api/v1/quality/stats');
}

export async function getExtractors(): Promise<ExtractorMetrics[]> {
  return apiClient.get<ExtractorMetrics[]>('/api/v1/quality/extractors');
}

export async function getExtractorMetrics(name: string): Promise<ExtractorMetrics> {
  const extractor_name = encodeURIComponent(name);
  return apiClient.get<ExtractorMetrics>(`/api/v1/quality/extractors/${extractor_name}`);
}

export async function getExtractorAnomalies(name: string, window = 100): Promise<AnomalyRecord[]> {
  const extractor_name = encodeURIComponent(name);
  return apiClient.get<AnomalyRecord[]>(`/api/v1/quality/extractors/${extractor_name}/anomalies`, {
    params: { window },
  });
}

export async function getCircuitBreakerStatus(name: string): Promise<CircuitBreakerStatus> {
  const extractor_name = encodeURIComponent(name);
  return apiClient.get<CircuitBreakerStatus>(
    `/api/v1/quality/extractors/${extractor_name}/circuit-breaker`
  );
}

export async function resetCircuitBreaker(
  name: string,
  force = false
): Promise<{ message: string; previous_state: string; new_state: string }> {
  const extractor_name = encodeURIComponent(name);
  return apiClient.post(
    `/api/v1/quality/extractors/${extractor_name}/circuit-breaker/reset`,
    undefined,
    { params: { force } }
  );
}

export async function compareExtractors(req: ABCompareRequest): Promise<ABCompareResponse> {
  return apiClient.post<ABCompareResponse>('/api/v1/quality/ab-test/compare', req);
}

export async function getGraphTopologyMetrics(): Promise<GraphTopologyMetrics> {
  return apiClient.get<GraphTopologyMetrics>('/api/v1/graph/quality/metrics');
}

export async function getGraphIntegrityIssues(): Promise<{ issues: GraphIntegrityIssue[] }> {
  return apiClient.get<{ issues: GraphIntegrityIssue[] }>('/api/v1/graph/integrity/issues');
}

export async function getGraphCompletenessReport(): Promise<GraphCompletenessReport> {
  return apiClient.get<GraphCompletenessReport>('/api/v1/graph/completeness/report');
}
