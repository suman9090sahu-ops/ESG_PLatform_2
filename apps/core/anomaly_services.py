"""
Authoritative ESG Anomaly Detection Engine Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 15 Requirements:
- Clear architectural separation between Deterministic Validation and Anomaly Detection:
  * VALIDATION: "Is this data structurally and logically acceptable?"
  * ANOMALY DETECTION: "Is this data unusual or suspicious compared with expected patterns?"
- Anomaly ≠ Invalid: Anomalies serve as review signals and risk telemetry, never automatic rejection.
- Explainable, deterministic rule architecture:
  * Category A: Historical Consumption Spike (>100% or configured threshold)
  * Category B: Historical Consumption Drop (>50% or configured threshold)
  * Category C: Period-over-Period Variance (>50% or configured threshold)
  * Category D: Duplicate-Like Activity Suspect
  * Category E: Configured Operational Threshold Breach
  * Category F: Operational Intensity Anomaly
- Baseline Calculation Invariants:
  * Strict unit consistency: compares only identical units of measure.
  * Strict scope alignment: compares only same operational site and same activity master.
  * Handles insufficient historical data, zero baselines, and new sites safely without false alerts.
- Idempotency & Historical Lineage:
  * Running detection repeatedly updates active findings rather than spamming duplicate open records.
  * Preserves historical detection runs and review records across correction & resubmission lifecycles.
- Scoped Queryset Access & Object-Level Authorization (Zero client trust, anti-IDOR):
  * Site Managers: view-only for assigned operational sites.
  * Subsidiary Managers: authorized division/company review workspace with review actions.
  * ESG Managers & MEIL Operators: enterprise governance authority.
  * Auditors: strictly read-only assurance access.
- Review Lifecycle Management (OPEN -> ACKNOWLEDGED / EXPLAINED / RESOLVED / DISMISSED):
  * Atomic transactions, mandatory justification commentary, and AuthAuditLog integration.
"""

import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.auth_services import log_auth_event
from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    AnomalyCategory,
    AnomalyDetectionRun,
    AnomalyRecord,
    AnomalyRule,
    AnomalySeverity,
    AnomalyStatus,
    AuthAuditLog,
    RecordStatus,
    ReportingPeriod,
    Role,
    Site,
    Submission,
    UnitOfMeasure,
)
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_sites,
    get_accessible_subsidiaries,
    user_can_access_site,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. DEFAULT ANOMALY RULES SEEDING & RESOLUTION
# -----------------------------------------------------------------------------

def ensure_default_anomaly_rules() -> List[AnomalyRule]:
    """
    Seeds or retrieves canonical deterministic Anomaly Rules for the platform.
    Ensures the anomaly engine is initialized with standard explainable rules.
    """
    defaults = [
        {
            "code": "HIST_SPIKE_100",
            "name": "Historical Consumption Spike (>100%)",
            "description": "Flags records where measured consumption is 100% or more above the site's historical average for the same activity and unit.",
            "category": AnomalyCategory.HISTORICAL_SPIKE,
            "severity": AnomalySeverity.HIGH,
            "threshold_percentage": Decimal("100.00"),
            "rule_parameters": {"min_baseline_records": 2, "extreme_spike_percentage": 200.0},
        },
        {
            "code": "HIST_DROP_50",
            "name": "Historical Consumption Drop (>50%)",
            "description": "Flags records where measured consumption is 50% or more below the site's historical average, which may indicate missing data or meter defects.",
            "category": AnomalyCategory.HISTORICAL_DROP,
            "severity": AnomalySeverity.MEDIUM,
            "threshold_percentage": Decimal("50.00"),
            "rule_parameters": {"min_baseline_records": 2, "extreme_drop_percentage": 80.0},
        },
        {
            "code": "PERIOD_VAR_50",
            "name": "Period-over-Period Variance (>50%)",
            "description": "Flags records where measured consumption deviates by more than 50% from the immediately preceding reporting period or measurement.",
            "category": AnomalyCategory.PERIOD_VARIANCE,
            "severity": AnomalySeverity.MEDIUM,
            "threshold_percentage": Decimal("50.00"),
            "rule_parameters": {"min_baseline_records": 1},
        },
        {
            "code": "DUPLICATE_RECORD",
            "name": "Duplicate-Like Operational Telemetry",
            "description": "Flags records with identical measurement date, quantity, unit, and activity on the same site, or duplicate evidence reference numbers.",
            "category": AnomalyCategory.DUPLICATE_SUSPECT,
            "severity": AnomalySeverity.HIGH,
            "threshold_percentage": None,
            "rule_parameters": {},
        },
        {
            "code": "THRESHOLD_BREACH",
            "name": "Operational Threshold Breach",
            "description": "Flags telemetry entries that exceed configured operational maximums or fall below expected minimum operational floors.",
            "category": AnomalyCategory.THRESHOLD_BREACH,
            "severity": AnomalySeverity.HIGH,
            "threshold_percentage": None,
            "rule_parameters": {"max_quantity": 50000.0, "min_quantity": 0.0001},
        },
        {
            "code": "INTENSITY_OUTLIER",
            "name": "Operational Intensity Outlier",
            "description": "Flags records displaying unusually high operational rate or consumption density where supported by operational parameters.",
            "category": AnomalyCategory.INTENSITY_ANOMALY,
            "severity": AnomalySeverity.LOW,
            "threshold_percentage": Decimal("100.00"),
            "rule_parameters": {},
        },
    ]

    rules = []
    for item in defaults:
        rule, _ = AnomalyRule.objects.get_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "description": item["description"],
                "category": item["category"],
                "severity": item["severity"],
                "threshold_percentage": item["threshold_percentage"],
                "rule_parameters": item["rule_parameters"],
                "is_active": True,
                "version": 1,
            },
        )
        rules.append(rule)
    return rules


