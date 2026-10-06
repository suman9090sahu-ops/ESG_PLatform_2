"""
Organization Management Forms for MEIL ESG CONTROL TOWER.

Includes:
- SubsidiaryForm: Division / company creation & editing
- ProjectForm: Infrastructure project management with scoped subsidiary choices
- SiteForm: Operational site management with scoped project choices
- Styled with Bootstrap 5 input components matching Phase 01 design tokens
"""

from django import forms
from apps.core.models import Company, OrganizationStatus, Project, Site, Subsidiary
from apps.core.scope_services import get_accessible_projects, get_accessible_subsidiaries


class SubsidiaryForm(forms.ModelForm):
    """Form for creating and editing Subsidiary Companies / Divisions."""

    class Meta:
        model = Subsidiary
        fields = [
            "company",
            "name",
            "code",
            "legal_name",
            "short_name",
            "industry",
            "country",
            "registered_address",
            "status",
        ]
        widgets = {
            "company": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. MEIL Hydro & Infrastructure Division"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. MEIL-HYDRO"}),
            "legal_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Megha Hydro Power Infrastructure Ltd."}),
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Hydro Division"}),
            "industry": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Hydroelectric Power & Water Engineering"}),
            "country": forms.TextInput(attrs={"class": "form-control", "placeholder": "India"}),
            "registered_address": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Corporate registered office address"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = Company.objects.filter(is_active=True).order_by("name")


class ProjectForm(forms.ModelForm):
    """Form for creating and editing Infrastructure Projects with scope enforcement."""

    class Meta:
        model = Project
        fields = [
            "subsidiary",
            "name",
            "code",
            "description",
            "location",
            "start_date",
            "end_date",
            "status",
        ]
        widgets = {
            "subsidiary": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Polavaram Irrigation & Powerhouse"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. PRJ-POL-01"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Engineering scope and ESG boundary description"}),
            "location": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Godavari Basin, Andhra Pradesh"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            # Enforce server-side subsidiary scope filtering
            self.fields["subsidiary"].queryset = get_accessible_subsidiaries(user).filter(is_active=True)
        else:
            self.fields["subsidiary"].queryset = Subsidiary.objects.filter(is_active=True).order_by("name")


class SiteForm(forms.ModelForm):
    """Form for creating and editing Operational Sites with scope enforcement."""

    class Meta:
        model = Site
        fields = [
            "project",
            "name",
            "code",
            "facility_type",
            "location",
            "latitude",
            "longitude",
            "contact_person",
            "contact_email",
            "description",
            "status",
        ]
        widgets = {
            "project": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Polavaram Dam Headworks Site"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. SITE-POL-101"}),
            "facility_type": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Hydroelectric Dam / Substation / Array"}),
            "location": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Polavaram, Eluru District, AP"}),
            "latitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001", "placeholder": "e.g. 17.251400"}),
            "longitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001", "placeholder": "e.g. 81.654200"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Er. K. Srinivasa Rao"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "e.g. polavaram.site1@meilgroup.com"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Facility telemetry boundaries, fuel meters, and grid interconnects"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            # Enforce server-side project scope filtering
            self.fields["project"].queryset = get_accessible_projects(user).filter(is_active=True)
        else:
            self.fields["project"].queryset = Project.objects.filter(is_active=True).order_by("name")
