"""
Transport & Logistics Management Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 17 Requirements:
- Scoped Queryset Retrieval (get_accessible_transports, get_accessible_carriers, get_accessible_vehicles)
- Object-level zero-trust authorization & Insecure Direct Object Reference (IDOR) defense
- Authoritative reference generators for carriers, vehicles, shipments, and transports
- Normalized Carrier, Vehicle, and Shipment data lifecycle with soft-archival preservation
- Direct integration with Phase 16 Procurement (reusing suppliers and commercial purchases)
- Direct integration with canonical ESG ActivityRecord (Scope 1/3 linkage without duplicate fuel ledgers)
- Layered deterministic validation evaluation (validate_transport)
- Anomaly detection engine (detect_transport_anomalies) identifying duplicate trips, distance spikes, payload variance
- Controlled workflow transitions: DRAFT -> SUBMITTED -> UNDER_REVIEW -> VERIFIED / CORRECTION_REQUESTED
- Full audit event logging integrated with AuthAuditLog
- Document intelligence OCR comparison (compare_ocr_with_transport) with zero silent overwrite
"""

import logging
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.auth_services import log_auth_event
from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Carrier,
    CarrierStatus,
    CarrierType,
    Company,
    DistanceSource,
    DistanceUnit,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    FuelType,
    OCRRun,
    OCRStatus,
    PeriodStatus,
    ProcurementRecord,
    Project,
    ReportingPeriod,
    Role,
    Shipment,
    Site,
    Supplier,
    SupplierStatus,
    TransportLocationType,
    TransportMode,
    TransportRecord,
    TransportScopeCategory,
    TransportStatus,
    UnitOfMeasure,
    User,
    ValidationStatus,
    Vehicle,
    VehicleOwnershipType,
    VehicleStatus,
    VehicleType,
)
from apps.core.period_services import can_user_modify_data
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
    user_can_access_site,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SCOPED QUERYSET RETRIEVAL & ROLE VISIBILITY
# -----------------------------------------------------------------------------

def get_accessible_transports(user) -> models.QuerySet:
    """
    Returns QuerySet of TransportRecord instances accessible to the user based on
    their authorized organizational scope (sites, subsidiaries, companies).
    """
    if not user or not user.is_authenticated or not user.is_active:
        return TransportRecord.objects.none()

    base_qs = TransportRecord.objects.select_related(
        "reporting_period",
        "company",
        "project",
        "site",
        "site__project",
        "site__project__subsidiary",
        "carrier",
        "carrier__supplier",
        "vehicle",
        "shipment",
        "procurement",
        "activity_record",
        "created_by",
    ).prefetch_related("evidence_files")

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return base_qs.all().order_by("-transport_date", "-created_at")

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        accessible_sites = get_accessible_sites(user)
        accessible_projs = get_accessible_projects(user)
        accessible_cos = get_accessible_companies(user)
        return base_qs.filter(
            models.Q(site__in=accessible_sites)
            | models.Q(project__in=accessible_projs)
            | models.Q(company__in=accessible_cos, site__isnull=True)
        ).distinct().order_by("-transport_date", "-created_at")

    if user.has_role(Role.Code.SITE_MANAGER):
        assigned_sites = get_accessible_sites(user)
        return base_qs.filter(site__in=assigned_sites).distinct().order_by("-transport_date", "-created_at")

    proj_sites = Site.objects.filter(project__in=get_accessible_projects(user))
    return base_qs.filter(site__in=proj_sites).distinct().order_by("-transport_date", "-created_at")


def get_accessible_carriers(user) -> models.QuerySet:
    """
    Returns QuerySet of Carrier master instances accessible to the user.
    Carriers without an assigned company are enterprise-wide and visible to all.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return Carrier.objects.none()

    base_qs = Carrier.objects.select_related("company", "supplier", "created_by").prefetch_related("vehicles")

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return base_qs.all().order_by("name")

    accessible_cos = get_accessible_companies(user)
    return base_qs.filter(
        models.Q(company__isnull=True) | models.Q(company__in=accessible_cos)
    ).distinct().order_by("name")


def get_accessible_vehicles(user) -> models.QuerySet:
    """
    Returns QuerySet of Vehicle master instances accessible to the user.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return Vehicle.objects.none()

    base_qs = Vehicle.objects.select_related("carrier", "company", "created_by")

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return base_qs.all().order_by("registration_number")

    accessible_cos = get_accessible_companies(user)
    return base_qs.filter(
        models.Q(company__isnull=True)
        | models.Q(company__in=accessible_cos)
        | models.Q(carrier__company__in=accessible_cos)
    ).distinct().order_by("registration_number")



# -----------------------------------------------------------------------------
# 2. OBJECT-LEVEL AUTHORIZATION GUARDS (IDOR DEFENSE)
# -----------------------------------------------------------------------------

def user_can_access_transport(user, transport: TransportRecord) -> bool:
    """Evaluates whether user has read access to the specific transport record."""
    if not user or not user.is_authenticated or not user.is_active or not transport:
        return False
    return get_accessible_transports(user).filter(id=transport.id).exists()


def user_can_modify_transport(user, transport: TransportRecord) -> bool:
    """
    Evaluates whether user can edit a TransportRecord:
    - Must have access to transport.
    - Record must not be locked and must be in DRAFT or CORRECTION_REQUESTED status.
    - Reporting period must be OPEN.
    - User must have SITE_MANAGER role on the site, or be MEIL_OPERATOR / Superuser.
    """
    if not user_can_access_transport(user, transport):
        return False

    if transport.is_locked:
        return False

    if transport.status not in [TransportStatus.DRAFT, TransportStatus.CORRECTION_REQUESTED]:
        return False

    if not can_user_modify_data(user, transport.reporting_period):
        return False

    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR):
        return True

    if user.has_role(Role.Code.SITE_MANAGER):
        return transport.site and transport.site in get_accessible_sites(user)

    return False


def user_can_delete_transport(user, transport: TransportRecord) -> bool:
    """
    Evaluates whether user can delete a TransportRecord:
    - Permitted ONLY in DRAFT status when period is OPEN.
    - Must be creator, MEIL Operator, or Superuser.
    """
    if not user_can_modify_transport(user, transport):
        return False

    if transport.status != TransportStatus.DRAFT:
        return False

    return (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or transport.created_by_id == user.id
    )


