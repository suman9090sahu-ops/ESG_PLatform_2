"""
Authoritative ESG Validation Engine Service for MEIL ESG CONTROL TOWER.

Fulfills Phase 10 Requirements:
- Multi-layer Deterministic Validation Architecture (Layers 1-7)
  * Layer 1: Structural Validation (Quantity, Unit, Date, Site, Activity, Period)
  * Layer 2: Scope & Organizational Hierarchy (Site-Project-Subsidiary-Company Alignment, Active States)
  * Layer 3: Temporal Governance & Reporting Period Boundaries (Open Status, Date Range, Future Dates)
  * Layer 4: Activity Master & Unit Compatibility (Permissible Units, Physical Dimensions)
  * Layer 5: Supporting Evidence Requirements & Document Integrity (Mandatory Evidence, Taxonomy, Hashes)
  * Layer 6: Consistency & Deterministic Duplicate Checks (Non-negative, Zero-quantity Advisory, Duplicates)
  * Layer 7: Workflow & Submission Readiness
- Controlled Severity Model (ERROR, WARNING, INFO)
- Immutable Historical Validation Runs & Granular Field-Level Results Preservation
- Server-side RBAC & IDOR-safe Execution Guards
- Safe Rule Execution without eval() or exec()
"""

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.utils import timezone

from apps.core.activity_services import validate_activity_unit
from apps.core.auth_services import log_auth_event
from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Evidence,
    EvidenceStatus,
    MasterStatus,
    OrganizationStatus,
    PeriodStatus,
    RecordStatus,
    ReportingPeriod,
    Role,
    Site,
    UnitOfMeasure,
    ValidationCategory,
    ValidationResult,
    ValidationRule,
    ValidationRun,
    ValidationSeverity,
    ValidationStatus,
)
from apps.core.scope_services import user_can_access_site

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. DATA TRANSFER OBJECT (DTO) FOR ENGINE RESULTS
# -----------------------------------------------------------------------------

@dataclass
class ValidationFinding:
    """Represents a discrete rule outcome produced during engine evaluation."""
    rule_code: str
    severity: str
    message: str
    field_name: str = ""
    is_blocking: bool = False
    context_data: dict = field(default_factory=dict)


# -----------------------------------------------------------------------------
# 2. DETERMINISTIC VALIDATION LOGIC BY LAYER
# -----------------------------------------------------------------------------

# --- Layer 1: Structural Validators ---

def check_struct_req_quantity(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if record.quantity is None:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message="Consumption quantity is required.",
            field_name="quantity",
            is_blocking=rule.is_blocking,
        )
    return None


def check_struct_req_unit(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.unit_id:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message="Unit of measure is required.",
            field_name="unit",
            is_blocking=rule.is_blocking,
        )
    return None


def check_struct_req_date(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.measurement_date:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message="Measurement date is required.",
            field_name="measurement_date",
            is_blocking=rule.is_blocking,
        )
    return None


def check_struct_req_site(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.site_id:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message="Operational site is required.",
            field_name="site",
            is_blocking=rule.is_blocking,
        )
    return None


def check_struct_req_activity(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.activity_id:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message="Activity definition is required.",
            field_name="activity",
            is_blocking=rule.is_blocking,
        )
    return None


def check_struct_req_period(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.reporting_period_id:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message="Reporting period is required.",
            field_name="reporting_period",
            is_blocking=rule.is_blocking,
        )
    return None


# --- Layer 2: Scope & Hierarchy Validators ---

def check_scope_site_hierarchy(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.site_id:
        return None
    site = record.site
    try:
        project = site.project
        subsidiary = project.subsidiary
        company = subsidiary.company
        if not (project and subsidiary and company):
            raise AttributeError("Broken hierarchy link")
    except Exception as e:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=f"Site organizational hierarchy is broken: {e}",
            field_name="site",
            is_blocking=rule.is_blocking,
        )
    return None


