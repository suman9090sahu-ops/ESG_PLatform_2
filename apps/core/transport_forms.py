"""
Forms for Transport & Logistics Management (Phase 17) in MEIL ESG CONTROL TOWER.

Fulfills Phase 17 Requirements:
- Scoped candidate choices (Sites, Projects, Carriers, Vehicles, Periods) strictly aligned with RBAC
- Zero-trust server-side validation against tampering and IDOR attacks
- Integrated Shipment cargo fields directly alongside transport movement parameters
- Rich filter toolbars for transports, carriers, and vehicles
- Governance forms for Subsidiary Manager review decisions, Site Manager corrections, and evidence uploads
"""

from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import (
    ActivityRecord,
    Carrier,
    CarrierStatus,
    CarrierType,
    Company,
    DistanceSource,
    DistanceUnit,
    EvidenceType,
    FuelType,
    PeriodStatus,
    ProcurementRecord,
    Project,
    ReportingPeriod,
    Shipment,
    Site,
    Supplier,
    TransportLocationType,
    TransportMode,
    TransportRecord,
    TransportScopeCategory,
    TransportStatus,
    UnitOfMeasure,
    ValidationStatus,
    Vehicle,
    VehicleOwnershipType,
    VehicleStatus,
    VehicleType,
)
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
)
from apps.core.transport_services import (
    get_accessible_carriers,
    get_accessible_vehicles,
)


# -----------------------------------------------------------------------------
# 1. CARRIER MASTER FORMS
# -----------------------------------------------------------------------------

class CarrierForm(forms.ModelForm):
    """Form for registering and updating transport providers and logistics carriers."""

    class Meta:
        model = Carrier
        fields = [
            "carrier_code",
            "name",
            "legal_name",
            "carrier_type",
            "status",
            "supplier",
            "company",
            "contact_person",
            "contact_email",
            "contact_phone",
            "notes",
        ]
        widgets = {
            "carrier_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. CARR-001"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Carrier trade name"}),
            "legal_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Registered corporate name"}),
            "carrier_type": forms.Select(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "supplier": forms.Select(attrs={"class": "form-control"}),
            "company": forms.Select(attrs={"class": "form-control"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control", "placeholder": "Dispatch Manager"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "dispatch@carrier.com"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+91 98765 00000"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Fleet capabilities, contract references..."}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user:
            self.fields["company"].queryset = get_accessible_companies(self.user)
            self.fields["company"].required = False
            self.fields["company"].empty_label = "-- Enterprise-Wide (All Companies) --"

            from apps.core.procurement_services import get_accessible_suppliers
            self.fields["supplier"].queryset = get_accessible_suppliers(self.user)
            self.fields["supplier"].required = False
            self.fields["supplier"].empty_label = "-- Not Linked to Procurement Supplier --"

    def clean_carrier_code(self):
        code = self.cleaned_data.get("carrier_code", "").strip().upper()
        if not code:
            raise ValidationError("Carrier code cannot be blank.")
        qs = Carrier.objects.filter(carrier_code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"A carrier with code '{code}' already exists.")
        return code


class CarrierFilterForm(forms.Form):
    """Filter toolbar for Carrier Directory."""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Search name or code..."}),
    )
    carrier_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Types")] + CarrierType.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses")] + CarrierStatus.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )


# -----------------------------------------------------------------------------
# 2. VEHICLE MASTER FORMS
# -----------------------------------------------------------------------------

class VehicleForm(forms.ModelForm):
    """Form for registering and updating vehicle fleet master records."""

    class Meta:
        model = Vehicle
        fields = [
            "vehicle_identifier",
            "registration_number",
            "carrier",
            "company",
            "ownership_type",
            "vehicle_type",
            "fuel_type",
            "capacity_payload",
            "capacity_unit",
            "status",
            "notes",
        ]
        widgets = {
            "vehicle_identifier": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. VEH-001"}),
            "registration_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. AP-04-TX-1234"}),
            "carrier": forms.Select(attrs={"class": "form-control"}),
            "company": forms.Select(attrs={"class": "form-control"}),
            "ownership_type": forms.Select(attrs={"class": "form-control"}),
            "vehicle_type": forms.Select(attrs={"class": "form-control"}),
            "fuel_type": forms.Select(attrs={"class": "form-control"}),
            "capacity_payload": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "e.g. 25.00"}),
            "capacity_unit": forms.Select(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Engine specs, emission standard..."}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user:
            self.fields["carrier"].queryset = get_accessible_carriers(self.user)
            self.fields["carrier"].required = False
            self.fields["carrier"].empty_label = "-- Company Fleet (No 3rd Party Carrier) --"

            self.fields["company"].queryset = get_accessible_companies(self.user)
            self.fields["company"].required = False
            self.fields["company"].empty_label = "-- Enterprise-Wide / Inherit Carrier Company --"

    def clean_registration_number(self):
        reg = self.cleaned_data.get("registration_number", "").strip().upper()
        if not reg:
            raise ValidationError("Registration number cannot be blank.")
        qs = Vehicle.objects.filter(registration_number=reg)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"A vehicle with registration '{reg}' already exists.")
        return reg