# -----------------------------------------------------------------------------
# 2. HISTORICAL BASELINE CALCULATION ENGINE
# -----------------------------------------------------------------------------

def compute_historical_baseline(
    record: ActivityRecord,
    rule: Optional[AnomalyRule] = None,
) -> Tuple[Optional[Decimal], int, str]:
    """
    Computes rolling historical baseline for an ActivityRecord.

    Invariants:
    - Strictly matches: same site, same activity, same unit of measure.
    - Strictly excludes current record being evaluated (id != record.id).
    - Excludes incompatible units (does not convert across dissimilar dimensions).
    - Enforces minimum historical sample count (default: 2 records).
    - Returns (baseline_average, count, reason_or_status).
    - If historical data is insufficient (< min_records), returns (None, count, "Baseline unavailable").
    """
    if not record.site_id or not record.activity_id or not record.unit_id:
        return None, 0, "Missing site, activity, or unit configuration."

    min_records = 2
    if rule and rule.rule_parameters:
        min_records = int(rule.rule_parameters.get("min_baseline_records", 2))

    # Query comparable historical records
    comparable_qs = ActivityRecord.objects.filter(
        site_id=record.site_id,
        activity_id=record.activity_id,
        unit_id=record.unit_id,
    ).exclude(id=record.id)

    # Exclude invalid/unvalidated records if they have errors
    comparable_qs = comparable_qs.filter(
        status__in=[RecordStatus.READY, RecordStatus.SUBMITTED, RecordStatus.VERIFIED, RecordStatus.APPROVED]
    )

    count = comparable_qs.count()
    if count < min_records:
        return None, count, f"Insufficient historical records ({count} found, minimum {min_records} required)."

    # Compute aggregate average
    agg = comparable_qs.aggregate(avg_qty=models.Avg("quantity"))
    avg_qty = agg.get("avg_qty")

    if avg_qty is None:
        return None, count, "Unable to calculate historical average."

    return Decimal(str(round(avg_qty, 4))), count, f"Calculated from {count} comparable records."


def compute_period_variance_baseline(
    record: ActivityRecord,
) -> Tuple[Optional[Decimal], Optional[str]]:
    """
    Finds the most recent prior comparable record for period-over-period comparison.
    Returns (prior_quantity, prior_period_code).
    """
    if not record.site_id or not record.activity_id or not record.unit_id:
        return None, None

    prior_rec = (
        ActivityRecord.objects.filter(
            site_id=record.site_id,
            activity_id=record.activity_id,
            unit_id=record.unit_id,
        )
        .exclude(id=record.id)
        .filter(
            status__in=[RecordStatus.READY, RecordStatus.SUBMITTED, RecordStatus.VERIFIED, RecordStatus.APPROVED]
        )
        .order_by("-measurement_date", "-created_at")
        .first()
    )

    if not prior_rec:
        return None, None

    prior_period_code = prior_rec.reporting_period.code if prior_rec.reporting_period else ""
    return Decimal(str(prior_rec.quantity)), prior_period_code


# -----------------------------------------------------------------------------
# 3. DETERMINISTIC RULE EVALUATION IMPLEMENTATIONS
# -----------------------------------------------------------------------------

