"""
Evidence Forms for MEIL ESG CONTROL TOWER.

Includes:
- EvidenceUploadForm: Secure upload form with client feedback and server-side validation.
- EvidenceRetireForm: Form requiring audit justification to retire an evidence document.
- EvidenceFilterForm: Responsive filter form for the evidence repository list.
"""

from django import forms
from django.core.exceptions import ValidationError

from apps.core.evidence_services import validate_evidence_file
from apps.core.models import EvidenceStatus, EvidenceType, ReportingPeriod, Site
from apps.core.period_services import get_accessible_reporting_periods
from apps.core.scope_services import get_accessible_sites


class EvidenceUploadForm(forms.Form):
    """
    Form for uploading supporting evidence files against an ActivityRecord.
    Enforces extension, MIME, size, and header signature validation.
    """

    file = forms.FileField(
        required=True,
        widget=forms.FileInput(
            attrs={
                "class": "form-control",
                "id": "id_evidence_file",
                "accept": ".pdf,.jpg,.jpeg,.png,.xlsx,.xls,.csv,.docx",
            }
        ),
        help_text="Permitted formats: PDF, JPG, PNG, Excel (.xlsx/.xls), CSV, Word (.docx). Maximum file size: 25 MB.",
    )

    evidence_type = forms.ChoiceField(
        choices=EvidenceType.choices,
        initial=EvidenceType.INVOICE,
        required=True,
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_evidence_type",
            }
        ),
        help_text="Categorize the type of supporting documentation.",
    )

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "id": "id_description",
                "rows": 3,
                "placeholder": "e.g., Diesel delivery invoice INV-2025-09-001 from Indian Oil Corporation Ltd.",
            }
        ),
        help_text="Optional document details, invoice reference number, or operational context.",
    )

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            raise ValidationError("Please select a file to upload.")

        try:
            self.file_metadata = validate_evidence_file(uploaded)
        except ValidationError as e:
            raise e
        except Exception as e:
            raise ValidationError(f"File validation failed: {str(e)}")

        return uploaded


class EvidenceRetireForm(forms.Form):
    """
    Form for retiring an active evidence document with required audit justification.
    """

    reason = forms.CharField(
        required=True,
        min_length=5,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "id": "id_retire_reason",
                "rows": 3,
                "placeholder": "State the audit or operational reason for retiring this document (e.g., Replaced by revised tax invoice dated Oct 15).",
            }
        ),
        help_text="Audit rationale is required to retire or supersede verified evidence.",
    )


class EvidenceFilterForm(forms.Form):
    """
    Filter form for the scoped Evidence repository list view.
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
        empty_label="All Reporting Cycles",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    evidence_type = forms.ChoiceField(
        choices=[("", "All Evidence Types")] + list(EvidenceType.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    status = forms.ChoiceField(
        choices=[("", "All Statuses")] + list(EvidenceStatus.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Search filename or notes...",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            self.fields["site"].queryset = get_accessible_sites(user).order_by("name")
            self.fields["reporting_period"].queryset = get_accessible_reporting_periods(user).order_by("-start_date")
