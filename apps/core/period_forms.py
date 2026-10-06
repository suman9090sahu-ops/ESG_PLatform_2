"""
Reporting Period Management Forms for MEIL ESG CONTROL TOWER.

Includes:
- ReportingPeriodForm: Creation and editing with server-side scoped company/subsidiary choices,
  date validation, overlap prevention, and duplicate code detection.
- ReportingPeriodStatusForm: Controlled lifecycle transition form with rationale/audit notes.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import Company, PeriodStatus, ReportingPeriod, Subsidiary
from apps.core.scope_services import get_accessible_companies, get_accessible_subsidiaries


class ReportingPeriodForm(forms.ModelForm):
    """
    Form for creating and editing Reporting Periods with server-side organizational scope validation.
    """

    class Meta:
        model = ReportingPeriod
        fields = [
            "company",
            "subsidiary",
            "code",
            "name",
            "fiscal_year",
            "start_date",
            "end_date",
            "status",
            "description",
        ]
        widgets = {
            "company": forms.Select(attrs={"class": "form-select", "id": "id_company"}),
            "subsidiary": forms.Select(attrs={"class": "form-select", "id": "id_subsidiary"}),
            "code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. FY2025-26",
                    "id": "id_code",
                }
            ),
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. FY 2025-26 Annual ESG Reporting Cycle",
                    "id": "id_name",
                }
            ),
            "fiscal_year": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. FY 2025-26",
                    "id": "id_fiscal_year",
                }
            ),
            "start_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                    "id": "id_start_date",
                }
            ),
            "end_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                    "id": "id_end_date",
                }
            ),
            "status": forms.Select(attrs={"class": "form-select", "id": "id_status"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Operational notes, regulatory scope (e.g. SEBI BRSR Core), or boundary notes.",
                    "id": "id_description",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Configure subsidiary field to be optional
        self.fields["subsidiary"].required = False
        self.fields["subsidiary"].empty_label = "— Enterprise-Wide (All Subsidiaries) —"

        # Scope company choices to user's accessible companies
        if user:
            self.fields["company"].queryset = get_accessible_companies(user).filter(is_active=True)
            self.fields["subsidiary"].queryset = get_accessible_subsidiaries(user).filter(is_active=True)
        else:
            self.fields["company"].queryset = Company.objects.filter(is_active=True)
            self.fields["subsidiary"].queryset = Subsidiary.objects.filter(is_active=True)

        # In edit mode for locked or finalized periods, disable critical fields
        if self.instance and self.instance.pk:
            if not self.instance.allows_metadata_edit:
                for field_name in ["company", "subsidiary", "code", "start_date", "end_date", "fiscal_year"]:
                    self.fields[field_name].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        company = cleaned_data.get("company")
        subsidiary = cleaned_data.get("subsidiary")
        code = cleaned_data.get("code")

        # 1. Date order validation
        if start_date and end_date:
            if start_date >= end_date:
                self.add_error("end_date", "End date must be strictly after the start date.")

        # 2. Duplicate identifier prevention per company
        if company and code:
            existing_code = ReportingPeriod.objects.filter(company=company, code__iexact=code)
            if self.instance and self.instance.pk:
                existing_code = existing_code.exclude(pk=self.instance.pk)
            if existing_code.exists():
                self.add_error(
                    "code",
                    f"A reporting period with code '{code}' already exists for {company.name}.",
                )

        # 3. Overlapping period validation within the same organizational scope
        if company and start_date and end_date:
            qs = ReportingPeriod.objects.filter(company=company)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if subsidiary:
                qs = qs.filter(
                    models.Q(subsidiary=subsidiary) | models.Q(subsidiary__isnull=True)
                )

            overlapping = qs.filter(
                start_date__lte=end_date,
                end_date__gte=start_date,
            ).first()

            if overlapping:
                sub_label = f" ({overlapping.subsidiary.name})" if overlapping.subsidiary else " (Enterprise-wide)"
                self.add_error(
                    "start_date",
                    f"Date range overlaps with existing period '{overlapping.name}'{sub_label} "
                    f"[{overlapping.start_date} to {overlapping.end_date}].",
                )

        return cleaned_data


class ReportingPeriodStatusForm(forms.Form):
    """
    Form for executing a controlled status lifecycle transition.
    """

    target_status = forms.ChoiceField(
        choices=PeriodStatus.choices,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_target_status"}),
        help_text="Select destination lifecycle state.",
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Reason or compliance documentation for this status change...",
                "id": "id_transition_reason",
            }
        ),
        help_text="Optional audit log rationale.",
    )

    def __init__(self, *args, period=None, **kwargs):
        super().__init__(*args, **kwargs)
        if period:
            allowed = period.get_allowed_transitions()
            self.fields["target_status"].choices = [
                (c, l) for c, l in PeriodStatus.choices if c in allowed
            ]
