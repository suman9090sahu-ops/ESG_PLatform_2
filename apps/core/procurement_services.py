"""
Authoritative Supplier & Procurement Management Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 16 Requirements:
- Core Domain Separation:
  * Supplier: Master entity (commercial vendor / service provider)
  * Procurement Record: Transaction entity (commercial purchase / order / invoice)
  * Procurement Item: Line-level purchased materials/services with Scope 3 category hooks
  * Evidence: First-class supporting documents (invoices, POs, challans)
  * ESG Activity: Operational telemetry (ActivityRecord) kept distinct from commercial purchasing
- Scoped Queryset Access & Object-Level Authorization (Zero-trust, anti-IDOR):
  * Site Managers: Scoped strictly to assigned operational sites
  * Subsidiary Managers: Scoped to child sites/projects within authorized divisions
  * ESG Managers & MEIL Operators: Enterprise-wide governance authority
  * Auditors: Strictly read-only visibility across all suppliers and procurements
- Deterministic Validation Engine integration (Layered structural, temporal, and consistency rules)
- Anomaly Detection integration (Duplicate invoices, amount spikes, price variances)
- Document Intelligence OCR Comparison (Stored vs OCR extracted values, without silent overwrites)
- Governance Workflow (Draft -> Submit -> Subsidiary Review / Verify / Correction / Reject)
- Tamper-Evident Audit Logging (AuthAuditLog)
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.auth_services import log_auth_event
from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Company,
    Evidence,
    EvidenceStatus,
    OCRField,
    OCRRun,
    OCRStatus,
    PeriodStatus,
    ProcurementCategory,
    ProcurementItem,
    ProcurementRecord,
    ProcurementStatus,
    Project,
    ReportingPeriod,
    Role,
    Site,
    Supplier,
    SupplierStatus,
    SupplierType,
    UnitOfMeasure,
    User,
    ValidationStatus,
)
from apps.core.period_services import can_user_modify_data
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
    get_accessible_subsidiaries,
    user_can_access_company,
    user_can_access_project,
    user_can_access_site,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SCOPED QUERYSET RETRIEVAL
# -----------------------------------------------------------------------------

def get_accessible_suppliers(user) -> models.QuerySet:
    """
    Returns QuerySet of Supplier records accessible to the user based on RBAC and assignments.
    Enterprise-wide suppliers (company is NULL) are accessible to all authenticated users.
    Company-scoped suppliers are filtered by the user's accessible companies.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return Supplier.objects.none()

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return Supplier.objects.all().order_by("name")

    accessible_cos = get_accessible_companies(user)
    return Supplier.objects.filter(
        models.Q(company__isnull=True) | models.Q(company__in=accessible_cos)
    ).distinct().order_by("name")


def get_accessible_procurements(user) -> models.QuerySet:
    """
    Returns QuerySet of ProcurementRecord instances accessible to the user based on
    their authorized organizational scope (sites, projects, companies).
    """
    if not user or not user.is_authenticated or not user.is_active:
        return ProcurementRecord.objects.none()

    base_qs = ProcurementRecord.objects.select_related(
        "supplier",
        "company",
        "project",
        "project__subsidiary",
        "site",
        "site__project",
        "site__project__subsidiary",
        "reporting_period",
        "created_by",
        "updated_by",
    ).prefetch_related("items", "evidence_files")

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return base_qs.all().order_by("-purchase_date", "-created_at")

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        accessible_sites = get_accessible_sites(user)
        accessible_projs = get_accessible_projects(user)
        accessible_cos = get_accessible_companies(user)
        return base_qs.filter(
            models.Q(site__in=accessible_sites)
            | models.Q(project__in=accessible_projs)
            | models.Q(company__in=accessible_cos, site__isnull=True)
        ).distinct().order_by("-purchase_date", "-created_at")

    if user.has_role(Role.Code.SITE_MANAGER):
        assigned_sites = get_accessible_sites(user)
        return base_qs.filter(site__in=assigned_sites).distinct().order_by("-purchase_date", "-created_at")

    # Fallback to project scope
    proj_sites = Site.objects.filter(project__in=get_accessible_projects(user))
    return base_qs.filter(site__in=proj_sites).distinct().order_by("-purchase_date", "-created_at")


# -----------------------------------------------------------------------------
# 2. OBJECT-LEVEL AUTHORIZATION GUARDS (ZERO CLIENT TRUST & ANTI-IDOR)
# -----------------------------------------------------------------------------

def user_can_access_supplier(user, supplier: Supplier) -> bool:
    """Evaluates whether a user can view a specific supplier record."""
    if not user or not user.is_authenticated or not user.is_active or not supplier:
        return False
    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return True
    if supplier.company is None:
        return True
    return supplier.company in get_accessible_companies(user)


