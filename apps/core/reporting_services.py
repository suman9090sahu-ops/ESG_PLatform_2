"""
Reporting, Consolidation, and Traceability Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 20 Requirements:
- Real database-backed ESG aggregation & consolidation (Scope 1, Scope 2, Scope 3, Water, Waste)
- Standard GHG emission factor conversions with transparent regulatory methodology (IPCC / CEA / India GHG Program)
- ESG Manager Corporate Governance Dashboard data aggregation
- Auditor Independent Assurance Dashboard data aggregation (Read-only)
- 5-Layer "Trace This Number" audit lineage engine:
    1. Report / BRSR Disclosure Level
    2. Consolidated Enterprise / Subsidiary Level
    3. Verified Submission & Review Decisions Level (including Submitter, Verifier, and Correction history)
    4. Operational Site Telemetry & Deterministic Validation Level
    5. Supporting Audit Evidence Level (File integrity, SHA-256 cryptographic hash, OCR intelligence)
    6. Chronological Immutable Audit Trail (AuthAuditLog events)
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.auth_services import log_auth_event
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AnomalyRecord,
    AnomalyStatus,
    AuthAuditLog,
    Company,
    CorrectionRequest,
    Evidence,
    EvidenceStatus,
    OrganizationStatus,
    PeriodStatus,
    Project,
    RecordStatus,
    ReportingPeriod,
    Role,
    ScopeClassification,
    Site,
    Submission,
    SubmissionReview,
    SubmissionStatus,
    Subsidiary,
    ValidationStatus,
)
from apps.core.period_services import get_accessible_reporting_periods, get_current_reporting_period
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
    get_accessible_subsidiaries,
)
from apps.core.submission_services import get_accessible_submissions

logger = logging.getLogger("apps.core")

# -----------------------------------------------------------------------------
# 1. STANDARD REGULATORY EMISSION FACTORS & METHODOLOGY
# -----------------------------------------------------------------------------

# Standard India & International Regulatory Factors
# Stored as Decimal factors (kg CO2e per base unit)
EMISSION_FACTORS: Dict[str, Dict[str, Any]] = {
    # Fuel (Scope 1) - kg CO2e / Litre
    "FUEL-DIESEL-STAT": {
        "factor": Decimal("2.6800"),
        "factor_unit": "kg CO₂e / L",
        "scope": ScopeClassification.SCOPE_1,
        "source": "India GHG Program / IPCC 2006 Stationary Combustion",
        "methodology": "Quantity (L) × 2.68 kg CO₂e/L ÷ 1,000",
    },
    "FUEL-DIESEL-MOB": {
        "factor": Decimal("2.6800"),
        "factor_unit": "kg CO₂e / L",
        "scope": ScopeClassification.SCOPE_1,
        "source": "India GHG Program / IPCC 2006 Mobile Combustion",
        "methodology": "Quantity (L) × 2.68 kg CO₂e/L ÷ 1,000",
    },
    "FUEL-PETROL-MOB": {
        "factor": Decimal("2.3100"),
        "factor_unit": "kg CO₂e / L",
        "scope": ScopeClassification.SCOPE_1,
        "source": "India GHG Program / IPCC 2006 Mobile Combustion",
        "methodology": "Quantity (L) × 2.31 kg CO₂e/L ÷ 1,000",
    },
    # Electricity (Scope 2) - kg CO2e / kWh
    "ELEC-GRID": {
        "factor": Decimal("0.8200"),
        "factor_unit": "kg CO₂e / kWh",
        "scope": ScopeClassification.SCOPE_2,
        "source": "Central Electricity Authority (CEA) CO₂ Baseline Database v19 (National Weighted Average)",
        "methodology": "Quantity (kWh) × 0.82 kg CO₂e/kWh ÷ 1,000",
    },
    "ELEC-RENEWABLE-CAPTIVE": {
        "factor": Decimal("0.0000"),
        "factor_unit": "kg CO₂e / kWh",
        "scope": ScopeClassification.SCOPE_2,
        "source": "GHG Protocol Scope 2 Guidance (Zero-emission on-site renewable generation)",
        "methodology": "Renewable generation emission factor: 0.00 kg CO₂e/kWh",
    },
    # Water (Non-GHG Physical Resource)
    "WATER-GROUND": {
        "factor": Decimal("0.0000"),
        "factor_unit": "kL withdrawn",
        "scope": ScopeClassification.NON_GHG,
        "source": "SEBI BRSR Principle 6 (Water Withdrawal & Consumption)",
        "methodology": "Physical resource extraction volumetric ledger (kL)",
    },
    "WATER-MUNICIPAL": {
        "factor": Decimal("0.0000"),
        "factor_unit": "kL purchased",
        "scope": ScopeClassification.NON_GHG,
        "source": "SEBI BRSR Principle 6 (Purchased Third-Party Water)",
        "methodology": "Physical resource procurement volumetric ledger (kL)",
    },
    # Waste (Non-GHG Physical Metric / Scope 3 Cat 5)
    "WASTE-HAZARDOUS": {
        "factor": Decimal("0.0000"),
        "factor_unit": "kg generated",
        "scope": ScopeClassification.NON_GHG,
        "source": "SEBI BRSR Principle 6 (Hazardous Waste Handling)",
        "methodology": "Authorized hazardous waste manifest tracking",
    },
    "WASTE-NONHAZARDOUS": {
        "factor": Decimal("0.0000"),
        "factor_unit": "Tonnes generated",
        "scope": ScopeClassification.NON_GHG,
        "source": "SEBI BRSR Principle 6 (Non-Hazardous Waste & Scrap)",
        "methodology": "Weighbridge certified scrap & construction debris",
    },
}

DEFAULT_SCOPE1_FACTOR = Decimal("2.6800")
DEFAULT_SCOPE2_FACTOR = Decimal("0.8200")


def calculate_record_emissions(record: ActivityRecord) -> Dict[str, Any]:
    """
    Computes greenhouse gas emissions and standard regulatory metadata for an ActivityRecord.

    Returns dict containing:
    - emissions_tco2e: Decimal emissions in metric tonnes CO2e (or 0 for non-GHG)
    - emission_factor: Decimal factor value
    - factor_unit: string unit description
    - factor_source: string standard source
    - methodology: string formula representation
    - scope: ScopeClassification string
    """
    activity_code = record.activity.code if record.activity else ""
    qty = record.quantity or Decimal("0")
    unit_sym = record.unit.symbol if record.unit else ""

    info = EMISSION_FACTORS.get(activity_code)

    if not info:
        # Fallback to category / scope heuristics
        scope = record.activity.scope_classification if record.activity else ScopeClassification.SCOPE_1
        if scope == ScopeClassification.SCOPE_1:
            factor = DEFAULT_SCOPE1_FACTOR
            factor_unit = "kg CO₂e / unit"
            source = "IPCC 2006 Default Combustion Factor"
        elif scope == ScopeClassification.SCOPE_2:
            factor = DEFAULT_SCOPE2_FACTOR
            factor_unit = "kg CO₂e / kWh"
            source = "CEA CO₂ Baseline Database v19"
        else:
            factor = Decimal("0.0000")
            factor_unit = f"{unit_sym} logged"
            source = "Operational Physical Observation"
        methodology = f"Quantity ({qty} {unit_sym}) × {factor} {factor_unit} ÷ 1,000"
    else:
        factor = info["factor"]
        factor_unit = info["factor_unit"]
        scope = info["scope"]
        source = info["source"]
        methodology = info["methodology"]

    # Compute emissions in metric tonnes (1 tCO2e = 1,000 kg CO2e)
    if scope in [ScopeClassification.SCOPE_1, ScopeClassification.SCOPE_2, ScopeClassification.SCOPE_3]:
        # Handle MWh conversion if needed (1 MWh = 1,000 kWh)
        multiplier = Decimal("1.0")
        if unit_sym.upper() == "MWH":
            multiplier = Decimal("1000.0")
        elif unit_sym.upper() == "KL" and "DIESEL" in activity_code:
            multiplier = Decimal("1000.0")

        emissions_tco2e = (qty * multiplier * factor) / Decimal("1000.0")
    else:
        emissions_tco2e = Decimal("0.0000")

    return {
        "emissions_tco2e": round(emissions_tco2e, 4),
        "emission_factor": factor,
        "factor_unit": factor_unit,
        "factor_source": source,
        "methodology": methodology,
        "scope": scope,
    }


# -----------------------------------------------------------------------------
# 2. CONSOLIDATED ENTERPRISE REPORTING ENGINE
# -----------------------------------------------------------------------------

def get_consolidated_report(
    user,
    period_id: Optional[int] = None,
    subsidiary_id: Optional[int] = None,
    scope_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregates verified enterprise operational data across subsidiaries, projects, and sites.
    Applies authoritative emission factors to derive Scope 1, Scope 2, Scope 3, Water, and Waste totals.
    """
    # 1. Resolve Accessible Temporal Boundary
    accessible_periods = get_accessible_reporting_periods(user).order_by("-start_date")
    current_period = None
    if period_id:
        current_period = accessible_periods.filter(pk=period_id).first()
    if not current_period:
        today = timezone.localdate()
        current_period = (
            accessible_periods.filter(code="FY2025-26").first()
            or accessible_periods.filter(start_date__lte=today, end_date__gte=today, status=PeriodStatus.OPEN).first()
            or accessible_periods.filter(status=PeriodStatus.OPEN).order_by("start_date").first()
            or accessible_periods.first()
        )

    # 2. Resolve Accessible Subsidiaries
    accessible_subs = get_accessible_subsidiaries(user).select_related("company").order_by("name")
    if subsidiary_id:
        target_subs = accessible_subs.filter(pk=subsidiary_id)
    else:
        target_subs = accessible_subs

    # 3. Query Scoped Activity Records
    accessible_sites = get_accessible_sites(user).filter(project__subsidiary__in=target_subs)
    records_qs = ActivityRecord.objects.filter(
        site__in=accessible_sites,
    ).select_related(
        "site",
        "site__project",
        "site__project__subsidiary",
        "site__project__subsidiary__company",
        "reporting_period",
        "activity",
        "activity__category",
        "unit",
        "created_by",
        "updated_by",
    ).prefetch_related(
        "submissions",
        "submissions__reviews",
        "evidence_files",
    )

    if current_period:
        records_qs = records_qs.filter(reporting_period=current_period)

    # 4. Filter by Verified Status (for Governed Reporting)
    verified_records = records_qs.filter(
        status__in=[RecordStatus.VERIFIED, RecordStatus.APPROVED]
    ).order_by("-measurement_date")

    # Pending records awaiting verification
    pending_records = records_qs.filter(
        status=RecordStatus.SUBMITTED
    ).order_by("-measurement_date")

    # 5. Calculate Metrics & Line Items
    total_scope1_tco2e = Decimal("0.0000")
    total_scope2_tco2e = Decimal("0.0000")
    total_scope3_tco2e = Decimal("0.0000")
    total_water_kl = Decimal("0.0000")
    total_waste_tonnes = Decimal("0.0000")

    disclosures_list: List[Dict[str, Any]] = []

    for rec in verified_records:
        calc = calculate_record_emissions(rec)
        scope = calc["scope"]
        tco2e = calc["emissions_tco2e"]

        if scope == ScopeClassification.SCOPE_1:
            total_scope1_tco2e += tco2e
        elif scope == ScopeClassification.SCOPE_2:
            total_scope2_tco2e += tco2e
        elif scope == ScopeClassification.SCOPE_3:
            total_scope3_tco2e += tco2e
        elif "WATER" in rec.activity.code:
            total_water_kl += rec.quantity or Decimal("0")
        elif "WASTE" in rec.activity.code:
            total_waste_tonnes += rec.quantity or Decimal("0")

        # Find latest verified submission and review
        latest_sub = rec.submissions.order_by("-submission_number").first()
        latest_review = latest_sub.latest_review if latest_sub else None

        item = {
            "record": rec,
            "id": rec.id,
            "record_id": rec.id,
            "activity_name": rec.activity.name,
            "activity_code": rec.activity.code,
            "category": rec.activity.category.name if rec.activity.category else "General",
            "scope": scope,
            "subsidiary": rec.site.project.subsidiary,
            "project": rec.site.project,
            "site": rec.site,
            "measurement_date": rec.measurement_date,
            "quantity": rec.quantity,
            "formatted_value": f"{rec.quantity:,.4f}" if rec.quantity else "0.0000",
            "unit": rec.unit.symbol if rec.unit else "",
            "unit_symbol": rec.unit.symbol if rec.unit else "",
            "emissions_tco2e": tco2e,
            "calculated_emissions_tco2e": tco2e,
            "emission_factor": calc["emission_factor"],
            "factor_unit": calc["factor_unit"],
            "factor_source": calc["factor_source"],
            "methodology": calc["methodology"],
            "status": rec.status,
            "status_display": rec.get_status_display(),
            "latest_submission": latest_sub,
            "verified_by": latest_review.reviewer if latest_review else None,
            "verified_at": latest_review.created_at if latest_review else rec.updated_at,
            "evidence_count": rec.evidence_count,
            "has_evidence": rec.has_evidence,
            "validation_status": rec.validation_status,
            "trace_url": reverse("core:trace_number_detail", kwargs={"record_id": rec.id}),
        }
        disclosures_list.append(item)

    # Optional Scope Filtering on Disclosures List
    if scope_filter:
        scope_upper = scope_filter.upper()
        if scope_upper in ["SCOPE_1", "SCOPE 1"]:
            disclosures_list = [d for d in disclosures_list if d["scope"] == ScopeClassification.SCOPE_1]
        elif scope_upper in ["SCOPE_2", "SCOPE 2"]:
            disclosures_list = [d for d in disclosures_list if d["scope"] == ScopeClassification.SCOPE_2]
        elif scope_upper in ["SCOPE_3", "SCOPE 3"]:
            disclosures_list = [d for d in disclosures_list if d["scope"] == ScopeClassification.SCOPE_3]
        elif scope_upper in ["WATER"]:
            disclosures_list = [d for d in disclosures_list if "WATER" in d["activity_code"]]
        elif scope_upper in ["WASTE"]:
            disclosures_list = [d for d in disclosures_list if "WASTE" in d["activity_code"]]

    total_ghg_tco2e = total_scope1_tco2e + total_scope2_tco2e + total_scope3_tco2e

    # 6. Subsidiary Breakdown Aggregation
    subsidiary_breakdowns: List[Dict[str, Any]] = []
    for sub in target_subs:
        sub_records = [d for d in disclosures_list if d["subsidiary"].id == sub.id]
        sub_s1 = sum(d["emissions_tco2e"] for d in sub_records if d["scope"] == ScopeClassification.SCOPE_1)
        sub_s2 = sum(d["emissions_tco2e"] for d in sub_records if d["scope"] == ScopeClassification.SCOPE_2)
        sub_s3 = sum(d["emissions_tco2e"] for d in sub_records if d["scope"] == ScopeClassification.SCOPE_3)
        sub_water = sum(d["quantity"] for d in sub_records if "WATER" in d["activity_code"])
        sub_waste = sum(d["quantity"] for d in sub_records if "WASTE" in d["activity_code"])

        sub_projects_count = sub.projects.filter(status=OrganizationStatus.ACTIVE).count()
        sub_sites_count = Site.objects.filter(project__subsidiary=sub, status=OrganizationStatus.ACTIVE).count()
        sub_pending_count = pending_records.filter(site__project__subsidiary=sub).count()

        subsidiary_breakdowns.append({
            "subsidiary": sub,
            "projects_count": sub_projects_count,
            "sites_count": sub_sites_count,
            "verified_records_count": len(sub_records),
            "pending_count": sub_pending_count,
            "scope1_tco2e": round(sub_s1, 4),
            "scope2_tco2e": round(sub_s2, 4),
            "scope3_tco2e": round(sub_s3, 4),
            "total_ghg_tco2e": round(sub_s1 + sub_s2 + sub_s3, 4),
            "water_kl": round(sub_water, 2),
            "waste_tonnes": round(sub_waste, 2),
        })

    return {
        "current_period": current_period,
        "accessible_periods": accessible_periods,
        "accessible_subsidiaries": accessible_subs,
        "selected_subsidiary_id": subsidiary_id,
        "scope_filter": scope_filter,
        "total_verified_count": verified_records.count(),
        "total_pending_count": pending_records.count(),
        "total_scope1_tco2e": round(total_scope1_tco2e, 4),
        "total_scope2_tco2e": round(total_scope2_tco2e, 4),
        "total_scope3_tco2e": round(total_scope3_tco2e, 4),
        "total_ghg_tco2e": round(total_ghg_tco2e, 4),
        "total_water_kl": round(total_water_kl, 2),
        "total_waste_tonnes": round(total_waste_tonnes, 2),
        "disclosures": disclosures_list,
        "subsidiary_breakdowns": subsidiary_breakdowns,
    }