def check_scope_period_company(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not (record.site_id and record.reporting_period_id):
        return None
    site_company = record.site.project.subsidiary.company
    period_company = record.reporting_period.company
    if site_company.id != period_company.id:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=(
                f"Reporting period enterprise company '{period_company.name}' does not match "
                f"the operational site's company '{site_company.name}'."
            ),
            field_name="reporting_period",
            is_blocking=rule.is_blocking,
            context_data={"site_company": site_company.name, "period_company": period_company.name},
        )
    if record.reporting_period.subsidiary_id:
        site_subsidiary = record.site.project.subsidiary
        if record.reporting_period.subsidiary_id != site_subsidiary.id:
            return ValidationFinding(
                rule_code=rule.code,
                severity=rule.severity,
                message=(
                    f"Reporting period subsidiary '{record.reporting_period.subsidiary.name}' does not match "
                    f"the operational site's division '{site_subsidiary.name}'."
                ),
                field_name="reporting_period",
                is_blocking=rule.is_blocking,
                context_data={"site_subsidiary": site_subsidiary.name, "period_subsidiary": record.reporting_period.subsidiary.name},
            )
    return None


def check_scope_site_active(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.site_id:
        return None
    if record.site.status != OrganizationStatus.ACTIVE:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=f"Operational site '{record.site.name}' ({record.site.code}) is inactive.",
            field_name="site",
            is_blocking=rule.is_blocking,
        )
    return None


def check_scope_activity_active(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.activity_id:
        return None
    if not record.activity.is_active:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=f"Activity definition '{record.activity.name}' ({record.activity.code}) is inactive.",
            field_name="activity",
            is_blocking=rule.is_blocking,
        )
    return None


# --- Layer 3: Period & Temporal Validators ---

def check_period_status_open(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.reporting_period_id:
        return None
    if record.reporting_period.status != PeriodStatus.OPEN:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=(
                f"Reporting period '{record.reporting_period.code}' is currently in "
                f"'{record.reporting_period.get_status_display()}' status. Records can only be validated in OPEN periods."
            ),
            field_name="reporting_period",
            is_blocking=rule.is_blocking,
            context_data={"period_status": record.reporting_period.status},
        )
    return None


def check_period_date_boundary(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not (record.reporting_period_id and record.measurement_date):
        return None
    start = record.reporting_period.start_date
    end = record.reporting_period.end_date
    if record.measurement_date < start or record.measurement_date > end:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=(
                f"Measurement date ({record.measurement_date}) falls outside the reporting cycle window: "
                f"{start} to {end}."
            ),
            field_name="measurement_date",
            is_blocking=rule.is_blocking,
            context_data={"measurement_date": str(record.measurement_date), "start_date": str(start), "end_date": str(end)},
        )
    return None


def check_period_future_date(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.measurement_date:
        return None
    today = timezone.now().date()
    if record.measurement_date > today:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=f"Measurement date ({record.measurement_date}) is in the future relative to server date ({today}).",
            field_name="measurement_date",
            is_blocking=rule.is_blocking,
            context_data={"measurement_date": str(record.measurement_date), "today": str(today)},
        )
    return None


# --- Layer 4: Activity & Unit Compatibility Validators ---

def check_act_permissible_unit(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not (record.activity_id and record.unit_id):
        return None
    if not validate_activity_unit(record.activity, record.unit):
        allowed_symbols = [record.activity.base_unit.symbol] + [u.symbol for u in record.activity.allowed_units.all()]
        allowed_str = ", ".join(dict.fromkeys(allowed_symbols))
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=(
                f"Unit '{record.unit.name} ({record.unit.symbol})' is not permissible for activity "
                f"'{record.activity.name}'. Approved units: {allowed_str}."
            ),
            field_name="unit",
            is_blocking=rule.is_blocking,
            context_data={"unit_symbol": record.unit.symbol, "allowed_units": allowed_str},
        )
    return None


def check_act_unit_dimension(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not (record.activity_id and record.unit_id):
        return None
    base_dim = record.activity.base_unit.dimension
    unit_dim = record.unit.dimension
    if base_dim != unit_dim:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=(
                f"Physical dimension '{record.unit.get_dimension_display()}' conflicts with activity's "
                f"base dimension '{record.activity.base_unit.get_dimension_display()}'."
            ),
            field_name="unit",
            is_blocking=rule.is_blocking,
            context_data={"unit_dimension": unit_dim, "base_dimension": base_dim},
        )
    return None


# --- Layer 5: Evidence Validators ---