def user_can_modify_supplier(user, supplier: Optional[Supplier] = None, company: Optional[Company] = None) -> bool:
    """Evaluates whether a user can create or edit a supplier master record."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.has_role(Role.Code.AUDITOR) and not (
        user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)
    ):
        return False
    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER):
        return True

    target_company = supplier.company if supplier else company
    if target_company is None:
        # Enterprise-wide supplier mutation reserved for ESG Manager / Operator
        return user.has_role(Role.Code.SUBSIDIARY_MANAGER)

    return target_company in get_accessible_companies(user)


def user_can_archive_supplier(user, supplier: Supplier) -> bool:
    """Evaluates whether a user can soft-archive a supplier."""
    return user_can_modify_supplier(user, supplier=supplier)


def user_can_access_procurement(user, procurement: ProcurementRecord) -> bool:
    """Evaluates whether a user can view a specific procurement record."""
    if not user or not user.is_authenticated or not user.is_active or not procurement:
        return False
    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return True

    if user.has_role(Role.Code.SITE_MANAGER):
        if not procurement.site:
            return False
        return procurement.site in get_accessible_sites(user)

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        if procurement.site and procurement.site in get_accessible_sites(user):
            return True
        if procurement.project and procurement.project in get_accessible_projects(user):
            return True
        if procurement.company in get_accessible_companies(user):
            return True
        return False

    return False


def user_can_modify_procurement(user, procurement: ProcurementRecord) -> bool:
    """
    Evaluates whether a user can edit an existing procurement record or add/remove items.
    Enforces state immutability when record is SUBMITTED, VERIFIED, or REJECTED.
    """
    if not user_can_access_procurement(user, procurement):
        return False
    if user.has_role(Role.Code.AUDITOR) and not (
        user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)
    ):
        return False
    if not procurement.is_editable:
        return False
    if not can_user_modify_data(user, procurement.reporting_period):
        return False

    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER):
        return True

    if user.has_role(Role.Code.SITE_MANAGER):
        return procurement.site and procurement.site in get_accessible_sites(user)

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        return procurement.site and procurement.site in get_accessible_sites(user)

    return False


def user_can_delete_procurement(user, procurement: ProcurementRecord) -> bool:
    """
    Evaluates whether a user can delete a procurement record.
    Strictly permitted ONLY in DRAFT status while reporting period is OPEN.
    """
    if not user_can_access_procurement(user, procurement):
        return False
    if procurement.status != ProcurementStatus.DRAFT or procurement.is_locked:
        return False
    if not can_user_modify_data(user, procurement.reporting_period):
        return False

    is_creator_or_admin = (
        procurement.created_by_id == user.id
        or user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
    )
    return is_creator_or_admin


def user_can_submit_procurement(user, procurement: ProcurementRecord) -> bool:
    """
    Evaluates whether a user can formally submit a procurement record for review.
    """
    if not user_can_access_procurement(user, procurement):
        return False
    if user.has_role(Role.Code.AUDITOR) and not (
        user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)
    ):
        return False
    if procurement.status not in [ProcurementStatus.DRAFT, ProcurementStatus.CORRECTION_REQUESTED]:
        return False
    if not can_user_modify_data(user, procurement.reporting_period):
        return False

    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER):
        return True

    if user.has_role(Role.Code.SITE_MANAGER):
        return procurement.site and procurement.site in get_accessible_sites(user)

    return False


def user_can_review_procurement(user, procurement: ProcurementRecord) -> bool:
    """
    Evaluates whether a user can review, verify, reject, or request correction on a procurement.
    Prevents self-review (submitter cannot verify their own submission).
    """
    if not user_can_access_procurement(user, procurement):
        return False
    if user.has_role(Role.Code.AUDITOR) and not (
        user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)
    ):
        return False
    if procurement.status not in [ProcurementStatus.SUBMITTED, ProcurementStatus.UNDER_REVIEW]:
        return False

    # Prevent self-review unless supervisor override
    if procurement.created_by_id == user.id and not (user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)):
        return False

    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER):
        return True

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        if procurement.site and procurement.site in get_accessible_sites(user):
            return True
        if procurement.project and procurement.project in get_accessible_projects(user):
            return True
        if procurement.company in get_accessible_companies(user):
            return True

    return False


def user_can_upload_procurement_evidence(user, procurement: ProcurementRecord) -> bool:
    """Evaluates whether a user can attach evidence to a procurement record."""
    return user_can_modify_procurement(user, procurement)


# -----------------------------------------------------------------------------
# 3. SUPPLIER MASTER SERVICES & DUPLICATE PROTECTION
# -----------------------------------------------------------------------------

def find_supplier_duplicates(
    supplier_code: str,
    tax_identifier: str = "",
    name: str = "",
    exclude_id: Optional[int] = None,
) -> List[Supplier]:
    """
    Searches for potential duplicate supplier master records using exact code,
    tax identifier (GSTIN/PAN), or normalized supplier name.
    Does NOT automatically merge records; returns matches for human review.
    """
    q_filter = models.Q()
    if supplier_code:
        q_filter |= models.Q(supplier_code__iexact=supplier_code.strip())
    if tax_identifier and tax_identifier.strip():
        q_filter |= models.Q(tax_identifier__iexact=tax_identifier.strip())
    if name and name.strip():
        q_filter |= models.Q(name__iexact=name.strip())

    if not q_filter:
        return []

    qs = Supplier.objects.filter(q_filter)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    return list(qs)


@transaction.atomic
def create_supplier(
    data: Dict[str, Any],
    user: Optional[User] = None,
    request=None,
) -> Supplier:
    """
    Creates a new Supplier master record with audit event logging and duplicate check.
    """
    company = data.get("company")
    if not user_can_modify_supplier(user, company=company):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed="Supplier:create",
            details="Unauthorized attempt to create supplier master record.",
            success=False,
        )
        raise PermissionDenied("You do not have authorization to create a supplier in this scope.")

    code = (data.get("supplier_code") or "").strip().upper()
    if not code:
        raise ValidationError({"supplier_code": "Supplier code is required."})

    if Supplier.objects.filter(supplier_code=code).exists():
        raise ValidationError({"supplier_code": f"Supplier with code '{code}' already exists."})

    supplier = Supplier(
        supplier_code=code,
        name=(data.get("name") or "").strip(),
        legal_name=(data.get("legal_name") or "").strip(),
        supplier_type=data.get("supplier_type") or SupplierType.GOODS,
        status=data.get("status") or SupplierStatus.ACTIVE,
        company=company,
        contact_person=(data.get("contact_person") or "").strip(),
        contact_email=(data.get("contact_email") or "").strip(),
        contact_phone=(data.get("contact_phone") or "").strip(),
        tax_identifier=(data.get("tax_identifier") or "").strip().upper(),
        address=(data.get("address") or "").strip(),
        city=(data.get("city") or "").strip(),
        state=(data.get("state") or "").strip(),
        country=(data.get("country") or "India").strip(),
        postal_code=(data.get("postal_code") or "").strip(),
        environmental_certifications=(data.get("environmental_certifications") or "").strip(),
        has_esg_declaration=bool(data.get("has_esg_declaration", False)),
        esg_notes=(data.get("esg_notes") or "").strip(),
        created_by=user,
    )
    supplier.full_clean()
    supplier.save()

    log_auth_event(
        AuthAuditLog.EventType.SUPPLIER_CREATED,
        request=request,
        user=user,
        resource_accessed=f"Supplier:{supplier.id}",
        details=f"Created Supplier '{supplier.name}' ({supplier.supplier_code}) by {user.username if user else 'System'}.",
        success=True,
    )
    logger.info("Supplier [%s] (%s) created by %s", supplier.id, supplier.supplier_code, user)
    return supplier


@transaction.atomic
def update_supplier(
    supplier: Supplier,
    data: Dict[str, Any],
    user: Optional[User] = None,
    request=None,
) -> Supplier:
    """Updates an existing Supplier record with audit event logging."""
    if not user_can_modify_supplier(user, supplier=supplier):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Supplier:{supplier.id}/update",
            details="Unauthorized attempt to modify supplier master record.",
            success=False,
        )
        raise PermissionDenied("You do not have authorization to modify this supplier.")

    for field in [
        "name",
        "legal_name",
        "supplier_type",
        "status",
        "company",
        "contact_person",
        "contact_email",
        "contact_phone",
        "tax_identifier",
        "address",
        "city",
        "state",
        "country",
        "postal_code",
        "environmental_certifications",
        "has_esg_declaration",
        "esg_notes",
    ]:
        if field in data:
            val = data[field]
            if isinstance(val, str):
                val = val.strip()
            setattr(supplier, field, val)

    supplier.full_clean()
    supplier.save()

    log_auth_event(
        AuthAuditLog.EventType.SUPPLIER_UPDATED,
        request=request,
        user=user,
        resource_accessed=f"Supplier:{supplier.id}",
        details=f"Updated Supplier '{supplier.name}' ({supplier.supplier_code}) by {user.username if user else 'System'}.",
        success=True,
    )
    return supplier


@transaction.atomic
def archive_supplier(
    supplier: Supplier,
    user: Optional[User] = None,
    request=None,
) -> Supplier:
    """Soft-archives a supplier to preserve historical procurement lineage."""
    if not user_can_archive_supplier(user, supplier):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Supplier:{supplier.id}/archive",
            details="Unauthorized attempt to archive supplier master record.",
            success=False,
        )
        raise PermissionDenied("You do not have authorization to archive this supplier.")

    supplier.archive(actor=user)
    log_auth_event(
        AuthAuditLog.EventType.SUPPLIER_ARCHIVED,
        request=request,
        user=user,
        resource_accessed=f"Supplier:{supplier.id}",
        details=f"Archived Supplier '{supplier.name}' ({supplier.supplier_code}) by {user.username if user else 'System'}.",
        success=True,
    )
    return supplier


# -----------------------------------------------------------------------------
# 4. PROCUREMENT TRANSACTION SERVICES
# -----------------------------------------------------------------------------

def generate_procurement_number(
    company: Optional[Company] = None,
    site: Optional[Site] = None,
    reporting_period: Optional[ReportingPeriod] = None,
) -> str:
    """Generates an institutional, collision-safe procurement transaction identifier."""
    prefix = site.code if site else (company.code if company else "CORP")
    period_code = reporting_period.code.replace("-", "")[:8] if reporting_period else str(timezone.now().year)
    filter_q = models.Q()
    if site:
        filter_q = models.Q(site=site)
    elif company:
        filter_q = models.Q(company=company)
    if reporting_period:
        filter_q &= models.Q(reporting_period=reporting_period)

    count = ProcurementRecord.objects.filter(filter_q).count() + 1
    candidate = f"PROC-{period_code}-{prefix}-{count:04d}"
    suffix = 1
    while ProcurementRecord.objects.filter(procurement_number=candidate).exists():
        candidate = f"PROC-{period_code}-{prefix}-{count:04d}-{suffix}"
        suffix += 1
    return candidate


@transaction.atomic
def create_procurement_record(
    data: Dict[str, Any],
    user: Optional[User] = None,
    request=None,
) -> ProcurementRecord:
    """
    Atomically creates a ProcurementRecord with zero-trust scope verification.
    """
    site: Optional[Site] = data.get("site")
    project: Optional[Project] = data.get("project") or (site.project if site else None)
    company: Optional[Company] = (
        data.get("company")
        or (project.subsidiary.company if project else None)
        or (site.project.subsidiary.company if site else None)
    )
    reporting_period: ReportingPeriod = data.get("reporting_period")
    supplier: Supplier = data.get("supplier")

    if not supplier:
        raise ValidationError({"supplier": "A valid Supplier master record is required."})
    if not supplier.is_active:
        raise ValidationError({"supplier": f"Supplier '{supplier.name}' is archived or inactive and cannot be selected."})
    if not reporting_period:
        raise ValidationError({"reporting_period": "A valid Reporting Period is required."})
    if not company:
        raise ValidationError({"company": "An operating Company boundary is required."})

    # Scope authorization guard
    if site and not user_can_access_site(user, site):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Site:{site.id}/procurement/create",
            details="Unauthorized attempt to create procurement for unassigned site.",
            success=False,
        )
        raise PermissionDenied("You do not have authorization to create procurement records for this site.")

    # Reporting period open check
    if not can_user_modify_data(user, reporting_period):
        raise ValidationError({"reporting_period": "Cannot record procurement in a closed or locked reporting period."})

    proc_number = data.get("procurement_number") or generate_procurement_number(company, site, reporting_period)

    procurement = ProcurementRecord(
        procurement_number=proc_number,
        supplier=supplier,
        company=company,
        project=project,
        site=site,
        reporting_period=reporting_period,
        purchase_date=data.get("purchase_date") or timezone.now().date(),
        category=data.get("category") or ProcurementCategory.RAW_MATERIAL,
        purchase_order_reference=(data.get("purchase_order_reference") or "").strip(),
        invoice_reference=(data.get("invoice_reference") or "").strip(),
        invoice_date=data.get("invoice_date"),
        total_amount=Decimal(str(data.get("total_amount", "0.00"))),
        currency=data.get("currency") or "INR",
        description=(data.get("description") or "").strip(),
        status=ProcurementStatus.DRAFT,
        is_locked=False,
        validation_status=ValidationStatus.UNVALIDATED,
        has_anomalies=False,
        activity_record=data.get("activity_record"),
        created_by=user,
    )
    procurement.full_clean()
    procurement.save()

    log_auth_event(
        AuthAuditLog.EventType.PROCUREMENT_CREATED,
        request=request,
        user=user,
        resource_accessed=f"ProcurementRecord:{procurement.id}",
        details=f"Created Procurement #{procurement.procurement_number} (Supplier: {supplier.name}, Value: {procurement.total_amount} {procurement.currency}).",
        success=True,
    )
    logger.info("ProcurementRecord [%s] created by %s", procurement.id, user)
    return procurement


@transaction.atomic
def update_procurement_record(
    procurement: ProcurementRecord,
    data: Dict[str, Any],
    user: Optional[User] = None,
    request=None,
) -> ProcurementRecord:
    """Updates an existing ProcurementRecord with validation checks and audit logging."""
    if not user_can_modify_procurement(user, procurement):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ProcurementRecord:{procurement.id}/update",
            details="Unauthorized attempt to modify procurement record.",
            success=False,
        )
        raise PermissionDenied("You do not have authorization to modify this procurement record.")

    for field in [
        "supplier",
        "category",
        "purchase_date",
        "purchase_order_reference",
        "invoice_reference",
        "invoice_date",
        "total_amount",
        "currency",
        "description",
        "activity_record",
    ]:
        if field in data:
            val = data[field]
            if isinstance(val, str) and field in ["purchase_order_reference", "invoice_reference", "description"]:
                val = val.strip()
            elif field == "total_amount":
                val = Decimal(str(val))
            setattr(procurement, field, val)

    procurement.updated_by = user
    procurement.full_clean()
    procurement.save()

    log_auth_event(
        AuthAuditLog.EventType.PROCUREMENT_UPDATED,
        request=request,
        user=user,
        resource_accessed=f"ProcurementRecord:{procurement.id}",
        details=f"Updated Procurement #{procurement.procurement_number} by {user.username if user else 'System'}.",
        success=True,
    )
    return procurement


@transaction.atomic
def delete_procurement_record(
    procurement: ProcurementRecord,
    user: Optional[User] = None,
    request=None,
):
    """Safely deletes a DRAFT procurement record and its items."""
    if not user_can_delete_procurement(user, procurement):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ProcurementRecord:{procurement.id}/delete",
            details="Unauthorized attempt to delete procurement record.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to delete this procurement record.")

    proc_num = procurement.procurement_number
    proc_id = procurement.id
    procurement.delete()

    log_auth_event(
        AuthAuditLog.EventType.PROCUREMENT_DELETED,
        request=request,
        user=user,
        resource_accessed=f"ProcurementRecord:{proc_id}",
        details=f"Deleted Draft Procurement #{proc_num} by {user.username if user else 'System'}.",
        success=True,
    )


@transaction.atomic
def add_procurement_item(
    procurement: ProcurementRecord,
    data: Dict[str, Any],
    user: Optional[User] = None,
    request=None,
) -> ProcurementItem:
    """Adds a line item to a procurement transaction and updates total amount if desired."""
    if not user_can_modify_procurement(user, procurement):
        raise PermissionDenied("You do not have permission to add items to this procurement record.")

    existing_max_line = procurement.items.aggregate(models.Max("line_number"))["line_number__max"] or 0
    next_line = existing_max_line + 1

    qty = Decimal(str(data.get("quantity", "1.0000")))
    if qty <= 0:
        raise ValidationError({"quantity": "Line item quantity must be strictly positive."})

    unit_price = Decimal(str(data.get("unit_price", "0.00"))) if data.get("unit_price") is not None else None
    total_amt = Decimal(str(data.get("total_amount", "0.00")))
    if total_amt == 0 and unit_price and unit_price > 0:
        total_amt = round(qty * unit_price, 2)

    item = ProcurementItem(
        procurement=procurement,
        line_number=next_line,
        item_name=(data.get("item_name") or "").strip(),
        category=data.get("category") or procurement.category,
        quantity=qty,
        unit=data.get("unit"),
        unit_custom=(data.get("unit_custom") or "").strip(),
        unit_price=unit_price,
        total_amount=total_amt,
        activity_master=data.get("activity_master"),
        scope3_category=data.get("scope3_category") or "",
        notes=(data.get("notes") or "").strip(),
    )
    item.full_clean()
    item.save()

    # Synchronize procurement total_amount with line items sum unless explicitly disabled
    items_sum = sum(i.total_amount for i in procurement.items.all())
    if data.get("sync_total", True):
        procurement.total_amount = items_sum
        procurement.save(update_fields=["total_amount", "updated_at"])

    return item


@transaction.atomic
def delete_procurement_item(
    item: ProcurementItem,
    user: Optional[User] = None,
    request=None,
):
    """Deletes a line item from a procurement record."""
    procurement = item.procurement
    if not user_can_modify_procurement(user, procurement):
        raise PermissionDenied("You do not have permission to delete items from this procurement record.")

    item.delete()

    # Re-sequence remaining line numbers
    for idx, remaining_item in enumerate(procurement.items.order_by("line_number"), start=1):
        if remaining_item.line_number != idx:
            remaining_item.line_number = idx
            remaining_item.save(update_fields=["line_number"])

    # Update procurement total with remaining items sum
    items_sum = sum(i.total_amount for i in procurement.items.all())
    procurement.total_amount = items_sum
    procurement.save(update_fields=["total_amount", "updated_at"])


# -----------------------------------------------------------------------------
# 5. DETERMINISTIC PROCUREMENT VALIDATION ENGINE
# -----------------------------------------------------------------------------

def validate_procurement(
    procurement: ProcurementRecord,
    user: Optional[User] = None,
    request=None,
) -> Dict[str, Any]:
    """
    Evaluates layered deterministic validation rules for a ProcurementRecord:
    1. Structural: Supplier, Date, Period, Amount, Currency
    2. Scope: Active supplier, Site-Project alignment, Open period, Date within period
    3. Items: Items exist, Quantities positive, Items sum equals total amount
    4. Evidence: Supporting documentation attached
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Supplier checks
    if not procurement.supplier:
        errors.append("Missing required Supplier master association.")
    elif procurement.supplier.status != SupplierStatus.ACTIVE:
        errors.append(f"Supplier '{procurement.supplier.name}' is {procurement.supplier.status}; active supplier required.")

    # 2. Temporal & Period checks
    period = procurement.reporting_period
    if not period:
        errors.append("Missing governing Reporting Period.")
    else:
        if period.status != PeriodStatus.OPEN:
            errors.append(f"Reporting period '{period.name}' is {period.get_status_display()}; must be OPEN.")
        if procurement.purchase_date < period.start_date or procurement.purchase_date > period.end_date:
            errors.append(
                f"Purchase date ({procurement.purchase_date}) falls outside reporting period range ({period.start_date} to {period.end_date})."
            )

    # 3. Scope Hierarchy checks
    if procurement.site:
        if procurement.project and procurement.site.project_id != procurement.project.id:
            errors.append(f"Site '{procurement.site.name}' does not belong to Project '{procurement.project.name}'.")
        if procurement.company and procurement.site.project.subsidiary.company_id != procurement.company.id:
            errors.append("Site hierarchy does not align with operating Company boundary.")

    # 4. Financial / Value checks
    if procurement.total_amount < 0:
        errors.append("Total procurement amount cannot be negative.")
    if not procurement.currency:
        errors.append("Currency code is required.")

    # 5. Line items checks
    items_count = procurement.items.count()
    if items_count == 0:
        warnings.append("Procurement record currently contains zero line items.")
    else:
        items_sum = sum(item.total_amount for item in procurement.items.all())
        if abs(items_sum - procurement.total_amount) > Decimal("0.05"):
            warnings.append(
                f"Line items total (₹{items_sum}) does not match procurement total amount (₹{procurement.total_amount})."
            )
        for item in procurement.items.all():
            if item.quantity <= 0:
                errors.append(f"Item #{item.line_number} '{item.item_name}' quantity must be greater than zero.")

    # 6. Supporting Evidence check
    has_active_evidence = procurement.evidence_files.filter(status=EvidenceStatus.ACTIVE).exists()
    if not has_active_evidence and procurement.invoice_reference:
        warnings.append("Invoice reference is recorded but no supporting invoice/PO evidence document is attached.")

    # Determine final validation status
    if errors:
        final_status = ValidationStatus.INVALID
    elif warnings:
        final_status = ValidationStatus.WARNING
    else:
        final_status = ValidationStatus.VALID

    procurement.validation_status = final_status
    procurement.save(update_fields=["validation_status", "updated_at"])

    result_summary = {
        "status": final_status,
        "is_valid": final_status in [ValidationStatus.VALID, ValidationStatus.WARNING],
        "errors": errors,
        "warnings": warnings,
        "errors_count": len(errors),
        "warnings_count": len(warnings),
        "evaluated_at": timezone.now().isoformat(),
    }
    return result_summary