# -----------------------------------------------------------------------------
# 3. ESG MANAGER DASHBOARD CONTEXT PROVIDER
# -----------------------------------------------------------------------------

def get_esg_manager_dashboard_context(user) -> Dict[str, Any]:
    """
    Derives real database metrics for the ESG Manager Corporate Governance Dashboard.
    Zero synthetic or hardcoded numbers; all metrics reflect live database state.
    """
    report_data = get_consolidated_report(user)
    current_period = report_data["current_period"]

    accessible_companies = get_accessible_companies(user)
    accessible_subs = get_accessible_subsidiaries(user)
    accessible_sites = get_accessible_sites(user)

    # Submissions across user scope
    all_submissions = get_accessible_submissions(user)
    verified_submissions_count = all_submissions.filter(
        status__in=[SubmissionStatus.VERIFIED, SubmissionStatus.APPROVED]
    ).count()
    pending_submissions_count = all_submissions.filter(
        status=SubmissionStatus.SUBMITTED
    ).count()
    under_review_count = all_submissions.filter(
        status=SubmissionStatus.UNDER_REVIEW
    ).count()
    correction_requested_count = all_submissions.filter(
        status__in=[SubmissionStatus.CORRECTION_REQUESTED, SubmissionStatus.REJECTED]
    ).count()

    # Anomalies across enterprise scope
    anomalies_qs = AnomalyRecord.objects.filter(
        activity_record__site__in=accessible_sites
    ).select_related("rule", "activity_record", "activity_record__site", "activity_record__activity")

    open_anomalies_count = anomalies_qs.filter(status=AnomalyStatus.OPEN).count()
    total_anomalies_count = anomalies_qs.count()
    recent_anomalies = anomalies_qs.filter(status=AnomalyStatus.OPEN).order_by("-created_at")[:5]

    # Recent verified submissions table
    recent_verified = all_submissions.filter(
        status__in=[SubmissionStatus.VERIFIED, SubmissionStatus.APPROVED]
    ).select_related(
        "activity_record",
        "activity_record__activity",
        "activity_record__unit",
        "site",
        "site__project",
        "site__project__subsidiary",
        "submitted_by",
    ).prefetch_related("reviews", "reviews__reviewer").order_by("-updated_at")[:8]

    # Recent compliance audit logs
    recent_audit_events = AuthAuditLog.objects.filter(
        event_type__in=[
            AuthAuditLog.EventType.SUBMISSION_VERIFIED,
            AuthAuditLog.EventType.SUBMISSION_CREATED,
            AuthAuditLog.EventType.RESUBMISSION_CREATED,
            AuthAuditLog.EventType.CORRECTION_REQUESTED,
            AuthAuditLog.EventType.ANOMALY_DETECTED,
            AuthAuditLog.EventType.VALIDATION_EXECUTED,
        ]
    ).order_by("-created_at")[:6]

    return {
        "page_title": "ESG Manager Corporate Governance Dashboard",
        "page_subtitle": "Enterprise GHG Consolidation, Verification Pipeline & Disclosures",
        "active_nav": "esg_dashboard",
        "role_code": Role.Code.ESG_MANAGER,
        "current_period": current_period,
        "companies_count": accessible_companies.count(),
        "subsidiaries_count": accessible_subs.count(),
        "sites_count": accessible_sites.count(),
        # Emissions
        "total_scope1_tco2e": report_data["total_scope1_tco2e"],
        "total_scope2_tco2e": report_data["total_scope2_tco2e"],
        "total_scope3_tco2e": report_data["total_scope3_tco2e"],
        "total_ghg_tco2e": report_data["total_ghg_tco2e"],
        "total_water_kl": report_data["total_water_kl"],
        "total_waste_tonnes": report_data["total_waste_tonnes"],
        # Workflow Counts
        "verified_submissions_count": verified_submissions_count,
        "pending_submissions_count": pending_submissions_count,
        "under_review_count": under_review_count,
        "correction_requested_count": correction_requested_count,
        "open_anomalies_count": open_anomalies_count,
        "total_anomalies_count": total_anomalies_count,
        # Tables
        "subsidiary_breakdowns": report_data["subsidiary_breakdowns"],
        "recent_verified": recent_verified,
        "recent_anomalies": recent_anomalies,
        "recent_audit_events": recent_audit_events,
    }


