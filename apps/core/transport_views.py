"""
Views for Transport & Logistics Management (Phase 17) in MEIL ESG CONTROL TOWER.

Fulfills Phase 17 Requirements:
- Strict object-level RBAC & Anti-IDOR protection across all routes
- Transport Provider (Carrier) directory, profiling, and lifecycle
- Vehicle fleet asset management with Scope 1 (owned) vs Scope 3 (third-party) classification
- Transport Ledger with modal/route filtering, embedded shipment details, and KPI analytics
- Evidence document attachment with SHA-256 tamper-evident integrity
- Deterministic validation & operational anomaly detection
- Formal Submission & Subsidiary Manager Review Desk (Verify, Request Correction, Reject)
- Site Manager Correction & Resubmission workflow
- Document intelligence OCR reconciliation with zero silent overwrite
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
from apps.core.evidence_services import create_evidence_record
from apps.core.models import (
    ActivityRecord,
    AuthAuditLog,
    Carrier,
    CarrierStatus,
    CarrierType,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    OCRRun,
    OCRStatus,
    Role,
    Shipment,
    TransportMode,
    TransportRecord,
    TransportScopeCategory,
    TransportStatus,
    ValidationStatus,
    Vehicle,
    VehicleOwnershipType,
    VehicleStatus,
    VehicleType,
)
from apps.core.transport_forms import (
    CarrierFilterForm,
    CarrierForm,
    ShipmentForm,
    TransportCorrectionForm,
    TransportEvidenceUploadForm,
    TransportFilterForm,
    TransportRecordForm,
    TransportReviewForm,
    VehicleFilterForm,
    VehicleForm,
)
from apps.core.transport_services import (
    archive_carrier,
    archive_vehicle,
    compare_ocr_with_transport,
    correct_transport_record,
    create_carrier,
    create_transport_record,
    create_vehicle,
    delete_transport_record,
    detect_transport_anomalies,
    get_accessible_carriers,
    get_accessible_transports,
    get_accessible_vehicles,
    review_transport_record,
    submit_transport_record,
    update_carrier,
    update_transport_record,
    update_vehicle,
    user_can_access_carrier,
    user_can_access_transport,
    user_can_access_vehicle,
    user_can_delete_transport,
    user_can_modify_carrier,
    user_can_modify_transport,
    user_can_modify_vehicle,
    user_can_review_transport,
    user_can_submit_transport,
    validate_transport,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. CARRIER MASTER VIEWS
# -----------------------------------------------------------------------------

@login_required
def carrier_list_view(request):
    """Catalog of accessible Transport Providers & Logistics Carriers."""
    carriers_qs = get_accessible_carriers(request.user)

    filter_form = CarrierFilterForm(request.GET)
    if filter_form.is_valid():
        search = filter_form.cleaned_data.get("search")
        if search:
            carriers_qs = carriers_qs.filter(
                models.Q(name__icontains=search)
                | models.Q(carrier_code__icontains=search)
                | models.Q(contact_person__icontains=search)
            )
        c_type = filter_form.cleaned_data.get("carrier_type")
        if c_type:
            carriers_qs = carriers_qs.filter(carrier_type=c_type)
        status = filter_form.cleaned_data.get("status")
        if status:
            carriers_qs = carriers_qs.filter(status=status)

    total_carriers = carriers_qs.count()
    active_carriers = carriers_qs.filter(status=CarrierStatus.ACTIVE).count()
    road_carriers = carriers_qs.filter(carrier_type=CarrierType.ROAD_CARRIER).count()
    logistics_3pl = carriers_qs.filter(carrier_type=CarrierType.LOGISTICS_3PL).count()

    paginator = Paginator(carriers_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    can_create = user_can_modify_carrier(request.user, None)

    context = {
        "page_obj": page_obj,
        "filter_form": filter_form,
        "total_carriers": total_carriers,
        "active_carriers": active_carriers,
        "road_carriers": road_carriers,
        "logistics_3pl": logistics_3pl,
        "can_create": can_create,
    }
    return render(request, "transport/carrier_list.html", context)


@login_required
def carrier_detail_view(request, carrier_id):
    """Detailed profile, vehicle fleet, and transport trip history for a Carrier."""
    carrier = get_object_or_404(Carrier, id=carrier_id)
    if not user_can_access_carrier(request.user, carrier):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Carrier:{carrier_id}",
            details="Unauthorized attempt to access carrier profile.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to view this carrier.")

    vehicles = carrier.vehicles.all()[:20]
    transports = carrier.transports.select_related("site", "reporting_period").order_by("-transport_date")[:20]
    can_edit = user_can_modify_carrier(request.user, carrier)

    context = {
        "carrier": carrier,
        "vehicles": vehicles,
        "transports": transports,
        "can_edit": can_edit,
    }
    return render(request, "transport/carrier_detail.html", context)


@login_required
def carrier_create_view(request):
    """Registers a new Transport Carrier."""
    if not user_can_modify_carrier(request.user, None):
        raise PermissionDenied("Access Denied: You do not have authorization to register carriers.")

    if request.method == "POST":
        form = CarrierForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                carrier = create_carrier(form.cleaned_data, user=request.user, request=request)
                messages.success(request, f"Carrier '{carrier.name}' ({carrier.carrier_code}) registered successfully.")
                return redirect("core:carrier_detail", carrier_id=carrier.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = CarrierForm(user=request.user)

    return render(request, "transport/carrier_form.html", {"form": form, "is_create": True})


@login_required
def carrier_edit_view(request, carrier_id):
    """Edits an existing Transport Carrier master record."""
    carrier = get_object_or_404(Carrier, id=carrier_id)
    if not user_can_modify_carrier(request.user, carrier):
        raise PermissionDenied("Access Denied: You do not have authorization to edit this carrier.")

    if request.method == "POST":
        form = CarrierForm(request.POST, instance=carrier, user=request.user)
        if form.is_valid():
            try:
                update_carrier(carrier, form.cleaned_data, user=request.user, request=request)
                messages.success(request, f"Carrier '{carrier.name}' updated successfully.")
                return redirect("core:carrier_detail", carrier_id=carrier.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = CarrierForm(instance=carrier, user=request.user)

    return render(request, "transport/carrier_form.html", {"form": form, "carrier": carrier, "is_create": False})


@login_required
@require_POST
def carrier_archive_view(request, carrier_id):
    """Soft-archives a carrier master record."""
    carrier = get_object_or_404(Carrier, id=carrier_id)
    if not user_can_modify_carrier(request.user, carrier):
        raise PermissionDenied("Access Denied: You cannot archive this carrier.")

    archive_carrier(carrier, user=request.user, request=request)
    messages.warning(request, f"Carrier '{carrier.name}' has been soft-archived.")
    return redirect("core:carrier_list")


# -----------------------------------------------------------------------------
# 2. VEHICLE MASTER VIEWS
# -----------------------------------------------------------------------------

@login_required
def vehicle_list_view(request):
    """Fleet catalog of accessible vehicles and mobile combustion assets."""
    vehicles_qs = get_accessible_vehicles(request.user)

    filter_form = VehicleFilterForm(request.GET)
    if filter_form.is_valid():
        search = filter_form.cleaned_data.get("search")
        if search:
            vehicles_qs = vehicles_qs.filter(
                models.Q(registration_number__icontains=search)
                | models.Q(vehicle_identifier__icontains=search)
            )
        owner_type = filter_form.cleaned_data.get("ownership_type")
        if owner_type:
            vehicles_qs = vehicles_qs.filter(ownership_type=owner_type)
        v_type = filter_form.cleaned_data.get("vehicle_type")
        if v_type:
            vehicles_qs = vehicles_qs.filter(vehicle_type=v_type)
        fuel = filter_form.cleaned_data.get("fuel_type")
        if fuel:
            vehicles_qs = vehicles_qs.filter(fuel_type=fuel)
        status = filter_form.cleaned_data.get("status")
        if status:
            vehicles_qs = vehicles_qs.filter(status=status)

    total_vehicles = vehicles_qs.count()
    active_vehicles = vehicles_qs.filter(status=VehicleStatus.ACTIVE).count()
    owned_vehicles = vehicles_qs.filter(ownership_type__in=[VehicleOwnershipType.OWNED, VehicleOwnershipType.LEASED]).count()
    heavy_trucks = vehicles_qs.filter(vehicle_type=VehicleType.TRUCK_HEAVY).count()

    paginator = Paginator(vehicles_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    can_create = user_can_modify_vehicle(request.user, None)

    context = {
        "page_obj": page_obj,
        "filter_form": filter_form,
        "total_vehicles": total_vehicles,
        "active_vehicles": active_vehicles,
        "owned_vehicles": owned_vehicles,
        "heavy_trucks": heavy_trucks,
        "can_create": can_create,
    }
    return render(request, "transport/vehicle_list.html", context)


@login_required
def vehicle_detail_view(request, vehicle_id):
    """Detailed vehicle asset profile, payload specs, and trip history."""
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    if not user_can_access_vehicle(request.user, vehicle):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Vehicle:{vehicle_id}",
            details="Unauthorized attempt to view vehicle details.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to view this vehicle.")

    transports = vehicle.transports.select_related("site", "reporting_period").order_by("-transport_date")[:20]
    can_edit = user_can_modify_vehicle(request.user, vehicle)

    context = {
        "vehicle": vehicle,
        "transports": transports,
        "can_edit": can_edit,
    }
    return render(request, "transport/vehicle_detail.html", context)


@login_required
def vehicle_create_view(request):
    """Registers a new Vehicle asset."""
    if not user_can_modify_vehicle(request.user, None):
        raise PermissionDenied("Access Denied: You do not have authorization to register vehicles.")

    if request.method == "POST":
        form = VehicleForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                vehicle = create_vehicle(form.cleaned_data, user=request.user, request=request)
                messages.success(request, f"Vehicle '{vehicle.registration_number}' registered successfully.")
                return redirect("core:vehicle_detail", vehicle_id=vehicle.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = VehicleForm(user=request.user)

    return render(request, "transport/vehicle_form.html", {"form": form, "is_create": True})


@login_required
def vehicle_edit_view(request, vehicle_id):
    """Edits an existing Vehicle master record."""
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    if not user_can_modify_vehicle(request.user, vehicle):
        raise PermissionDenied("Access Denied: You do not have authorization to edit this vehicle.")

    if request.method == "POST":
        form = VehicleForm(request.POST, instance=vehicle, user=request.user)
        if form.is_valid():
            try:
                update_vehicle(vehicle, form.cleaned_data, user=request.user, request=request)
                messages.success(request, f"Vehicle '{vehicle.registration_number}' updated successfully.")
                return redirect("core:vehicle_detail", vehicle_id=vehicle.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = VehicleForm(instance=vehicle, user=request.user)

    return render(request, "transport/vehicle_form.html", {"form": form, "vehicle": vehicle, "is_create": False})


@login_required
@require_POST
def vehicle_archive_view(request, vehicle_id):
    """Soft-archives a vehicle master record."""
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    if not user_can_modify_vehicle(request.user, vehicle):
        raise PermissionDenied("Access Denied: You cannot archive this vehicle.")

    archive_vehicle(vehicle, user=request.user, request=request)
    messages.warning(request, f"Vehicle '{vehicle.registration_number}' has been soft-archived.")
    return redirect("core:vehicle_list")


# -----------------------------------------------------------------------------
# 3. TRANSPORT RECORD VIEWS
# -----------------------------------------------------------------------------

@login_required
def transport_list_view(request):
    """Authoritative Transport & Logistics Ledger."""
    transports_qs = get_accessible_transports(request.user)

    filter_form = TransportFilterForm(request.GET)
    if filter_form.is_valid():
        search = filter_form.cleaned_data.get("search")
        if search:
            transports_qs = transports_qs.filter(
                models.Q(transport_reference__icontains=search)
                | models.Q(origin_location__icontains=search)
                | models.Q(destination_location__icontains=search)
                | models.Q(carrier__name__icontains=search)
                | models.Q(vehicle__registration_number__icontains=search)
                | models.Q(shipment__material_description__icontains=search)
            )
        mode = filter_form.cleaned_data.get("transport_mode")
        if mode:
            transports_qs = transports_qs.filter(transport_mode=mode)
        status = filter_form.cleaned_data.get("status")
        if status:
            transports_qs = transports_qs.filter(status=status)
        scope = filter_form.cleaned_data.get("scope_category")
        if scope:
            transports_qs = transports_qs.filter(scope_category=scope)
        val_status = filter_form.cleaned_data.get("validation_status")
        if val_status:
            transports_qs = transports_qs.filter(validation_status=val_status)
        anom = filter_form.cleaned_data.get("has_anomalies")
        if anom == "yes":
            transports_qs = transports_qs.filter(has_anomalies=True)
        elif anom == "no":
            transports_qs = transports_qs.filter(has_anomalies=False)

    # Specific carrier filter via GET
    carrier_param = request.GET.get("carrier")
    if carrier_param:
        transports_qs = transports_qs.filter(carrier_id=carrier_param)

    # Specific vehicle filter via GET
    vehicle_param = request.GET.get("vehicle")
    if vehicle_param:
        transports_qs = transports_qs.filter(vehicle_id=vehicle_param)

    # KPI telemetry
    total_transports = transports_qs.count()
    road_transports = transports_qs.filter(transport_mode=TransportMode.ROAD).count()
    submitted_transports = transports_qs.filter(status=TransportStatus.SUBMITTED).count()
    verified_transports = transports_qs.filter(status=TransportStatus.VERIFIED).count()
    anomalous_transports = transports_qs.filter(has_anomalies=True).count()
    total_distance_km = transports_qs.filter(distance_unit="KM").aggregate(models.Sum("distance"))["distance__sum"] or Decimal("0.00")

    paginator = Paginator(transports_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    is_site_mgr = request.user.has_role(Role.Code.SITE_MANAGER)
    is_sub_mgr = request.user.has_role(Role.Code.SUBSIDIARY_MANAGER)
    can_create = (
        request.user.is_superuser
        or request.user.has_role(Role.Code.MEIL_OPERATOR)
        or request.user.has_role(Role.Code.ESG_MANAGER)
        or is_site_mgr
    )

    context = {
        "page_obj": page_obj,
        "filter_form": filter_form,
        "total_count": total_transports,
        "total_transports": total_transports,
        "road_transports": road_transports,
        "submitted_transports": submitted_transports,
        "pending_review": submitted_transports,
        "verified_transports": verified_transports,
        "anomalous_transports": anomalous_transports,
        "anomalies_count": anomalous_transports,
        "total_distance_km": total_distance_km,
        "can_create": can_create,
        "is_sub_mgr": is_sub_mgr,
    }
    return render(request, "transport/transport_list.html", context)



@login_required
def transport_detail_view(request, transport_id):
    """
    Comprehensive Transport Detail View with complete traceability:
    movement parameters, shipment cargo, carrier/vehicle, route, evidence,
    validation status, active anomalies, and review decisions.
    """
    transport = get_object_or_404(
        TransportRecord.objects.select_related(
            "reporting_period",
            "company",
            "project",
            "site",
            "carrier",
            "vehicle",
            "shipment",
            "procurement",
            "activity_record",
            "parent_transport",
            "created_by",
            "updated_by",
        ),
        id=transport_id,
    )
    if not user_can_access_transport(request.user, transport):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"TransportRecord:{transport_id}",
            details="Unauthorized attempt to view transport record.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to view this transport record.")

    evidence_files = transport.evidence_files.filter(status=EvidenceStatus.ACTIVE).select_related("uploaded_by")

    # Fetch OCR runs for attached evidence
    ocr_runs = OCRRun.objects.filter(evidence__in=evidence_files).select_related("evidence").prefetch_related("fields")

    can_edit = user_can_modify_transport(request.user, transport)
    can_submit = user_can_submit_transport(request.user, transport) and transport.status in [
        TransportStatus.DRAFT, TransportStatus.CORRECTION_REQUESTED
    ]
    can_review = user_can_review_transport(request.user, transport)
    can_upload_evidence = user_can_modify_transport(request.user, transport)

    # Fetch audit events
    audit_events = AuthAuditLog.objects.filter(
        resource_accessed__startswith=f"TransportRecord:{transport.id}"
    ).select_related("user").order_by("-created_at")[:15]

    context = {
        "transport": transport,
        "evidence_files": evidence_files,
        "ocr_runs": ocr_runs,
        "audit_events": audit_events,
        "can_edit": can_edit,
        "can_submit": can_submit,
        "can_review": can_review,
        "can_upload_evidence": can_upload_evidence,
    }
    return render(request, "transport/transport_detail.html", context)


@login_required
def transport_create_view(request):
    """Records a new Transport event with embedded or linked shipment."""
    can_create = (
        request.user.is_superuser
        or request.user.has_role(Role.Code.MEIL_OPERATOR)
        or request.user.has_role(Role.Code.ESG_MANAGER)
        or request.user.has_role(Role.Code.SITE_MANAGER)
    )
    if not can_create:
        raise PermissionDenied("Access Denied: You do not have authorization to record transport events.")

    if request.method == "POST":
        form = TransportRecordForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                shipment_data = {}
                if form.cleaned_data.get("shipment_material"):
                    shipment_data = {
                        "material_description": form.cleaned_data["shipment_material"],
                        "quantity": form.cleaned_data.get("shipment_quantity") or Decimal("0.0000"),
                        "unit": form.cleaned_data.get("shipment_unit"),
                        "weight_net": form.cleaned_data.get("shipment_weight_net"),
                        "delivery_reference": form.cleaned_data.get("shipment_delivery_ref", ""),
                    }
                transport = create_transport_record(
                    form.cleaned_data,
                    user=request.user,
                    request=request,
                    shipment_data=shipment_data if shipment_data else None,
                )
                messages.success(request, f"Transport #{transport.transport_reference} recorded successfully.")
                return redirect("core:transport_detail", transport_id=transport.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = TransportRecordForm(user=request.user)

    return render(request, "transport/transport_form.html", {"form": form, "is_create": True})


@login_required
def transport_edit_view(request, transport_id):
    """Edits a draft or correction-requested transport record."""
    transport = get_object_or_404(TransportRecord, id=transport_id)
    if not user_can_modify_transport(request.user, transport):
        raise PermissionDenied("Access Denied: You do not have authorization to edit this transport record.")

    if request.method == "POST":
        form = TransportRecordForm(request.POST, instance=transport, user=request.user)
        if form.is_valid():
            try:
                shipment_data = {}
                if form.cleaned_data.get("shipment_material"):
                    shipment_data = {
                        "material_description": form.cleaned_data["shipment_material"],
                        "quantity": form.cleaned_data.get("shipment_quantity") or Decimal("0.0000"),
                        "unit": form.cleaned_data.get("shipment_unit"),
                        "weight_net": form.cleaned_data.get("shipment_weight_net"),
                        "delivery_reference": form.cleaned_data.get("shipment_delivery_ref", ""),
                    }
                update_transport_record(
                    transport,
                    form.cleaned_data,
                    user=request.user,
                    request=request,
                    shipment_data=shipment_data if shipment_data else None,
                )
                messages.success(request, f"Transport #{transport.transport_reference} updated successfully.")
                return redirect("core:transport_detail", transport_id=transport.id)
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
    else:
        form = TransportRecordForm(instance=transport, user=request.user)

    return render(request, "transport/transport_form.html", {"form": form, "transport": transport, "is_create": False})


@login_required
@require_POST
def transport_delete_view(request, transport_id):
    """Deletes a draft transport record."""
    transport = get_object_or_404(TransportRecord, id=transport_id)
    if not user_can_delete_transport(request.user, transport):
        raise PermissionDenied("Access Denied: You cannot delete this transport record.")

    ref = transport.transport_reference
    delete_transport_record(transport, user=request.user, request=request)
    messages.success(request, f"Draft Transport #{ref} has been deleted.")
    return redirect("core:transport_list")


@login_required
def transport_evidence_upload_view(request, transport_id):
    """Uploads supporting documentation (Lorry Receipt, Trip Sheet) directly to a TransportRecord."""
    transport = get_object_or_404(TransportRecord, id=transport_id)
    if not user_can_modify_transport(request.user, transport):
        raise PermissionDenied("Access Denied: You cannot attach evidence to this transport record.")

    if request.method == "POST":
        form = TransportEvidenceUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                evidence = create_evidence_record(
                    transport_record=transport,
                    uploaded_file=form.cleaned_data["file"],
                    evidence_type=form.cleaned_data["evidence_type"],
                    description=form.cleaned_data["description"],
                    user=request.user,
                    request=request,
                )
                messages.success(
                    request,
                    f"Evidence '{evidence.original_filename}' uploaded successfully for Transport #{transport.transport_reference}."
                )
                return redirect("core:transport_detail", transport_id=transport.id)
            except ValidationError as exc:
                messages.error(request, f"Upload validation failed: {exc}")
    else:
        form = TransportEvidenceUploadForm()

    return render(request, "transport/transport_evidence_upload.html", {"form": form, "transport": transport})


@login_required
@require_POST
def transport_validate_view(request, transport_id):
    """Triggers deterministic validation rules evaluation on a TransportRecord."""
    transport = get_object_or_404(TransportRecord, id=transport_id)
    if not user_can_access_transport(request.user, transport):
        raise PermissionDenied("Access Denied.")

    result = validate_transport(transport, user=request.user, request=request)
    if result["status"] == ValidationStatus.VALID:
        messages.success(request, f"Transport #{transport.transport_reference} passed all validation checks.")
    elif result["status"] == ValidationStatus.WARNING:
        messages.warning(
            request,
            f"Transport #{transport.transport_reference} validated with warnings: {'; '.join(result['warnings'])}"
        )
    else:
        messages.error(
            request,
            f"Validation failed for Transport #{transport.transport_reference}: {'; '.join(result['errors'])}"
        )

    return redirect("core:transport_detail", transport_id=transport.id)


@login_required
@require_POST
def transport_anomaly_detect_view(request, transport_id):
    """Evaluates transport anomaly detection rules."""
    transport = get_object_or_404(TransportRecord, id=transport_id)
    if not user_can_access_transport(request.user, transport):
        raise PermissionDenied("Access Denied.")

    anomalies = detect_transport_anomalies(transport, user=request.user, request=request)
    if anomalies:
        messages.warning(
            request,
            f"Detected {len(anomalies)} anomalies on Transport #{transport.transport_reference}."
        )
    else:
        messages.success(
            request,
            f"No anomalies detected for Transport #{transport.transport_reference}."
        )

    return redirect("core:transport_detail", transport_id=transport.id)


@login_required
@require_POST
def transport_submit_view(request, transport_id):
    """Submits a TransportRecord for formal Subsidiary Review."""
    transport = get_object_or_404(TransportRecord, id=transport_id)
    if not user_can_submit_transport(request.user, transport):
        raise PermissionDenied("Access Denied: You cannot submit this transport record.")

    try:
        submit_transport_record(transport, user=request.user, request=request)
        messages.success(
            request,
            f"Transport #{transport.transport_reference} submitted successfully for Subsidiary Review."
        )
    except ValidationError as exc:
        messages.error(request, f"Submission blocked: {exc}")

    return redirect("core:transport_detail", transport_id=transport.id)


@login_required
def transport_review_inbox_view(request):
    """Subsidiary Manager review workspace for submitted transport operations."""
    if not (
        request.user.is_superuser
        or request.user.has_role(Role.Code.MEIL_OPERATOR)
        or request.user.has_role(Role.Code.ESG_MANAGER)
        or request.user.has_role(Role.Code.SUBSIDIARY_MANAGER)
    ):
        raise PermissionDenied("Access Denied: Review inbox reserved for managers.")

    transports_qs = get_accessible_transports(request.user).filter(
        status__in=[TransportStatus.SUBMITTED, TransportStatus.UNDER_REVIEW]
    ).order_by("-transport_date")

    paginator = Paginator(transports_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "page_obj": page_obj,
        "pending_count": transports_qs.count(),
    }
    return render(request, "transport/transport_review_inbox.html", context)


@login_required
def transport_review_view(request, transport_id):
    """Review execution workspace for Subsidiary Manager."""
    transport = get_object_or_404(TransportRecord, id=transport_id)
    if not user_can_review_transport(request.user, transport):
        raise PermissionDenied("Access Denied: You do not have authorization to review this transport record.")

    if request.method == "POST":
        form = TransportReviewForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data["action"]
            comments = form.cleaned_data.get("comments", "")
            try:
                review_transport_record(transport, reviewer=request.user, action=action, comments=comments, request=request)
                if action == "VERIFY":
                    messages.success(request, f"Transport #{transport.transport_reference} verified successfully.")
                elif action == "REQUEST_CORRECTION":
                    messages.warning(request, f"Correction requested for Transport #{transport.transport_reference}.")
                else:
                    messages.error(request, f"Transport #{transport.transport_reference} rejected.")
                return redirect("core:transport_review_inbox")
            except ValidationError as exc:
                messages.error(request, f"Review error: {exc}")
    else:
        form = TransportReviewForm()

    context = {
        "transport": transport,
        "form": form,
        "evidence_files": transport.evidence_files.filter(status=EvidenceStatus.ACTIVE),
    }
    return render(request, "transport/transport_review.html", context)


@login_required
def transport_correction_view(request, transport_id):
    """Site Manager workspace for remediating a CORRECTION_REQUESTED transport record."""
    transport = get_object_or_404(TransportRecord, id=transport_id)
    if transport.status != TransportStatus.CORRECTION_REQUESTED:
        messages.info(request, f"Transport #{transport.transport_reference} is not currently awaiting correction.")
        return redirect("core:transport_detail", transport_id=transport.id)

    if not user_can_modify_transport(request.user, transport):
        raise PermissionDenied("Access Denied: You cannot modify this transport record.")

    if request.method == "POST":
        form = TransportRecordForm(request.POST, instance=transport, user=request.user)
        correction_form = TransportCorrectionForm(request.POST)
        if form.is_valid() and correction_form.is_valid():
            try:
                shipment_data = {}
                if form.cleaned_data.get("shipment_material"):
                    shipment_data = {
                        "material_description": form.cleaned_data["shipment_material"],
                        "quantity": form.cleaned_data.get("shipment_quantity") or Decimal("0.0000"),
                        "unit": form.cleaned_data.get("shipment_unit"),
                        "weight_net": form.cleaned_data.get("shipment_weight_net"),
                        "delivery_reference": form.cleaned_data.get("shipment_delivery_ref", ""),
                    }
                update_transport_record(
                    transport,
                    form.cleaned_data,
                    user=request.user,
                    request=request,
                    shipment_data=shipment_data if shipment_data else None,
                )
                correct_transport_record(
                    transport,
                    user=request.user,
                    correction_notes=correction_form.cleaned_data["correction_notes"],
                    request=request,
                )
                messages.success(
                    request,
                    f"Transport #{transport.transport_reference} resubmitted successfully after correction."
                )
                return redirect("core:transport_detail", transport_id=transport.id)
            except ValidationError as exc:
                messages.error(request, f"Correction submission failed: {exc}")
    else:
        form = TransportRecordForm(instance=transport, user=request.user)
        correction_form = TransportCorrectionForm()

    context = {
        "transport": transport,
        "form": form,
        "correction_form": correction_form,
    }
    return render(request, "transport/transport_correction.html", context)


@login_required
def transport_ocr_compare_view(request, transport_id, evidence_id):
    """Automated document intelligence comparison for a transport evidence document."""
    transport = get_object_or_404(TransportRecord, id=transport_id)
    if not user_can_access_transport(request.user, transport):
        raise PermissionDenied("Access Denied.")

    evidence = get_object_or_404(Evidence, id=evidence_id, transport_record=transport)
    ocr_run = OCRRun.objects.filter(evidence=evidence, status=OCRStatus.COMPLETED).order_by("-created_at").first()

    comparison = None
    if ocr_run:
        comparison = compare_ocr_with_transport(ocr_run, transport)

    context = {
        "transport": transport,
        "evidence": evidence,
        "ocr_run": ocr_run,
        "comparison": comparison,
    }
    return render(request, "transport/transport_ocr_compare.html", context)
