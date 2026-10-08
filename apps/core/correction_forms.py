"""
Forms for Site Manager Correction, Revision, and Resubmission Actions.

Fulfills Phase 14 Requirements:
- Server-side validation for Site Manager corrections
- Restricts editing exclusively to approved operational fields
- Compulsory non-empty explanation of changes made
- Resubmission confirmation and validation acknowledgement
"""

from decimal import Decimal
from django import forms

from apps.core.models import ActivityRecord, UnitOfMeasure


class CorrectionUpdateForm(forms.ModelForm):
    """
    Form for Site Manager to modify correctable operational activity data
    in response to an authoritative Correction Request.
    """

    site_manager_notes = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Explain the operational changes made, documents updated, or corrections applied in detail...",
            }
        ),
        required=True,
        label="Correction Notes & Explanation",
        help_text="Mandatory explanation of what was corrected, which document was updated, or how variances were addressed.",
    )

    class Meta:
        model = ActivityRecord
        fields = [
            "quantity",
            "unit",
            "measurement_date",
            "notes",
            "evidence_reference",
        ]
        widgets = {
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control font-monospace",
                    "step": "any",
                    "placeholder": "Enter corrected consumption quantity",
                }
            ),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "measurement_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Operational telemetry notes, meter serial numbers, meter readings...",
                }
            ),
            "evidence_reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Invoice #, Challan #, or document reference",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Filter units compatible with the activity dimension if possible
            if self.instance.activity and self.instance.activity.base_unit:
                base_dim = self.instance.activity.base_unit.dimension
                self.fields["unit"].queryset = UnitOfMeasure.objects.filter(
                    is_active=True, dimension=base_dim
                ).order_by("name")
            else:
                self.fields["unit"].queryset = UnitOfMeasure.objects.filter(
                    is_active=True
                ).order_by("name")

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        if quantity is not None and quantity < Decimal("0"):
            raise forms.ValidationError("Operational quantity must be a non-negative number.")
        return quantity


class ResubmitCorrectionForm(forms.Form):
    """
    Form to formally resubmit a corrected ActivityRecord back to the Subsidiary Manager review queue.
    """

    resubmission_comments = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Provide handover comments, notes on resolved discrepancies, or verification details for the reviewer...",
            }
        ),
        required=False,
        label="Resubmission Remarks",
        help_text="Optional remarks for the Subsidiary Reviewer regarding this resubmission iteration.",
    )
    confirm = forms.BooleanField(
        required=True,
        label="I confirm the operational telemetry has been corrected and revalidated according to review instructions, and is ready for Subsidiary Manager sign-off.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
