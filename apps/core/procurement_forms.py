"""
Forms for Supplier & Procurement Management (Phase 16) in MEIL ESG CONTROL TOWER.

Fulfills Phase 16 Requirements:
- Scoped candidate choices (Sites, Suppliers, Periods) strictly aligned with RBAC
- Zero-trust anti-tampering server-side validation
- Rich filtering toolbars with status, category, anomaly, and validation controls
- Structured review & correction explanation forms
"""

from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import (
    ActivityMaster,
    Company,
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
    ValidationStatus,
)
from apps.core.procurement_services import (
    get_accessible_suppliers,
    user_can_modify_supplier,
)
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
)


# -----------------------------------------------------------------------------
# 1. SUPPLIER MASTER FORMS
# -----------------------------------------------------------------------------

class SupplierForm(forms.ModelForm):
    """Form for creating and editing Supplier master records."""

    class Meta:
        model = Supplier
        fields = [
            "supplier_code",
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
        ]
        widgets = {
            "supplier_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. SUP-MEIL-001"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Tata Steel Ltd"}),
            "legal_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Tata Steel Limited"}),
            "supplier_type": forms.Select(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "company": forms.Select(attrs={"class": "form-control"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control", "placeholder": "Primary Contact"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "vendor@example.com"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+91 98765 43210"}),
            "tax_identifier": forms.TextInput(attrs={"class": "form-control", "placeholder": "GSTIN / PAN / Tax ID"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "country": forms.TextInput(attrs={"class": "form-control"}),
            "postal_code": forms.TextInput(attrs={"class": "form-control"}),
            "environmental_certifications": forms.TextInput(attrs={"class": "form-control", "placeholder": "ISO 14001, ISO 50001, GreenPro"}),
            "has_esg_declaration": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "esg_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Renewable energy usage, emission disclosures..."}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if "country" in self.fields:
            self.fields["country"].required = False
            self.fields["country"].initial = "India"

        if self.user:
            self.fields["company"].queryset = get_accessible_companies(self.user)
            self.fields["company"].required = False
            self.fields["company"].empty_label = "-- Enterprise-Wide (All Subsidiaries) --"

    def clean_supplier_code(self):
        code = self.cleaned_data.get("supplier_code", "").strip().upper()
        if not code:
            raise ValidationError("Supplier code cannot be blank.")
        qs = Supplier.objects.filter(supplier_code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"A supplier with code '{code}' already exists.")
        return code


class SupplierFilterForm(forms.Form):
    """Filter toolbar for Supplier catalog."""

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Search name, code, tax ID..."}),
    )
    supplier_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Supplier Types")] + list(SupplierType.choices),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses")] + list(SupplierStatus.choices),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    company = forms.ModelChoiceField(
        required=False,
        queryset=Company.objects.none(),
        empty_label="All Companies",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields["company"].queryset = get_accessible_companies(user)


# -----------------------------------------------------------------------------
# 2. PROCUREMENT TRANSACTION FORMS
# -----------------------------------------------------------------------------

class ProcurementRecordForm(forms.ModelForm):
    """Form for creating and editing Procurement transactions."""

    class Meta:
        model = ProcurementRecord
        fields = [
            "supplier",
            "site",
            "project",
            "reporting_period",
            "purchase_date",
            "category",
            "purchase_order_reference",
            "invoice_reference",
            "invoice_date",
            "total_amount",
            "currency",
            "description",
        ]
        widgets = {
            "supplier": forms.Select(attrs={"class": "form-control select2"}),
            "site": forms.Select(attrs={"class": "form-control"}),
            "project": forms.Select(attrs={"class": "form-control"}),
            "reporting_period": forms.Select(attrs={"class": "form-control"}),
            "purchase_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "category": forms.Select(attrs={"class": "form-control"}),
            "purchase_order_reference": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. PO-2026-0891"}),
            "invoice_reference": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. INV-TATA-4412"}),
            "invoice_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "total_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "currency": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Transaction scope, commercial notes..."}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user:
            self.fields["supplier"].queryset = get_accessible_suppliers(self.user).filter(status=SupplierStatus.ACTIVE)
            self.fields["site"].queryset = get_accessible_sites(self.user)
            self.fields["project"].queryset = get_accessible_projects(self.user)
            self.fields["project"].required = False

            # Reporting periods open for modification
            self.fields["reporting_period"].queryset = ReportingPeriod.objects.filter(
                status=PeriodStatus.OPEN
            ).order_by("-start_date")

            # Auto-select site if user is Site Manager with exactly 1 site
            if self.user.has_role(Role.Code.SITE_MANAGER):
                sites_qs = self.fields["site"].queryset
                if sites_qs.count() == 1 and not self.instance.pk:
                    self.fields["site"].initial = sites_qs.first()

    def clean(self):
        cleaned_data = super().clean()
        purchase_date = cleaned_data.get("purchase_date")
        reporting_period = cleaned_data.get("reporting_period")
        site = cleaned_data.get("site")
        project = cleaned_data.get("project")

        if site and project and site.project_id != project.id:
            raise ValidationError({"project": f"Site '{site.name}' does not belong to Project '{project.name}'."})

        if site and not project:
            cleaned_data["project"] = site.project

        if purchase_date and reporting_period:
            if purchase_date < reporting_period.start_date or purchase_date > reporting_period.end_date:
                raise ValidationError({
                    "purchase_date": (
                        f"Purchase date ({purchase_date}) must fall within the selected reporting period "
                        f"({reporting_period.start_date} to {reporting_period.end_date})."
                    )
                })

        total_amount = cleaned_data.get("total_amount")
        if total_amount is not None and total_amount < Decimal("0.00"):
            raise ValidationError({"total_amount": "Total procurement amount cannot be negative."})

        return cleaned_data


class ProcurementItemForm(forms.ModelForm):
    """Form for adding or editing a line item within a procurement transaction."""

    sync_total = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Sync with Procurement Total (Recalculate parent transaction amount from items)",
    )

    class Meta:
        model = ProcurementItem
        fields = [
            "item_name",
            "category",
            "quantity",
            "unit",
            "unit_custom",
            "unit_price",
            "total_amount",
            "activity_master",
            "scope3_category",
            "notes",
        ]
        widgets = {
            "item_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. TMT Steel Bars 16mm / Diesel HSD"}),
            "category": forms.Select(attrs={"class": "form-control"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "min": "0.0001"}),
            "unit": forms.Select(attrs={"class": "form-control"}),
            "unit_custom": forms.TextInput(attrs={"class": "form-control", "placeholder": "Custom unit if not in master"}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "total_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "activity_master": forms.Select(attrs={"class": "form-control"}),
            "scope3_category": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.TextInput(attrs={"class": "form-control", "placeholder": "Item specifications / grade"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["total_amount"].required = False
        self.fields["unit"].queryset = UnitOfMeasure.objects.filter(is_active=True).order_by("name")
        self.fields["unit"].required = False
        self.fields["activity_master"].queryset = ActivityMaster.objects.filter(status="ACTIVE").order_by("name")
        self.fields["activity_master"].required = False
        self.fields["scope3_category"].required = False

    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get("quantity")
        if quantity is not None and quantity <= Decimal("0"):
            raise ValidationError({"quantity": "Item quantity must be strictly greater than zero."})

        total_amount = cleaned_data.get("total_amount")
        unit_price = cleaned_data.get("unit_price")

        # Auto-compute total_amount from qty and unit_price if zero
        if (total_amount is None or total_amount == Decimal("0.00")) and quantity and unit_price:
            cleaned_data["total_amount"] = round(quantity * unit_price, 2)

        return cleaned_data


class ProcurementFilterForm(forms.Form):
    """Filter toolbar for Procurement Ledger."""

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Search reference, invoice, PO..."}),
    )
    supplier = forms.ModelChoiceField(
        required=False,
        queryset=Supplier.objects.none(),
        empty_label="All Suppliers",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    site = forms.ModelChoiceField(
        required=False,
        queryset=Site.objects.none(),
        empty_label="All Sites",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    category = forms.ChoiceField(
        required=False,
        choices=[("", "All Categories")] + list(ProcurementCategory.choices),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses")] + list(ProcurementStatus.choices),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    reporting_period = forms.ModelChoiceField(
        required=False,
        queryset=ReportingPeriod.objects.all().order_by("-start_date"),
        empty_label="All Periods",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    validation_status = forms.ChoiceField(
        required=False,
        choices=[("", "All Validation Statuses")] + list(ValidationStatus.choices),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    has_anomalies = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All Telemetry"),
            ("yes", "Anomalies Flagged"),
            ("no", "Clean Telemetry"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields["supplier"].queryset = get_accessible_suppliers(user)
            self.fields["site"].queryset = get_accessible_sites(user)


class ProcurementReviewForm(forms.Form):
    """Form for Subsidiary Manager review actions on a submitted procurement record."""

    action = forms.ChoiceField(
        choices=[
            ("VERIFY", "Verify / Approve Procurement"),
            ("REQUEST_CORRECTION", "Request Correction / Clarification"),
            ("REJECT", "Reject Procurement"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Verification notes or review commentary..."}),
    )
    correction_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Specific issues requiring correction by Site Manager..."}),
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        comments = (cleaned_data.get("comments") or "").strip()
        correction_notes = (cleaned_data.get("correction_notes") or "").strip()

        if action == "REJECT" and not comments:
            raise ValidationError({"comments": "A justification is mandatory when rejecting a procurement record."})

        if action == "REQUEST_CORRECTION" and not (correction_notes or comments):
            raise ValidationError({"correction_notes": "Specific correction instructions are required."})

        return cleaned_data


class ProcurementCorrectionForm(forms.ModelForm):
    """Form for Site Manager correcting a procurement record that was flagged for correction."""

    explanation = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Explain the changes made in response to the correction request...",
        }),
        help_text="Mandatory audit justification explaining the remediation.",
    )

    class Meta:
        model = ProcurementRecord
        fields = [
            "purchase_date",
            "category",
            "purchase_order_reference",
            "invoice_reference",
            "invoice_date",
            "total_amount",
            "currency",
            "description",
        ]
        widgets = {
            "purchase_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "category": forms.Select(attrs={"class": "form-control"}),
            "purchase_order_reference": forms.TextInput(attrs={"class": "form-control"}),
            "invoice_reference": forms.TextInput(attrs={"class": "form-control"}),
            "invoice_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "total_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "currency": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
