"""
Forms for Emission Factor Administration and Calculation Management.

Fulfills Phase 24 Requirements:
- Server-side validation of emission factor parameters
- Protection against invalid / negative factor values
- Enforcement of required regulatory authority and vintage year metadata
"""

from decimal import Decimal
from django import forms

from apps.core.models import (
    ActivityMaster,
    EmissionFactor,
    EmissionFactorStatus,
    ReportingPeriod,
    Scope3Category,
    ScopeClassification,
    UnitOfMeasure,
)


class EmissionFactorForm(forms.ModelForm):
    """
    Governance Form for creating and editing Regulatory Emission Factors.
    Restricted to authorized roles (ESG_MANAGER, MEIL_OPERATOR).
    """

    class Meta:
        model = EmissionFactor
        fields = [
            "name",
            "code",
            "activity",
            "scope",
            "scope3_category",
            "calculation_method",
            "factor_value",
            "factor_unit",
            "input_unit",
            "output_unit",
            "source",
            "effective_year",
            "reporting_period",
            "geography",
            "version",
            "status",
            "methodology_notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. IPCC 2006 Diesel Stationary Combustion"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. EF-DIESEL-STAT-2024"}),
            "activity": forms.Select(attrs={"class": "form-select"}),
            "scope": forms.Select(attrs={"class": "form-select"}),
            "scope3_category": forms.Select(attrs={"class": "form-select"}),
            "calculation_method": forms.Select(attrs={"class": "form-select"}),
            "factor_value": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001", "placeholder": "2.680000"}),
            "factor_unit": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. kg CO₂e / L"}),
            "input_unit": forms.Select(attrs={"class": "form-select"}),
            "output_unit": forms.TextInput(attrs={"class": "form-control", "placeholder": "kg CO₂e"}),
            "source": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. India GHG Program / IPCC 2006"}),
            "effective_year": forms.NumberInput(attrs={"class": "form-control", "min": 2000, "max": 2050}),
            "reporting_period": forms.Select(attrs={"class": "form-select"}),
            "geography": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. India (National)"}),
            "version": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. v1.0"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "methodology_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Regulatory methodology, IPCC tier reference, or equation details."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activity"].queryset = ActivityMaster.objects.filter(is_active=True).order_by("name")
        self.fields["input_unit"].queryset = UnitOfMeasure.objects.filter(is_active=True).order_by("name")
        self.fields["reporting_period"].queryset = ReportingPeriod.objects.all().order_by("-start_date")
        self.fields["scope3_category"].queryset = Scope3Category.objects.filter(is_active=True).order_by("category_number")
        self.fields["scope3_category"].empty_label = "— Select Scope 3 Category (Optional) —"
        self.fields["scope3_category"].required = False
        self.fields["calculation_method"].required = False
        self.fields["reporting_period"].required = False
        self.fields["activity"].required = False

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if not code:
            raise forms.ValidationError("Emission factor unique code is required.")
        return code

    def clean_factor_value(self):
        val = self.cleaned_data.get("factor_value")
        if val is None or val < Decimal("0.0"):
            raise forms.ValidationError("Factor value must be zero or a positive decimal number.")
        return val

    def clean(self):
        cleaned_data = super().clean()
        activity = cleaned_data.get("activity")
        if activity and not cleaned_data.get("activity_code"):
            cleaned_data["activity_code"] = activity.code
        return cleaned_data