class VehicleFilterForm(forms.Form):
    """Filter toolbar for Fleet Vehicle Catalog."""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Search registration..."}),
    )
    ownership_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Ownerships")] + VehicleOwnershipType.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )
    vehicle_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Vehicle Types")] + VehicleType.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )
    fuel_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Fuel Types")] + FuelType.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses")] + VehicleStatus.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )


# -----------------------------------------------------------------------------
# 3. SHIPMENT & CARGO FORM
# -----------------------------------------------------------------------------

class ShipmentForm(forms.ModelForm):
    """Embedded or standalone form for shipment consignment details."""

    class Meta:
        model = Shipment
        fields = [
            "material_description",
            "quantity",
            "unit",
            "unit_custom",
            "weight_gross",
            "weight_net",
            "weight_unit",
            "delivery_reference",
            "consignment_value",
            "currency",
            "notes",
        ]
        widgets = {
            "material_description": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. TMT Steel Bars 16mm"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "placeholder": "0.0000"}),
            "unit": forms.Select(attrs={"class": "form-control"}),
            "unit_custom": forms.TextInput(attrs={"class": "form-control", "placeholder": "Custom unit"}),
            "weight_gross": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "placeholder": "Gross weight"}),
            "weight_net": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "placeholder": "Net weight (MT)"}),
            "weight_unit": forms.Select(attrs={"class": "form-control"}),
            "delivery_reference": forms.TextInput(attrs={"class": "form-control", "placeholder": "Lorry Receipt / Challan Ref"}),
            "consignment_value": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
            "currency": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.TextInput(attrs={"class": "form-control", "placeholder": "Cargo notes"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unit"].empty_label = "-- Standard Unit --"
        self.fields["material_description"].required = False


# -----------------------------------------------------------------------------
# 4. TRANSPORT RECORD FORM
# -----------------------------------------------------------------------------

class TransportRecordForm(forms.ModelForm):
    """Comprehensive form for recording and editing physical transportation events."""

    # Optional embedded shipment fields
    shipment_material = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Cement, Structural Steel, Excavator Spares"}),
        label="Consignment Material",
    )
    shipment_quantity = forms.DecimalField(
        max_digits=14,
        decimal_places=4,
        required=False,
        initial=Decimal("0.0000"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
        label="Quantity",
    )
    shipment_unit = forms.ModelChoiceField(
        queryset=UnitOfMeasure.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Unit",
    )
    shipment_weight_net = forms.DecimalField(
        max_digits=14,
        decimal_places=4,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "Weight in MT"}),
        label="Net Payload Weight (MT)",
    )
    shipment_delivery_ref = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Lorry Receipt (LR) / Challan #"}),
        label="Consignment / Delivery Reference",
    )

    class Meta:
        model = TransportRecord
        fields = [
            "transport_reference",
            "reporting_period",
            "company",
            "project",
            "site",
            "transport_date",
            "transport_mode",
            "carrier",
            "vehicle",
            "procurement",
            "origin_type",
            "origin_location",
            "origin_site",
            "destination_type",
            "destination_location",
            "destination_site",
            "distance",
            "distance_unit",
            "distance_source",
            "freight_amount",
            "currency",
            "fuel_quantity",
            "fuel_unit",
            "activity_record",
            "scope_category",
        ]
        widgets = {
            "transport_reference": forms.TextInput(attrs={"class": "form-control", "placeholder": "Auto-generated if empty"}),
            "reporting_period": forms.Select(attrs={"class": "form-control"}),
            "company": forms.Select(attrs={"class": "form-control"}),
            "project": forms.Select(attrs={"class": "form-control"}),
            "site": forms.Select(attrs={"class": "form-control"}),
            "transport_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "transport_mode": forms.Select(attrs={"class": "form-control"}),
            "carrier": forms.Select(attrs={"class": "form-control"}),
            "vehicle": forms.Select(attrs={"class": "form-control"}),
            "procurement": forms.Select(attrs={"class": "form-control"}),
            "origin_type": forms.Select(attrs={"class": "form-control"}),
            "origin_location": forms.TextInput(attrs={"class": "form-control", "placeholder": "Origin facility / City"}),
            "origin_site": forms.Select(attrs={"class": "form-control"}),
            "destination_type": forms.Select(attrs={"class": "form-control"}),
            "destination_location": forms.TextInput(attrs={"class": "form-control", "placeholder": "Destination site / Depot"}),
            "destination_site": forms.Select(attrs={"class": "form-control"}),
            "distance": forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "placeholder": "0.0"}),
            "distance_unit": forms.Select(attrs={"class": "form-control"}),
            "distance_source": forms.Select(attrs={"class": "form-control"}),
            "freight_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
            "currency": forms.Select(attrs={"class": "form-control"}),
            "fuel_quantity": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "Trip fuel if metered"}),
            "fuel_unit": forms.TextInput(attrs={"class": "form-control", "placeholder": "L"}),
            "activity_record": forms.Select(attrs={"class": "form-control"}),
            "scope_category": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["transport_reference"].required = False
        self.fields["company"].required = False
        self.fields["scope_category"].required = False

        if self.user:
            self.fields["company"].queryset = get_accessible_companies(self.user)
            self.fields["project"].queryset = get_accessible_projects(self.user)
            self.fields["site"].queryset = get_accessible_sites(self.user)
            self.fields["origin_site"].queryset = get_accessible_sites(self.user)
            self.fields["destination_site"].queryset = get_accessible_sites(self.user)
            self.fields["carrier"].queryset = get_accessible_carriers(self.user)
            self.fields["vehicle"].queryset = get_accessible_vehicles(self.user)

            from apps.core.procurement_services import get_accessible_procurements
            self.fields["procurement"].queryset = get_accessible_procurements(self.user)

            from apps.core.data_entry_services import get_accessible_activity_records
            self.fields["activity_record"].queryset = get_accessible_activity_records(self.user)

            if not self.instance.pk:
                self.fields["reporting_period"].queryset = ReportingPeriod.objects.filter(status=PeriodStatus.OPEN)
            else:
                self.fields["reporting_period"].queryset = ReportingPeriod.objects.all()

        # Nullable helper labels
        self.fields["project"].empty_label = "-- Select Project (Optional) --"
        self.fields["site"].empty_label = "-- Select Site Boundary (Optional) --"
        self.fields["origin_site"].empty_label = "-- Select Site if internal --"
        self.fields["destination_site"].empty_label = "-- Select Site if internal --"
        self.fields["carrier"].empty_label = "-- Select Carrier / Transport Partner --"
        self.fields["vehicle"].empty_label = "-- Select Specific Vehicle Asset --"
        self.fields["procurement"].empty_label = "-- Not Linked to Procurement --"
        self.fields["activity_record"].empty_label = "-- Not Linked to Activity Record --"

        # Initialize embedded shipment data if instance exists
        if self.instance and self.instance.pk and self.instance.shipment:
            shp = self.instance.shipment
            self.fields["shipment_material"].initial = shp.material_description
            self.fields["shipment_quantity"].initial = shp.quantity
            self.fields["shipment_unit"].initial = shp.unit
            self.fields["shipment_weight_net"].initial = shp.weight_net
            self.fields["shipment_delivery_ref"].initial = shp.delivery_reference

    def clean(self):
        cleaned_data = super().clean()
        dist = cleaned_data.get("distance")
        if dist is not None and dist < Decimal("0"):
            self.add_error("distance", "Distance cannot be negative.")

        amt = cleaned_data.get("freight_amount")
        if amt is not None and amt < Decimal("0"):
            self.add_error("freight_amount", "Freight amount cannot be negative.")

        fuel = cleaned_data.get("fuel_quantity")
        if fuel is not None and fuel < Decimal("0"):
            self.add_error("fuel_quantity", "Fuel quantity cannot be negative.")

        # Ensure site-project alignment
        site = cleaned_data.get("site")
        project = cleaned_data.get("project")
        company = cleaned_data.get("company")
        if site and project and site.project_id != project.id:
            self.add_error("site", f"Site '{site.name}' does not belong to Project '{project.name}'.")

        # Auto-resolve company from site or project if not provided
        if not company:
            if site and site.project and site.project.subsidiary:
                cleaned_data["company"] = site.project.subsidiary.company
            elif project and project.subsidiary:
                cleaned_data["company"] = project.subsidiary.company

        if not cleaned_data.get("company"):
            self.add_error("company", "Operating Company is required.")

        # Auto-infer Scope 1 vs Scope 3 category if not specified
        if not cleaned_data.get("scope_category"):
            vehicle = cleaned_data.get("vehicle")
            if vehicle and getattr(vehicle, "is_owned", False):
                cleaned_data["scope_category"] = TransportScopeCategory.SCOPE_1
            else:
                cleaned_data["scope_category"] = TransportScopeCategory.SCOPE_3_CAT_04

        return cleaned_data