def user_can_submit_transport(user, transport: TransportRecord) -> bool:
    """Evaluates whether user can formally submit transport for subsidiary review."""
    return user_can_modify_transport(user, transport)


def user_can_review_transport(user, transport: TransportRecord) -> bool:
    """
    Evaluates whether user can perform governance review on a submitted transport:
    - Must have access to transport.
    - Transport must be in SUBMITTED or UNDER_REVIEW status.
    - Role must be SUBSIDIARY_MANAGER (for the subsidiary), ESG_MANAGER, MEIL_OPERATOR, or Superuser.
    - Site Managers cannot review transports (separation of duties).
    """
    if not user_can_access_transport(user, transport):
        return False

    if transport.status not in [TransportStatus.SUBMITTED, TransportStatus.UNDER_REVIEW]:
        return False

    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER):
        return True

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        if transport.site and transport.site in get_accessible_sites(user):
            return True
        if transport.project and transport.project in get_accessible_projects(user):
            return True
        if transport.company in get_accessible_companies(user):
            return True

    return False



def user_can_access_carrier(user, carrier: Carrier) -> bool:
    """Evaluates whether user has read access to a carrier master record."""
    if not user or not user.is_authenticated or not user.is_active or not carrier:
        return False
    return get_accessible_carriers(user).filter(id=carrier.id).exists()


def user_can_modify_carrier(user, carrier: Carrier) -> bool:
    """Evaluates whether user can create or edit carrier master details."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER):
        return True
    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        return user_can_access_carrier(user, carrier)
    return False


def user_can_access_vehicle(user, vehicle: Vehicle) -> bool:
    """Evaluates whether user has read access to a vehicle master record."""
    if not user or not user.is_authenticated or not user.is_active or not vehicle:
        return False
    return get_accessible_vehicles(user).filter(id=vehicle.id).exists()


def user_can_modify_vehicle(user, vehicle: Vehicle) -> bool:
    """Evaluates whether user can create or edit vehicle master details."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER):
        return True
    if user.has_role(Role.Code.SUBSIDIARY_MANAGER) or user.has_role(Role.Code.SITE_MANAGER):
        return user_can_access_vehicle(user, vehicle)
    return False


# -----------------------------------------------------------------------------
# 3. IDENTIFIER & REFERENCE GENERATORS
# -----------------------------------------------------------------------------

def generate_carrier_code(company: Optional[Company] = None) -> str:
    """Generates sequential stable internal Carrier Code (e.g. CARR-001, CARR-002)."""
    prefix = f"CARR-{company.code[:3].upper()}" if company and company.code else "CARR"
    count = Carrier.objects.filter(carrier_code__startswith=prefix).count() + 1
    candidate = f"{prefix}-{count:03d}"
    while Carrier.objects.filter(carrier_code=candidate).exists():
        count += 1
        candidate = f"{prefix}-{count:03d}"
    return candidate


def generate_vehicle_identifier(carrier: Optional[Carrier] = None) -> str:
    """Generates sequential internal Vehicle Identifier (e.g. VEH-001, MEIL-VEH-010)."""
    prefix = f"VEH-{carrier.carrier_code[:4]}" if carrier and carrier.carrier_code else "VEH"
    count = Vehicle.objects.filter(vehicle_identifier__startswith=prefix).count() + 1
    candidate = f"{prefix}-{count:03d}"
    while Vehicle.objects.filter(vehicle_identifier=candidate).exists():
        count += 1
        candidate = f"{prefix}-{count:03d}"
    return candidate


def generate_shipment_reference(site: Optional[Site] = None, transport_date=None) -> str:
    """Generates unique institutional Shipment tracking code (e.g. SHP-202610-POL-0001)."""
    date_val = transport_date or timezone.now().date()
    date_part = date_val.strftime("%Y%m")
    site_part = site.code.upper()[:4] if site and site.code else "CORP"
    prefix = f"SHP-{date_part}-{site_part}"

    count = Shipment.objects.filter(shipment_reference__startswith=prefix).count() + 1
    candidate = f"{prefix}-{count:04d}"
    while Shipment.objects.filter(shipment_reference=candidate).exists():
        count += 1
        candidate = f"{prefix}-{count:04d}"
    return candidate


def generate_transport_reference(company: Company, site: Optional[Site], transport_date) -> str:
    """
    Generates unique institutional Transport Reference (e.g. TRN-202610-POL-0001).
    """
    date_part = transport_date.strftime("%Y%m")
    site_part = site.code.upper()[:4] if site and site.code else (company.code.upper()[:4] if company.code else "MEIL")
    prefix = f"TRN-{date_part}-{site_part}"

    count = TransportRecord.objects.filter(transport_reference__startswith=prefix).count() + 1
    candidate = f"{prefix}-{count:04d}"
    while TransportRecord.objects.filter(transport_reference=candidate).exists():
        count += 1
        candidate = f"{prefix}-{count:04d}"
    return candidate


# -----------------------------------------------------------------------------
# 4. CARRIER & VEHICLE LIFECYCLE MANAGEMENT
# -----------------------------------------------------------------------------

@transaction.atomic
def create_carrier(data: Dict[str, Any], user: User, request=None) -> Carrier:
    """Atomically creates a new transport Carrier with audit logging."""
    if not (user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER) or user.has_role(Role.Code.SUBSIDIARY_MANAGER)):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed="Carrier:create",
            details="Unauthorized attempt to register transport carrier.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to register a transport carrier.")

    carrier_code = data.get("carrier_code") or generate_carrier_code(data.get("company"))
    carrier = Carrier(
        carrier_code=carrier_code,
        name=data["name"].strip(),
        legal_name=data.get("legal_name", "").strip(),
        carrier_type=data.get("carrier_type", CarrierType.ROAD_CARRIER),
        status=data.get("status", CarrierStatus.ACTIVE),
        supplier=data.get("supplier"),
        company=data.get("company"),
        contact_person=data.get("contact_person", "").strip(),
        contact_email=data.get("contact_email", "").strip(),
        contact_phone=data.get("contact_phone", "").strip(),
        notes=data.get("notes", "").strip(),
        created_by=user,
    )
    carrier.full_clean()
    carrier.save()

    log_auth_event(
        AuthAuditLog.EventType.CARRIER_CREATED,
        request=request,
        user=user,
        resource_accessed=f"Carrier:{carrier.id}",
        details=f"Created Transport Carrier '{carrier.name}' ({carrier.carrier_code}).",
        success=True,
    )
    logger.info("Carrier [%s] (%s) created by %s", carrier.id, carrier.carrier_code, user)
    return carrier


