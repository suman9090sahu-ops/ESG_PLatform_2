"""
Forms for ESG Validation Engine and Rule Governance for MEIL ESG CONTROL TOWER.

Fulfills Phase 10 Requirements:
- ValidationRuleForm: Controlled modification of validation rules by ESG Managers / MEIL Operators
- ValidationRuleFilterForm: Categorical and severity filtering for validation rules management ledger
"""

from django import forms

from apps.core.models import (
    ValidationCategory,
    ValidationRule,
    ValidationSeverity,
)


class ValidationRuleForm(forms.ModelForm):
    """
    Form for editing ValidationRule properties.
    Code and category remain immutable to maintain engine registry alignment.
    """

    class Meta:
        model = ValidationRule
        fields = [
            "name",
            "description",
            "severity",
            "is_active",
            "is_blocking",
            "rule_parameters",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Human-readable rule name"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Operational rationale and guidelines"}),
            "severity": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_blocking": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "rule_parameters": forms.Textarea(attrs={"class": "form-control font-monospace small", "rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["severity"].help_text = "ERROR blocks submission; WARNING alerts review staff."
            self.fields["is_blocking"].help_text = "If checked, violations will prevent advancing records to Ready/Submitted status."


class ValidationRuleFilterForm(forms.Form):
    """
    Filter form for the Validation Rules repository.
    """

    category = forms.ChoiceField(
        choices=[("", "All Categories")] + ValidationCategory.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    severity = forms.ChoiceField(
        choices=[("", "All Severities")] + ValidationSeverity.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    is_active = forms.ChoiceField(
        choices=[("", "All Statuses"), ("1", "Active"), ("0", "Inactive")],
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control form-control-sm", "placeholder": "Search rule name, code, description..."}
        ),
    )