def check_evid_mandatory_check(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.activity_id:
        return None

    # Check whether evidence is required by:
    # 1. ActivityMaster JSON rules
    # 2. Rule parameters (e.g. mandatory_activities list)
    # 3. Specific fuel / utility activities that mandate compliance evidence
    act_rules = record.activity.validation_rules or {}
    rule_params = rule.rule_parameters or {}

    is_mandatory = False
    if act_rules.get("evidence_required") is True:
        is_mandatory = True
    elif act_rules.get("evidence_mandatory") is True:
        is_mandatory = True
    elif record.activity.code in rule_params.get("mandatory_activities", []):
        is_mandatory = True
    elif record.activity.code in ["FUEL-DIESEL-STAT", "ELEC-GRID", "WASTE-HAZARDOUS"]:
        is_mandatory = True
    elif rule.applicable_activity_id == record.activity_id:
        is_mandatory = True

    active_evidence_count = record.evidence_files.filter(status=EvidenceStatus.ACTIVE).count()

    if is_mandatory and active_evidence_count == 0:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=(
                f"Supporting audit evidence (e.g. utility bill, fuel challan, or weighbridge receipt) "
                f"is mandatory for '{record.activity.name}' before submission."
            ),
            field_name="evidence",
            is_blocking=rule.is_blocking,
            context_data={"evidence_count": 0, "activity_code": record.activity.code},
        )

    if not is_mandatory and active_evidence_count == 0 and record.evidence_reference:
        return ValidationFinding(
            rule_code=rule.code,
            severity=ValidationSeverity.INFO,
            message=(
                f"Document reference '{record.evidence_reference}' is noted, but no physical file has been attached yet."
            ),
            field_name="evidence",
            is_blocking=False,
            context_data={"evidence_reference": record.evidence_reference},
        )

    return None


def check_evid_type_match(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not record.activity_id:
        return None

    act_rules = record.activity.validation_rules or {}
    rule_params = rule.rule_parameters or {}

    expected_types = (
        act_rules.get("required_evidence_types")
        or act_rules.get("evidence_taxonomy")
        or rule_params.get("expected_evidence_types")
    )
    if not expected_types:
        return None

    active_evidences = record.evidence_files.filter(status=EvidenceStatus.ACTIVE)
    if not active_evidences.exists():
        return None

    present_types = set(active_evidences.values_list("evidence_type", flat=True))
    if not present_types.intersection(set(expected_types)):
        expected_str = ", ".join(expected_types)
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=(
                f"Attached evidence document type(s) do not match recommended categories for {record.activity.name}. "
                f"Expected: {expected_str}."
            ),
            field_name="evidence",
            is_blocking=rule.is_blocking,
            context_data={"expected_types": expected_types, "present_types": list(present_types)},
        )
    return None


def check_evid_file_integrity(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    active_evidences = record.evidence_files.filter(status=EvidenceStatus.ACTIVE)
    corrupted = []
    for ev in active_evidences:
        if ev.file_size <= 0 or not ev.file_hash:
            corrupted.append(ev.original_filename)

    if corrupted:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=f"Detected invalid or corrupted evidence files: {', '.join(corrupted)}.",
            field_name="evidence",
            is_blocking=rule.is_blocking,
            context_data={"corrupted_files": corrupted},
        )
    return None


# --- Layer 6: Consistency & Duplicate Validators ---

def check_consist_positive_quantity(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if record.quantity is not None and record.quantity < 0:
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message="Consumption quantity cannot be negative.",
            field_name="quantity",
            is_blocking=rule.is_blocking,
            context_data={"quantity": str(record.quantity)},
        )
    return None