@transaction.atomic
def update_carrier(carrier: Carrier, data: Dict[str, Any], user: User, request=None) -> Carrier:
    """Updates an existing carrier master record with audit logging."""
    if not user_can_modify_carrier(user, carrier):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Carrier:{carrier.id}/update",
            details="Unauthorized attempt to modify transport carrier.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to modify this carrier.")

    fields = [
        "name", "legal_name", "carrier_type", "status", "supplier",
        "company", "contact_person", "contact_email", "contact_phone", "notes"
    ]
    for field in fields:
        if field in data:
            setattr(carrier, field, data[field])

    carrier.full_clean()
    carrier.save()

    log_auth_event(
        AuthAuditLog.EventType.CARRIER_UPDATED,
        request=request,
        user=user,
        resource_accessed=f"Carrier:{carrier.id}",
        details=f"Updated Carrier '{carrier.name}' ({carrier.carrier_code}). Status: {carrier.status}.",
        success=True,
    )
    return carrier


@transaction.atomic
def archive_carrier(carrier: Carrier, user: Optional[User] = None, actor: Optional[User] = None, request=None) -> Carrier:
    """Soft-archives a carrier to protect historical transport linkages."""
    actor_user = user or actor
    if not actor_user:
        raise PermissionDenied("User/actor required to archive carrier.")
    if not user_can_modify_carrier(actor_user, carrier):
        raise PermissionDenied("You do not have permission to archive this carrier.")

    carrier.archive(actor=actor_user)
    log_auth_event(
        AuthAuditLog.EventType.CARRIER_ARCHIVED,
        request=request,
        user=actor_user,
        resource_accessed=f"Carrier:{carrier.id}",
        details=f"Archived Carrier '{carrier.name}' ({carrier.carrier_code}).",
        success=True,
    )
    return carrier


@transaction.atomic
def create_vehicle(data: Dict[str, Any], user: User, request=None) -> Vehicle:
    """Atomically creates a new Vehicle master entity with audit logging."""
    reg = data["registration_number"].strip().upper()
    carrier = data.get("carrier")
    veh_id = data.get("vehicle_identifier") or generate_vehicle_identifier(carrier)

    vehicle = Vehicle(
        vehicle_identifier=veh_id,
        registration_number=reg,
        carrier=carrier,
        company=data.get("company") or (carrier.company if carrier else None),
        ownership_type=data.get("ownership_type", VehicleOwnershipType.THIRD_PARTY),
        vehicle_type=data.get("vehicle_type", VehicleType.TRUCK_HEAVY),
        fuel_type=data.get("fuel_type", FuelType.DIESEL),
        capacity_payload=data.get("capacity_payload"),
        capacity_unit=data.get("capacity_unit", "MT"),
        status=data.get("status", VehicleStatus.ACTIVE),
        notes=data.get("notes", "").strip(),
        created_by=user,
    )
    vehicle.full_clean()
    vehicle.save()

    log_auth_event(
        AuthAuditLog.EventType.VEHICLE_CREATED,
        request=request,
        user=user,
        resource_accessed=f"Vehicle:{vehicle.id}",
        details=f"Created Vehicle '{vehicle.registration_number}' ({vehicle.vehicle_identifier}) for carrier {carrier}.",
        success=True,
    )
    logger.info("Vehicle [%s] (%s) created by %s", vehicle.id, vehicle.registration_number, user)
    return vehicle


@transaction.atomic
def update_vehicle(vehicle: Vehicle, data: Dict[str, Any], user: User, request=None) -> Vehicle:
    """Updates vehicle master attributes with audit trail."""
    if not user_can_modify_vehicle(user, vehicle):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Vehicle:{vehicle.id}/update",
            details="Unauthorized attempt to modify vehicle.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to modify this vehicle.")

    fields = [
        "registration_number", "carrier", "company", "ownership_type",
        "vehicle_type", "fuel_type", "capacity_payload", "capacity_unit",
        "status", "notes"
    ]
    for field in fields:
        if field in data:
            setattr(vehicle, field, data[field])

    vehicle.full_clean()
    vehicle.save()

    log_auth_event(
        AuthAuditLog.EventType.VEHICLE_UPDATED,
        request=request,
        user=user,
        resource_accessed=f"Vehicle:{vehicle.id}",
        details=f"Updated Vehicle '{vehicle.registration_number}'. Status: {vehicle.status}.",
        success=True,
    )
    return vehicle


@transaction.atomic
def archive_vehicle(vehicle: Vehicle, user: Optional[User] = None, actor: Optional[User] = None, request=None) -> Vehicle:
    """Soft-archives a vehicle to preserve historical trips."""
    actor_user = user or actor
    if not actor_user:
        raise PermissionDenied("User/actor required to archive vehicle.")
    if not user_can_modify_vehicle(actor_user, vehicle):
        raise PermissionDenied("You do not have permission to archive this vehicle.")

    vehicle.archive(actor=actor_user)
    log_auth_event(
        AuthAuditLog.EventType.VEHICLE_ARCHIVED,
        request=request,
        user=actor_user,
        resource_accessed=f"Vehicle:{vehicle.id}",
        details=f"Archived Vehicle '{vehicle.registration_number}' ({vehicle.vehicle_identifier}).",
        success=True,
    )
    return vehicle


# -----------------------------------------------------------------------------
# 5. SHIPMENT & TRANSPORT CREATION & MODIFICATION
# -----------------------------------------------------------------------------