def evaluate_historical_spike(
    record: ActivityRecord,
    rule: AnomalyRule,
) -> Optional[Dict[str, Any]]:
    """
    Category A: Historical Spike Detection.
    Evaluates whether current consumption significantly exceeds the site's historical baseline.
    """
    baseline, count, note = compute_historical_baseline(record, rule)
    if baseline is None:
        # Insufficient baseline -> no false anomaly
        return None

    if record.quantity is None:
        return None

    unit_sym = record.unit.symbol if record.unit else ""
    threshold_pct = rule.threshold_percentage or Decimal("100.00")

    if baseline == Decimal("0"):
        if record.quantity > Decimal("0"):
            return {
                "rule": rule,
                "severity": AnomalySeverity.HIGH,
                "observed_value": record.quantity,
                "baseline_value": baseline,
                "deviation_value": record.quantity,
                "deviation_percentage": None,
                "explanation": (
                    f"{record.activity.name} consumption of {record.quantity} {unit_sym} was recorded "
                    f"against a zero historical baseline ({count} prior records average 0 {unit_sym})."
                ),
                "context_data": {
                    "baseline_sample_size": count,
                    "baseline_type": "HISTORICAL_AVERAGE",
                    "unit": unit_sym,
                },
            }
        return None

    deviation = record.quantity - baseline
    variance_pct = (deviation / baseline) * Decimal("100.0")

    if variance_pct >= threshold_pct:
        # Assign risk severity based on magnitude
        extreme_threshold = Decimal(str(rule.rule_parameters.get("extreme_spike_percentage", 200.0)))
        if variance_pct >= extreme_threshold:
            severity = AnomalySeverity.CRITICAL
        elif variance_pct >= Decimal("150.0"):
            severity = AnomalySeverity.HIGH
        else:
            severity = rule.severity or AnomalySeverity.MEDIUM

        return {
            "rule": rule,
            "severity": severity,
            "observed_value": record.quantity,
            "baseline_value": baseline,
            "deviation_value": deviation,
            "deviation_percentage": Decimal(str(round(variance_pct, 2))),
            "explanation": (
                f"{record.activity.name} consumption of {record.quantity} {unit_sym} is "
                f"{variance_pct:.1f}% above the site's historical baseline of {baseline:.2f} {unit_sym} "
                f"(evaluated across {count} historical records)."
            ),
            "context_data": {
                "baseline_sample_size": count,
                "baseline_type": "HISTORICAL_AVERAGE",
                "unit": unit_sym,
                "threshold_percentage": float(threshold_pct),
            },
        }

    return None


def evaluate_historical_drop(
    record: ActivityRecord,
    rule: AnomalyRule,
) -> Optional[Dict[str, Any]]:
    """
    Category B: Historical Drop Detection.
    Evaluates whether current consumption is unusually lower than historical baseline.
    """
    baseline, count, note = compute_historical_baseline(record, rule)
    if baseline is None or baseline == Decimal("0"):
        return None

    if record.quantity is None:
        return None

    unit_sym = record.unit.symbol if record.unit else ""
    threshold_pct = rule.threshold_percentage or Decimal("50.00")

    if record.quantity >= baseline:
        return None

    drop_amount = baseline - record.quantity
    drop_pct = (drop_amount / baseline) * Decimal("100.0")

    if drop_pct >= threshold_pct:
        extreme_drop = Decimal(str(rule.rule_parameters.get("extreme_drop_percentage", 80.0)))
        severity = AnomalySeverity.HIGH if drop_pct >= extreme_drop else (rule.severity or AnomalySeverity.MEDIUM)

        return {
            "rule": rule,
            "severity": severity,
            "observed_value": record.quantity,
            "baseline_value": baseline,
            "deviation_value": -drop_amount,
            "deviation_percentage": Decimal(str(round(-drop_pct, 2))),
            "explanation": (
                f"{record.activity.name} consumption of {record.quantity} {unit_sym} is "
                f"{drop_pct:.1f}% below the site's historical baseline of {baseline:.2f} {unit_sym}. "
                f"May indicate incomplete telemetry entry, meter malfunction, or operational shutdown."
            ),
            "context_data": {
                "baseline_sample_size": count,
                "baseline_type": "HISTORICAL_AVERAGE",
                "unit": unit_sym,
                "threshold_percentage": float(threshold_pct),
            },
        }

    return None


def evaluate_period_variance(
    record: ActivityRecord,
    rule: AnomalyRule,
) -> Optional[Dict[str, Any]]:
    """
    Category C: Period-over-Period Variance Detection.
    Compares current consumption against the most recent prior comparable period.
    """
    prior_val, prior_period_code = compute_period_variance_baseline(record)
    if prior_val is None or record.quantity is None:
        return None

    unit_sym = record.unit.symbol if record.unit else ""
    threshold_pct = rule.threshold_percentage or Decimal("50.00")

    if prior_val == Decimal("0"):
        if record.quantity > Decimal("0"):
            return {
                "rule": rule,
                "severity": AnomalySeverity.MEDIUM,
                "observed_value": record.quantity,
                "baseline_value": prior_val,
                "deviation_value": record.quantity,
                "deviation_percentage": None,
                "explanation": (
                    f"{record.activity.name} shows consumption of {record.quantity} {unit_sym} following a "
                    f"zero-consumption measurement in the preceding period ({prior_period_code or 'prior record'})."
                ),
                "context_data": {
                    "prior_period": prior_period_code,
                    "unit": unit_sym,
                },
            }
        return None

    diff = record.quantity - prior_val
    variance_pct = (abs(diff) / prior_val) * Decimal("100.0")

    if variance_pct >= threshold_pct:
        direction = "increase" if diff > 0 else "decrease"
        severity = AnomalySeverity.HIGH if variance_pct >= Decimal("100.0") else (rule.severity or AnomalySeverity.MEDIUM)

        return {
            "rule": rule,
            "severity": severity,
            "observed_value": record.quantity,
            "baseline_value": prior_val,
            "deviation_value": diff,
            "deviation_percentage": Decimal(str(round((diff / prior_val) * Decimal("100.0"), 2))),
            "explanation": (
                f"{record.activity.name} reflects a {variance_pct:.1f}% {direction} compared with "
                f"the previous period ({prior_val:.2f} {unit_sym} in {prior_period_code or 'prior cycle'})."
            ),
            "context_data": {
                "prior_period": prior_period_code,
                "prior_value": float(prior_val),
                "unit": unit_sym,
                "threshold_percentage": float(threshold_pct),
            },
        }

    return None