def check_consist_zero_quantity(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if record.quantity is not None and record.quantity == Decimal("0"):
        return ValidationFinding(
            rule_code=rule.code,
            severity=rule.severity,
            message=(
                f"Zero consumption recorded for '{record.activity.name}'. "
                "Confirm whether equipment or site facilities were idle or offline during this interval."
            ),
            field_name="quantity",
            is_blocking=rule.is_blocking,
            context_data={"quantity": "0"},
        )
    return None


def check_consist_duplicate_check(record: ActivityRecord, rule: ValidationRule) -> Optional[ValidationFinding]:
    if not (record.site_id and record.activity_id and record.measurement_date):
        return None

    # Deterministic query: same site, activity, measurement date
    qs = ActivityRecord.objects.filter(
        site_id=record.site_id,
        activity_id=record.activity_id,
        measurement_date=record.measurement_date,
    )
    if record.id:
        qs = qs.exclude(id=record.id)

    # If reference provided, exact match on reference
    if record.evidence_reference:
        ref_match = qs.filter(evidence_reference=record.evidence_reference).first()
        if ref_match:
            return ValidationFinding(
                rule_code=rule.code,
                severity=rule.severity,
                message=(
                    f"Duplicate telemetry entry: Existing Record #{ref_match.id} has identical site, "
                    f"activity, measurement date ({record.measurement_date}), and document reference '{record.evidence_reference}'."
                ),
                field_name="evidence_reference",
                is_blocking=rule.is_blocking,
                context_data={"duplicate_record_id": ref_match.id},
            )

    # General duplicate check on identical date and quantity
    if record.quantity is not None:
        qty_match = qs.filter(quantity=record.quantity).first()
        if qty_match:
            return ValidationFinding(
                rule_code=rule.code,
                severity=rule.severity,
                message=(
                    f"Potential duplicate operational entry: Record #{qty_match.id} exists with "
                    f"the same site, activity, date ({record.measurement_date}), and quantity ({record.quantity} {record.unit.symbol if record.unit else ''})."
                ),
                field_name="quantity",
                is_blocking=rule.is_blocking,
                context_data={"duplicate_record_id": qty_match.id},
            )

    return None


# --- Registry Mapping ---

RULE_REGISTRY = {
    # Layer 1: Structural
    "STRUCT_REQ_QUANTITY": check_struct_req_quantity,
    "STRUCT_REQ_UNIT": check_struct_req_unit,
    "STRUCT_REQ_DATE": check_struct_req_date,
    "STRUCT_REQ_SITE": check_struct_req_site,
    "STRUCT_REQ_ACTIVITY": check_struct_req_activity,
    "STRUCT_REQ_PERIOD": check_struct_req_period,
    # Layer 2: Scope
    "SCOPE_SITE_HIERARCHY": check_scope_site_hierarchy,
    "SCOPE_PERIOD_COMPANY": check_scope_period_company,
    "SCOPE_SITE_ACTIVE": check_scope_site_active,
    "SCOPE_ACTIVITY_ACTIVE": check_scope_activity_active,
    # Layer 3: Period
    "PERIOD_STATUS_OPEN": check_period_status_open,
    "PERIOD_DATE_BOUNDARY": check_period_date_boundary,
    "PERIOD_FUTURE_DATE": check_period_future_date,
    # Layer 4: Activity
    "ACT_PERMISSIBLE_UNIT": check_act_permissible_unit,
    "ACT_UNIT_DIMENSION": check_act_unit_dimension,
    # Layer 5: Evidence
    "EVID_MANDATORY_CHECK": check_evid_mandatory_check,
    "EVID_TYPE_MATCH": check_evid_type_match,
    "EVID_FILE_INTEGRITY": check_evid_file_integrity,
    # Layer 6: Consistency
    "CONSIST_POSITIVE_QUANTITY": check_consist_positive_quantity,
    "CONSIST_ZERO_QUANTITY": check_consist_zero_quantity,
    "CONSIST_DUPLICATE_CHECK": check_consist_duplicate_check,
}


# -----------------------------------------------------------------------------
# 3. CORE VALIDATION ENGINE EXECUTION
# -----------------------------------------------------------------------------

def execute_validation_run(
    record: ActivityRecord,
    executed_by=None,
    request=None,
) -> ValidationRun:
    """
    Executes a comprehensive, deterministic validation evaluation for an ActivityRecord.

    Steps:
    1. Loads all applicable active ValidationRules.
    2. Runs each rule in order through the deterministic validator pipeline.
    3. Aggregates findings into ERROR, WARNING, INFO.
    4. Computes composite ValidationStatus (VALID, WARNING, INVALID).
    5. Atomically creates ValidationRun and related ValidationResults.
    6. Updates record.validation_status and record.last_validated_at.
    7. Logs immutable security and governance audit event to AuthAuditLog.
    """
    start_time = time.perf_counter()

    # Pre-fetch relations if needed
    if not record.id:
        record.refresh_from_db()

    # Get applicable active rules (enterprise-wide OR specific to this activity)
    rules_qs = ValidationRule.objects.filter(is_active=True).filter(
        models.Q(applicable_activity__isnull=True) | models.Q(applicable_activity_id=record.activity_id)
    ).order_by("category", "code")

    rules = list(rules_qs)
    findings: List[ValidationFinding] = []
    rule_snapshots = {}

    for rule in rules:
        rule_snapshots[rule.code] = {
            "name": rule.name,
            "version": rule.version,
            "severity": rule.severity,
            "category": rule.category,
            "is_blocking": rule.is_blocking,
        }
        handler = RULE_REGISTRY.get(rule.code)
        if handler:
            finding = handler(record, rule)
            if finding:
                findings.append(finding)

    # Compute metric counts
    error_count = sum(1 for f in findings if f.severity == ValidationSeverity.ERROR)
    warning_count = sum(1 for f in findings if f.severity == ValidationSeverity.WARNING)
    info_count = sum(1 for f in findings if f.severity == ValidationSeverity.INFO)

    # Compute status
    if error_count > 0:
        final_status = ValidationStatus.INVALID
        summary = f"Validation Failed: {error_count} error(s), {warning_count} warning(s) detected."
    elif warning_count > 0:
        final_status = ValidationStatus.WARNING
        summary = f"Valid with Warnings: {warning_count} warning(s) noted."
    else:
        final_status = ValidationStatus.VALID
        summary = "Validation Passed: All structural, scope, period, and evidence rules satisfied."

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    with transaction.atomic():
        # Compute run number
        last_run = record.validation_runs.order_by("-run_number").first()
        run_number = (last_run.run_number + 1) if last_run else 1

        val_run = ValidationRun.objects.create(
            activity_record=record,
            run_number=run_number,
            status=final_status,
            total_rules_evaluated=len(rules),
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            summary_message=summary,
            executed_by=executed_by,
            execution_duration_ms=duration_ms,
            rule_version_snapshot=rule_snapshots,
        )

        # Bulk create results
        rule_map = {r.code: r for r in rules}
        result_objs = []
        for finding in findings:
            target_rule = rule_map.get(finding.rule_code)
            if not target_rule:
                continue
            result_objs.append(
                ValidationResult(
                    validation_run=val_run,
                    activity_record=record,
                    rule=target_rule,
                    severity=finding.severity,
                    is_blocking=finding.is_blocking,
                    field_name=finding.field_name,
                    message=finding.message,
                    context_data=finding.context_data,
                )
            )
        if result_objs:
            ValidationResult.objects.bulk_create(result_objs)

        # Update record state
        record.validation_status = final_status
        record.last_validated_at = val_run.executed_at

        # If record is in READY status and validation fails, revert to DRAFT
        if record.status == RecordStatus.READY and final_status == ValidationStatus.INVALID:
            record.status = RecordStatus.DRAFT

        record.save(update_fields=["validation_status", "last_validated_at", "status"])

    # Audit logging
    log_auth_event(
        user=executed_by,
        event_type=AuthAuditLog.EventType.VALIDATION_EXECUTED,
        resource_accessed=f"ActivityRecord:{record.id}:ValidationRun:{val_run.id}",
        details=f"Validation Run #{run_number} executed for Record #{record.id}. Status: {final_status}. {summary}",
        success=(final_status != ValidationStatus.INVALID),
        request=request,
    )
    logger.info("Validation run #%d for Record #%d completed: status=%s", run_number, record.id, final_status)

    return val_run


def validate_activity_record(record: ActivityRecord, executed_by=None, request=None) -> ValidationRun:
    """Convenience alias for execute_validation_run."""
    return execute_validation_run(record, executed_by=executed_by, request=request)


def validate_activity_records(records_qs, executed_by=None, request=None) -> dict:
    """
    Evaluates validation rules across a queryset of ActivityRecords.
    Returns summary dictionary with aggregate telemetry.
    """
    total = 0
    passed = 0
    warnings = 0
    failed = 0
    runs = []

    for record in records_qs:
        total += 1
        run = execute_validation_run(record, executed_by=executed_by, request=request)
        runs.append(run)
        if run.status == ValidationStatus.VALID:
            passed += 1
        elif run.status == ValidationStatus.WARNING:
            warnings += 1
        else:
            failed += 1

    return {
        "total_evaluated": total,
        "valid_count": passed,
        "warning_count": warnings,
        "invalid_count": failed,
        "total": total,
        "valid": passed,
        "warning": warnings,
        "invalid": failed,
        "runs": runs,
    }


# -----------------------------------------------------------------------------
# 4. RBAC & PERMISSION EVALUATORS
# -----------------------------------------------------------------------------

def user_can_validate_record(user, record: ActivityRecord) -> bool:
    """
    Evaluates whether a user is authorized to execute validation on an ActivityRecord.
    - SITE_MANAGER: Authorized ONLY if assigned to the operational site.
    - SUBSIDIARY_MANAGER: Authorized if child site under assigned subsidiary.
    - MEIL_OPERATOR / ESG_MANAGER / Superuser: Enterprise authorization.
    - AUDITOR: Read-only assurance (cannot trigger validation state mutation).
    """
    if not user or not user.is_authenticated or not user.is_active or not record:
        return False

    if user.has_role(Role.Code.AUDITOR) and not (user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)):
        return False

    # Check access to the underlying site
    return user_can_access_site(user, record.site)