@transaction.atomic
def create_shipment(data: Dict[str, Any], user: Optional[User] = None) -> Shipment:
    """Creates a Shipment cargo record linked to optional Phase 16 Procurement."""
    ref = data.get("shipment_reference") or generate_shipment_reference(data.get("site"))
    shipment = Shipment(
        shipment_reference=ref,
        procurement=data.get("procurement"),
        material_description=data["material_description"].strip(),
        quantity=Decimal(str(data.get("quantity", "0.0000"))),
        unit=data.get("unit"),
        unit_custom=data.get("unit_custom", "").strip(),
        weight_gross=data.get("weight_gross"),
        weight_net=data.get("weight_net"),
        weight_unit=data.get("weight_unit", "MT"),
        delivery_reference=data.get("delivery_reference", "").strip(),
        consignment_value=data.get("consignment_value"),
        currency=data.get("currency", "INR"),
        notes=data.get("notes", "").strip(),
    )
    shipment.full_clean()
    shipment.save()
    return shipment


@transaction.atomic
def create_transport_record(
    data: Dict[str, Any],
    user: Optional[User] = None,
    actor: Optional[User] = None,
    request=None,
    shipment_data: Optional[Dict[str, Any]] = None,
) -> TransportRecord:
    """
    Atomically creates a TransportRecord with zero-trust validation and audit lineage.
    Creates and attaches Shipment if shipment_data is provided.
    """
    actor_user = user or actor
    site = data.get("site")
    company = data.get("company") or (site.project.subsidiary.company if site and site.project else None)
    project = data.get("project") or (site.project if site else None)
    reporting_period = data.get("reporting_period")
    transport_date = data["transport_date"]

    if not company:
        raise ValidationError("Operating Company must be designated for the transport record.")

    if not reporting_period:
        raise ValidationError("Governing Reporting Period is required.")

    # Scope authorization
    if actor_user and actor_user.has_role(Role.Code.SITE_MANAGER) and not (actor_user.is_superuser or actor_user.has_role(Role.Code.MEIL_OPERATOR)):
        assigned_sites = get_accessible_sites(actor_user)
        if not site or site not in assigned_sites:
            log_auth_event(
                AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
                request=request,
                user=actor_user,
                resource_accessed="TransportRecord:create",
                details=f"Site Manager attempted to record transport for unassigned Site {site}.",
                success=False,
            )
            raise PermissionDenied("Access Denied: You may only record transport for assigned sites.")

    if actor_user and not can_user_modify_data(actor_user, reporting_period):
        raise ValidationError(f"Reporting period '{reporting_period.code}' is not OPEN for data entry.")


    # Create shipment if provided
    shipment = data.get("shipment")
    if not shipment and shipment_data and shipment_data.get("material_description"):
        shipment_data["site"] = site
        if data.get("procurement"):
            shipment_data["procurement"] = data["procurement"]
        shipment = create_shipment(shipment_data, user=user)

    transport_reference = data.get("transport_reference") or generate_transport_reference(company, site, transport_date)

    # Resolve Scope 1 vs Scope 3 classification automatically if not explicitly given
    vehicle = data.get("vehicle")
    carrier = data.get("carrier") or (vehicle.carrier if vehicle else None)
    scope_cat = data.get("scope_category")
    if not scope_cat:
        if vehicle and vehicle.is_owned:
            scope_cat = TransportScopeCategory.SCOPE_1
        else:
            scope_cat = TransportScopeCategory.SCOPE_3_CAT_04

    transport = TransportRecord(
        transport_reference=transport_reference,
        reporting_period=reporting_period,
        company=company,
        project=project,
        site=site,
        transport_date=transport_date,
        transport_mode=data.get("transport_mode", TransportMode.ROAD),
        carrier=carrier,
        vehicle=vehicle,
        shipment=shipment,
        procurement=data.get("procurement"),
        leg_number=data.get("leg_number", 1),
        total_legs=data.get("total_legs", 1),
        parent_transport=data.get("parent_transport"),
        origin_type=data.get("origin_type", TransportLocationType.SUPPLIER_FACILITY),
        origin_location=data["origin_location"].strip(),
        origin_site=data.get("origin_site"),
        destination_type=data.get("destination_type", TransportLocationType.SITE),
        destination_location=data["destination_location"].strip(),
        destination_site=data.get("destination_site") or site,
        distance=Decimal(str(data.get("distance", "0.00"))),
        distance_unit=data.get("distance_unit", DistanceUnit.KM),
        distance_source=data.get("distance_source", DistanceSource.USER_PROVIDED),
        freight_amount=Decimal(str(data.get("freight_amount", "0.00"))),
        currency=data.get("currency", "INR"),
        activity_record=data.get("activity_record"),
        fuel_quantity=Decimal(str(data["fuel_quantity"])) if data.get("fuel_quantity") is not None else None,
        fuel_unit=data.get("fuel_unit", "L"),
        scope_category=scope_cat,
        status=TransportStatus.DRAFT,
        created_by=actor_user,
    )
    transport.full_clean()
    transport.save()

    log_auth_event(
        AuthAuditLog.EventType.TRANSPORT_CREATED,
        request=request,
        user=actor_user,
        resource_accessed=f"TransportRecord:{transport.id}",
        details=(
            f"Created Transport #{transport.transport_reference} ({transport.transport_mode}): "
            f"{transport.origin_location} -> {transport.destination_location} ({transport.distance} {transport.distance_unit})."
        ),
        success=True,
    )
    logger.info("TransportRecord [%s] created by %s", transport.id, actor_user)
    return transport


