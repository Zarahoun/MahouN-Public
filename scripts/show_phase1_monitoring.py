#!/usr/bin/env python3
"""
MAHOUN V2 — Phase 1 Auto-Approval Monitoring & Analytics CLI
===========================================================
Displays live statistics, confidence metrics, anomaly detections,
and active alerts from the Phase 1 persistent monitoring database.

Usage:
    source venv/bin/activate
    python scripts/show_phase1_monitoring.py
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mahoun.api.phase1_monitoring import get_decision_log, get_persistence
from mahoun.graph.semantic.phase_1_monitor import Phase1Monitor

# ANSI Color codes for terminal beauty
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner():
    print(f"""{CYAN}{BOLD}
╔══════════════════════════════════════════════════════════════════════════════════╗
║               MAHOUN V2 — PHASE 1 AUTO-APPROVAL MONITORING DASHBOARD             ║
║            Evidence-Based Legal Semantic Expansion & Quality Gate                ║
╚══════════════════════════════════════════════════════════════════════════════════╝{RESET}""")


def main():
    print_banner()
    
    print(f"{DIM}Connecting to persistence storage (SQLite WAL)...{RESET}")
    persistence = get_persistence()
    db_size = os.path.getsize(persistence.db_path) if os.path.exists(persistence.db_path) else 0
    row_counts = persistence.get_row_counts()
    
    print(f"{GREEN}✓ SQLite Database:{RESET} {persistence.db_path} ({db_size / 1024 / 1024:.2f} MB)")
    print(f"{DIM}  Table Records: Decisions={row_counts.get('decisions', 0):,}, "
          f"Alerts={row_counts.get('alerts', 0):,}, "
          f"Snapshots={row_counts.get('snapshots', 0):,}, "
          f"Rollbacks={row_counts.get('rollback_events', 0):,}{RESET}\n")

    print(f"{YELLOW}⏳ Analyzing in-memory candidate decision stream...{RESET}")
    log = get_decision_log()
    monitor = Phase1Monitor(log)
    snapshot = monitor.get_current_snapshot()

    # 1. Status & Core Counts
    status_color = GREEN if snapshot.auto_approval_status == "PHASE_1" else RED
    print(f"{BOLD}┌── CORE DECISION METRICS ────────────────────────────────────────────────────────┐{RESET}")
    print(f"│  Status:               {status_color}{BOLD}{snapshot.auto_approval_status}{RESET} (Gradual Rollout - High Confidence Simple Edges)")
    print(f"│  Total Candidates:     {BOLD}{snapshot.total_candidates:,}{RESET}")
    print(f"│  {GREEN}● Auto-Approved:{RESET}       {BOLD}{snapshot.auto_approved_count:,}{RESET} ({snapshot.auto_approval_rate:.1%})")
    print(f"│  {YELLOW}● Human Review:{RESET}        {BOLD}{snapshot.human_review_count:,}{RESET} ({snapshot.human_review_rate:.1%})")
    print(f"│  {RED}● Rejected:{RESET}            {BOLD}{snapshot.rejected_count:,}{RESET} ({snapshot.rejection_rate:.1%})")
    print(f"{BOLD}└─────────────────────────────────────────────────────────────────────────────────┘{RESET}\n")

    # 2. Confidence Calibration
    print(f"{BOLD}┌── CONFIDENCE CALIBRATION ───────────────────────────────────────────────────────┐{RESET}")
    print(f"│  Average (Auto-Approved): {CYAN}{snapshot.avg_confidence_auto:.4f}{RESET} (Target Threshold: ≥ 0.9850)")
    print(f"│  Average (Human Review):  {YELLOW}{snapshot.avg_confidence_review:.4f}{RESET}")
    print(f"│  Average (Rejected):      {RED}{snapshot.avg_confidence_rejected:.4f}{RESET}")
    print(f"{BOLD}└─────────────────────────────────────────────────────────────────────────────────┘{RESET}\n")

    # 3. Top Relationship Types
    print(f"{BOLD}┌── TOP RELATIONSHIP TYPES ───────────────────────────────────────────────────────┐{RESET}")
    sorted_rels = sorted(snapshot.relationship_type_breakdown.items(), key=lambda x: x[1], reverse=True)
    for rel_type, count in sorted_rels[:6]:
        # Filter special fuzz test strings if needed
        clean_rel = rel_type.replace('\n', ' ').strip()
        if len(clean_rel) > 30:
            clean_rel = clean_rel[:27] + "..."
        pct = (count / snapshot.total_candidates * 100) if snapshot.total_candidates else 0
        print(f"│  • {clean_rel:<30} {count:>8,} ({pct:>5.1f}%)")
    print(f"{BOLD}└─────────────────────────────────────────────────────────────────────────────────┘{RESET}\n")

    # 4. Extractor Performance
    print(f"{BOLD}┌── EXTRACTOR BREAKDOWN ──────────────────────────────────────────────────────────┐{RESET}")
    sorted_exts = sorted(snapshot.extractor_breakdown.items(), key=lambda x: x[1], reverse=True)
    for ext_name, count in sorted_exts[:6]:
        pct = (count / snapshot.total_candidates * 100) if snapshot.total_candidates else 0
        print(f"│  • {ext_name:<30} {count:>8,} ({pct:>5.1f}%)")
    print(f"{BOLD}└─────────────────────────────────────────────────────────────────────────────────┘{RESET}\n")

    # 5. Anomalies & Safety Alarms
    print(f"{BOLD}┌── SAFETY AUDIT & ANOMALIES ─────────────────────────────────────────────────────┐{RESET}")
    if snapshot.detected_anomalies:
        for anomaly in snapshot.detected_anomalies:
            print(f"│  {YELLOW}⚠️  Detected Anomaly:{RESET} {anomaly}")
    else:
        print(f"│  {GREEN}✓ No anomalies detected in current sliding window.{RESET}")

    if snapshot.active_alerts:
        print(f"│")
        for alert in snapshot.active_alerts:
            lvl_color = RED if alert.level.value in ("CRITICAL", "ROLLBACK") else YELLOW
            print(f"│  [{lvl_color}{alert.level.value}{RESET}] {alert.message}")
            print(f"│    Current: {alert.current_value:.4f} | Threshold: {alert.threshold:.4f}")
            print(f"│    Recommendation: {DIM}{alert.recommendation}{RESET}")
    else:
        print(f"│  {GREEN}✓ No active critical alerts.{RESET}")
    print(f"{BOLD}└─────────────────────────────────────────────────────────────────────────────────┘{RESET}\n")

    # Rollback check
    rollback_reason = monitor.check_rollback_conditions()
    if rollback_reason:
        print(f"{RED}{BOLD}🚨 ROLLBACK RECOMMENDATION: {rollback_reason}{RESET}\n")
    else:
        print(f"{GREEN}{BOLD}🛡️  Rollback Status: HEALTHY (No automatic circuit-breaker triggers met){RESET}\n")


if __name__ == "__main__":
    main()

