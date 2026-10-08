"""
Forms for Activity Master and ESG Data Catalog for MEIL ESG CONTROL TOWER.

Fulfills Phase 06 Requirements:
- ActivityMasterForm: Controlled creation and editing of ESG master activities
- ActivityCategoryForm: Management of ESG activity categories
- UnitOfMeasureForm: Standard measurement unit definitions
"""

from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    CollectionFrequency,
    MasterStatus,
    Scope3CalculationMethod,
    Scope3Category,
    ScopeClassification,
    UnitDimension,
    UnitOfMeasure,
)


class ActivityMasterForm(forms.ModelForm):
    """
    Form for creating and editing ActivityMaster catalog definitions.
    """

    class Meta:
        model = ActivityMaster
        fields = [
            "code",
            "name",
            "category",
            "activity_type",
            "base_unit",
            "allowed_units",
            "scope_classification",
            "scope3_category",
            "calculation_method",
            "collection_frequency",
            "evidence_requirement_hint",
            "description",
            "applicability_notes",
            "status",
        ]
        widgets = {
            "code": forms.TextInput(
                attrs={
                    "class": "form-control text-uppercase",
                    "placeholder": "e.g. FUEL-DIESEL-STAT",
                    "autocomplete": "off",
                }
            ),
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Diesel Consumption (Stationary Generators & Heavy Equipment)",
                }
            ),
            "category": forms.Select(attrs={"class": "form-select"}),
            "activity_type": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Stationary Combustion, Mobile Combustion, Purchased Electricity",
                }
            ),
            "base_unit": forms.Select(attrs={"class": "form-select"}),
            "allowed_units": forms.SelectMultiple(
                attrs={
                    "class": "form-select",
                    "size": "5",
                    "help_text": "Hold Ctrl/Cmd to select multiple valid reporting units.",
                }
            ),
            "scope_classification": forms.Select(attrs={"class": "form-select"}),
            "scope3_category": forms.Select(attrs={"class": "form-select"}),
            "calculation_method": forms.Select(attrs={"class": "form-select"}),
            "collection_frequency": forms.Select(attrs={"class": "form-select"}),
            "evidence_requirement_hint": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Fuel Log Book / Tax Invoice / HT Meter Reading Record",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Operational definition, boundary rules, and guidance for site managers.",
                }
            ),
            "applicability_notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Applicable site types (e.g. Construction sites, solar inverter yards, batching plants).",
                }
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter choices to active categories and units if creating
        self.fields["scope3_category"].queryset = Scope3Category.objects.filter(is_active=True).order_by("category_number")
        self.fields["scope3_category"].empty_label = "— Select Scope 3 Category (Optional) —"
        self.fields["scope3_category"].required = False
        self.fields["calculation_method"].required = False

        if not self.instance.pk:
            self.fields["category"].queryset = ActivityCategory.objects.filter(status=MasterStatus.ACTIVE)
            self.fields["base_unit"].queryset = UnitOfMeasure.objects.filter(status=MasterStatus.ACTIVE)
            self.fields["allowed_units"].queryset = UnitOfMeasure.objects.filter(status=MasterStatus.ACTIVE)
        else:
            self.fields["category"].queryset = ActivityCategory.objects.all()
            self.fields["base_unit"].queryset = UnitOfMeasure.objects.all()
            self.fields["allowed_units"].queryset = UnitOfMeasure.objects.all()

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if not code:
            raise ValidationError("Activity code is required.")
        qs = ActivityMaster.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"An activity master with code '{code}' already exists.")
        return code

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            # Ensure base_unit is always included in allowed_units
            if instance.base_unit:
                instance.allowed_units.add(instance.base_unit)
        return instance


class ActivityCategoryForm(forms.ModelForm):
    """
    Form for configuring ESG Activity Categories.
    """

    class Meta:
        model = ActivityCategory
        fields = ["code", "name", "description", "display_order", "status"]
        widgets = {
            "code": forms.TextInput(
                attrs={
                    "class": "form-control text-uppercase",
                    "placeholder": "e.g. FUEL",
                    "autocomplete": "off",
                }
            ),
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Fuel & Combustion",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Scope boundary and guidance for activities under this category.",
                }
            ),
            "display_order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if not code:
            raise ValidationError("Category code is required.")
        qs = ActivityCategory.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"An activity category with code '{code}' already exists.")
        return code


class UnitOfMeasureForm(forms.ModelForm):
    """
    Form for configuring standardized Units of Measure.
    """

    class Meta:
        model = UnitOfMeasure
        fields = ["code", "name", "symbol", "dimension", "description", "status"]
        widgets = {
            "code": forms.TextInput(
                attrs={
                    "class": "form-control text-uppercase",
                    "placeholder": "e.g. LITRE",
                    "autocomplete": "off",
                }
            ),
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Litre",
                }
            ),
            "symbol": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. L",
                }
            ),
            "dimension": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Standard measurement notes or conversion reference.",
                }
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if not code:
            raise ValidationError("Unit code is required.")
        qs = UnitOfMeasure.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"A unit with code '{code}' already exists.")
        return code
