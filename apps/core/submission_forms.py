"""
Forms for Activity Record Submission and Workflow Management.

Fulfills Phase 12 Requirements:
- Formal Submission Confirmation Form with submitter comments
- Submitter Confirmation Checkbox
- Safe Submission Withdrawal Form
"""

from django import forms


class ActivityRecordSubmitForm(forms.Form):
    """
    Form for confirming and executing formal activity record submission.
    """

    comments = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Optional operational notes, meter/invoice context, or remarks for subsidiary review...",
            }
        ),
        required=False,
        label="Operational Comments & Notes",
        help_text="Optional remarks for downstream Subsidiary Managers and ESG auditors.",
    )
    confirm = forms.BooleanField(
        required=True,
        label="I confirm this record telemetry and supporting documentation have been verified and are ready for formal downstream review.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        error_messages={
            "required": "You must confirm that this record data and documentation have been verified before submitting."
        },
    )


class SubmissionWithdrawForm(forms.Form):
    """
    Form for withdrawing an active submission prior to downstream review.
    """

    reason = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Provide the operational reason for withdrawing this submission (e.g. data re-measurement required, updated invoice received)...",
            }
        ),
        required=True,
        label="Reason for Withdrawal",
        help_text="Required for audit and compliance traceability.",
    )
    confirm = forms.BooleanField(
        required=True,
        label="I confirm that I want to withdraw this submission and return the activity record to DRAFT state for revision.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        error_messages={
            "required": "You must confirm the withdrawal action."
        },
    )
