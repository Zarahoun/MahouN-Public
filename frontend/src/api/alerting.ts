import { apiClient } from './client';

export type AlertSeverity = 'CRITICAL' | 'ERROR' | 'WARNING' | 'INFO';
export type AlertStatus = 'active' | 'acknowledged' | 'resolved' | 'suppressed';

export interface AlertMetadata {
  source: string;
  category: string;
  instance?: string | null;
  region?: string | null;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  fingerprint?: string | null;
}

export interface AlertRecord {
  alert_id: string;
  alert_name: string;
  severity: AlertSeverity;
  status: AlertStatus;
  message: string;
  triggered_at: string;
  updated_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  acknowledged_by?: string | null;
  resolved_by?: string | null;
  metadata: AlertMetadata;
  channels: string[];
  notification_count: number;
  last_notification_at?: string | null;
  related_alerts: string[];
  incident_id?: string | null;
  suggested_actions: string[];
  runbook_url?: string | null;
}

export interface AlertListResponse {
  total: number;
  returned: number;
  offset: number;
  limit: number;
  alerts: AlertRecord[];
  stats_summary: Record<string, number>;
}

export interface AlertStatistics {
  timestamp: string;
  time_window_hours: number;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_channel: Record<string, number>;
  total_triggered: number;
  total_acknowledged: number;
  total_resolved: number;
  avg_acknowledgement_time_seconds: number;
  avg_resolution_time_seconds: number;
  top_alert_names: Array<{ name: string; count: number }>;
  top_instances: Array<{ instance: string; count: number }>;
  trend_direction: string;
  trend_percentage: number;
}

export interface AlertListParams {
  severity?: AlertSeverity | '';
  status?: AlertStatus | '';
  category?: string;
  hours?: number;
  sort_by?: 'triggered_at' | 'severity' | 'status';
  sort_order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

export function getAlerts(params: AlertListParams = {}) {
  return apiClient.get<AlertListResponse>('/monitoring/alerts', { params: { ...params } });
}

export function getAlert(alertId: string) {
  return apiClient.get<AlertRecord>(`/monitoring/alerts/${encodeURIComponent(alertId)}`);
}

export function getAlertStatistics(hours = 24) {
  return apiClient.get<AlertStatistics>('/monitoring/alerts/stats', { params: { hours } });
}

export function acknowledgeAlert(
  alertId: string,
  body: {
    acknowledged_by: string;
    notes?: string;
    suppress_notifications?: boolean;
  }
) {
  return apiClient.post<AlertRecord>(
    `/monitoring/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    body
  );
}

export function resolveAlert(
  alertId: string,
  body: {
    resolved_by: string;
    resolution_notes: string;
    incident_id?: string;
  }
) {
  return apiClient.post<AlertRecord>(
    `/monitoring/alerts/${encodeURIComponent(alertId)}/resolve`,
    body
  );
}