def evaluate_duplicate_suspect(
    record: ActivityRecord,
    rule: AnomalyRule,
) -> Optional[Dict[str, Any]]:
    """
    Category D: Duplicate-Like Activity Detection.
    Detects potential duplicate entries based on matching dimensions (site, activity, unit, date, quantity, or evidence reference).
    """
    if not record.site_id or not record.activity_id or not record.unit_id or record.quantity is None:
        return None

    unit_sym = record.unit.symbol if record.unit else ""

    # Check 1: Duplicate evidence reference within the same reporting period
    if record.evidence_reference and record.reporting_period_id:
        dup_by_ref = (
            ActivityRecord.objects.filter(
                site_id=record.site_id,
                reporting_period_id=record.reporting_period_id,
                activity_id=record.activity_id,
                evidence_reference__iexact=record.evidence_reference.strip(),
            )
            .exclude(id=record.id)
            .first()
        )
        if dup_by_ref:
            return {
                "rule": rule,
                "severity": AnomalySeverity.HIGH,
                "observed_value": record.quantity,
                "baseline_value": dup_by_ref.quantity,
                "deviation_value": record.quantity - dup_by_ref.quantity,
                "deviation_percentage": Decimal("0.00") if record.quantity == dup_by_ref.quantity else None,
                "explanation": (
                    f"Duplicate document reference detected: Record #{dup_by_ref.id} shares identical "
                    f"evidence reference '{record.evidence_reference}' for {record.activity.name}."
                ),
                "context_data": {
                    "duplicate_record_id": dup_by_ref.id,
                    "matched_dimension": "EVIDENCE_REFERENCE",
                    "evidence_reference": record.evidence_reference,
                },
            }

    # Check 2: Identical quantity on identical measurement date
    if record.measurement_date:
        dup_by_date_qty = (
            ActivityRecord.objects.filter(
                site_id=record.site_id,
                activity_id=record.activity_id,
                unit_id=record.unit_id,
                measurement_date=record.measurement_date,
                quantity=record.quantity,
            )
            .exclude(id=record.id)
            .first()
        )
        if dup_by_date_qty:
            return {
                "rule": rule,
                "severity": AnomalySeverity.HIGH,
                "observed_value": record.quantity,
                "baseline_value": dup_by_date_qty.quantity,
                "deviation_value": Decimal("0.00"),
                "deviation_percentage": Decimal("0.00"),
                "explanation": (
                    f"Potential duplicate activity record detected: matches Record #{dup_by_date_qty.id} "
                    f"with identical quantity ({record.quantity} {unit_sym}) on date {record.measurement_date}."
                ),
                "context_data": {
                    "duplicate_record_id": dup_by_date_qty.id,
                    "matched_dimension": "DATE_AND_QUANTITY",
                    "measurement_date": record.measurement_date.isoformat(),
                },
            }

    return None


