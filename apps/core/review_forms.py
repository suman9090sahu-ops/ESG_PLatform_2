"""
Forms for Subsidiary Manager Review Workflow and Decision Confirmations.

Fulfills Phase 13 Requirements:
- Server-side validation for Verify, Request Correction, Explain, and Escalate
- Compulsory non-empty reasons for correction, explanation, and escalation
- Clear user guidance and confirmation checkboxes
"""

from django import forms
from apps.core.models import CorrectionAffectedArea, Role


class VerifySubmissionForm(forms.Form):
    """Form to process Subsidiary Manager verification decision."""

    comments = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Enter verification remarks, compliance findings, or operational sign-off notes (optional)...",
            }
        ),
        required=False,
        label="Verification Remarks",
        help_text="Optional remarks recorded in the permanent governance audit ledger.",
    )
    confirm = forms.BooleanField(
        required=True,
        label="I have inspected the operational telemetry, supporting evidence, OCR intel, and validation findings, and verify this submission for ESG governance.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class RequestCorrectionForm(forms.Form):
    """Form to process Subsidiary Manager correction request back to Site Manager."""

    reason = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Describe the discrepancy, variance, or documentation gap...",
            }
        ),
        required=True,
        label="Reason for Correction Request",
        help_text="Clear explanation of why this record cannot be verified in its current state.",
    )
    required_correction = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Specify exact steps required from Site Manager (e.g., re-upload legible invoice, adjust consumption quantity to match meter serial #104)...",
            }
        ),
        required=True,
        label="Required Action from Site Manager",
        help_text="Actionable revision instructions for the Site Manager.",
    )
    affected_area = forms.ChoiceField(
        choices=CorrectionAffectedArea.choices,
        initial=CorrectionAffectedArea.ACTIVITY_DATA,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Affected Area",
        help_text="Primary operational scope of the required correction.",
    )
    confirm = forms.BooleanField(
        required=True,
        label="I confirm this correction request will return the submission to Revision Requested status.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class ExplainSubmissionForm(forms.Form):
    """Form to record contextual operating explanation without altering underlying data."""

    explanation = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Record operational context, seasonal variance, equipment breakdown, maintenance cycle, or external circumstances...",
            }
        ),
        required=True,
        label="Contextual Explanation / Justification",
        help_text="Formal explanation preserved in the audit lineage. Does not alter operational telemetry or bypass validation rules.",
    )
    confirm = forms.BooleanField(
        required=True,
        label="I confirm this operating explanation is accurate and supported by site conditions.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class EscalateSubmissionForm(forms.Form):
    """Form to escalate submission to Corporate ESG Manager."""

    reason = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Explain why this submission requires corporate ESG Governance intervention (e.g. boundary ambiguity, regulatory classification conflict)...",
            }
        ),
        required=True,
        label="Escalation Rationale",
        help_text="Provide justification for transferring governance responsibility.",
    )
    target_role = forms.ChoiceField(
        choices=[
            (Role.Code.ESG_MANAGER, "ESG Governance Manager (Corporate Sustainability)"),
        ],
        initial=Role.Code.ESG_MANAGER,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Escalate Target Authority",
        help_text="Target governance authority for this escalation.",
    )
    confirm = forms.BooleanField(
        required=True,
        label="I confirm escalation of this submission to corporate ESG Governance.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