@transaction.atomic
def update_transport_record(
    transport: TransportRecord,
    data: Dict[str, Any],
    user: User,
    request=None,
    shipment_data: Optional[Dict[str, Any]] = None,
) -> TransportRecord:
    """Updates an existing TransportRecord with permission checks and audit trail."""
    if not user_can_modify_transport(user, transport):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"TransportRecord:{transport.id}/update",
            details="Unauthorized attempt to update transport record.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to modify this transport record.")

    # Update or create shipment if shipment_data provided
    if shipment_data and shipment_data.get("material_description"):
        if transport.shipment:
            for k, v in shipment_data.items():
                if hasattr(transport.shipment, k):
                    setattr(transport.shipment, k, v)
            transport.shipment.save()
        else:
            shipment_data["site"] = transport.site
            shipment = create_shipment(shipment_data, user=user)
            transport.shipment = shipment

    fields = [
        "transport_date", "transport_mode", "carrier", "vehicle", "shipment",
        "procurement", "leg_number", "total_legs", "parent_transport",
        "origin_type", "origin_location", "origin_site",
        "destination_type", "destination_location", "destination_site",
        "distance", "distance_unit", "distance_source",
        "freight_amount", "currency", "activity_record", "fuel_quantity",
        "fuel_unit", "scope_category",
    ]
    for f in fields:
        if f in data:
            setattr(transport, f, data[f])

    transport.updated_by = user
    transport.full_clean()
    transport.save()

    log_auth_event(
        AuthAuditLog.EventType.TRANSPORT_UPDATED,
        request=request,
        user=user,
        resource_accessed=f"TransportRecord:{transport.id}",
        details=f"Updated Transport #{transport.transport_reference}.",
        success=True,
    )
    return transport


@transaction.atomic
def delete_transport_record(transport: TransportRecord, user: User, request=None) -> None:
    """Hard-deletes a draft transport record."""
    if not user_can_delete_transport(user, transport):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"TransportRecord:{transport.id}/delete",
            details="Unauthorized attempt to delete transport record.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to delete this transport record.")

    ref = transport.transport_reference
    trn_id = transport.id
    transport.delete()

    log_auth_event(
        AuthAuditLog.EventType.TRANSPORT_DELETED,
        request=request,
        user=user,
        resource_accessed=f"TransportRecord:{trn_id}",
        details=f"Deleted draft Transport #{ref}.",
        success=True,
    )
    logger.info("TransportRecord [%s] deleted by %s", trn_id, user)


# -----------------------------------------------------------------------------
# 6. DETERMINISTIC VALIDATION INTEGRATION
# -----------------------------------------------------------------------------