def evaluate_threshold_breach(
    record: ActivityRecord,
    rule: AnomalyRule,
) -> Optional[Dict[str, Any]]:
    """
    Category E: Threshold Breach Detection.
    Flags values exceeding configured absolute operational capacity or floor limits.
    """
    if record.quantity is None:
        return None

    unit_sym = record.unit.symbol if record.unit else ""
    params = rule.rule_parameters or {}

    max_qty = params.get("max_quantity")
    min_qty = params.get("min_quantity")

    if max_qty is not None:
        max_decimal = Decimal(str(max_qty))
        if record.quantity > max_decimal:
            diff = record.quantity - max_decimal
            pct = (diff / max_decimal) * Decimal("100.0") if max_decimal > 0 else None
            severity = AnomalySeverity.CRITICAL if record.quantity >= max_decimal * 2 else AnomalySeverity.HIGH

            return {
                "rule": rule,
                "severity": severity,
                "observed_value": record.quantity,
                "baseline_value": max_decimal,
                "deviation_value": diff,
                "deviation_percentage": Decimal(str(round(pct, 2))) if pct is not None else None,
                "explanation": (
                    f"{record.activity.name} quantity of {record.quantity} {unit_sym} breaches "
                    f"configured maximum operational threshold limit of {max_decimal} {unit_sym}."
                ),
                "context_data": {
                    "threshold_type": "MAXIMUM_LIMIT",
                    "max_threshold": float(max_decimal),
                    "unit": unit_sym,
                },
            }

    if min_qty is not None:
        min_decimal = Decimal(str(min_qty))
        if Decimal("0") < record.quantity < min_decimal:
            diff = min_decimal - record.quantity
            return {
                "rule": rule,
                "severity": AnomalySeverity.LOW,
                "observed_value": record.quantity,
                "baseline_value": min_decimal,
                "deviation_value": -diff,
                "deviation_percentage": Decimal(str(round(-(diff / min_decimal) * Decimal("100.0"), 2))),
                "explanation": (
                    f"{record.activity.name} quantity of {record.quantity} {unit_sym} falls below "
                    f"the operational reporting threshold floor of {min_decimal} {unit_sym}."
                ),
                "context_data": {
                    "threshold_type": "MINIMUM_FLOOR",
                    "min_threshold": float(min_decimal),
                    "unit": unit_sym,
                },
            }

    return None


def evaluate_intensity_anomaly(
    record: ActivityRecord,
    rule: AnomalyRule,
) -> Optional[Dict[str, Any]]:
    """
    Category F: Operational Intensity Anomaly.
    Where supporting operational denominator data exists, flags abnormal ratios.
    If denominator data is unavailable, reports baseline unavailable without generating false anomalies.
    """
    # Safe check: if no operational intensity configuration exists for activity, gracefully return None
    params = rule.rule_parameters or {}
    expected_daily_max = params.get("max_daily_rate")

    if expected_daily_max and record.quantity:
        max_rate = Decimal(str(expected_daily_max))
        if record.quantity > max_rate:
            unit_sym = record.unit.symbol if record.unit else ""
            diff = record.quantity - max_rate
            return {
                "rule": rule,
                "severity": AnomalySeverity.LOW,
                "observed_value": record.quantity,
                "baseline_value": max_rate,
                "deviation_value": diff,
                "deviation_percentage": Decimal(str(round((diff / max_rate) * Decimal("100.0"), 2))),
                "explanation": (
                    f"{record.activity.name} operational intensity of {record.quantity} {unit_sym} "
                    f"exceeds benchmark standard daily operational rate of {max_rate} {unit_sym}."
                ),
                "context_data": {
                    "benchmark_rate": float(max_rate),
                    "unit": unit_sym,
                },
            }

    return None


# Rule category dispatcher mapping
RULE_DISPATCHER = {
    AnomalyCategory.HISTORICAL_SPIKE: evaluate_historical_spike,
    AnomalyCategory.HISTORICAL_DROP: evaluate_historical_drop,
    AnomalyCategory.PERIOD_VARIANCE: evaluate_period_variance,
    AnomalyCategory.DUPLICATE_SUSPECT: evaluate_duplicate_suspect,
    AnomalyCategory.THRESHOLD_BREACH: evaluate_threshold_breach,
    AnomalyCategory.INTENSITY_ANOMALY: evaluate_intensity_anomaly,
}


# -----------------------------------------------------------------------------
# 4. REUSABLE ANOMALY DETECTION SERVICE (CORE ENGINE)
# -----------------------------------------------------------------------------

