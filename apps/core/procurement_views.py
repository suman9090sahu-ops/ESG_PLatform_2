"""
Views for Supplier & Procurement Management (Phase 16) in MEIL ESG CONTROL TOWER.

Fulfills Phase 16 Requirements:
- Supplier catalog, detail, creation, editing, and soft-archival
- Procurement ledger, creation, detail, editing, and draft deletion
- Line-item creation and removal with automated total syncing
- Supporting evidence document attachment (Invoices, POs) via Phase 09 integration
- OCR document intelligence and telemetry comparison via Phase 11 integration
- Layered deterministic validation execution via Phase 10 integration
- Anomaly detection review signals via Phase 15 integration
- Review, verification, correction, and resubmission workflow
- Strict RBAC enforcement and Anti-IDOR security across all routes
"""

import logging
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import models
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.core.auth_services import log_auth_event, role_required
from apps.core.evidence_services import create_evidence_record, validate_evidence_file
from apps.core.models import (
    AuthAuditLog,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    OCRRun,
    OCRStatus,
    ProcurementCategory,
    ProcurementItem,
    ProcurementRecord,
    ProcurementStatus,
    Role,
    Supplier,
    SupplierStatus,
    SupplierType,
    ValidationStatus,
)
from apps.core.procurement_forms import (
    ProcurementCorrectionForm,
    ProcurementFilterForm,
    ProcurementItemForm,
    ProcurementRecordForm,
    ProcurementReviewForm,
    SupplierFilterForm,
    SupplierForm,
)
from apps.core.procurement_services import (
    add_procurement_item,
    archive_supplier,
    compare_ocr_with_procurement,
    create_procurement_record,
    create_supplier,
    delete_procurement_item,
    delete_procurement_record,
    detect_procurement_anomalies,
    get_accessible_procurements,
    get_accessible_suppliers,
    resubmit_procurement,
    review_procurement,
    submit_procurement,
    update_procurement_record,
    update_supplier,
    user_can_access_procurement,
    user_can_access_supplier,
    user_can_archive_supplier,
    user_can_delete_procurement,
    user_can_modify_procurement,
    user_can_modify_supplier,
    user_can_review_procurement,
    user_can_submit_procurement,
    user_can_upload_procurement_evidence,
    validate_procurement,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SUPPLIER MASTER VIEWS
# -----------------------------------------------------------------------------

@login_required
def supplier_list_view(request):
    """Catalog of accessible Supplier & Vendor master records."""
    suppliers_qs = get_accessible_suppliers(request.user)

    filter_form = SupplierFilterForm(request.GET, user=request.user)
    if filter_form.is_valid():
        search = filter_form.cleaned_data.get("search")
        if search:
            suppliers_qs = suppliers_qs.filter(
                models.Q(name__icontains=search)
                | models.Q(supplier_code__icontains=search)
                | models.Q(tax_identifier__icontains=search)
                | models.Q(contact_person__icontains=search)
            )
        supp_type = filter_form.cleaned_data.get("supplier_type")
        if supp_type:
            suppliers_qs = suppliers_qs.filter(supplier_type=supp_type)
        status = filter_form.cleaned_data.get("status")
        if status:
            suppliers_qs = suppliers_qs.filter(status=status)
        company = filter_form.cleaned_data.get("company")
        if company:
            suppliers_qs = suppliers_qs.filter(company=company)

    # KPI counts
    total_suppliers = suppliers_qs.count()
    active_suppliers = suppliers_qs.filter(status=SupplierStatus.ACTIVE).count()
    esg_declared = suppliers_qs.filter(has_esg_declaration=True).count()
    goods_suppliers = suppliers_qs.filter(supplier_type=SupplierType.GOODS).count()

    paginator = Paginator(suppliers_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    can_create = user_can_modify_supplier(request.user)

    context = {
        "page_obj": page_obj,
        "filter_form": filter_form,
        "total_suppliers": total_suppliers,
        "active_suppliers": active_suppliers,
        "esg_declared": esg_declared,
        "goods_suppliers": goods_suppliers,
        "can_create": can_create,
    }
    return render(request, "procurement/supplier_list.html", context)


@login_required
def supplier_detail_view(request, supplier_id):
    """Detailed profile, compliance accreditations, and procurement ledger for a Supplier."""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    if not user_can_access_supplier(request.user, supplier):
        raise PermissionDenied("Access Denied: You do not have authorization to view this supplier.")

    procurements = get_accessible_procurements(request.user).filter(supplier=supplier)[:25]
    can_edit = user_can_modify_supplier(request.user, supplier=supplier)
    can_archive = user_can_archive_supplier(request.user, supplier)

    context = {
        "supplier": supplier,
        "procurements": procurements,
        "can_edit": can_edit,
        "can_archive": can_archive,
    }
    return render(request, "procurement/supplier_detail.html", context)


@login_required
def supplier_create_view(request):
    """Registers a new Supplier master record."""
    if not user_can_modify_supplier(request.user):
        raise PermissionDenied("Access Denied: You do not have authorization to register suppliers.")

    if request.method == "POST":
        form = SupplierForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                supplier = create_supplier(form.cleaned_data, user=request.user, request=request)
                messages.success(request, f"Supplier '{supplier.name}' ({supplier.supplier_code}) successfully registered.")
                return redirect("core:supplier_detail", supplier_id=supplier.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = SupplierForm(user=request.user)

    return render(request, "procurement/supplier_form.html", {"form": form, "is_create": True})


@login_required
def supplier_edit_view(request, supplier_id):
    """Updates an existing Supplier master record."""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    if not user_can_modify_supplier(request.user, supplier=supplier):
        raise PermissionDenied("Access Denied: You do not have authorization to modify this supplier.")

    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier, user=request.user)
        if form.is_valid():
            try:
                update_supplier(supplier, form.cleaned_data, user=request.user, request=request)
                messages.success(request, f"Supplier '{supplier.name}' updated successfully.")
                return redirect("core:supplier_detail", supplier_id=supplier.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = SupplierForm(instance=supplier, user=request.user)

    return render(request, "procurement/supplier_form.html", {"form": form, "supplier": supplier, "is_create": False})


@login_required
@require_POST
def supplier_archive_view(request, supplier_id):
    """Soft-archives a supplier master record."""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    if not user_can_archive_supplier(request.user, supplier):
        raise PermissionDenied("Access Denied: You do not have authorization to archive this supplier.")

    archive_supplier(supplier, user=request.user, request=request)
    messages.warning(request, f"Supplier '{supplier.name}' has been archived.")
    return redirect("core:supplier_detail", supplier_id=supplier.id)


# -----------------------------------------------------------------------------
# 2. PROCUREMENT TRANSACTION VIEWS
# -----------------------------------------------------------------------------

@login_required
def procurement_list_view(request):
    """Operational and Governance Ledger of Procurement records."""
    procurements_qs = get_accessible_procurements(request.user)

    filter_form = ProcurementFilterForm(request.GET, user=request.user)
    if filter_form.is_valid():
        search = filter_form.cleaned_data.get("search")
        if search:
            procurements_qs = procurements_qs.filter(
                models.Q(procurement_number__icontains=search)
                | models.Q(invoice_reference__icontains=search)
                | models.Q(purchase_order_reference__icontains=search)
                | models.Q(supplier__name__icontains=search)
            )
        supp = filter_form.cleaned_data.get("supplier")
        if supp:
            procurements_qs = procurements_qs.filter(supplier=supp)
        site = filter_form.cleaned_data.get("site")
        if site:
            procurements_qs = procurements_qs.filter(site=site)
        cat = filter_form.cleaned_data.get("category")
        if cat:
            procurements_qs = procurements_qs.filter(category=cat)
        status = filter_form.cleaned_data.get("status")
        if status:
            procurements_qs = procurements_qs.filter(status=status)
        period = filter_form.cleaned_data.get("reporting_period")
        if period:
            procurements_qs = procurements_qs.filter(reporting_period=period)
        val_status = filter_form.cleaned_data.get("validation_status")
        if val_status:
            procurements_qs = procurements_qs.filter(validation_status=val_status)
        has_anom = filter_form.cleaned_data.get("has_anomalies")
        if has_anom == "yes":
            procurements_qs = procurements_qs.filter(has_anomalies=True)
        elif has_anom == "no":
            procurements_qs = procurements_qs.filter(has_anomalies=False)

    total_count = procurements_qs.count()
    total_spend = procurements_qs.aggregate(models.Sum("total_amount"))["total_amount__sum"] or Decimal("0.00")
    pending_review = procurements_qs.filter(status=ProcurementStatus.SUBMITTED).count()
    anomalies_count = procurements_qs.filter(has_anomalies=True).count()

    paginator = Paginator(procurements_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    is_site_mgr = request.user.has_role(Role.Code.SITE_MANAGER)
    is_sub_mgr = request.user.has_role(Role.Code.SUBSIDIARY_MANAGER)

    context = {
        "page_obj": page_obj,
        "filter_form": filter_form,
        "total_count": total_count,
        "total_spend": total_spend,
        "pending_review": pending_review,
        "anomalies_count": anomalies_count,
        "can_create": is_site_mgr or request.user.is_superuser or request.user.has_role(Role.Code.MEIL_OPERATOR),
        "is_sub_mgr": is_sub_mgr,
    }
    return render(request, "procurement/procurement_list.html", context)


@login_required
def procurement_detail_view(request, procurement_id):
    """Complete inspection page for a Procurement transaction."""
    procurement = get_object_or_404(
        ProcurementRecord.objects.select_related(
            "supplier", "site", "project", "company", "reporting_period", "created_by", "updated_by"
        ),
        id=procurement_id,
    )
    if not user_can_access_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You do not have authorization to view this procurement record.")

    items = procurement.items.select_related("unit", "activity_master").all()
    evidence_files = procurement.evidence_files.filter(status=EvidenceStatus.ACTIVE).select_related("uploaded_by")

    can_edit = user_can_modify_procurement(request.user, procurement)
    can_delete = user_can_delete_procurement(request.user, procurement)
    can_submit = user_can_submit_procurement(request.user, procurement)
    can_review = user_can_review_procurement(request.user, procurement)

    # Active anomalies for this record
    active_anomalies = detect_procurement_anomalies(procurement) if procurement.has_anomalies else []

    context = {
        "procurement": procurement,
        "items": items,
        "evidence_files": evidence_files,
        "can_edit": can_edit,
        "can_delete": can_delete,
        "can_submit": can_submit,
        "can_review": can_review,
        "active_anomalies": active_anomalies,
        "item_form": ProcurementItemForm() if can_edit else None,
    }
    return render(request, "procurement/procurement_detail.html", context)


@login_required
def procurement_create_view(request):
    """Creates a new commercial procurement record."""
    if not (
        request.user.has_role(Role.Code.SITE_MANAGER)
        or request.user.is_superuser
        or request.user.has_role(Role.Code.MEIL_OPERATOR)
        or request.user.has_role(Role.Code.ESG_MANAGER)
    ):
        raise PermissionDenied("Access Denied: You do not have authorization to create procurement records.")

    if request.method == "POST":
        form = ProcurementRecordForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                procurement = create_procurement_record(form.cleaned_data, user=request.user, request=request)
                messages.success(request, f"Procurement #{procurement.procurement_number} created successfully.")
                return redirect("core:procurement_detail", procurement_id=procurement.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = ProcurementRecordForm(user=request.user)

    return render(request, "procurement/procurement_form.html", {"form": form, "is_create": True})


@login_required
def procurement_edit_view(request, procurement_id):
    """Edits a draft procurement record."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_modify_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You do not have authorization to edit this procurement record.")

    if request.method == "POST":
        form = ProcurementRecordForm(request.POST, instance=procurement, user=request.user)
        if form.is_valid():
            try:
                update_procurement_record(procurement, form.cleaned_data, user=request.user, request=request)
                messages.success(request, f"Procurement #{procurement.procurement_number} updated successfully.")
                return redirect("core:procurement_detail", procurement_id=procurement.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = ProcurementRecordForm(instance=procurement, user=request.user)

    return render(request, "procurement/procurement_form.html", {"form": form, "procurement": procurement, "is_create": False})


@login_required
@require_POST
def procurement_delete_view(request, procurement_id):
    """Deletes a draft procurement record."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_delete_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You cannot delete this procurement record.")

    proc_num = procurement.procurement_number
    delete_procurement_record(procurement, user=request.user, request=request)
    messages.success(request, f"Draft Procurement #{proc_num} has been deleted.")
    return redirect("core:procurement_list")


@login_required
@require_POST
def procurement_item_create_view(request, procurement_id):
    """Adds a line item to an existing procurement transaction."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_modify_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You cannot modify items on this procurement record.")

    form = ProcurementItemForm(request.POST)
    if form.is_valid():
        try:
            item = add_procurement_item(procurement, form.cleaned_data, user=request.user, request=request)
            messages.success(request, f"Added line item #{item.line_number}: '{item.item_name}'.")
        except ValidationError as exc:
            messages.error(request, f"Error adding item: {exc}")
    else:
        messages.error(request, f"Invalid item form data: {form.errors}")

    return redirect("core:procurement_detail", procurement_id=procurement.id)


@login_required
@require_POST
def procurement_item_delete_view(request, procurement_id, item_id):
    """Removes a line item from a procurement transaction."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_modify_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You cannot delete items from this procurement record.")

    item = get_object_or_404(ProcurementItem, id=item_id, procurement=procurement)
    delete_procurement_item(item, user=request.user, request=request)
    messages.info(request, f"Removed line item #{item.line_number}.")
    return redirect("core:procurement_detail", procurement_id=procurement.id)


@login_required
def procurement_evidence_upload_view(request, procurement_id):
    """Uploads supporting documentation (invoices, POs) directly to a procurement record."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_upload_procurement_evidence(request.user, procurement):
        raise PermissionDenied("Access Denied: You cannot upload evidence for this procurement record.")

    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        evidence_type = request.POST.get("evidence_type") or EvidenceType.INVOICE
        description = request.POST.get("description", "")

        try:
            evidence = create_evidence_record(
                procurement_record=procurement,
                uploaded_file=uploaded_file,
                evidence_type=evidence_type,
                description=description,
                user=request.user,
                request=request,
            )
            messages.success(request, f"Evidence document '{evidence.original_filename}' uploaded successfully.")
            return redirect("core:procurement_detail", procurement_id=procurement.id)
        except (ValidationError, Exception) as exc:
            messages.error(request, f"Upload failed: {exc}")

    return render(request, "procurement/procurement_evidence_upload.html", {
        "procurement": procurement,
        "evidence_types": EvidenceType.choices,
    })


@login_required
@require_POST
def procurement_validate_view(request, procurement_id):
    """Evaluates deterministic validation rules against a procurement record."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_access_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You cannot validate this procurement record.")

    result = validate_procurement(procurement, user=request.user, request=request)

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("format") == "json":
        return JsonResponse({"success": True, "result": result})

    if result["status"] == ValidationStatus.VALID:
        messages.success(request, "Validation passed: Record meets all structural and consistency requirements.")
    elif result["status"] == ValidationStatus.WARNING:
        messages.warning(request, f"Validation warning: {len(result['warnings'])} non-blocking issues identified.")
    else:
        messages.error(request, f"Validation failed: {len(result['errors'])} blocking errors detected.")

    return redirect("core:procurement_detail", procurement_id=procurement.id)


@login_required
@require_POST
def procurement_anomaly_detect_view(request, procurement_id):
    """Executes anomaly detection check on a procurement record."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_access_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You cannot run anomaly detection on this procurement record.")

    anomalies = detect_procurement_anomalies(procurement, user=request.user, request=request)

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("format") == "json":
        return JsonResponse({"success": True, "anomalies": anomalies})

    if anomalies:
        messages.warning(request, f"Anomaly detection flagged {len(anomalies)} potential risk signals.")
    else:
        messages.success(request, "No procurement anomalies detected; telemetry matches expected historical patterns.")

    return redirect("core:procurement_detail", procurement_id=procurement.id)


@login_required
@require_POST
def procurement_submit_view(request, procurement_id):
    """Site Manager submits procurement record into review workflow."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_submit_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You cannot submit this procurement record.")

    comments = request.POST.get("comments", "")
    try:
        submit_procurement(procurement, user=request.user, request=request, comments=comments)
        messages.success(request, f"Procurement #{procurement.procurement_number} submitted for review.")
    except (ValidationError, Exception) as exc:
        messages.error(request, f"Submission blocked: {exc}")

    return redirect("core:procurement_detail", procurement_id=procurement.id)


@login_required
def procurement_review_inbox_view(request):
    """Inbox of submitted procurements requiring Subsidiary Manager review."""
    if not (
        request.user.has_role(Role.Code.SUBSIDIARY_MANAGER)
        or request.user.is_superuser
        or request.user.has_role(Role.Code.MEIL_OPERATOR)
        or request.user.has_role(Role.Code.ESG_MANAGER)
    ):
        raise PermissionDenied("Access Denied: Review inbox reserved for managers.")

    pending_qs = get_accessible_procurements(request.user).filter(
        status__in=[ProcurementStatus.SUBMITTED, ProcurementStatus.UNDER_REVIEW]
    ).order_by("-purchase_date")

    paginator = Paginator(pending_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(request, "procurement/procurement_review_inbox.html", {
        "page_obj": page_obj,
        "total_pending": pending_qs.count(),
    })


@login_required
def procurement_review_view(request, procurement_id):
    """Subsidiary Manager review panel for a submitted procurement transaction."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_review_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You do not have authorization to review this procurement record.")

    if request.method == "POST":
        form = ProcurementReviewForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data["action"]
            comments = form.cleaned_data.get("comments", "")
            correction_notes = form.cleaned_data.get("correction_notes", "")
            try:
                review_procurement(
                    procurement,
                    action=action,
                    user=request.user,
                    request=request,
                    comments=comments,
                    correction_notes=correction_notes,
                )
                messages.success(request, f"Review action '{action}' recorded for Procurement #{procurement.procurement_number}.")
                return redirect("core:procurement_detail", procurement_id=procurement.id)
            except (ValidationError, Exception) as exc:
                messages.error(request, f"Review failed: {exc}")
    else:
        form = ProcurementReviewForm()

    items = procurement.items.all()
    evidence_files = procurement.evidence_files.filter(status=EvidenceStatus.ACTIVE)
    anomalies = detect_procurement_anomalies(procurement) if procurement.has_anomalies else []

    return render(request, "procurement/procurement_review.html", {
        "procurement": procurement,
        "items": items,
        "evidence_files": evidence_files,
        "anomalies": anomalies,
        "form": form,
    })


@login_required
def procurement_correction_view(request, procurement_id):
    """Site Manager remediation editor for a procurement requiring correction."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if procurement.status != ProcurementStatus.CORRECTION_REQUESTED:
        messages.info(request, "This record does not currently require correction.")
        return redirect("core:procurement_detail", procurement_id=procurement.id)

    if not user_can_modify_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You cannot modify this procurement record.")

    if request.method == "POST":
        form = ProcurementCorrectionForm(request.POST, instance=procurement)
        if form.is_valid():
            try:
                explanation = form.cleaned_data["explanation"]
                update_procurement_record(procurement, form.cleaned_data, user=request.user, request=request)
                resubmit_procurement(procurement, user=request.user, request=request, explanation=explanation)
                messages.success(request, f"Procurement #{procurement.procurement_number} successfully corrected and resubmitted.")
                return redirect("core:procurement_detail", procurement_id=procurement.id)
            except (ValidationError, Exception) as exc:
                messages.error(request, f"Correction submission failed: {exc}")
    else:
        form = ProcurementCorrectionForm(instance=procurement)

    return render(request, "procurement/procurement_correction.html", {
        "procurement": procurement,
        "form": form,
        "items": procurement.items.all(),
    })


@login_required
def procurement_ocr_compare_view(request, procurement_id, evidence_id):
    """Compares extracted OCR document data with authoritative procurement record."""
    procurement = get_object_or_404(ProcurementRecord, id=procurement_id)
    if not user_can_access_procurement(request.user, procurement):
        raise PermissionDenied("Access Denied: You cannot inspect this procurement record.")

    evidence = get_object_or_404(Evidence, id=evidence_id, procurement_record=procurement)
    latest_run = evidence.ocr_runs.filter(status=OCRStatus.COMPLETED).order_by("-run_number").first()

    if not latest_run:
        messages.warning(request, "No completed OCR runs exist for this evidence document. Run OCR first.")
        return redirect("core:procurement_detail", procurement_id=procurement.id)

    comparison = compare_ocr_with_procurement(latest_run, procurement)

    return render(request, "procurement/procurement_ocr_compare.html", {
        "procurement": procurement,
        "evidence": evidence,
        "ocr_run": latest_run,
        "comparison": comparison,
    })