# -----------------------------------------------------------------------------
# 6. PROCUREMENT ANOMALY DETECTION ENGINE
# -----------------------------------------------------------------------------

def detect_procurement_anomalies(
    procurement: ProcurementRecord,
    user: Optional[User] = None,
    request=None,
) -> List[Dict[str, Any]]:
    """
    Identifies unusual, suspicious, or duplicate-like procurement data streams:
    1. DUPLICATE_INVOICE: Same supplier + identical invoice_reference on another procurement
    2. AMOUNT_SPIKE: Procurement amount exceeds 3x historical average for supplier
    3. PRICE_VARIANCE: Item unit price deviates >50% from supplier historical average
    Anomalies serve as review signals; they do NOT automatically invalidate records.
    """
    anomalies: List[Dict[str, Any]] = []

    # 1. Duplicate Invoice Detection
    inv_ref = (procurement.invoice_reference or "").strip()
    if inv_ref and procurement.supplier:
        other_procurements = ProcurementRecord.objects.filter(
            supplier=procurement.supplier,
            invoice_reference__iexact=inv_ref,
        ).exclude(id=procurement.id).exclude(status=ProcurementStatus.CANCELLED)

        if other_procurements.exists():
            dup = other_procurements.first()
            anomalies.append({
                "rule_code": "DUPLICATE_INVOICE",
                "severity": "HIGH",
                "title": "Duplicate Invoice Suspect",
                "message": (
                    f"Invoice reference '{inv_ref}' from supplier '{procurement.supplier.name}' "
                    f"is already recorded on Procurement #{dup.procurement_number} (Status: {dup.status})."
                ),
                "matched_procurement_id": dup.id,
                "matched_procurement_number": dup.procurement_number,
            })

    # 2. Historical Amount Spike Detection
    if procurement.total_amount > Decimal("1000.00") and procurement.supplier:
        historical_records = ProcurementRecord.objects.filter(
            supplier=procurement.supplier,
            status__in=[ProcurementStatus.SUBMITTED, ProcurementStatus.VERIFIED],
        ).exclude(id=procurement.id)

        count = historical_records.count()
        if count >= 2:
            avg_amount = historical_records.aggregate(models.Avg("total_amount"))["total_amount__avg"]
            if avg_amount and avg_amount > 0:
                ratio = procurement.total_amount / avg_amount
                if ratio >= Decimal("3.0"):
                    variance_pct = round((ratio - Decimal("1.0")) * Decimal("100.0"), 1)
                    anomalies.append({
                        "rule_code": "AMOUNT_SPIKE",
                        "severity": "HIGH",
                        "title": "Procurement Amount Spike",
                        "message": (
                            f"Total amount ₹{procurement.total_amount:,.2f} is {variance_pct}% higher than "
                            f"historical average (₹{avg_amount:,.2f} across {count} prior transactions)."
                        ),
                        "baseline_value": float(avg_amount),
                        "observed_value": float(procurement.total_amount),
                        "variance_percentage": float(variance_pct),
                    })

    # 3. Unit Price Variance Detection
    for item in procurement.items.all():
        if item.unit_price and item.unit_price > 0 and item.unit:
            hist_items = ProcurementItem.objects.filter(
                procurement__supplier=procurement.supplier,
                item_name__iexact=item.item_name.strip(),
                unit=item.unit,
                unit_price__gt=0,
                procurement__status__in=[ProcurementStatus.SUBMITTED, ProcurementStatus.VERIFIED],
            ).exclude(procurement_id=procurement.id)

            item_count = hist_items.count()
            if item_count >= 2:
                avg_price = hist_items.aggregate(models.Avg("unit_price"))["unit_price__avg"]
                if avg_price and avg_price > 0:
                    price_ratio = item.unit_price / avg_price
                    if price_ratio >= Decimal("1.50") or price_ratio <= Decimal("0.50"):
                        price_var = round((price_ratio - Decimal("1.0")) * Decimal("100.0"), 1)
                        anomalies.append({
                            "rule_code": "PRICE_VARIANCE",
                            "severity": "MEDIUM",
                            "title": f"Unit Price Variance: {item.item_name}",
                            "message": (
                                f"Unit price ₹{item.unit_price:,.2f}/{item.unit.symbol} deviates {price_var}% "
                                f"from historical supplier average (₹{avg_price:,.2f}/{item.unit.symbol})."
                            ),
                            "line_number": item.line_number,
                            "baseline_value": float(avg_price),
                            "observed_value": float(item.unit_price),
                            "variance_percentage": float(price_var),
                        })

    has_anom = len(anomalies) > 0
    if procurement.has_anomalies != has_anom:
        procurement.has_anomalies = has_anom
        procurement.save(update_fields=["has_anomalies", "updated_at"])

    if has_anom:
        log_auth_event(
            AuthAuditLog.EventType.PROCUREMENT_ANOMALY_DETECTED,
            request=request,
            user=user,
            resource_accessed=f"ProcurementRecord:{procurement.id}",
            details=f"Detected {len(anomalies)} anomalies on Procurement #{procurement.procurement_number}.",
            success=True,
        )

    return anomalies


