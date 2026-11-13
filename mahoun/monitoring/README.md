# Ultra-Professional Legal Monitoring System

Enterprise-grade monitoring and observability for Mahoun's legal-aware components with zero-hallucination guarantees.

## MANDATORY AI AGENT CONSTITUTIONAL BOOTSTRAP

All AI agents working on MAHOUN MUST perform the following initialization before any analysis, planning, coding, modification, refactoring, testing, or architectural decision.

## Step 1 — Constitutional Loading

The agent MUST read and understand:

`/home/haji/Desktop/KingMahouN/mahoun/constitutional/constitution/CONSTITUTION.md`

This document is the root authority for MAHOUN development governance.

No repository action is authorized before constitutional loading is completed.

## Step 2 — Authority Hierarchy

The following authority hierarchy MUST be respected:

1. Constitutional documents
2. Workflow definitions
3. Agent role instructions
4. Repository implementation details
5. Local tooling and IDE metadata

Lower-level instructions MUST NEVER override higher-level authority.

## Step 3 — Source of Truth

The directory:

`/home/haji/Desktop/KingMahouN/mahoun/constitutional/`

is the single authoritative governance source for:

- Architecture decisions
- Governance boundaries
- Security rules
- API evolution policies
- Workflow execution rules
- Agent behavior constraints

## Step 4 — Forbidden Assumptions

Agents MUST NOT consider the following as architectural authority:

- `.ai/`
- `.cursor/`
- `.vscode/`
- IDE-generated instructions
- Client-specific metadata
- Generated files
- Temporary agent memory
- Previous agent assumptions

These sources may be consulted only when explicitly referenced by constitutional documents.

## Step 5 — Conflict Resolution

If any conflict exists between:

- Agent instructions
- IDE instructions
- Client configuration
- Generated metadata
- Existing implementation

the constitutional documents ALWAYS take precedence.

## Step 6 — Architectural Changes

Before performing any of the following actions, the agent MUST consult relevant constitutional documents:

- Creating new modules
- Moving files
- Changing public APIs
- Modifying governance logic
- Altering contracts/schema
- Changing workflow behavior
- Refactoring core architecture

## Step 7 — Fail Closed Rule

If constitutional documents cannot be accessed, are missing, ambiguous, or contradictory:

The agent MUST NOT proceed with architectural changes.

The agent MUST:

1. Report the conflict.
2. Identify the missing authority source.
3. Request clarification.

Silent assumption is prohibited.

## Final Rule

MAHOUN is governed by constitutional architecture.

Agents are execution units, not architectural authorities.

No agent, model, IDE, plugin, or client configuration may redefine MAHOUN architecture outside the constitutional process.

## Overview

The Ultra-Professional Legal Monitoring System provides comprehensive monitoring, metrics collection, and alerting for legal reasoning operations. It integrates with Prometheus for metrics collection, Grafana for visualization, and includes ML-based anomaly detection via the UltraPerformanceMonitor.

## Key Features

### 1. **Prometheus Metrics Export**
- Automatic metrics export in Prometheus format
- Custom legal-specific metrics (court rank, legal domain, authority scores)
- Multi-dimensional metric analysis
- Real-time metric updates

### 2. **SLA Compliance Tracking**
- Configurable SLA targets for all metrics
- Automatic violation detection and alerting
- Compliance rate calculation
- Regulatory audit trail support

### 3. **Advanced Analytics**
- ML-based anomaly detection (via UltraPerformanceMonitor)
- Performance bottleneck identification
- Predictive performance modeling
- Optimization recommendations

### 4. **Real-Time Alerting**
- Multi-severity alert levels (CRITICAL, HIGH, MEDIUM, LOW, INFO)
- Alert deduplication to prevent alert fatigue
- Custom alert callbacks for integration
- Prometheus AlertManager integration

### 5. **Comprehensive Health Checks**
- Component-level health monitoring
- SLA compliance verification
- Performance degradation detection
- Automatic status reporting

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Legal-Aware Components                      │
│  (Retrieval, Migration, Graph Queries, Agents)              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│         UltraProfessionalLegalMonitoring                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Core Metrics Collection                              │  │
│  │  - Query latency (P50, P95, P99)                     │  │
│  │  - Throughput tracking                                │  │
│  │  - Error rate monitoring                              │  │
│  │  - Cache performance                                  │  │
│  │  - Authority score tracking                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  UltraPerformanceMonitor Integration                  │  │
│  │  - ML-based anomaly detection                         │  │
│  │  - Performance profiling                              │  │
│  │  - Bottleneck identification                          │  │
│  │  - Optimization recommendations                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SLA Compliance Engine                                │  │
│  │  - Target configuration                               │  │
│  │  - Violation detection                                │  │
│  │  - Compliance rate calculation                        │  │
│  │  - Alert triggering                                   │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
┌──────────────┐          ┌──────────────┐
│  Prometheus  │          │   Grafana    │
│   Metrics    │          │  Dashboard   │
│   Scraping   │          │ Visualization│
└──────────────┘          └──────────────┘
```

## Quick Start

### 1. Basic Usage

```python
from mahoun.monitoring.legal_metrics import legal_monitoring

