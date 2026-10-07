"""
Views for ESG Validation Engine and Data Quality Governance for MEIL ESG CONTROL TOWER.

Fulfills Phase 10 Requirements:
- Deterministic Record Validation Execution (record_validate_view)
- Batch Telemetry Validation (record_batch_validate_view)
- Granular Historical Validation Run Inspection (validation_run_detail_view)
- Enterprise Validation Rules Catalog & Governance (validation_rule_list_view, validation_rule_detail_view, validation_rule_toggle_view, validation_rule_edit_view)
- Strict Anti-IDOR Protections, Server-Side Authorization, and Immutable Security Audit Logging
"""

import json
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.auth_services import log_auth_event, role_required
from apps.core.data_entry_services import (
    get_accessible_activity_records,
    user_can_access_activity_record,
)
from apps.core.models import (
    ActivityRecord,
    AuthAuditLog,
    RecordStatus,
    Role,
    ValidationCategory,
    ValidationResult,
    ValidationRule,
    ValidationRun,
    ValidationSeverity,
    ValidationStatus,
)
from apps.core.validation_forms import (
    ValidationRuleFilterForm,
    ValidationRuleForm,
)
from apps.core.validation_services import (
    seed_standard_validation_rules,
    user_can_manage_validation_rules,
    user_can_validate_record,
    user_can_view_validation_rules,
    validate_activity_record,
    validate_activity_records,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. RECORD VALIDATION EXECUTION ENDPOINT
# -----------------------------------------------------------------------------

@login_required
@require_POST
def record_validate_view(request, record_id):
    """
    Executes Phase 10 Validation Engine for a specific ActivityRecord.
    Strictly enforces object-level authorization and anti-IDOR boundaries.
    """
    user = request.user

    # Fetch candidate record
    record = get_object_or_404(
        ActivityRecord.objects.select_related(
            "site",
            "site__project",
            "site__project__subsidiary",
            "site__project__subsidiary__company",
            "reporting_period",
            "activity",
            "activity__base_unit",
            "unit",
        ),
        pk=record_id,
    )

    # Enforce object authorization
    if not user_can_validate_record(user, record):
        log_auth_event(
            user=user,
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            resource_accessed=f"ActivityRecord:{record_id}:Validate",
            details=f"Unauthorized attempt to execute validation on ActivityRecord #{record_id} by user {user.username}.",
            success=False,
            request=request,
        )
        raise PermissionDenied("Access Denied: You are not authorized to validate this activity record.")

    # Execute deterministic validation engine
    val_run = validate_activity_record(record, executed_by=user, request=request)

    # Provide operational user feedback
    if val_run.status == ValidationStatus.VALID:
        messages.success(
            request,
            f"Validation Passed (Run #{val_run.run_number}): Record satisfies all deterministic ESG data quality and boundary rules.",
        )
    elif val_run.status == ValidationStatus.WARNING:
        messages.warning(
            request,
            f"Validation Passed with Warnings (Run #{val_run.run_number}): {val_run.warning_count} advisory warning(s) detected. Record is eligible for submission.",
        )
    else:
        messages.error(
            request,
            f"Validation Failed (Run #{val_run.run_number}): {val_run.error_count} blocking error(s) detected. Please correct data or attach required evidence before submitting.",
        )

    # AJAX / API response support
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", "")
    if is_ajax:
        return JsonResponse({
            "success": True,
            "run_id": val_run.id,
            "run_number": val_run.run_number,
            "status": val_run.status,
            "status_display": val_run.get_status_display(),
            "error_count": val_run.error_count,
            "warning_count": val_run.warning_count,
            "info_count": val_run.info_count,
            "summary": val_run.summary_message,
            "badge_class": val_run.badge_class,
        })

    return redirect("core:activity_record_detail", record_id=record.id)


# -----------------------------------------------------------------------------
# 2. BATCH VALIDATION EXECUTION ENDPOINT
# -----------------------------------------------------------------------------

@login_required
@require_POST
def record_batch_validate_view(request):
    """
    Executes batch validation across accessible unvalidated or draft activity records.
    """
    user = request.user
    accessible_qs = get_accessible_activity_records(user)

    # Filter to unvalidated or draft records
    target_status = request.POST.get("target_status", "UNVALIDATED")
    if target_status == "DRAFT":
        target_qs = accessible_qs.filter(status=RecordStatus.DRAFT)
    else:
        target_qs = accessible_qs.filter(validation_status=ValidationStatus.UNVALIDATED)

    summary = validate_activity_records(target_qs, executed_by=user, request=request)

    messages.info(
        request,
        f"Batch Validation Completed: Evaluated {summary['total_evaluated']} records. "
        f"Valid: {summary['valid_count']}, Warnings: {summary['warning_count']}, Invalid: {summary['invalid_count']}.",
    )
    return redirect("core:activity_record_list")


# -----------------------------------------------------------------------------
# 3. VALIDATION RUN AUDIT DETAIL VIEW
# -----------------------------------------------------------------------------

@login_required
def validation_run_detail_view(request, run_id):
    """
    Displays full audit inspection of a specific Validation Run and all associated rule findings.
    """
    user = request.user
    val_run = get_object_or_404(
        ValidationRun.objects.select_related(
            "activity_record",
            "activity_record__site",
            "activity_record__site__project",
            "activity_record__site__project__subsidiary",
            "activity_record__site__project__subsidiary__company",
            "activity_record__activity",
            "activity_record__reporting_period",
            "executed_by",
        ),
        pk=run_id,
    )

    # Object access check
    if not user_can_access_activity_record(user, val_run.activity_record):
        raise PermissionDenied("Access Denied: You are not authorized to view validation results for this record.")

    results = val_run.results.select_related("rule").order_by("severity", "id")

    context = {
        "page_title": f"Validation Run #{val_run.run_number}",
        "page_subtitle": f"Data Quality Audit for Record #{val_run.activity_record_id}",
        "active_nav": "activity_records",
        "val_run": val_run,
        "record": val_run.activity_record,
        "results": results,
    }
    return render(request, "validation/run_detail.html", context)


# -----------------------------------------------------------------------------
# 4. VALIDATION RULES REPOSITORY (GOVERNANCE LEDGER)
# -----------------------------------------------------------------------------

@login_required
def validation_rule_list_view(request):
    """
    Displays the governed catalog of Validation Rules across Layers 1-7.
    Accessible to ESG Manager, MEIL Operator, Auditor, and operational roles.
    """
    user = request.user
    if not user_can_view_validation_rules(user):
        raise PermissionDenied("Access Denied: You do not have permission to view validation rules.")

    # Ensure standard rules are seeded if database is fresh
    if not ValidationRule.objects.exists():
        seed_standard_validation_rules(user=user)

    rules_qs = ValidationRule.objects.select_related("applicable_activity", "created_by", "updated_by").order_by(
        "category", "code"
    )

    filter_form = ValidationRuleFilterForm(request.GET or None)
    if filter_form.is_valid():
        cat = filter_form.cleaned_data.get("category")
        sev = filter_form.cleaned_data.get("severity")
        act = filter_form.cleaned_data.get("is_active")
        search = filter_form.cleaned_data.get("search")

        if cat:
            rules_qs = rules_qs.filter(category=cat)
        if sev:
            rules_qs = rules_qs.filter(severity=sev)
        if act == "1":
            rules_qs = rules_qs.filter(is_active=True)
        elif act == "0":
            rules_qs = rules_qs.filter(is_active=False)
        if search:
            rules_qs = rules_qs.filter(
                models.Q(name__icontains=search)
                | models.Q(code__icontains=search)
                | models.Q(description__icontains=search)
            )

    total_rules = ValidationRule.objects.count()
    active_rules = ValidationRule.objects.filter(is_active=True).count()
    error_rules = ValidationRule.objects.filter(severity=ValidationSeverity.ERROR).count()
    warning_rules = ValidationRule.objects.filter(severity=ValidationSeverity.WARNING).count()

    can_manage = user_can_manage_validation_rules(user)

    context = {
        "page_title": "Validation Rules Governance",
        "page_subtitle": "Deterministic ESG Data Quality & Compliance Rules Catalog",
        "active_nav": "validation_rules",
        "filter_form": filter_form,
        "rules": rules_qs,
        "total_rules": total_rules,
        "active_rules": active_rules,
        "error_rules": error_rules,
        "warning_rules": warning_rules,
        "can_manage": can_manage,
    }
    return render(request, "validation/rule_list.html", context)


# -----------------------------------------------------------------------------
# 5. VALIDATION RULE DETAIL & GOVERNANCE VIEW
# -----------------------------------------------------------------------------

@login_required
def validation_rule_detail_view(request, rule_id):
    """
    Displays full details of a ValidationRule, including execution telemetry and configuration parameters.
    """
    user = request.user
    if not user_can_view_validation_rules(user):
        raise PermissionDenied("Access Denied: You do not have permission to view validation rules.")

    rule = get_object_or_404(
        ValidationRule.objects.select_related("applicable_activity", "created_by", "updated_by"),
        pk=rule_id,
    )

    recent_results = (
        ValidationResult.objects.filter(rule=rule)
        .select_related("activity_record", "validation_run")
        .order_by("-created_at")[:15]
    )

    can_manage = user_can_manage_validation_rules(user)

    context = {
        "page_title": f"Rule: {rule.code}",
        "page_subtitle": rule.name,
        "active_nav": "validation_rules",
        "rule": rule,
        "recent_results": recent_results,
        "can_manage": can_manage,
    }
    return render(request, "validation/rule_detail.html", context)


# -----------------------------------------------------------------------------
# 6. TOGGLE RULE ACTIVE STATUS (GOVERNANCE MUTATION)
# -----------------------------------------------------------------------------

@login_required
@require_POST
def validation_rule_toggle_view(request, rule_id):
    """
    Toggles the active state of a ValidationRule.
    Authorized ONLY for ESG Governance personas (ESG_MANAGER, MEIL_OPERATOR, Superuser).
    """
    user = request.user
    if not user_can_manage_validation_rules(user):
        log_auth_event(
            user=user,
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            resource_accessed=f"ValidationRule:{rule_id}:Toggle",
            details=f"Unauthorized attempt to toggle ValidationRule #{rule_id} by user {user.username}.",
            success=False,
            request=request,
        )
        raise PermissionDenied("You do not have permission to alter validation rule configurations.")

    rule = get_object_or_404(ValidationRule, pk=rule_id)
    rule.is_active = not rule.is_active
    rule.updated_by = user
    rule.save(update_fields=["is_active", "updated_by", "updated_at"])

    status_str = "Activated" if rule.is_active else "Deactivated"
    messages.success(request, f"Validation Rule [{rule.code}] successfully {status_str}.")

    log_auth_event(
        user=user,
        event_type=AuthAuditLog.EventType.VALIDATION_RULE_UPDATED,
        resource_accessed=f"ValidationRule:{rule.id}:{rule.code}",
        details=f"Rule {rule.code} {status_str} by user {user.username}.",
        success=True,
        request=request,
    )
    return redirect("core:validation_rule_list")


# -----------------------------------------------------------------------------
# 7. EDIT RULE SPECIFICATION (GOVERNANCE MUTATION)
# -----------------------------------------------------------------------------

@login_required
def validation_rule_edit_view(request, rule_id):
    """
    Allows ESG Managers to adjust description, severity, blocking status, and rule parameters.
    Code and category remain locked to prevent engine desynchronization.
    """
    user = request.user
    if not user_can_manage_validation_rules(user):
        raise PermissionDenied("You do not have permission to modify validation rule configurations.")

    rule = get_object_or_404(ValidationRule, pk=rule_id)

    if request.method == "POST":
        form = ValidationRuleForm(request.POST, instance=rule)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.version += 1
            rule.updated_by = user
            rule.save()

            messages.success(request, f"Validation Rule [{rule.code}] updated (Version {rule.version}).")
            log_auth_event(
                user=user,
                event_type=AuthAuditLog.EventType.VALIDATION_RULE_UPDATED,
                resource_accessed=f"ValidationRule:{rule.id}:{rule.code}",
                details=f"Validation rule {rule.code} modified (v{rule.version}) by user {user.username}.",
                success=True,
                request=request,
            )
            return redirect("core:validation_rule_detail", rule_id=rule.id)
    else:
        form = ValidationRuleForm(instance=rule)

    context = {
        "page_title": f"Edit Rule: {rule.code}",
        "page_subtitle": "Adjust Severity, Rationale & Operational Parameters",
        "active_nav": "validation_rules",
        "rule": rule,
        "form": form,
    }
    return render(request, "validation/rule_form.html", context)