class TransportFilterForm(forms.Form):
    """Filter toolbar for Transport Ledger."""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Search reference, route, carrier..."}),
    )
    transport_mode = forms.ChoiceField(
        required=False,
        choices=[("", "All Modes")] + TransportMode.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses")] + TransportStatus.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )
    scope_category = forms.ChoiceField(
        required=False,
        choices=[("", "All Scope Categories")] + TransportScopeCategory.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )
    validation_status = forms.ChoiceField(
        required=False,
        choices=[("", "All Validations")] + ValidationStatus.choices,
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )
    has_anomalies = forms.ChoiceField(
        required=False,
        choices=[("", "All Records"), ("yes", "Anomalous Only"), ("no", "Clean Records Only")],
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
    )


# -----------------------------------------------------------------------------
# 5. GOVERNANCE, REVIEW & CORRECTION FORMS
# -----------------------------------------------------------------------------

class TransportReviewForm(forms.Form):
    """Subsidiary Manager review action decision form."""
    action = forms.ChoiceField(
        choices=[
            ("VERIFY", "Verify / Approve Transport"),
            ("REQUEST_CORRECTION", "Request Correction / Return to Site Manager"),
            ("REJECT", "Reject Transport"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Governance Decision",
    )
    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Provide review observations, audit notes, or mandatory correction instructions..."}),
        label="Review Remarks & Instructions",
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        comments = cleaned_data.get("comments", "").strip()

        if action == "REQUEST_CORRECTION" and not comments:
            self.add_error("comments", "Mandatory correction instructions are required when returning a record for revision.")

        return cleaned_data


class TransportCorrectionForm(forms.Form):
    """Site Manager explanation form upon submitting corrected transport record."""
    correction_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 4,
            "placeholder": "Explain the modifications made (e.g., corrected route distance, attached missing Lorry Receipt, updated vehicle plate)..."
        }),
        label="Remediation Commentary & Justification",
    )


class TransportEvidenceUploadForm(forms.Form):
    """Evidence upload form specifically for transport and logistics documentation."""
    file = forms.FileField(
        widget=forms.FileInput(attrs={"class": "form-control"}),
        label="Evidence File (PDF, PNG, JPG, XLS, CSV)",
    )
    evidence_type = forms.ChoiceField(
        choices=[
            (EvidenceType.TRANSPORT_RECORD, "Transport / Logistics Record"),
            (EvidenceType.LORRY_RECEIPT, "Lorry Receipt / Consignment Note / Bilty"),
            (EvidenceType.WEIGHBRIDGE_SLIP, "Weighbridge / Weight Slip"),
            (EvidenceType.TRIP_SHEET, "Vehicle Trip Sheet / Log Book"),
            (EvidenceType.INVOICE, "Freight Invoice / Carrier Statement"),
            (EvidenceType.FUEL_CHALLAN, "Fuel Dispensation / Tanker Challan"),
            (EvidenceType.OTHER, "Other Supporting Document"),
        ],
        initial=EvidenceType.TRANSPORT_RECORD,
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Document Classification",
    )
    description = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. LR-40912 Dam Material Dispatch"}),
        label="Document Description / Identifier",
    )
