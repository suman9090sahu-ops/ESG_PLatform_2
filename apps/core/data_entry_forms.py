"""
Forms for ESG Data Entry and Activity Telemetry for MEIL ESG CONTROL TOWER.

Fulfills Phase 08 Requirements:
- ActivityRecordForm: Secure, scoped operational data logging for Site Managers
- ActivityRecordFilterForm: Responsive filtering for activity records ledger
- Server-side validation of site authorization, open reporting period, allowed physical units, and positive quantities
"""

from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError

from apps.core.activity_services import (
    get_accessible_activity_categories,
    get_accessible_activity_masters,
    get_accessible_units,
    validate_activity_unit,
)
from apps.core.data_entry_services import (
    get_candidate_activities_for_data_entry,
    get_candidate_periods_for_site,
    get_candidate_sites_for_data_entry,
    get_candidate_units_for_activity,
)
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    MasterStatus,
    OrganizationStatus,
    PeriodStatus,
    RecordStatus,
    ReportingPeriod,
    Site,
    UnitOfMeasure,
    ValidationStatus,
)
from apps.core.period_services import get_accessible_reporting_periods
from apps.core.scope_services import get_accessible_sites


class ActivityRecordForm(forms.ModelForm):
    """
    Operational data-entry form for recording ESG activity telemetry.
    Strictly scopes foreign key choices to user's authorized domain boundaries.
    """

    status = forms.ChoiceField(
        choices=[
            (RecordStatus.DRAFT, "Save as Draft"),
            (RecordStatus.READY, "Mark as Ready for Submission"),
        ],
        initial=RecordStatus.DRAFT,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Save as editable Draft or mark Ready for subsequent verification.",
    )

    class Meta:
        model = ActivityRecord
        fields = [
            "site",
            "reporting_period",
            "activity",
            "measurement_date",
            "quantity",
            "unit",
            "notes",
            "evidence_reference",
            "status",
        ]
        widgets = {
            "site": forms.Select(attrs={"class": "form-select", "id": "id_site"}),
            "reporting_period": forms.Select(attrs={"class": "form-select", "id": "id_reporting_period"}),
            "activity": forms.Select(attrs={"class": "form-select", "id": "id_activity"}),
            "measurement_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date", "id": "id_measurement_date"}
            ),
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.0001",
                    "min": "0",
                    "placeholder": "e.g. 1250.00",
                    "id": "id_quantity",
                }
            ),
            "unit": forms.Select(attrs={"class": "form-select", "id": "id_unit"}),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Enter operational notes, generator/vehicle ID, meter number, or invoice details.",
                    "id": "id_notes",
                }
            ),
            "evidence_reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Tax Invoice #INV-2025-883 or Fuel Challan #CH-104",
                    "id": "id_evidence_reference",
                }
            ),
        }

    def __init__(self, *args, user=None, initial_site=None, initial_period=None, initial_activity=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if user:
            # 1. Scope Sites to active authorized sites
            candidate_sites = get_candidate_sites_for_data_entry(user)
            self.fields["site"].queryset = candidate_sites
            self.fields["site"].empty_label = "— Select Authorized Site —"

            # Auto-select site if only 1 accessible or initial specified
            if initial_site and initial_site in candidate_sites:
                self.fields["site"].initial = initial_site
            elif candidate_sites.count() == 1 and not self.instance.pk:
                self.fields["site"].initial = candidate_sites.first()

            # 2. Scope Reporting Periods
            if self.instance.pk and self.instance.site:
                selected_site = self.instance.site
            else:
                selected_site = self.initial.get("site")

            if selected_site:
                periods_qs = get_candidate_periods_for_site(selected_site, user)
            else:
                periods_qs = get_accessible_reporting_periods(user).filter(status=PeriodStatus.OPEN)

            self.fields["reporting_period"].queryset = periods_qs
            self.fields["reporting_period"].empty_label = "— Select Open Reporting Period —"

            if initial_period and initial_period in periods_qs:
                self.fields["reporting_period"].initial = initial_period
            elif periods_qs.count() == 1 and not self.instance.pk:
                self.fields["reporting_period"].initial = periods_qs.first()

            # 3. Scope Activities to active approved catalog
            candidate_activities = get_candidate_activities_for_data_entry(user)
            self.fields["activity"].queryset = candidate_activities
            self.fields["activity"].empty_label = "— Select Approved ESG Activity —"

            if initial_activity and initial_activity in candidate_activities:
                self.fields["activity"].initial = initial_activity

            # 4. Scope Units
            if self.instance.pk and self.instance.activity:
                selected_activity = self.instance.activity
            else:
                selected_activity = self.initial.get("activity")
            if selected_activity:
                units_qs = get_candidate_units_for_activity(selected_activity)
            else:
                units_qs = get_accessible_units(user, include_inactive=False).filter(status=MasterStatus.ACTIVE)

            self.fields["unit"].queryset = units_qs
            self.fields["unit"].empty_label = "— Select Unit of Measure —"
            if selected_activity and not self.instance.pk:
                self.fields["unit"].initial = selected_activity.base_unit

    def clean(self):
        cleaned_data = super().clean()
        user = self.user

        site = cleaned_data.get("site")
        reporting_period = cleaned_data.get("reporting_period")
        activity = cleaned_data.get("activity")
        unit = cleaned_data.get("unit")
        measurement_date = cleaned_data.get("measurement_date")
        quantity = cleaned_data.get("quantity")

        # 1. Site Authorization Verification
        if site and user:
            candidate_sites = get_candidate_sites_for_data_entry(user)
            if site not in candidate_sites:
                raise ValidationError({
                    "site": f"You are not authorized to enter activity data for operational site '{site.name}'."
                })

        # 2. Reporting Period Lifecycle & Boundaries
        if reporting_period:
            if reporting_period.status != PeriodStatus.OPEN:
                raise ValidationError({
                    "reporting_period": (
                        f"Reporting period '{reporting_period.code}' is currently {reporting_period.get_status_display().upper()}. "
                        f"Data entry is prohibited in non-open periods."
                    )
                })

            if site:
                site_company = site.project.subsidiary.company
                site_subsidiary = site.project.subsidiary
                if reporting_period.company_id != site_company.id:
                    raise ValidationError({
                        "reporting_period": (
                            f"Reporting period '{reporting_period.code}' belongs to company '{reporting_period.company.name}', "
                            f"which does not match site '{site.name}' company '{site_company.name}'."
                        )
                    })
                if reporting_period.subsidiary_id and reporting_period.subsidiary_id != site_subsidiary.id:
                    raise ValidationError({
                        "reporting_period": (
                            f"Reporting period '{reporting_period.code}' belongs to subsidiary '{reporting_period.subsidiary.name}', "
                            f"which does not match site '{site.name}' division '{site_subsidiary.name}'."
                        )
                    })

            if measurement_date:
                if measurement_date < reporting_period.start_date or measurement_date > reporting_period.end_date:
                    raise ValidationError({
                        "measurement_date": (
                            f"Measurement date ({measurement_date}) must fall within reporting period '{reporting_period.code}' "
                            f"boundaries ({reporting_period.start_date} to {reporting_period.end_date})."
                        )
                    })

        # 3. Activity Master Verification
        if activity:
            if not activity.is_active or activity.status != MasterStatus.ACTIVE:
                raise ValidationError({
                    "activity": f"Activity '{activity.name}' is inactive and cannot accept operational telemetry entries."
                })

        # 4. Unit Permissibility Verification
        if activity and unit:
            if not validate_activity_unit(activity, unit):
                allowed_units = [activity.base_unit.symbol] + [u.symbol for u in activity.allowed_units.all()]
                allowed_str = ", ".join(dict.fromkeys(allowed_units))
                raise ValidationError({
                    "unit": (
                        f"Unit '{unit.name} ({unit.symbol})' is not permissible for activity '{activity.name}'. "
                        f"Permissible units: {allowed_str}."
                    )
                })

        # 5. Quantity Sanity Check
        if quantity is not None and quantity < 0:
            raise ValidationError({
                "quantity": "Consumption quantity cannot be negative."
            })

        return cleaned_data


class ActivityRecordFilterForm(forms.Form):
    """
    Filter form for the Site Manager Activity Records ledger view.
    """

    site = forms.ModelChoiceField(
        queryset=Site.objects.none(),
        required=False,
        empty_label="All Assigned Sites",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    reporting_period = forms.ModelChoiceField(
        queryset=ReportingPeriod.objects.none(),
        required=False,
        empty_label="All Periods",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    category = forms.ModelChoiceField(
        queryset=ActivityCategory.objects.none(),
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    status = forms.ChoiceField(
        choices=[("", "All Statuses")] + RecordStatus.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    validation_status = forms.ChoiceField(
        choices=[("", "All Validation States")] + ValidationStatus.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date", "placeholder": "From"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date", "placeholder": "To"}),
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control form-control-sm", "placeholder": "Search notes, code, invoice..."}
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["site"].queryset = get_candidate_sites_for_data_entry(user)
            self.fields["reporting_period"].queryset = get_accessible_reporting_periods(user)
            self.fields["category"].queryset = get_accessible_activity_categories(user)