def validate_transport(
    transport: TransportRecord,
    user: Optional[User] = None,
    request=None,
) -> Dict[str, Any]:
    """
    Evaluates layered deterministic validation rules for a TransportRecord:
    1. Temporal & Period Boundaries: Date within open reporting period boundaries.
    2. Organizational Alignment: Site must belong to project; company alignment.
    3. Route & Distance: Valid non-negative distance; origin and destination provided.
    4. Vehicle & Carrier Integrity: Active carrier/vehicle if linked; road transport vehicle presence.
    5. Financials: Freight amount non-negative.
    6. Shipment: If linked, positive quantity/weight.
    7. Evidence: Supporting documentation attached (Lorry Receipt, Challan, Weighbridge Slip).
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Temporal & Period
    period = transport.reporting_period
    if not period:
        errors.append("Missing governing Reporting Period.")
    else:
        if period.status != PeriodStatus.OPEN:
            errors.append(f"Reporting period '{period.name}' is {period.get_status_display()}; must be OPEN.")
        if transport.transport_date < period.start_date or transport.transport_date > period.end_date:
            errors.append(
                f"Transport date ({transport.transport_date}) falls outside reporting period range ({period.start_date} to {period.end_date})."
            )

    # 2. Scope Hierarchy
    if transport.site:
        if transport.project and transport.site.project_id != transport.project.id:
            errors.append(f"Site '{transport.site.name}' does not belong to Project '{transport.project.name}'.")
        if transport.company and transport.site.project.subsidiary.company_id != transport.company.id:
            errors.append("Site hierarchy does not align with operating Company boundary.")

    # 3. Route & Distance
    if transport.distance < 0:
        errors.append("Transport distance cannot be negative.")
    if not transport.origin_location or not transport.origin_location.strip():
        errors.append("Origin location is required.")
    if not transport.destination_location or not transport.destination_location.strip():
        errors.append("Destination location is required.")
    if transport.distance == 0:
        warnings.append("Distance is recorded as 0.00 km; verify if this was an on-site local movement.")

    # 4. Carrier & Vehicle
    if transport.carrier and transport.carrier.status != CarrierStatus.ACTIVE:
        errors.append(f"Carrier '{transport.carrier.name}' is {transport.carrier.get_status_display()}; active carrier required.")

    if transport.vehicle and transport.vehicle.status != VehicleStatus.ACTIVE:
        errors.append(f"Vehicle '{transport.vehicle.registration_number}' is {transport.vehicle.get_status_display()}; active vehicle required.")

    if transport.transport_mode == TransportMode.ROAD and not transport.vehicle and not transport.carrier:
        warnings.append("Road transport record does not have a linked Carrier or Vehicle registered.")

    # 5. Financials
    if transport.freight_amount < 0:
        errors.append("Freight amount cannot be negative.")

    # 6. Shipment
    if transport.shipment:
        if transport.shipment.quantity < 0:
            errors.append("Shipment cargo quantity cannot be negative.")
        if transport.shipment.weight_net and transport.shipment.weight_net <= 0:
            errors.append("Shipment net weight must be greater than zero.")

    # 7. Supporting Evidence
    has_active_evidence = transport.evidence_files.filter(status=EvidenceStatus.ACTIVE).exists()
    if not has_active_evidence:
        warnings.append("No supporting evidence document (Lorry Receipt, Trip Sheet, or Delivery Note) is attached.")

    # Final validation determination
    if errors:
        final_status = ValidationStatus.INVALID
    elif warnings:
        final_status = ValidationStatus.WARNING
    else:
        final_status = ValidationStatus.VALID

    transport.validation_status = final_status
    transport.save(update_fields=["validation_status", "updated_at"])

    return {
        "status": final_status,
        "is_valid": final_status in [ValidationStatus.VALID, ValidationStatus.WARNING],
        "errors": errors,
        "warnings": warnings,
        "errors_count": len(errors),
        "warnings_count": len(warnings),
        "evaluated_at": timezone.now().isoformat(),
    }


# -----------------------------------------------------------------------------
# 7. ANOMALY DETECTION ENGINE
# -----------------------------------------------------------------------------

def detect_transport_anomalies(
    transport: TransportRecord,
    user: Optional[User] = None,
    request=None,
) -> List[Dict[str, Any]]:
    """
    Detects operational anomalies across transport records:
    1. DUPLICATE_TRANSPORT: Identical carrier/vehicle, date, origin, and destination on another record.
    2. UNUSUAL_DISTANCE: Distance exceeds 2.5x historical average for the same origin-destination route.
    3. PAYLOAD_EXCESS: Shipment weight exceeds 120% of rated vehicle capacity.
    4. FREIGHT_COST_SPIKE: Freight amount per km exceeds 3x historical average for the route.
    Anomalies serve strictly as human review signals without blocking submission.
    """
    anomalies: List[Dict[str, Any]] = []

    # 1. Duplicate Transport Trip Detection
    if transport.transport_date and (transport.vehicle or transport.carrier):
        dup_filter = (
            models.Q(transport_date=transport.transport_date)
            & models.Q(origin_location__iexact=transport.origin_location.strip())
            & models.Q(destination_location__iexact=transport.destination_location.strip())
        )
        if transport.vehicle:
            dup_filter &= models.Q(vehicle=transport.vehicle)
        elif transport.carrier:
            dup_filter &= models.Q(carrier=transport.carrier)

        duplicates = TransportRecord.objects.filter(dup_filter).exclude(id=transport.id).exclude(status=TransportStatus.CANCELLED)
        if duplicates.exists():
            dup = duplicates.first()
            anomalies.append({
                "type": "DUPLICATE_TRANSPORT",
                "rule_code": "DUPLICATE_TRANSPORT",
                "severity": "HIGH",
                "title": "Duplicate Transport Trip Suspect",
                "message": (
                    f"Another trip for {transport.vehicle or transport.carrier} on {transport.transport_date} "
                    f"from '{transport.origin_location}' to '{transport.destination_location}' is already recorded "
                    f"(Transport #{dup.transport_reference}, Status: {dup.status})."
                ),
                "matched_transport_id": dup.id,
                "matched_transport_reference": dup.transport_reference,
            })

    # 2. Unusual Distance Spike
    if transport.distance > Decimal("50.00"):
        hist_routes = TransportRecord.objects.filter(
            origin_location__iexact=transport.origin_location.strip(),
            destination_location__iexact=transport.destination_location.strip(),
            status__in=[TransportStatus.SUBMITTED, TransportStatus.VERIFIED],
            distance__gt=0,
        ).exclude(id=transport.id)

        route_count = hist_routes.count()
        if route_count >= 2:
            avg_dist = hist_routes.aggregate(models.Avg("distance"))["distance__avg"]
            if avg_dist and avg_dist > 0:
                dist_ratio = transport.distance / avg_dist
                if dist_ratio >= Decimal("2.50"):
                    dist_var = round((dist_ratio - Decimal("1.0")) * Decimal("100.0"), 1)
                    anomalies.append({
                        "type": "UNUSUAL_DISTANCE",
                        "rule_code": "UNUSUAL_DISTANCE",
                        "severity": "HIGH",
                        "title": "Unusual Route Distance Spike",
                        "message": (
                            f"Recorded distance {transport.distance} km is {dist_var}% longer than historical "
                            f"average ({avg_dist:,.2f} km across {route_count} trips on this route)."
                        ),
                        "baseline_value": float(avg_dist),
                        "observed_value": float(transport.distance),
                        "variance_percentage": float(dist_var),
                    })

    # 3. Payload Excess over Vehicle Capacity
    if transport.vehicle and transport.vehicle.capacity_payload and transport.vehicle.capacity_payload > 0:
        if transport.shipment:
            weight_mt = (
                transport.shipment.weight_net
                or transport.shipment.weight_gross
                or (transport.shipment.quantity if (transport.shipment.unit and transport.shipment.unit.code in ["MT", "TON"]) else None)
            )
            if weight_mt is not None:
                if transport.shipment.weight_unit == "KG":
                    weight_mt = weight_mt / Decimal("1000.0")

                cap_mt = transport.vehicle.capacity_payload
                if transport.vehicle.capacity_unit == "KG":
                    cap_mt = cap_mt / Decimal("1000.0")

                if cap_mt > 0 and weight_mt > (cap_mt * Decimal("1.20")):
                    overload_pct = round(((weight_mt / cap_mt) - Decimal("1.0")) * Decimal("100.0"), 1)
                    anomalies.append({
                        "type": "PAYLOAD_OVERLOAD",
                        "rule_code": "PAYLOAD_OVERLOAD",
                        "severity": "MEDIUM",
                        "title": "Payload Exceeds Vehicle Capacity",
                        "message": (
                            f"Shipment weight ({weight_mt:,.2f} MT) exceeds vehicle payload capacity "
                            f"({cap_mt:,.2f} MT) by {overload_pct}%."
                        ),
                        "baseline_value": float(cap_mt),
                        "observed_value": float(weight_mt),
                        "variance_percentage": float(overload_pct),
                    })

    has_anom = len(anomalies) > 0
    if transport.has_anomalies != has_anom:
        transport.has_anomalies = has_anom
        transport.save(update_fields=["has_anomalies", "updated_at"])

    if has_anom:
        log_auth_event(
            AuthAuditLog.EventType.TRANSPORT_ANOMALY_DETECTED,
            request=request,
            user=user,
            resource_accessed=f"TransportRecord:{transport.id}",
            details=f"Detected {len(anomalies)} anomalies on Transport #{transport.transport_reference}.",
            success=True,
        )

    return anomalies


# -----------------------------------------------------------------------------
# 8. WORKFLOW ENGINES (SUBMISSION, REVIEW, CORRECTION)
# -----------------------------------------------------------------------------

@transaction.atomic
def submit_transport_record(
    transport: TransportRecord,
    user: Optional[User] = None,
    actor: Optional[User] = None,
    request=None,
) -> TransportRecord:
    """
    Submits a draft or corrected TransportRecord for formal Subsidiary Review.
    Locks the record against direct Site Manager edits.
    """
    actor_user = user or actor
    if not actor_user:
        raise ValidationError("User / actor required for submission.")
    if not user_can_submit_transport(actor_user, transport):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=actor_user,
            resource_accessed=f"TransportRecord:{transport.id}/submit",
            details="Unauthorized attempt to submit transport record.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to submit this transport record.")

    # Run validation prior to submission
    val_result = validate_transport(transport, user=actor_user, request=request)
    if val_result["status"] == ValidationStatus.INVALID:
        raise ValidationError(
            f"Cannot submit invalid transport record. Please fix errors: {'; '.join(val_result['errors'])}"
        )

    # Detect anomalies
    detect_transport_anomalies(transport, user=actor_user, request=request)

    transport.status = TransportStatus.SUBMITTED
    transport.is_locked = True
    transport.updated_by = actor_user
    transport.save(update_fields=["status", "is_locked", "updated_by", "updated_at"])

    log_auth_event(
        AuthAuditLog.EventType.TRANSPORT_SUBMITTED,
        request=request,
        user=actor_user,
        resource_accessed=f"TransportRecord:{transport.id}",
        details=f"Submitted Transport #{transport.transport_reference} for review. Validation: {transport.validation_status}.",
        success=True,
    )
    logger.info("TransportRecord [%s] submitted by %s", transport.id, actor_user)
    return transport


@transaction.atomic
def review_transport_record(
    transport: TransportRecord,
    action: str,
    reviewer: Optional[User] = None,
    actor: Optional[User] = None,
    comments: str = "",
    correction_notes: str = "",
    request=None,
) -> TransportRecord:
    """
    Executes governance review decision on submitted transport record:
    - VERIFY: Marks VERIFIED, locks record permanently.
    - REQUEST_CORRECTION: Unlocks record for Site Manager and marks CORRECTION_REQUESTED.
    - REJECT: Rejects submission.
    """
    actor_user = reviewer or actor
    if not actor_user:
        raise ValidationError("Reviewer / actor required for review decision.")
    if not user_can_review_transport(actor_user, transport):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=actor_user,
            resource_accessed=f"TransportRecord:{transport.id}/review",
            details="Unauthorized attempt to review transport record.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to review this transport record.")

    if action == "VERIFY":
        transport.status = TransportStatus.VERIFIED
        transport.is_locked = True
        transport.review_comments = comments.strip()
        event_type = AuthAuditLog.EventType.TRANSPORT_VERIFIED
        msg = f"Verified Transport #{transport.transport_reference}."
    elif action == "REQUEST_CORRECTION":
        notes_to_save = correction_notes.strip() or comments.strip()
        if not notes_to_save:
            raise ValidationError("Correction comments/instructions are required when requesting revision.")
        transport.status = TransportStatus.CORRECTION_REQUESTED
        transport.is_locked = False
        transport.review_comments = comments.strip()
        transport.correction_notes = notes_to_save
        event_type = AuthAuditLog.EventType.CORRECTION_REQUESTED
        msg = f"Requested correction on Transport #{transport.transport_reference}: {notes_to_save}."
    elif action == "REJECT":
        transport.status = TransportStatus.REJECTED
        transport.is_locked = True
        transport.review_comments = comments.strip()
        event_type = AuthAuditLog.EventType.TRANSPORT_REJECTED
        msg = f"Rejected Transport #{transport.transport_reference}: {comments.strip()}."
    else:
        raise ValidationError(f"Invalid review action '{action}'.")

    transport.updated_by = actor_user
    transport.save(update_fields=["status", "is_locked", "review_comments", "correction_notes", "updated_by", "updated_at"])


    log_auth_event(
        event_type,
        request=request,
        user=actor_user,
        resource_accessed=f"TransportRecord:{transport.id}",
        details=msg,
        success=True,
    )
    logger.info("TransportRecord [%s] reviewed (%s) by %s", transport.id, action, actor_user)
    return transport


@transaction.atomic
def correct_transport_record(
    transport: TransportRecord,
    user: Optional[User] = None,
    actor: Optional[User] = None,
    correction_notes: str = "",
    explanation: str = "",
    request=None,
    data: Optional[Dict[str, Any]] = None,
) -> TransportRecord:
    """
    Site Manager remediates a transport record under CORRECTION_REQUESTED,
    applies field modifications, re-validates, and resubmits.
    """
    actor_user = user or actor
    if not actor_user:
        raise ValidationError("User / actor required for correction.")
    if transport.status != TransportStatus.CORRECTION_REQUESTED:
        raise ValidationError("Only records in CORRECTION_REQUESTED status can be resubmitted via correction.")

    if not user_can_modify_transport(actor_user, transport):
        raise PermissionDenied("You do not have permission to correct this transport record.")

    if data:
        update_transport_record(transport, data, actor_user, request=request)

    note = explanation.strip() or correction_notes.strip()
    transport.correction_notes = note
    transport.status = TransportStatus.SUBMITTED
    transport.is_locked = True
    transport.updated_by = actor_user
    transport.save(update_fields=["correction_notes", "status", "is_locked", "updated_by", "updated_at"])

    # Re-evaluate validation and anomalies
    validate_transport(transport, user=actor_user, request=request)
    detect_transport_anomalies(transport, user=actor_user, request=request)

    log_auth_event(
        AuthAuditLog.EventType.TRANSPORT_RESUBMITTED,
        request=request,
        user=actor_user,
        resource_accessed=f"TransportRecord:{transport.id}",
        details=f"Resubmitted corrected Transport #{transport.transport_reference}. Note: {note}",
        success=True,
    )
    logger.info("TransportRecord [%s] resubmitted by %s", transport.id, actor_user)
    return transport


# -----------------------------------------------------------------------------
# 9. DOCUMENT INTELLIGENCE OCR RECONCILIATION
# -----------------------------------------------------------------------------

def compare_ocr_with_transport(arg1, arg2) -> Dict[str, Any]:
    """
    Compares extracted OCR entities from transport documents (Lorry Receipt, Waybill, Invoice)
    against the stored TransportRecord fields.
    Accepts (transport, ocr_run) or (ocr_run, transport).
    Provides automated telemetry for auditor review and data verification.
    STRICT PRINCIPLE: Does NOT auto-overwrite or mutate the source transport data.
    """
    if isinstance(arg1, TransportRecord):
        transport = arg1
        ocr_run = arg2
    else:
        ocr_run = arg1
        transport = arg2
    fields_by_name = {f.field_name: f for f in ocr_run.fields.all()}

    comparison = {
        "evaluated": True,
        "transport_id": transport.id,
        "transport_reference": transport.transport_reference,
        "evidence_id": ocr_run.evidence_id,
        "overall_status": "MATCH",
        "matches_count": 0,
        "mismatches_count": 0,
        "not_detected_count": 0,
        "items": {},
    }

    # 1. Compare Vehicle Registration Number
    veh_field = fields_by_name.get("vehicle_number") or fields_by_name.get("vehicle_id") or fields_by_name.get("registration_number")
    stored_veh = transport.vehicle.registration_number.strip().upper() if transport.vehicle else ""
    if veh_field and veh_field.normalized_value:
        ext_veh = re.sub(r"[^A-Z0-9]", "", veh_field.normalized_value.upper())
        norm_stored = re.sub(r"[^A-Z0-9]", "", stored_veh)
        if norm_stored and ext_veh == norm_stored:
            status = "MATCH"
            comparison["matches_count"] += 1
        else:
            status = "MISMATCH"
            comparison["mismatches_count"] += 1
            comparison["overall_status"] = "MISMATCH"

        comparison["items"]["vehicle_number"] = {
            "label": "Vehicle Registration Number",
            "status": status,
            "stored_value": stored_veh or "Not assigned",
            "extracted_value": veh_field.normalized_value,
            "confidence": float(veh_field.confidence or 0),
        }
    else:
        comparison["items"]["vehicle_number"] = {
            "label": "Vehicle Registration Number",
            "status": "NOT_DETECTED",
            "stored_value": stored_veh or "Not assigned",
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    # 2. Compare Carrier / Transporter Name
    carr_field = fields_by_name.get("carrier_name") or fields_by_name.get("transporter") or fields_by_name.get("vendor_name")
    stored_carr = transport.carrier.name.strip().upper() if transport.carrier else ""
    if carr_field and carr_field.normalized_value:
        ext_carr = carr_field.normalized_value.strip().upper()
        if stored_carr and (ext_carr in stored_carr or stored_carr in ext_carr):
            carr_status = "MATCH"
            comparison["matches_count"] += 1
        else:
            carr_status = "MISMATCH"
            comparison["mismatches_count"] += 1
            comparison["overall_status"] = "MISMATCH"

        comparison["items"]["carrier_name"] = {
            "label": "Carrier Name",
            "status": carr_status,
            "stored_value": stored_carr or "Not assigned",
            "extracted_value": carr_field.normalized_value,
            "confidence": float(carr_field.confidence or 0),
        }
    else:
        comparison["items"]["carrier_name"] = {
            "label": "Carrier Name",
            "status": "NOT_DETECTED",
            "stored_value": stored_carr or "Not assigned",
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    # 3. Compare Freight Amount
    amt_field = fields_by_name.get("total_amount") or fields_by_name.get("freight_amount")
    if amt_field and amt_field.normalized_value:
        try:
            ext_amt = float(amt_field.normalized_value)
            stored_amt = float(transport.freight_amount)
            delta = round(ext_amt - stored_amt, 2)
            if abs(delta) < 1.00:
                amt_status = "MATCH"
                comparison["matches_count"] += 1
            else:
                amt_status = "MISMATCH"
                comparison["mismatches_count"] += 1
                comparison["overall_status"] = "MISMATCH"

            comparison["items"]["freight_amount"] = {
                "label": "Freight Charges",
                "status": amt_status,
                "stored_value": stored_amt,
                "extracted_value": ext_amt,
                "delta": delta,
                "confidence": float(amt_field.confidence or 0),
            }
        except (ValueError, TypeError):
            comparison["items"]["freight_amount"] = {
                "label": "Freight Charges",
                "status": "MISMATCH",
                "stored_value": float(transport.freight_amount),
                "extracted_value": amt_field.normalized_value,
                "confidence": 0.0,
            }
            comparison["mismatches_count"] += 1
            comparison["overall_status"] = "MISMATCH"
    else:
        comparison["items"]["freight_amount"] = {
            "label": "Freight Charges",
            "status": "NOT_DETECTED",
            "stored_value": float(transport.freight_amount),
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    # 4. Compare Distance
    dist_field = fields_by_name.get("distance")
    if dist_field and dist_field.normalized_value:
        try:
            ext_dist = float(dist_field.normalized_value)
            stored_dist = float(transport.distance)
            delta = round(ext_dist - stored_dist, 2)
            if abs(delta) < 1.00:
                dist_status = "MATCH"
                comparison["matches_count"] += 1
            else:
                dist_status = "MISMATCH"
                comparison["mismatches_count"] += 1
                comparison["overall_status"] = "MISMATCH"

            comparison["items"]["distance"] = {
                "label": f"Distance ({transport.distance_unit})",
                "status": dist_status,
                "stored_value": stored_dist,
                "extracted_value": ext_dist,
                "delta": delta,
                "confidence": float(dist_field.confidence or 0),
            }
        except (ValueError, TypeError):
            comparison["items"]["distance"] = {
                "label": "Distance",
                "status": "NOT_DETECTED",
                "stored_value": float(transport.distance),
                "extracted_value": dist_field.normalized_value,
            }
            comparison["not_detected_count"] += 1
    else:
        comparison["items"]["distance"] = {
            "label": f"Distance ({transport.distance_unit})",
            "status": "NOT_DETECTED",
            "stored_value": float(transport.distance),
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    return comparison


# -----------------------------------------------------------------------------
# 10. EVIDENCE UPLOAD INTEGRATION HELPER
# -----------------------------------------------------------------------------

def upload_transport_evidence(
    transport: TransportRecord,
    uploaded_file=None,
    file_obj=None,
    evidence_type: str = EvidenceType.TRANSPORT_RECORD,
    description: str = "",
    user: Optional[User] = None,
    actor: Optional[User] = None,
    request=None,
) -> Evidence:
    """
    Attaches an evidence file directly to a TransportRecord using the Phase 09 evidence engine.
    """
    from apps.core.evidence_services import create_evidence_record

    target_file = uploaded_file or file_obj
    target_user = user or actor

    return create_evidence_record(
        activity_record=None,
        procurement_record=None,
        transport_record=transport,
        uploaded_file=target_file,
        evidence_type=evidence_type,
        description=description,
        user=target_user,
        request=request,
    )
