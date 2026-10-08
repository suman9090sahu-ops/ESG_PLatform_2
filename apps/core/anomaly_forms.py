"""
Forms for ESG Anomaly Detection Engine and Review Workflows in apps.core.
"""

from django import forms
from apps.core.models import (
    AnomalyCategory,
    AnomalySeverity,
    AnomalyStatus,
)


class AnomalyFilterForm(forms.Form):
    """Filter form for Anomaly Desk."""

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Search rule, site, activity, reason...",
            }
        ),
    )
    severity = forms.ChoiceField(
        required=False,
        choices=[("", "All Severities")] + list(AnomalySeverity.choices),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses")] + list(AnomalyStatus.choices),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    category = forms.ChoiceField(
        required=False,
        choices=[("", "All Categories")] + list(AnomalyCategory.choices),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    site = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )
    period = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )


class AnomalyReviewActionForm(forms.Form):
    """Action form for executing Anomaly review transitions (Acknowledge, Explain, Resolve, Dismiss)."""

    action = forms.ChoiceField(
        choices=[
            ("ACKNOWLEDGE", "Acknowledge"),
            ("EXPLAIN", "Explain Operational Context"),
            ("RESOLVE", "Mark as Resolved"),
            ("DISMISS", "Dismiss Finding"),
        ],
        widget=forms.HiddenInput(),
    )
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Provide detailed operational rationale, justification, or resolution explanation...",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        comment = cleaned_data.get("comment", "").strip()

        if action in ["EXPLAIN", "RESOLVE", "DISMISS"] and not comment:
            self.add_error("comment", f"An explanation is required to {action.lower()} this anomaly.")

        return cleaned_data