# Track a legal query
await legal_monitoring.track_legal_query(
    query="ماده 183 قانون مدنی",
    duration=0.5,
    filtered_count=3,
    result_count=10,
    court_rank="SUPREME_COURT",
    legal_domain="civil_law",
    authority_score=0.92,
    cache_hit=True
)

# Get statistics
stats = legal_monitoring.get_comprehensive_stats()
print(f"Total queries: {stats['total_queries']}")
print(f"P95 latency: {stats['p95_latency']:.3f}s")
print(f"SLA compliance: {stats['sla_compliance_rate']:.2%}")

# Export Prometheus metrics
metrics = legal_monitoring.export_prometheus_metrics()

# Health check
health = await legal_monitoring.health_check()
print(f"Status: {health['status']}")
```

### 2. Decorator Usage

```python
from mahoun.monitoring.legal_metrics import track_legal_query_decorator

@track_legal_query_decorator
async def my_legal_query(query: str):
    # Your query logic here
    results = await perform_query(query)
    return results
```

### 3. Custom SLA Targets

```python
from mahoun.monitoring.legal_metrics import legal_monitoring, SLATarget, AlertSeverity

# Add custom SLA target
legal_monitoring.add_sla_target(SLATarget(
    metric_name="custom_metric",
    target_value=0.95,
    comparison="greater_than",
    severity=AlertSeverity.HIGH,
    description="Custom metric must be above 95%"
))
```

### 4. Alert Callbacks

```python
from mahoun.monitoring.alerting import Alert

def my_alert_handler(alert: Alert):
    print(f"Alert: {alert.severity.value} - {alert.message}")
    # Send to Slack, PagerDuty, etc.

legal_monitoring.register_alert_callback(my_alert_handler)
```

## Metrics Reference

### Core Metrics

| Metric Name | Type | Description |
|------------|------|-------------|
| `legal_query_throughput_total` | Counter | Total number of legal queries processed |
| `legal_query_latency_seconds` | Gauge | Average query latency in seconds |
| `legal_query_latency_seconds_p50` | Gauge | 50th percentile query latency |
| `legal_query_latency_seconds_p95` | Gauge | 95th percentile query latency |
| `legal_query_latency_seconds_p99` | Gauge | 99th percentile query latency |
| `legal_documents_filtered_total` | Counter | Total documents filtered |
| `legal_query_error_rate` | Gauge | Query error rate (0-1) |
| `legal_cache_hit_rate` | Gauge | Cache hit rate (0-1) |
| `legal_authority_score` | Gauge | Average authority score |
| `legal_sla_compliance_rate` | Gauge | SLA compliance rate (0-1) |

### Dimensional Metrics

| Metric Name | Labels | Description |
|------------|--------|-------------|
| `legal_court_rank_distribution` | `court_rank` | Query distribution by court rank |
| `legal_legal_domain_distribution` | `legal_domain` | Query distribution by legal domain |
| `legal_errors_by_type_total` | `error_type` | Error count by type |

## SLA Targets

### Default SLA Targets

1. **Query Latency P95**: < 500ms (HIGH severity)
2. **Error Rate**: < 1% (CRITICAL severity)
3. **Cache Hit Rate**: > 70% (MEDIUM severity)
4. **Authority Score**: > 0.75 (MEDIUM severity)

### Customizing SLA Targets

```python
# Modify existing target
legal_monitoring.sla_targets["query_latency_p95"].target_value = 0.3  # 300ms