# -----------------------------------------------------------------------------
# 4. AUDITOR ASSURANCE DASHBOARD CONTEXT PROVIDER
# -----------------------------------------------------------------------------

def get_auditor_dashboard_context(user) -> Dict[str, Any]:
    """
    Derives real database metrics for the Auditor Independent Assurance Dashboard.
    Enforces strict read-only assurance mode with full traceability links.
    """
    report_data = get_consolidated_report(user)
    current_period = report_data["current_period"]

    accessible_sites = get_accessible_sites(user)
    verified_disclosures = report_data["disclosures"]

    total_disclosures = len(verified_disclosures)
    with_evidence_count = sum(1 for d in verified_disclosures if d["has_evidence"])
    evidence_coverage_pct = round((with_evidence_count / total_disclosures * 100), 1) if total_disclosures > 0 else 0.0

    valid_conformance_count = sum(1 for d in verified_disclosures if d["validation_status"] == ValidationStatus.VALID)
    conformance_pct = round((valid_conformance_count / total_disclosures * 100), 1) if total_disclosures > 0 else 0.0

    # Anomalies count
    anomalies_qs = AnomalyRecord.objects.filter(
        activity_record__site__in=accessible_sites
    )
    open_findings_count = anomalies_qs.filter(status=AnomalyStatus.OPEN).count()

    # Recent Audit Log events
    recent_audit_trail = AuthAuditLog.objects.filter(
        event_type__in=[
            AuthAuditLog.EventType.SUBMISSION_VERIFIED,
            AuthAuditLog.EventType.CORRECTION_REQUESTED,
            AuthAuditLog.EventType.EVIDENCE_UPLOADED,
            AuthAuditLog.EventType.VALIDATION_EXECUTED,
            AuthAuditLog.EventType.ANOMALY_DETECTED,
        ]
    ).order_by("-created_at")[:8]

    return {
        "page_title": "Auditor Independent Assurance Dashboard",
        "page_subtitle": "Read-Only Governed Data, GHG Formula Lineage & Audit Trail Verification",
        "active_nav": "auditor_dashboard",
        "role_code": Role.Code.AUDITOR,
        "is_read_only": True,
        "current_period": current_period,
        "total_disclosures": total_disclosures,
        "total_ghg_tco2e": report_data["total_ghg_tco2e"],
        "total_scope1_tco2e": report_data["total_scope1_tco2e"],
        "total_scope2_tco2e": report_data["total_scope2_tco2e"],
        "evidence_coverage_pct": evidence_coverage_pct,
        "with_evidence_count": with_evidence_count,
        "conformance_pct": conformance_pct,
        "open_findings_count": open_findings_count,
        "disclosures": verified_disclosures,
        "subsidiary_breakdowns": report_data["subsidiary_breakdowns"],
        "recent_audit_trail": recent_audit_trail,
    }