@transaction.atomic
def detect_anomalies_for_record(
    record: ActivityRecord,
    user=None,
    submission: Optional[Submission] = None,
    detection_run: Optional[AnomalyDetectionRun] = None,
    request=None,
) -> List[AnomalyRecord]:
    """
    Executes the deterministic Anomaly Engine across an ActivityRecord.

    Invariants:
    - Never mutates the underlying ActivityRecord quantity, date, or operational data.
    - Anomaly detection is a review signal, NOT automatic validation rejection.
    - Idempotent: Repeated runs update active findings rather than creating duplicate open entries.
    - Correction-aware: If a previously flagged record is corrected to normal, open anomalies are resolved.
    - Preserves rule code and rule version at time of evaluation for regulatory audit lineage.
    - Records AuthAuditLog event ANOMALY_DETECTED for newly flagged anomalies.
    """
    # Ensure canonical rules exist
    ensure_default_anomaly_rules()

    # Determine active rules applicable to this record
    applicable_rules = AnomalyRule.objects.filter(is_active=True).filter(
        models.Q(applicable_activity__isnull=True) | models.Q(applicable_activity=record.activity)
    )

    detected_anomalies = []

    for rule in applicable_rules:
        evaluator = RULE_DISPATCHER.get(rule.category)
        if not evaluator:
            continue

        finding = evaluator(record, rule)

        # Check existing open/acknowledged anomaly for this record + rule
        existing_anomaly = AnomalyRecord.objects.filter(
            activity_record=record,
            rule=rule,
            status__in=[AnomalyStatus.OPEN, AnomalyStatus.ACKNOWLEDGED],
        ).first()

        if finding:
            if existing_anomaly:
                # Update existing open anomaly with latest telemetry
                existing_anomaly.observed_value = finding["observed_value"]
                existing_anomaly.baseline_value = finding["baseline_value"]
                existing_anomaly.deviation_value = finding["deviation_value"]
                existing_anomaly.deviation_percentage = finding["deviation_percentage"]
                existing_anomaly.explanation = finding["explanation"]
                existing_anomaly.context_data = finding["context_data"]
                existing_anomaly.severity = finding["severity"]
                existing_anomaly.rule_version = rule.version
                if submission and not existing_anomaly.submission_id:
                    existing_anomaly.submission = submission
                if detection_run and not existing_anomaly.detection_run_id:
                    existing_anomaly.detection_run = detection_run
                existing_anomaly.save(
                    update_fields=[
                        "observed_value",
                        "baseline_value",
                        "deviation_value",
                        "deviation_percentage",
                        "explanation",
                        "context_data",
                        "severity",
                        "rule_version",
                        "submission",
                        "detection_run",
                        "updated_at",
                    ]
                )
                detected_anomalies.append(existing_anomaly)
            else:
                # Create new AnomalyRecord
                new_anomaly = AnomalyRecord.objects.create(
                    activity_record=record,
                    submission=submission,
                    detection_run=detection_run,
                    rule=rule,
                    rule_code=rule.code,
                    rule_version=rule.version,
                    severity=finding["severity"],
                    status=AnomalyStatus.OPEN,
                    observed_value=finding["observed_value"],
                    baseline_value=finding["baseline_value"],
                    deviation_value=finding["deviation_value"],
                    deviation_percentage=finding["deviation_percentage"],
                    explanation=finding["explanation"],
                    context_data=finding["context_data"],
                    is_active=True,
                )
                detected_anomalies.append(new_anomaly)

                # Log audit event
                log_auth_event(
                    event_type=AuthAuditLog.EventType.ANOMALY_DETECTED,
                    user=user,
                    resource_accessed=f"ActivityRecord:{record.id}:Anomaly:{new_anomaly.id}",
                    details=(
                        f"Anomaly [{new_anomaly.severity}] flagged on Record #{record.id} "
                        f"under Rule {rule.code} (v{rule.version}): {new_anomaly.explanation[:150]}"
                    ),
                    success=True,
                    request=request,
                )
                logger.info(
                    "Anomaly #%d [%s] detected for Record #%d under %s",
                    new_anomaly.id,
                    new_anomaly.severity,
                    record.id,
                    rule.code,
                )
        else:
            # Finding is None: If an open anomaly existed previously, the record was likely corrected
            if existing_anomaly:
                existing_anomaly.status = AnomalyStatus.RESOLVED
                existing_anomaly.resolution_action = "RESOLVED"
                existing_anomaly.review_comment = (
                    "Automatically resolved: updated telemetry complies with operational baseline."
                )
                existing_anomaly.is_active = False
                existing_anomaly.reviewed_at = timezone.now()
                existing_anomaly.reviewed_by = user
                existing_anomaly.save(
                    update_fields=[
                        "status",
                        "resolution_action",
                        "review_comment",
                        "is_active",
                        "reviewed_at",
                        "reviewed_by",
                        "updated_at",
                    ]
                )
                log_auth_event(
                    event_type=AuthAuditLog.EventType.ANOMALY_RESOLVED,
                    user=user,
                    resource_accessed=f"ActivityRecord:{record.id}:Anomaly:{existing_anomaly.id}",
                    details=f"Anomaly #{existing_anomaly.id} auto-resolved after telemetry normalization on Record #{record.id}.",
                    success=True,
                    request=request,
                )

    return detected_anomalies


# -----------------------------------------------------------------------------
# 5. BATCH ANOMALY DETECTION RUN
# -----------------------------------------------------------------------------