# Add new target
legal_monitoring.add_sla_target(SLATarget(
    metric_name="retrieval_quality",
    target_value=0.90,
    comparison="greater_than",
    severity=AlertSeverity.HIGH,
    description="Retrieval quality must be above 90%"
))
```

## Prometheus Integration

### 1. Update Prometheus Configuration

Add the legal monitoring scrape target to `monitoring/prometheus/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'legal-monitoring'
    static_configs:
      - targets: ['api:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s
```

### 2. Alert Rules

Alert rules are defined in `monitoring/prometheus/alerts/legal_monitoring_alerts.yml`.

Key alerts:
- **LegalQueryErrorRateHigh**: Error rate > 5%
- **LegalQueryLatencyP95High**: P95 latency > 1.0s
- **LegalSLAComplianceLow**: SLA compliance < 95%
- **LegalCacheHitRateLow**: Cache hit rate < 50%

### 3. FastAPI Integration

```python
from fastapi import FastAPI
from mahoun.monitoring.metrics_endpoint import register_metrics_endpoint

app = FastAPI()

# Register metrics endpoint
register_metrics_endpoint(app)

# Metrics available at: GET /metrics
# Health check at: GET /health/legal-monitoring
# Stats at: GET /stats/legal-monitoring
```

## Grafana Dashboard

### Importing the Dashboard

1. Open Grafana UI
2. Navigate to Dashboards → Import
3. Upload `monitoring/grafana/dashboards/legal_monitoring.json`
4. Select Prometheus datasource
5. Click Import

### Dashboard Panels

1. **Legal Query Throughput**: Real-time query rate
2. **Legal Query Latency**: P50, P95, P99 percentiles
3. **Error Rate**: Query error rate with threshold
4. **Cache Hit Rate**: Metadata cache performance
5. **SLA Compliance Rate**: Overall SLA compliance gauge
6. **Authority Score**: Average authority score trend
7. **Court Rank Distribution**: Pie chart of queries by court
8. **Legal Domain Distribution**: Bar chart of queries by domain
9. **Documents Filtered Rate**: Filtering rate over time
10. **Error Distribution**: Table of errors by type
11. **Recent Alerts**: List of active alerts

## Advanced Features

### 1. Anomaly Detection

The system uses ML-based anomaly detection via UltraPerformanceMonitor:

```python
# Anomalies are automatically detected
stats = legal_monitoring.get_comprehensive_stats()
anomalies = stats['ultra_monitor']['anomalies_detected']
print(f"Anomalies detected: {anomalies}")
```

### 2. Performance Bottlenecks

```python
# Get performance bottlenecks
stats = legal_monitoring.get_comprehensive_stats()
bottlenecks = stats.get('bottlenecks', [])

for bottleneck in bottlenecks:
    print(f"Bottleneck: {bottleneck['operation']}")
    print(f"  P95 duration: {bottleneck['p95_duration']:.2f}ms")
    print(f"  Samples: {bottleneck['samples']}")
```

### 3. Optimization Recommendations

```python
# Get optimization recommendations
stats = legal_monitoring.get_comprehensive_stats()
recommendations = stats['performance_report']['recommendations']

for rec in recommendations:
    print(f"💡 {rec}")
```

### 4. Recent Query Analysis

```python
# Analyze recent queries
stats = legal_monitoring.get_comprehensive_stats()
recent_queries = stats['recent_queries']

for query in recent_queries[-5:]:
    print(f"Query: {query['query_id']}")
    print(f"  Duration: {query['duration']:.3f}s")
    print(f"  Court: {query['court_rank']}")
    print(f"  Domain: {query['domain']}")
    print(f"  Authority: {query['authority']:.2f}")
```

## Production Deployment

### 1. Environment Variables

```bash
# Enable monitoring features
ENABLE_ULTRA_MONITORING=true
ENABLE_PROMETHEUS=true
ENABLE_SLA_TRACKING=true

# Monitoring configuration
MONITORING_WINDOW_SIZE=1000
ANOMALY_CONTAMINATION=0.05
ALERT_DEDUP_WINDOW=300
```

### 2. Docker Compose

```yaml
services:
  api:
    environment:
      - ENABLE_ULTRA_MONITORING=true
      - ENABLE_PROMETHEUS=true
    ports:
      - "8000:8000"
  
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus:/etc/prometheus
    ports:
      - "9090:9090"
  
  grafana:
    image: grafana/grafana:latest
    volumes:
      - ./monitoring/grafana:/etc/grafana/provisioning
    ports:
      - "3000:3000"
```

### 3. Health Check Endpoint

```bash
# Check monitoring health
curl http://localhost:8000/health/legal-monitoring

# Get comprehensive stats
curl http://localhost:8000/stats/legal-monitoring

# Get Prometheus metrics
curl http://localhost:8000/metrics
```

## Troubleshooting

### High Error Rate

1. Check error distribution: `stats['errors_by_type']`
2. Review recent queries with errors
3. Check SLA violations for patterns
4. Review alert history

### High Latency

1. Check P95/P99 latency trends
2. Identify bottlenecks: `stats['bottlenecks']`
3. Review optimization recommendations
4. Check cache hit rate

### Low Cache Hit Rate

1. Review cache configuration
2. Check query patterns
3. Increase cache size if needed
4. Review cache TTL settings

### SLA Violations

1. Check which SLAs are failing: `stats['recent_sla_violations']`
2. Review alert history
3. Adjust SLA targets if needed
4. Investigate root causes

## Best Practices

1. **Monitor Continuously**: Keep monitoring enabled in production
2. **Set Realistic SLAs**: Base targets on actual performance data
3. **Review Regularly**: Check stats and recommendations weekly
4. **Alert Fatigue**: Use appropriate severity levels and deduplication
5. **Capacity Planning**: Use trends to predict resource needs
6. **Audit Compliance**: Maintain monitoring data for regulatory audits

## API Reference

### `UltraProfessionalLegalMonitoring`

Main monitoring class with comprehensive features.

#### Methods

- `track_legal_query()`: Track a legal query with full context
- `get_stats()`: Get current statistics
- `get_comprehensive_stats()`: Get stats with UltraPerformanceMonitor data
- `export_prometheus_metrics()`: Export metrics in Prometheus format
- `health_check()`: Comprehensive health check
- `add_sla_target()`: Add or update SLA target
- `register_alert_callback()`: Register custom alert handler
- `reset()`: Reset all metrics
- `print_summary()`: Print human-readable summary

## Support

For issues or questions:
- Check logs: `mahoun.monitoring.legal_metrics`
- Review health check: `/health/legal-monitoring`
- Check Grafana dashboard for visual insights
- Review Prometheus alerts

## License

Part of the Mahoun Platform - Enterprise Legal Reasoning System