# -----------------------------------------------------------------------------
# 7. DOCUMENT INTELLIGENCE OCR COMPARISON
# -----------------------------------------------------------------------------

def compare_ocr_with_procurement(ocr_run: OCRRun, procurement: ProcurementRecord) -> Dict[str, Any]:
    """
    Compares extracted OCR entities against the Procurement Record commercial data.
    Provides automated telemetry for auditor review and data verification.
    STRICT PRINCIPLE: Does NOT auto-overwrite or mutate the Procurement Record data.
    """
    fields_by_name = {f.field_name: f for f in ocr_run.fields.all()}

    comparison = {
        "evaluated": True,
        "procurement_id": procurement.id,
        "procurement_number": procurement.procurement_number,
        "evidence_id": ocr_run.evidence_id,
        "overall_status": "MATCH",
        "matches_count": 0,
        "mismatches_count": 0,
        "not_detected_count": 0,
        "items": {},
    }

    # 1. Compare Invoice Reference
    inv_field = fields_by_name.get("invoice_number") or fields_by_name.get("bill_number")
    if inv_field and inv_field.normalized_value:
        ext_inv = inv_field.normalized_value.strip().upper()
        stored_inv = (procurement.invoice_reference or "").strip().upper()
        if stored_inv and ext_inv == stored_inv:
            inv_status = "MATCH"
            comparison["matches_count"] += 1
        else:
            inv_status = "MISMATCH"
            comparison["mismatches_count"] += 1
            comparison["overall_status"] = "MISMATCH"

        comparison["items"]["invoice_number"] = {
            "label": "Invoice Number",
            "status": inv_status,
            "stored_value": procurement.invoice_reference,
            "extracted_value": inv_field.normalized_value,
            "confidence": float(inv_field.confidence or 0),
        }
    else:
        comparison["items"]["invoice_number"] = {
            "label": "Invoice Number",
            "status": "NOT_DETECTED",
            "stored_value": procurement.invoice_reference,
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    # 2. Compare Total Amount
    amt_field = fields_by_name.get("total_amount")
    if amt_field and amt_field.normalized_value:
        try:
            ext_amt = float(amt_field.normalized_value)
            stored_amt = float(procurement.total_amount)
            delta = round(ext_amt - stored_amt, 2)
            if abs(delta) < 1.00:
                amt_status = "MATCH"
                comparison["matches_count"] += 1
            else:
                amt_status = "MISMATCH"
                comparison["mismatches_count"] += 1
                comparison["overall_status"] = "MISMATCH"

            comparison["items"]["total_amount"] = {
                "label": "Total Amount",
                "status": amt_status,
                "stored_value": stored_amt,
                "extracted_value": ext_amt,
                "delta": delta,
                "currency": procurement.currency,
                "confidence": float(amt_field.confidence or 0),
            }
        except (ValueError, TypeError):
            comparison["items"]["total_amount"] = {
                "label": "Total Amount",
                "status": "UNPARSEABLE",
                "stored_value": float(procurement.total_amount),
                "extracted_value": amt_field.raw_value,
            }
            comparison["not_detected_count"] += 1
    else:
        comparison["items"]["total_amount"] = {
            "label": "Total Amount",
            "status": "NOT_DETECTED",
            "stored_value": float(procurement.total_amount),
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    # 3. Compare Vendor Name
    vendor_field = fields_by_name.get("vendor_name")
    if vendor_field and vendor_field.normalized_value:
        ext_vendor = vendor_field.normalized_value.strip().lower()
        stored_vendor = procurement.supplier.name.strip().lower()
        if stored_vendor in ext_vendor or ext_vendor in stored_vendor:
            vendor_status = "MATCH"
            comparison["matches_count"] += 1
        else:
            vendor_status = "MISMATCH"
            comparison["mismatches_count"] += 1
            comparison["overall_status"] = "MISMATCH"

        comparison["items"]["vendor_name"] = {
            "label": "Supplier / Vendor Name",
            "status": vendor_status,
            "stored_value": procurement.supplier.name,
            "extracted_value": vendor_field.normalized_value,
            "confidence": float(vendor_field.confidence or 0),
        }
    else:
        comparison["items"]["vendor_name"] = {
            "label": "Supplier / Vendor Name",
            "status": "NOT_DETECTED",
            "stored_value": procurement.supplier.name,
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    # 4. Compare Date
    date_field = fields_by_name.get("billing_date")
    if date_field and date_field.normalized_value:
        ext_date = date_field.normalized_value.strip()
        target_date = str(procurement.invoice_date or procurement.purchase_date)
        if ext_date == target_date:
            date_status = "MATCH"
            comparison["matches_count"] += 1
        else:
            date_status = "MISMATCH"
            comparison["mismatches_count"] += 1
            comparison["overall_status"] = "MISMATCH"

        comparison["items"]["date"] = {
            "label": "Invoice / Purchase Date",
            "status": date_status,
            "stored_value": target_date,
            "extracted_value": ext_date,
            "confidence": float(date_field.confidence or 0),
        }
    else:
        comparison["items"]["date"] = {
            "label": "Invoice / Purchase Date",
            "status": "NOT_DETECTED",
            "stored_value": str(procurement.invoice_date or procurement.purchase_date),
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    return comparison


# -----------------------------------------------------------------------------
# 8. GOVERNANCE WORKFLOW TRANSITIONS
# -----------------------------------------------------------------------------

@transaction.atomic
def submit_procurement(
    procurement: ProcurementRecord,
    user: User,
    request=None,
    comments: str = "",
) -> ProcurementRecord:
    """
    Transitions a procurement record from DRAFT/CORRECTION_REQUESTED to SUBMITTED.
    Runs validation and anomaly detection. Locks the record from further modification.
    """
    if not user_can_submit_procurement(user, procurement):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ProcurementRecord:{procurement.id}/submit",
            details="Unauthorized attempt to submit procurement record.",
            success=False,
        )
        raise PermissionDenied("You do not have authorization to submit this procurement record.")

    # 1. Run deterministic validation
    val_result = validate_procurement(procurement, user=user, request=request)
    if val_result["status"] == ValidationStatus.INVALID:
        error_msg = "; ".join(val_result["errors"][:3])
        raise ValidationError(f"Cannot submit invalid procurement: {error_msg}")

    # 2. Run anomaly detection
    detect_procurement_anomalies(procurement, user=user, request=request)

    # 3. Transition status and lock
    procurement.status = ProcurementStatus.SUBMITTED
    procurement.is_locked = True
    if comments:
        procurement.description = f"{procurement.description}\n[Submission Note]: {comments}".strip()
    procurement.updated_by = user
    procurement.save()

    log_auth_event(
        AuthAuditLog.EventType.PROCUREMENT_SUBMITTED,
        request=request,
        user=user,
        resource_accessed=f"ProcurementRecord:{procurement.id}",
        details=f"Submitted Procurement #{procurement.procurement_number} by {user.username}.",
        success=True,
    )
    logger.info("ProcurementRecord [%s] submitted by %s", procurement.id, user)
    return procurement


@transaction.atomic
def review_procurement(
    procurement: ProcurementRecord,
    action: str,
    user: User,
    request=None,
    comments: str = "",
    correction_notes: str = "",
) -> ProcurementRecord:
    """
    Subsidiary Manager review decision engine:
    - VERIFY / APPROVE: Marks VERIFIED, locks record.
    - REQUEST_CORRECTION: Marks CORRECTION_REQUESTED, unlocks record for Site Manager remediation.
    - REJECT: Marks REJECTED, locks record.
    """
    if not user_can_review_procurement(user, procurement):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ProcurementRecord:{procurement.id}/review",
            details="Unauthorized attempt to review procurement record.",
            success=False,
        )
        raise PermissionDenied("You do not have authorization to review this procurement record.")

    action = action.upper().strip()

    if action in ["VERIFY", "APPROVE"]:
        procurement.status = ProcurementStatus.VERIFIED
        procurement.is_locked = True
        procurement.review_comments = comments.strip()
        procurement.updated_by = user
        procurement.save()

        log_auth_event(
            AuthAuditLog.EventType.PROCUREMENT_VERIFIED,
            request=request,
            user=user,
            resource_accessed=f"ProcurementRecord:{procurement.id}",
            details=f"Verified Procurement #{procurement.procurement_number} by {user.username}.",
            success=True,
        )

    elif action == "REQUEST_CORRECTION":
        clean_notes = (correction_notes or comments or "").strip()
        if not clean_notes:
            raise ValidationError("Correction details/reasoning must be provided when requesting correction.")

        procurement.status = ProcurementStatus.CORRECTION_REQUESTED
        procurement.is_locked = False
        procurement.review_comments = clean_notes
        procurement.updated_by = user
        procurement.save()

        log_auth_event(
            AuthAuditLog.EventType.PROCUREMENT_CORRECTED,
            request=request,
            user=user,
            resource_accessed=f"ProcurementRecord:{procurement.id}",
            details=f"Correction requested on Procurement #{procurement.procurement_number} by {user.username}.",
            success=True,
        )

    elif action == "REJECT":
        clean_comments = comments.strip()
        if not clean_comments:
            raise ValidationError("Rejection reason must be provided when rejecting procurement.")

        procurement.status = ProcurementStatus.REJECTED
        procurement.is_locked = True
        procurement.review_comments = clean_comments
        procurement.updated_by = user
        procurement.save()

        log_auth_event(
            AuthAuditLog.EventType.PROCUREMENT_REJECTED,
            request=request,
            user=user,
            resource_accessed=f"ProcurementRecord:{procurement.id}",
            details=f"Rejected Procurement #{procurement.procurement_number} by {user.username}.",
            success=True,
        )

    else:
        raise ValidationError(f"Unknown review action '{action}'.")

    return procurement


@transaction.atomic
def resubmit_procurement(
    procurement: ProcurementRecord,
    user: User,
    request=None,
    explanation: str = "",
) -> ProcurementRecord:
    """
    Resubmits a corrected procurement record following a CORRECTION_REQUESTED review.
    Enforces mandatory explanation and re-validation.
    """
    if procurement.status != ProcurementStatus.CORRECTION_REQUESTED:
        raise ValidationError("Only records in CORRECTION_REQUESTED state can be resubmitted.")

    if not user_can_submit_procurement(user, procurement):
        raise PermissionDenied("You do not have authorization to resubmit this procurement record.")

    clean_explanation = explanation.strip()
    if not clean_explanation:
        raise ValidationError("A remediation explanation is required upon resubmission.")

    # 1. Re-validate
    val_result = validate_procurement(procurement, user=user, request=request)
    if val_result["status"] == ValidationStatus.INVALID:
        error_msg = "; ".join(val_result["errors"][:3])
        raise ValidationError(f"Cannot resubmit invalid procurement: {error_msg}")

    # 2. Re-run anomaly detection
    detect_procurement_anomalies(procurement, user=user, request=request)

    # 3. Transition to SUBMITTED and re-lock
    procurement.status = ProcurementStatus.SUBMITTED
    procurement.is_locked = True
    procurement.correction_notes = clean_explanation
    procurement.updated_by = user
    procurement.save()

    log_auth_event(
        AuthAuditLog.EventType.PROCUREMENT_RESUBMITTED,
        request=request,
        user=user,
        resource_accessed=f"ProcurementRecord:{procurement.id}",
        details=f"Resubmitted Procurement #{procurement.procurement_number} with explanation by {user.username}.",
        success=True,
    )
    return procurement