def run_batch_anomaly_detection(
    records_qs,
    user=None,
    scope_type="BATCH",
    submission: Optional[Submission] = None,
    site: Optional[Site] = None,
    period: Optional[ReportingPeriod] = None,
    request=None,
) -> AnomalyDetectionRun:
    """
    Executes anomaly detection across a queryset of ActivityRecords and records a DetectionRun instance.
    """
    start_time = time.time()
    next_run_number = 1
    last_run = AnomalyDetectionRun.objects.order_by("-id").first()
    if last_run:
        next_run_number = last_run.run_number + 1

    detection_run = AnomalyDetectionRun.objects.create(
        run_number=next_run_number,
        scope_type=scope_type,
        submission=submission,
        site=site,
        reporting_period=period,
        executed_by=user,
        status="IN_PROGRESS",
    )

    total_evaluated = 0
    total_flagged = 0

    records = list(
        records_qs.select_related(
            "site",
            "activity",
            "unit",
            "reporting_period",
        )
    )

    for record in records:
        total_evaluated += 1
        anomalies = detect_anomalies_for_record(
            record=record,
            user=user,
            submission=submission,
            detection_run=detection_run,
            request=request,
        )
        total_flagged += len(anomalies)

    duration_ms = int((time.time() - start_time) * 1000)

    detection_run.records_evaluated = total_evaluated
    detection_run.anomalies_detected = total_flagged
    detection_run.execution_duration_ms = duration_ms
    detection_run.status = "COMPLETED"
    detection_run.summary_message = (
        f"Anomaly evaluation completed: {total_flagged} anomalies identified across {total_evaluated} records "
        f"in {duration_ms} ms."
    )
    detection_run.save()

    log_auth_event(
        event_type=AuthAuditLog.EventType.ANOMALY_DETECTION_RUN,
        user=user,
        resource_accessed=f"AnomalyDetectionRun:{detection_run.id}",
        details=detection_run.summary_message,
        success=True,
        request=request,
    )

    return detection_run


# -----------------------------------------------------------------------------
# 6. QUERYSET SCOPING & OBJECT-LEVEL AUTHORIZATION (ANTI-IDOR)
# -----------------------------------------------------------------------------

def get_accessible_anomalies(user):
    """
    Returns QuerySet of AnomalyRecord instances accessible to the user based on RBAC scope.

    Strict organizational boundaries:
    - SITE_MANAGER: Confined exclusively to anomalies for assigned operational sites.
    - SUBSIDIARY_MANAGER: Confined to anomalies under child sites of assigned subsidiaries.
    - MEIL_OPERATOR / ESG_MANAGER / AUDITOR / Superuser: Confined to enterprise scope.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return AnomalyRecord.objects.none()

    base_qs = AnomalyRecord.objects.select_related(
        "activity_record",
        "activity_record__activity",
        "activity_record__activity__category",
        "activity_record__unit",
        "activity_record__site",
        "activity_record__site__project",
        "activity_record__site__project__subsidiary",
        "activity_record__site__project__subsidiary__company",
        "activity_record__reporting_period",
        "submission",
        "rule",
        "reviewed_by",
        "detection_run",
    )

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        accessible_companies = get_accessible_companies(user)
        return base_qs.filter(
            activity_record__site__project__subsidiary__company__in=accessible_companies
        ).order_by("-created_at")

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        accessible_subs = get_accessible_subsidiaries(user)
        return base_qs.filter(
            activity_record__site__project__subsidiary__in=accessible_subs
        ).order_by("-created_at")

    if user.has_role(Role.Code.SITE_MANAGER):
        accessible_sites = get_accessible_sites(user)
        return base_qs.filter(activity_record__site__in=accessible_sites).order_by("-created_at")

    return AnomalyRecord.objects.none()


def user_can_access_anomaly(user, anomaly: AnomalyRecord) -> bool:
    """Verifies object-level access authorization to an AnomalyRecord."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return get_accessible_anomalies(user).filter(pk=anomaly.pk).exists()