def user_can_view_validation_rules(user) -> bool:
    """
    Validation rules catalog is viewable by Governance, Assurance, and Supervisory roles:
    - ESG_MANAGER, MEIL_OPERATOR, AUDITOR, SUBSIDIARY_MANAGER.
    - Site Managers execute validation and view record results, but do not access the rules governance ledger.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return bool(
        user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
        or user.has_role(Role.Code.SUBSIDIARY_MANAGER)
    )


def user_can_manage_validation_rules(user) -> bool:
    """
    Only ESG Governance roles (ESG_MANAGER, MEIL_OPERATOR, Superuser) can alter rules.
    Site Managers, Subsidiary Managers, and Auditors are strictly prohibited.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    return (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
    )


# -----------------------------------------------------------------------------
# 5. STANDARD VALIDATION RULES SEEDER
# -----------------------------------------------------------------------------

STANDARD_VALIDATION_RULES = [
    # Layer 1: Structural
    {
        "code": "STRUCT_REQ_QUANTITY",
        "name": "Quantity Mandatory",
        "category": ValidationCategory.STRUCTURAL,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Verifies that consumption or operational quantity is explicitly specified.",
    },
    {
        "code": "STRUCT_REQ_UNIT",
        "name": "Unit of Measure Mandatory",
        "category": ValidationCategory.STRUCTURAL,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Verifies that an authoritative physical unit of measure is attached.",
    },
    {
        "code": "STRUCT_REQ_DATE",
        "name": "Measurement Date Mandatory",
        "category": ValidationCategory.STRUCTURAL,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Verifies that the date of physical observation or billing is recorded.",
    },
    {
        "code": "STRUCT_REQ_SITE",
        "name": "Operational Site Mandatory",
        "category": ValidationCategory.STRUCTURAL,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Verifies that the activity record is anchored to an approved operational site.",
    },
    {
        "code": "STRUCT_REQ_ACTIVITY",
        "name": "Activity Master Definition Mandatory",
        "category": ValidationCategory.STRUCTURAL,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Verifies that the activity record is bound to an active catalog activity.",
    },
    {
        "code": "STRUCT_REQ_PERIOD",
        "name": "Reporting Period Mandatory",
        "category": ValidationCategory.STRUCTURAL,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Verifies that the activity record is bound to a regulatory reporting period.",
    },
    # Layer 2: Scope
    {
        "code": "SCOPE_SITE_HIERARCHY",
        "name": "Site Organizational Hierarchy Alignment",
        "category": ValidationCategory.SCOPE,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Enforces unbroken relational hierarchy: Site -> Project -> Subsidiary -> Company.",
    },
    {
        "code": "SCOPE_PERIOD_COMPANY",
        "name": "Reporting Period Enterprise Match",
        "category": ValidationCategory.SCOPE,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Ensures the reporting period company matches the operational site's enterprise company.",
    },
    {
        "code": "SCOPE_SITE_ACTIVE",
        "name": "Operational Site Status Active",
        "category": ValidationCategory.SCOPE,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Ensures operational site is currently active in the organizational registry.",
    },
    {
        "code": "SCOPE_ACTIVITY_ACTIVE",
        "name": "Activity Definition Status Active",
        "category": ValidationCategory.SCOPE,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Prohibits logging or processing data against inactive or retired activity masters.",
    },
    # Layer 3: Period
    {
        "code": "PERIOD_STATUS_OPEN",
        "name": "Reporting Period Open Boundary",
        "category": ValidationCategory.PERIOD,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Prohibits recording or validating operational data inside closed, locked, or finalized periods.",
    },
    {
        "code": "PERIOD_DATE_BOUNDARY",
        "name": "Measurement Date Within Period Window",
        "category": ValidationCategory.PERIOD,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Enforces that the measurement date falls strictly within the reporting period start and end dates.",
    },
    {
        "code": "PERIOD_FUTURE_DATE",
        "name": "Future Measurement Date Advisory",
        "category": ValidationCategory.PERIOD,
        "severity": ValidationSeverity.WARNING,
        "is_blocking": False,
        "description": "Warns operational staff when measurement date occurs after the current calendar date.",
    },
    # Layer 4: Activity
    {
        "code": "ACT_PERMISSIBLE_UNIT",
        "name": "Permissible Unit for Activity",
        "category": ValidationCategory.ACTIVITY,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Ensures unit of measure belongs to the approved allowed unit set for the Activity Master.",
    },
    {
        "code": "ACT_UNIT_DIMENSION",
        "name": "Unit Physical Dimension Consistency",
        "category": ValidationCategory.ACTIVITY,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Enforces dimensional consistency (volume, mass, energy) matching the activity base unit.",
    },
    # Layer 5: Evidence
    {
        "code": "EVID_MANDATORY_CHECK",
        "name": "Mandatory Supporting Audit Evidence",
        "category": ValidationCategory.EVIDENCE,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Verifies that active supporting evidence documents (invoices, challans) are attached when required.",
        "rule_parameters": {
            "mandatory_activities": ["FUEL-DIESEL-STAT", "ELEC-GRID", "WASTE-HAZARDOUS"]
        },
    },
    {
        "code": "EVID_TYPE_MATCH",
        "name": "Evidence Document Taxonomy Alignment",
        "category": ValidationCategory.EVIDENCE,
        "severity": ValidationSeverity.WARNING,
        "is_blocking": False,
        "description": "Checks whether attached evidence documents match the recommended category taxonomy.",
    },
    {
        "code": "EVID_FILE_INTEGRITY",
        "name": "Evidence File Integrity & Cryptographic Hash",
        "category": ValidationCategory.EVIDENCE,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Verifies that attached evidence documents have positive file size and cryptographic SHA-256 fingerprint.",
    },
    # Layer 6: Consistency
    {
        "code": "CONSIST_POSITIVE_QUANTITY",
        "name": "Non-Negative Consumption Quantity",
        "category": ValidationCategory.CONSISTENCY,
        "severity": ValidationSeverity.ERROR,
        "is_blocking": True,
        "description": "Strictly prohibits negative physical consumption quantities.",
    },
    {
        "code": "CONSIST_ZERO_QUANTITY",
        "name": "Zero Consumption Advisory Check",
        "category": ValidationCategory.CONSISTENCY,
        "severity": ValidationSeverity.WARNING,
        "is_blocking": False,
        "description": "Flags zero consumption for operational review to confirm equipment dormancy.",
    },
    {
        "code": "CONSIST_DUPLICATE_CHECK",
        "name": "Deterministic Duplicate Telemetry Check",
        "category": ValidationCategory.CONSISTENCY,
        "severity": ValidationSeverity.WARNING,
        "is_blocking": False,
        "description": "Detects potential duplicate entries sharing identical site, activity, date, and invoice reference.",
    },
]


def seed_standard_validation_rules(user=None) -> int:
    """
    Seeds standard deterministic rules into the database if not present.
    Returns count of newly created rules.
    """
    created_count = 0
    for rdata in STANDARD_VALIDATION_RULES:
        rule, created = ValidationRule.objects.get_or_create(
            code=rdata["code"],
            defaults={
                "name": rdata["name"],
                "description": rdata.get("description", ""),
                "category": rdata["category"],
                "severity": rdata["severity"],
                "is_blocking": rdata.get("is_blocking", True),
                "rule_parameters": rdata.get("rule_parameters", {}),
                "is_active": True,
                "version": 1,
                "created_by": user,
                "updated_by": user,
            },
        )
        if created:
            created_count += 1
    return created_count
