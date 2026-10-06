"""
Authentication and Role-Based Dashboard Views for MEIL ESG CONTROL TOWER.

Includes:
- Login, Logout, Password Change, and Password Reset views
- Object-level authorization enforcement
- Audit event logging on authentication and denial events
- Role-specific dashboard placeholders with Phase 01 design tokens
"""

import logging
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.core.auth_services import (
    get_post_login_redirect_url,
    get_user_accessible_sites,
    get_user_accessible_subsidiaries,
    log_auth_event,
    role_required,
    user_can_access_site,
    user_can_access_subsidiary,
)
from apps.core.forms import (
    CustomPasswordChangeForm,
    CustomPasswordResetForm,
    CustomSetPasswordForm,
    LoginForm,
)
from apps.core.models import AuthAuditLog, Role, Site, Subsidiary

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# AUTHENTICATION: LOGIN & LOGOUT
# -----------------------------------------------------------------------------

@csrf_protect
@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Production login view.
    - Renders accessible login card.
    - Generic error messages to avoid user enumeration.
    - Inactive account detection.
    - Session rotation on successful authentication.
    - Role-based destination routing with open redirect protection.
    """
    if request.user.is_authenticated:
        return redirect(get_post_login_redirect_url(request, request.user))

    redirect_to = request.POST.get("next") or request.GET.get("next", "")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            remember_me = form.cleaned_data.get("remember_me")
            if not remember_me:
                request.session.set_expiry(0)  # Expires when browser closes
            else:
                request.session.set_expiry(28800)  # 8 hours

            log_auth_event(
                AuthAuditLog.EventType.LOGIN_SUCCESS,
                request=request,
                user=user,
                details=f"Successful login for user '{user.username}' (Primary role: {user.get_primary_role()}).",
                success=True,
            )

            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}.")
            return redirect(get_post_login_redirect_url(request, user))

        # Failed authentication
        attempted_username = request.POST.get("username", "")
        log_auth_event(
            AuthAuditLog.EventType.LOGIN_FAILURE,
            request=request,
            username_attempted=attempted_username,
            details=f"Failed login attempt for username '{attempted_username}'.",
            success=False,
        )
    else:
        form = LoginForm(request)

    context = {
        "form": form,
        "next": redirect_to,
        "auth_title": "Enterprise ESG Sign In",
        "auth_subtitle": "MEIL Control Tower & SEBI BRSR Governance Portal",
    }
    return render(request, "auth/login.html", context)


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """
    Secure logout view.
    Invalidates authenticated session and clears session cookies.
    """
    if request.user.is_authenticated:
        user = request.user
        log_auth_event(
            AuthAuditLog.EventType.LOGOUT,
            request=request,
            user=user,
            details=f"User '{user.username}' logged out.",
            success=True,
        )
        logout(request)
        messages.info(request, "You have been securely signed out of MEIL ESG Control Tower.")

    return redirect("core:login")


# -----------------------------------------------------------------------------
# PASSWORD MANAGEMENT VIEWS
# -----------------------------------------------------------------------------

@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def password_change_view(request):
    """
    Secure password change view for authenticated users.
    Validates against all Django AUTH_PASSWORD_VALIDATORS.
    """
    if request.method == "POST":
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            log_auth_event(
                AuthAuditLog.EventType.PASSWORD_CHANGE,
                request=request,
                user=request.user,
                details="Password changed successfully.",
                success=True,
            )
            messages.success(request, "Your password has been updated successfully.")
            return redirect("core:password_change_done")
    else:
        form = CustomPasswordChangeForm(user=request.user)

    context = {
        "form": form,
        "page_title": "Change Password",
        "auth_title": "Update Security Password",
        "auth_subtitle": "Ensure your new password meets MEIL enterprise complexity standards.",
    }
    return render(request, "auth/password_change.html", context)


@login_required
def password_change_done_view(request):
    """Confirmation page after successful password change."""
    return render(request, "auth/password_change_done.html")


class CustomPasswordResetView(PasswordResetView):
    """Password reset request view using Phase 01 layout."""

    form_class = CustomPasswordResetForm
    template_name = "auth/password_reset.html"
    email_template_name = "auth/password_reset_email.html"
    success_url = reverse_lazy("core:password_reset_done")

    def form_valid(self, form):
        email = form.cleaned_data.get("email", "")
        log_auth_event(
            AuthAuditLog.EventType.PASSWORD_RESET_REQUEST,
            request=self.request,
            username_attempted=email,
            details=f"Password reset requested for email '{email}'.",
            success=True,
        )
        return super().form_valid(form)


class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = "auth/password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    form_class = CustomSetPasswordForm
    template_name = "auth/password_reset_confirm.html"
    success_url = reverse_lazy("core:password_reset_complete")

    def form_valid(self, form):
        user = form.user
        log_auth_event(
            AuthAuditLog.EventType.PASSWORD_RESET_SUCCESS,
            request=self.request,
            user=user,
            details=f"Password reset completed for user '{user.username}'.",
            success=True,
        )
        return super().form_valid(form)


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "auth/password_reset_complete.html"


# -----------------------------------------------------------------------------
# ROLE DASHBOARD PLACEHOLDERS & OBJECT ACCESS ROUTES
# -----------------------------------------------------------------------------

@role_required(Role.Code.SITE_MANAGER, Role.Code.MEIL_OPERATOR)
def site_manager_dashboard(request):
    """
    Site Manager operational dashboard.
    Restricted to SITE_MANAGER and MEIL_OPERATOR.
    Displays operational sites explicitly assigned to the authenticated user.
    """
    assigned_sites = get_user_accessible_sites(request.user)
    context = {
        "page_title": "Site Manager Operational Dashboard",
        "page_subtitle": "Operational Telemetry, ESG Data Ingestion & Site Compliance",
        "active_nav": "site_dashboard",
        "assigned_sites": assigned_sites,
        "role_code": Role.Code.SITE_MANAGER,
    }
    return render(request, "dashboards/site_manager.html", context)


@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
)
def site_detail_view(request, site_id):
    """
    Object-level access verification endpoint for an Operational Site.
    Verifies user_can_access_site(request.user, site).
    Guards against Insecure Direct Object Reference (IDOR).
    """
    site = get_object_or_404(Site, id=site_id)

    if not user_can_access_site(request.user, site):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Site:{site.id} ({site.code})",
            details=f"IDOR violation: User '{request.user.username}' denied access to unassigned site '{site.name}'.",
            success=False,
        )
        raise PermissionDenied(f"Access Denied: You are not authorized to access operational site '{site.code}'.")

    context = {
        "page_title": f"Site: {site.name}",
        "page_subtitle": f"Code: {site.code} | Project: {site.project.name} | Division: {site.project.subsidiary.name}",
        "active_nav": "site_dashboard",
        "site": site,
    }
    return render(request, "dashboards/site_detail.html", context)


@role_required(Role.Code.SUBSIDIARY_MANAGER, Role.Code.MEIL_OPERATOR)
def subsidiary_manager_dashboard(request):
    """
    Subsidiary Manager review dashboard.
    Displays subsidiaries explicitly assigned to the user.
    """
    assigned_subsidiaries = get_user_accessible_subsidiaries(request.user)
    context = {
        "page_title": "Subsidiary Manager Governance Dashboard",
        "page_subtitle": "Division Data Review, Validation Anomalies & Verification Escalation",
        "active_nav": "sub_dashboard",
        "assigned_subsidiaries": assigned_subsidiaries,
        "role_code": Role.Code.SUBSIDIARY_MANAGER,
    }
    return render(request, "dashboards/subsidiary_manager.html", context)


@role_required(Role.Code.SUBSIDIARY_MANAGER, Role.Code.MEIL_OPERATOR, Role.Code.ESG_MANAGER, Role.Code.AUDITOR)
def subsidiary_detail_view(request, subsidiary_id):
    """
    Object-level access verification endpoint for a Subsidiary.
    Guards against IDOR.
    """
    subsidiary = get_object_or_404(Subsidiary, id=subsidiary_id)

    if not user_can_access_subsidiary(request.user, subsidiary):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Subsidiary:{subsidiary.id} ({subsidiary.code})",
            details=f"IDOR violation: User '{request.user.username}' denied access to unassigned subsidiary '{subsidiary.name}'.",
            success=False,
        )
        raise PermissionDenied(f"Access Denied: You are not authorized to view subsidiary '{subsidiary.code}'.")

    projects = subsidiary.projects.filter(is_active=True).prefetch_related("sites")
    context = {
        "page_title": f"Subsidiary: {subsidiary.name}",
        "page_subtitle": f"Code: {subsidiary.code} | Enterprise: {subsidiary.company.name}",
        "active_nav": "sub_dashboard",
        "subsidiary": subsidiary,
        "projects": projects,
    }
    return render(request, "dashboards/subsidiary_detail.html", context)


@role_required(Role.Code.ESG_MANAGER, Role.Code.MEIL_OPERATOR)
def esg_manager_dashboard(request):
    """
    ESG Manager Corporate Governance Dashboard.
    Scope 1, 2, 3 GHG consolidation, emission factors, and SEBI BRSR Core finalization.
    """
    context = {
        "page_title": "ESG Manager Corporate Governance Dashboard",
        "page_subtitle": "Enterprise GHG Consolidation, Emission Factors & SEBI BRSR Finalization",
        "active_nav": "esg_dashboard",
        "role_code": Role.Code.ESG_MANAGER,
    }
    return render(request, "dashboards/esg_manager.html", context)


@role_required(Role.Code.AUDITOR, Role.Code.MEIL_OPERATOR)
def auditor_dashboard(request):
    """
    Auditor Independent Assurance Dashboard.
    Read-only governed disclosures, calculation lineage, evidence inspection, and audit trail.
    """
    context = {
        "page_title": "Auditor Independent Assurance Dashboard",
        "page_subtitle": "Read-Only Governed Data, GHG Formula Lineage & Audit Trail Verification",
        "active_nav": "auditor_dashboard",
        "role_code": Role.Code.AUDITOR,
    }
    return render(request, "dashboards/auditor.html", context)


@role_required(Role.Code.MEIL_OPERATOR)
def meil_operator_dashboard(request):
    """
    MEIL Operator Control Hub.
    Operational administration, telemetry sync status, entity monitoring, and security audit log.
    """
    recent_audit_events = AuthAuditLog.objects.all().order_by("-created_at")[:10]
    context = {
        "page_title": "MEIL Operator Control Hub",
        "page_subtitle": "Operational System Control, Telemetry Pipelines & Security Audit Telemetry",
        "active_nav": "operator_dashboard",
        "recent_audit_events": recent_audit_events,
        "role_code": Role.Code.MEIL_OPERATOR,
    }
    return render(request, "dashboards/meil_operator.html", context)