def user_can_review_anomaly(user, anomaly: AnomalyRecord) -> bool:
    """
    Evaluates whether a user has authority to execute review actions on an anomaly.

    Permitted roles:
    - SUBSIDIARY_MANAGER (for assigned subsidiary scope)
    - ESG_MANAGER & MEIL_OPERATOR (enterprise scope)
    - Superuser

    Prohibited:
    - SITE_MANAGER (view only, cannot dismiss/resolve/explain anomalies)
    - AUDITOR (strictly read-only assurance)
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser:
        return True

    # Auditor is strictly read-only
    if user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR):
        return False

    # Site manager cannot perform review actions on anomalies
    if user.has_role(Role.Code.SITE_MANAGER) and not (
        user.has_role(Role.Code.SUBSIDIARY_MANAGER)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.MEIL_OPERATOR)
    ):
        return False

    return (
        user.has_role(Role.Code.SUBSIDIARY_MANAGER)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.MEIL_OPERATOR)
    ) and user_can_access_anomaly(user, anomaly)


# -----------------------------------------------------------------------------
# 7. REVIEW LIFECYCLE ACTION SERVICES
# -----------------------------------------------------------------------------

@transaction.atomic
def execute_anomaly_review_action(
    anomaly: AnomalyRecord,
    action: str,
    comment: str,
    user,
    request=None,
) -> AnomalyRecord:
    """
    Executes a controlled review lifecycle state transition on an AnomalyRecord.

    Supported actions:
    - ACKNOWLEDGE: status -> ACKNOWLEDGED
    - EXPLAIN: status -> EXPLAINED (mandatory justification comment)
    - RESOLVE: status -> RESOLVED (mandatory resolution comment, is_active=False)
    - DISMISS: status -> DISMISSED (mandatory dismissal reason, is_active=False)

    Invariants:
    - Server-side authorization check (user_can_review_anomaly).
    - Prevents double-resolution or acting on terminal states.
    - Requires non-empty commentary for EXPLAIN, RESOLVE, and DISMISS.
    - Emits appropriate AuthAuditLog security and governance event.
    """
    if not user_can_review_anomaly(user, anomaly):
        raise PermissionDenied("You do not have authorization to review or update this anomaly.")

    locked_anomaly = AnomalyRecord.objects.select_for_update().get(pk=anomaly.pk)

    action = action.upper().strip()
    comment = comment.strip() if comment else ""

    if action in ["EXPLAIN", "RESOLVE", "DISMISS"] and not comment:
        raise ValidationError(f"A detailed explanation is mandatory to {action.lower()} this anomaly.")

    if locked_anomaly.status in [AnomalyStatus.RESOLVED, AnomalyStatus.DISMISSED]:
        raise ValidationError(
            f"Anomaly #{locked_anomaly.id} is already {locked_anomaly.get_status_display()} and cannot be modified."
        )

    now = timezone.now()

    if action == "ACKNOWLEDGE":
        locked_anomaly.status = AnomalyStatus.ACKNOWLEDGED
        locked_anomaly.resolution_action = "ACKNOWLEDGED"
        event_type = AuthAuditLog.EventType.ANOMALY_ACKNOWLEDGED
    elif action == "EXPLAIN":
        locked_anomaly.status = AnomalyStatus.EXPLAINED
        locked_anomaly.resolution_action = "EXPLAINED"
        event_type = AuthAuditLog.EventType.ANOMALY_EXPLAINED
    elif action == "RESOLVE":
        locked_anomaly.status = AnomalyStatus.RESOLVED
        locked_anomaly.resolution_action = "RESOLVED"
        locked_anomaly.is_active = False
        event_type = AuthAuditLog.EventType.ANOMALY_RESOLVED
    elif action == "DISMISS":
        locked_anomaly.status = AnomalyStatus.DISMISSED
        locked_anomaly.resolution_action = "DISMISSED"
        locked_anomaly.is_active = False
        event_type = AuthAuditLog.EventType.ANOMALY_DISMISSED
    else:
        raise ValidationError(f"Unknown anomaly review action '{action}'.")

    locked_anomaly.review_comment = comment
    locked_anomaly.reviewed_by = user
    locked_anomaly.reviewed_at = now
    locked_anomaly.save(
        update_fields=[
            "status",
            "resolution_action",
            "review_comment",
            "reviewed_by",
            "reviewed_at",
            "is_active",
            "updated_at",
        ]
    )

    log_auth_event(
        event_type=event_type,
        user=user,
        resource_accessed=f"ActivityRecord:{locked_anomaly.activity_record_id}:Anomaly:{locked_anomaly.id}",
        details=(
            f"Anomaly #{locked_anomaly.id} [{locked_anomaly.severity}] {action} by {user.username}. "
            f"Comment: {comment[:150] if comment else 'Acknowledged'}"
        ),
        success=True,
        request=request,
    )

    logger.info(
        "Anomaly #%d transitioned to %s by %s",
        locked_anomaly.id,
        locked_anomaly.status,
        user.username,
    )

    return locked_anomaly


# -----------------------------------------------------------------------------
# 8. ANOMALY METRICS AGGREGATION SERVICE
# -----------------------------------------------------------------------------

def get_anomaly_dashboard_metrics(user) -> Dict[str, Any]:
    """
    Calculates real metrics for the Anomaly Desk without fabrication.
    """
    accessible_anomalies = get_accessible_anomalies(user)

    total_count = accessible_anomalies.count()
    open_count = accessible_anomalies.filter(status=AnomalyStatus.OPEN).count()
    acknowledged_count = accessible_anomalies.filter(status=AnomalyStatus.ACKNOWLEDGED).count()
    explained_count = accessible_anomalies.filter(status=AnomalyStatus.EXPLAINED).count()
    resolved_count = accessible_anomalies.filter(status=AnomalyStatus.RESOLVED).count()
    dismissed_count = accessible_anomalies.filter(status=AnomalyStatus.DISMISSED).count()

    high_risk_count = accessible_anomalies.filter(
        severity__in=[AnomalySeverity.HIGH, AnomalySeverity.CRITICAL],
        status__in=[AnomalyStatus.OPEN, AnomalyStatus.ACKNOWLEDGED],
    ).count()

    return {
        "total_count": total_count,
        "open_count": open_count,
        "acknowledged_count": acknowledged_count,
        "explained_count": explained_count,
        "resolved_count": resolved_count,
        "dismissed_count": dismissed_count,
        "actionable_count": open_count + acknowledged_count,
        "high_risk_count": high_risk_count,
    }