# -----------------------------------------------------------------------------
# 5. 5-LAYER "TRACE THIS NUMBER" LINEAGE ENGINE
# -----------------------------------------------------------------------------

def get_trace_lineage_context(record_id: int, user=None) -> Dict[str, Any]:
    """
    Constructs the authoritative 5-tier audit lineage for an ESG metric / ActivityRecord.

    Tier 1: Regulatory ESG Report & BRSR Disclosure
    Tier 2: Consolidated Enterprise / Subsidiary Lineage
    Tier 3: Verified Submission & Governance Review Decisions (Submitter, Verifier, Corrections)
    Tier 4: Operational Site Telemetry & Deterministic Validation
    Tier 5: Supporting Audit Evidence & Cryptographic Checksum (SHA-256, OCR Intelligence)
    Tier 6: Chronological Audit Trail (AuthAuditLog events)
    """
    record = (
        ActivityRecord.objects.select_related(
            "site",
            "site__project",
            "site__project__subsidiary",
            "site__project__subsidiary__company",
            "reporting_period",
            "activity",
            "activity__category",
            "activity__base_unit",
            "unit",
            "created_by",
            "updated_by",
        )
        .prefetch_related(
            "submissions",
            "submissions__reviews",
            "submissions__reviews__reviewer",
            "submissions__correction_requests",
            "submissions__validation_run",
            "evidence_files",
            "evidence_files__uploaded_by",
            "evidence_files__ocr_runs",
            "evidence_files__ocr_runs__fields",
            "validation_runs",
            "validation_runs__results",
            "anomalies",
        )
        .filter(pk=record_id)
        .first()
    )

    if not record:
        return {}

    # Calculate emissions & formula lineage
    calc = calculate_record_emissions(record)

    # 1. REPORT LEVEL
    period = record.reporting_period
    company = record.site.project.subsidiary.company

    # 2. CONSOLIDATED DATA LEVEL
    subsidiary = record.site.project.subsidiary
    project = record.site.project
    site = record.site

    # 3. VERIFIED SUBMISSION LEVEL
    submissions = list(record.submissions.order_by("submission_number"))
    latest_submission = submissions[-1] if submissions else None
    primary_submission = (
        next((s for s in reversed(submissions) if s.is_verified), None)
        or latest_submission
    )

    all_reviews: List[SubmissionReview] = []
    for sub in submissions:
        all_reviews.extend(list(sub.reviews.all()))
    all_reviews.sort(key=lambda r: r.created_at)

    latest_review = all_reviews[-1] if all_reviews else None
    verifier_review = next((r for r in reversed(all_reviews) if r.action == "VERIFY"), None)

    # Correction requests
    all_corrections: List[CorrectionRequest] = []
    for sub in submissions:
        all_corrections.extend(list(sub.correction_requests.all()))
    all_corrections.sort(key=lambda c: c.created_at)

    had_corrections = len(all_corrections) > 0 or len(submissions) > 1

    # 4. SITE DATA LEVEL
    latest_val_run = record.latest_validation_run
    val_results = latest_val_run.results.select_related("rule").order_by("severity", "id") if latest_val_run else []

    # 5. EVIDENCE LEVEL
    evidence_files = list(record.evidence_files.all())
    evidence_details = []
    for ev in evidence_files:
        ocr_runs = list(ev.ocr_runs.order_by("-created_at"))
        latest_ocr = ocr_runs[0] if ocr_runs else None
        fields = list(latest_ocr.fields.all()) if latest_ocr else []

        evidence_details.append({
            "evidence": ev,
            "id": ev.id,
            "filename": ev.original_filename,
            "evidence_type": ev.evidence_type,
            "evidence_type_display": ev.get_evidence_type_display(),
            "file_size": ev.file_size,
            "file_hash": ev.file_hash,
            "uploaded_by": ev.uploaded_by,
            "created_at": ev.created_at,
            "status": ev.status,
            "download_url": reverse("core:evidence_download", kwargs={"evidence_id": ev.id}),
            "preview_url": reverse("core:evidence_preview", kwargs={"evidence_id": ev.id}),
            "detail_url": reverse("core:evidence_detail", kwargs={"evidence_id": ev.id}),
            "ocr_metadata": ev.ocr_metadata,
            "latest_ocr": latest_ocr,
            "ocr_fields": fields,
        })

    # 6. AUDIT TRAIL
    audit_events = AuthAuditLog.objects.filter(
        models.Q(resource_accessed__icontains=f"ActivityRecord:{record.id}")
        | models.Q(resource_accessed__icontains=f"Submission:{primary_submission.id if primary_submission else 0}")
    ).order_by("-created_at")[:15]

    return {
        "record": record,
        "calc": calc,
        # Layer 1: Report
        "layer1_report": {
            "period": period,
            "company": company,
            "metric_name": record.activity.name,
            "metric_code": record.activity.code,
            "scope": calc["scope"],
            "raw_quantity": record.quantity,
            "unit": record.unit.symbol if record.unit else "",
            "emissions_tco2e": calc["emissions_tco2e"],
            "emission_factor": calc["emission_factor"],
            "factor_unit": calc["factor_unit"],
            "factor_source": calc["factor_source"],
            "methodology": calc["methodology"],
        },
        # Layer 2: Consolidated Scope
        "layer2_consolidated": {
            "company": company,
            "subsidiary": subsidiary,
            "project": project,
            "site": site,
            "facility_type": site.facility_type,
            "location": site.location,
            "coordinates": f"{site.latitude}, {site.longitude}" if site.latitude and site.longitude else "—",
        },
        # Layer 3: Submission & Review Governance
        "layer3_submission": {
            "submissions": submissions,
            "primary_submission": primary_submission,
            "submission_number": primary_submission.submission_number if primary_submission else 1,
            "submitted_by": primary_submission.submitted_by if primary_submission else record.created_by,
            "submitted_at": primary_submission.submitted_at if primary_submission else record.created_at,
            "status": primary_submission.status if primary_submission else record.status,
            "status_display": primary_submission.get_status_display() if primary_submission else record.get_status_display(),
            "verifier": verifier_review.reviewer if verifier_review else (latest_review.reviewer if latest_review else None),
            "verified_at": verifier_review.created_at if verifier_review else (latest_review.created_at if latest_review else None),
            "review_comments": verifier_review.comments if verifier_review else (latest_review.comments if latest_review else ""),
            "all_reviews": all_reviews,
            "had_corrections": had_corrections,
            "corrections": all_corrections,
        },
        # Layer 4: Operational Site Telemetry & Validation
        "layer4_site_data": {
            "record_id": record.id,
            "measurement_date": record.measurement_date,
            "created_by": record.created_by,
            "created_at": record.created_at,
            "notes": record.notes,
            "evidence_reference": record.evidence_reference,
            "validation_status": record.validation_status,
            "latest_validation_run": latest_val_run,
            "validation_results": val_results,
        },
        # Layer 5: Evidence & Cryptographic Checksum
        "layer5_evidence": {
            "evidence_count": len(evidence_details),
            "has_evidence": len(evidence_details) > 0,
            "evidence_list": evidence_details,
        },
        # Layer 6: Audit Trail
        "audit_events": audit_events,
    }
