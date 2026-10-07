"""
Organization Hierarchy and Scoped Management Views for MEIL ESG CONTROL TOWER.

Fulfills Phase 03 requirements:
- Organization Overview / Hierarchy Explorer
- Scoped Listing and Detail Views for Companies, Subsidiaries, Projects, and Sites
- Scoped Create and Edit Forms with Server-Side Scope Choice Filtering
- Safe Deactivation / Archiving Policy (preventing accidental cascade deletion)
- Server-Side Object-Level Authorization & IDOR Protection with Audit Logging
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.core.auth_services import log_auth_event
from apps.core.models import (
    AuthAuditLog,
    Company,
    OrganizationStatus,
    Project,
    ReportingPeriod,
    Role,
    Site,
    Subsidiary,
)
from apps.core.org_forms import ProjectForm, SiteForm, SubsidiaryForm
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
    get_accessible_subsidiaries,
    safe_deactivate_entity,
    user_can_access_company,
    user_can_access_project,
    user_can_access_site,
    user_can_access_subsidiary,
    user_can_manage_hierarchy,
    user_can_manage_project,
    user_can_manage_site,
    user_can_manage_subsidiary,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. HIERARCHY OVERVIEW & EXPLORER
# -----------------------------------------------------------------------------

@login_required
def org_overview(request):
    """
    Organization Hierarchy Explorer.
    Displays multi-tiered tree structure (Enterprise -> Subsidiaries -> Projects -> Sites)
    scoped by the authenticated user's authorized reach.
    """
    user = request.user
    # Site managers are restricted to their operational site screens
    if user.has_role(Role.Code.SITE_MANAGER) and not (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.SUBSIDIARY_MANAGER)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed="/organization/",
            details="Site Manager attempted to access enterprise organization hierarchy overview.",
            success=False,
        )
        raise PermissionDenied("Site Managers do not have permission to view enterprise organization management.")

    companies = get_accessible_companies(user).prefetch_related("subsidiaries")
    subsidiaries = get_accessible_subsidiaries(user).prefetch_related("projects", "projects__sites")
    projects = get_accessible_projects(user)
    sites = get_accessible_sites(user)

    can_manage = user_can_manage_hierarchy(user)

    context = {
        "page_title": "Organization Hierarchy & Scope",
        "page_subtitle": "MEIL Enterprise Structure, Operating Divisions, Infrastructure Projects & Sites",
        "active_nav": "entities",
        "companies": companies,
        "subsidiaries": subsidiaries,
        "total_companies": companies.count(),
        "total_subsidiaries": subsidiaries.count(),
        "total_projects": projects.count(),
        "total_sites": sites.count(),
        "can_manage": can_manage,
    }
    return render(request, "organization/overview.html", context)


# -----------------------------------------------------------------------------
# 2. COMPANY / ENTERPRISE VIEWS
# -----------------------------------------------------------------------------

@login_required
def company_list_view(request):
    """List accessible companies / enterprise root entities."""
    user = request.user
    if user.has_role(Role.Code.SITE_MANAGER) and not (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.SUBSIDIARY_MANAGER)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        raise PermissionDenied("Access Denied.")

    companies = get_accessible_companies(user)
    search_q = request.GET.get("q", "").strip()
    if search_q:
        companies = companies.filter(Q(name__icontains=search_q) | Q(code__icontains=search_q))

    context = {
        "page_title": "Enterprise Operating Companies",
        "page_subtitle": "Enterprise Group Entities & Holding Corporate Root",
        "active_nav": "entities",
        "companies": companies,
        "search_q": search_q,
        "can_manage": user_can_manage_hierarchy(user),
    }
    return render(request, "organization/company_list.html", context)


@login_required
def company_detail_view(request, company_id):
    """Company detail with child subsidiaries and aggregated infrastructure metrics."""
    company = get_object_or_404(Company, id=company_id)
    if not user_can_access_company(request.user, company):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Company:{company.id} ({company.code})",
            details="IDOR violation attempt on Company detail.",
            success=False,
        )
        raise PermissionDenied("Access Denied: Unassigned enterprise company scope.")

    subsidiaries = get_accessible_subsidiaries(request.user).filter(company=company)
    projects = get_accessible_projects(request.user).filter(subsidiary__company=company)
    sites = get_accessible_sites(request.user).filter(project__subsidiary__company=company)

    context = {
        "page_title": f"Company: {company.name}",
        "page_subtitle": f"Code: {company.code} | Status: {company.status} | Country: {company.country}",
        "active_nav": "entities",
        "company": company,
        "subsidiaries": subsidiaries,
        "projects_count": projects.count(),
        "sites_count": sites.count(),
        "can_manage": user_can_manage_hierarchy(request.user),
    }
    return render(request, "organization/company_detail.html", context)


# -----------------------------------------------------------------------------
# 3. SUBSIDIARY VIEWS
# -----------------------------------------------------------------------------

@login_required
def subsidiary_list_view(request):
    """List accessible subsidiary companies / divisions."""
    user = request.user
    if user.has_role(Role.Code.SITE_MANAGER) and not (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.SUBSIDIARY_MANAGER)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        raise PermissionDenied("Access Denied.")

    subsidiaries = get_accessible_subsidiaries(user)
    search_q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if search_q:
        subsidiaries = subsidiaries.filter(
            Q(name__icontains=search_q) | Q(code__icontains=search_q) | Q(industry__icontains=search_q)
        )
    if status_filter:
        subsidiaries = subsidiaries.filter(status=status_filter)

    context = {
        "page_title": "Subsidiaries & Operating Divisions",
        "page_subtitle": "Divisional Business Units Governing ESG Telemetry and Review Workflows",
        "active_nav": "entities",
        "subsidiaries": subsidiaries,
        "search_q": search_q,
        "status_filter": status_filter,
        "statuses": OrganizationStatus.choices,
        "can_create": user_can_manage_hierarchy(user),
    }
    return render(request, "organization/subsidiary_list.html", context)


@login_required
def subsidiary_detail_view(request, subsidiary_id):
    """Subsidiary detail view with projects and sites drilldown."""
    subsidiary = get_object_or_404(Subsidiary, id=subsidiary_id)
    if not user_can_access_subsidiary(request.user, subsidiary):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Subsidiary:{subsidiary.id} ({subsidiary.code})",
            details="IDOR violation attempt on Subsidiary detail.",
            success=False,
        )
        raise PermissionDenied(f"Access Denied: Unassigned subsidiary '{subsidiary.code}'.")

    projects = get_accessible_projects(request.user).filter(subsidiary=subsidiary).prefetch_related("sites")
    sites = get_accessible_sites(request.user).filter(project__subsidiary=subsidiary)

    can_edit = user_can_manage_subsidiary(request.user, subsidiary)
    can_create_project = user_can_manage_project(request.user, subsidiary=subsidiary)

    context = {
        "page_title": f"Subsidiary: {subsidiary.name}",
        "page_subtitle": f"Code: {subsidiary.code} | Enterprise: {subsidiary.company.name} | Status: {subsidiary.status}",
        "active_nav": "entities",
        "subsidiary": subsidiary,
        "projects": projects,
        "sites": sites,
        "can_edit": can_edit,
        "can_create_project": can_create_project,
    }
    return render(request, "organization/subsidiary_detail.html", context)


@login_required
def subsidiary_create_view(request):
    """Create new Subsidiary Company (MEIL_OPERATOR or Superuser only)."""
    if not user_can_manage_hierarchy(request.user):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed="/organization/subsidiaries/create/",
            details="Unauthorized attempt to create subsidiary.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to create subsidiaries.")

    if request.method == "POST":
        form = SubsidiaryForm(request.POST)
        if form.is_valid():
            sub = form.save()
            log_auth_event(
                AuthAuditLog.EventType.ORGANIZATION_CREATED,
                request=request,
                user=request.user,
                resource_accessed=f"Subsidiary:{sub.id} ({sub.code})",
                details=f"Created subsidiary '{sub.name}'.",
                success=True,
            )
            messages.success(request, f"Subsidiary '{sub.name}' created successfully.")
            return redirect("core:org_subsidiary_detail", subsidiary_id=sub.id)
    else:
        form = SubsidiaryForm()

    context = {
        "page_title": "Register Subsidiary Division",
        "page_subtitle": "Define a corporate division or operating company under MEIL Enterprise",
        "active_nav": "entities",
        "form": form,
        "is_create": True,
    }
    return render(request, "organization/subsidiary_form.html", context)


@login_required
def subsidiary_edit_view(request, subsidiary_id):
    """Edit existing Subsidiary Company."""
    subsidiary = get_object_or_404(Subsidiary, id=subsidiary_id)
    if not user_can_manage_subsidiary(request.user, subsidiary):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Subsidiary:{subsidiary.id}/edit/",
            details="Unauthorized attempt to edit subsidiary.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to edit this subsidiary.")

    if request.method == "POST":
        form = SubsidiaryForm(request.POST, instance=subsidiary)
        if form.is_valid():
            sub = form.save()
            log_auth_event(
                AuthAuditLog.EventType.ORGANIZATION_UPDATED,
                request=request,
                user=request.user,
                resource_accessed=f"Subsidiary:{sub.id} ({sub.code})",
                details=f"Updated subsidiary '{sub.name}'.",
                success=True,
            )
            messages.success(request, f"Subsidiary '{sub.name}' updated successfully.")
            return redirect("core:org_subsidiary_detail", subsidiary_id=sub.id)
    else:
        form = SubsidiaryForm(instance=subsidiary)

    context = {
        "page_title": f"Edit Subsidiary: {subsidiary.name}",
        "page_subtitle": f"Code: {subsidiary.code}",
        "active_nav": "entities",
        "form": form,
        "subsidiary": subsidiary,
        "is_create": False,
    }
    return render(request, "organization/subsidiary_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def subsidiary_deactivate_view(request, subsidiary_id):
    """Safely archive / deactivate a subsidiary without cascade hard-delete."""
    subsidiary = get_object_or_404(Subsidiary, id=subsidiary_id)
    if not user_can_manage_subsidiary(request.user, subsidiary):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Subsidiary:{subsidiary.id}/deactivate/",
            details="Unauthorized attempt to deactivate subsidiary.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to deactivate this subsidiary.")

    if request.method == "POST":
        safe_deactivate_entity(subsidiary, user=request.user, request=request)
        messages.warning(request, f"Subsidiary '{subsidiary.name}' has been archived and marked Inactive.")
        return redirect("core:org_subsidiary_list")

    context = {
        "page_title": f"Archive Subsidiary: {subsidiary.name}",
        "entity": subsidiary,
        "entity_type": "Subsidiary Division",
        "child_count": subsidiary.projects.count(),
        "child_type": "Projects",
        "cancel_url": reverse("core:org_subsidiary_detail", kwargs={"subsidiary_id": subsidiary.id}),
    }
    return render(request, "organization/confirm_deactivate.html", context)


# -----------------------------------------------------------------------------
# 4. PROJECT VIEWS
# -----------------------------------------------------------------------------

@login_required
def project_list_view(request):
    """List accessible infrastructure projects."""
    user = request.user
    projects = get_accessible_projects(user).annotate(
        annotated_sites_count=Count("sites", filter=Q(sites__status=OrganizationStatus.ACTIVE))
    )
    subsidiaries = get_accessible_subsidiaries(user)

    search_q = request.GET.get("q", "").strip()
    sub_filter = request.GET.get("subsidiary", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if search_q:
        projects = projects.filter(Q(name__icontains=search_q) | Q(code__icontains=search_q) | Q(location__icontains=search_q))
    if sub_filter:
        projects = projects.filter(subsidiary_id=sub_filter)
    if status_filter:
        projects = projects.filter(status=status_filter)

    can_create = user_can_manage_project(user)

    context = {
        "page_title": "Infrastructure Projects",
        "page_subtitle": "Engineering, EPC & Operational Projects Grouping Site Assets",
        "active_nav": "projects" if user.has_role(Role.Code.SITE_MANAGER) else "entities",
        "projects": projects,
        "subsidiaries": subsidiaries,
        "search_q": search_q,
        "sub_filter": sub_filter,
        "status_filter": status_filter,
        "statuses": OrganizationStatus.choices,
        "can_create": can_create,
    }
    return render(request, "organization/project_list.html", context)


@login_required
def project_detail_view(request, project_id):
    """Project detail with child operational sites and geographic scope."""
    project = get_object_or_404(Project, id=project_id)
    if not user_can_access_project(request.user, project):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Project:{project.id} ({project.code})",
            details="IDOR violation attempt on Project detail.",
            success=False,
        )
        raise PermissionDenied(f"Access Denied: Unassigned project '{project.code}'.")

    sites = get_accessible_sites(request.user).filter(project=project)
    can_edit = user_can_manage_project(request.user, project=project)
    can_create_site = user_can_manage_site(request.user, project=project)

    # Phase 04 Reporting Period Integration
    reporting_periods = ReportingPeriod.objects.filter(
        company=project.company
    ).filter(
        Q(subsidiary__isnull=True) | Q(subsidiary=project.subsidiary)
    ).order_by("-start_date")

    context = {
        "page_title": f"Project: {project.name}",
        "page_subtitle": f"Code: {project.code} | Division: {project.subsidiary.name} | Status: {project.status}",
        "active_nav": "projects" if request.user.has_role(Role.Code.SITE_MANAGER) else "entities",
        "project": project,
        "sites": sites,
        "reporting_periods": reporting_periods,
        "can_edit": can_edit,
        "can_create_site": can_create_site,
    }
    return render(request, "organization/project_detail.html", context)


@login_required
def project_create_view(request):
    """Create new infrastructure project within user's authorized scope."""
    if not user_can_manage_project(request.user):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed="/organization/projects/create/",
            details="Unauthorized attempt to create project.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to create projects.")

    initial = {}
    sub_id = request.GET.get("subsidiary_id")
    if sub_id:
        sub = Subsidiary.objects.filter(id=sub_id).first()
        if sub and user_can_access_subsidiary(request.user, sub):
            initial["subsidiary"] = sub

    if request.method == "POST":
        # Check submitted subsidiary against user's authorized scope
        sub_id = request.POST.get("subsidiary")
        if sub_id:
            try:
                target_sub = Subsidiary.objects.filter(id=sub_id).first()
                if target_sub and not user_can_manage_project(request.user, subsidiary=target_sub):
                    log_auth_event(
                        AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
                        request=request,
                        user=request.user,
                        resource_accessed=f"Subsidiary:{target_sub.id} ({target_sub.code})",
                        details="Attempted to create project under unauthorized subsidiary scope.",
                        success=False,
                    )
                    raise PermissionDenied("You cannot create a project under this subsidiary.")
            except (ValueError, TypeError):
                pass

        form = ProjectForm(request.POST, user=request.user)
        if form.is_valid():
            selected_sub = form.cleaned_data.get("subsidiary")
            if not user_can_manage_project(request.user, subsidiary=selected_sub):
                raise PermissionDenied("You cannot create a project under this subsidiary.")

            proj = form.save(commit=False)
            proj.created_by = request.user
            proj.updated_by = request.user
            proj.save()

            log_auth_event(
                AuthAuditLog.EventType.PROJECT_CREATED,
                request=request,
                user=request.user,
                resource_accessed=f"Project:{proj.id} ({proj.code})",
                details=f"Created project '{proj.name}'.",
                success=True,
            )
            messages.success(request, f"Project '{proj.name}' created successfully.")
            return redirect("core:org_project_detail", project_id=proj.id)
    else:
        form = ProjectForm(initial=initial, user=request.user)

    context = {
        "page_title": "Register Infrastructure Project",
        "page_subtitle": "Define a project scope under an authorized subsidiary division",
        "active_nav": "entities",
        "form": form,
        "is_create": True,
    }
    return render(request, "organization/project_form.html", context)


@login_required
def project_edit_view(request, project_id):
    """Edit existing infrastructure project."""
    project = get_object_or_404(Project, id=project_id)
    if not user_can_manage_project(request.user, project=project):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Project:{project.id}/edit/",
            details="Unauthorized attempt to edit project.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to edit this project.")

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project, user=request.user)
        if form.is_valid():
            selected_sub = form.cleaned_data.get("subsidiary")
            if not user_can_manage_project(request.user, subsidiary=selected_sub):
                raise PermissionDenied("You cannot assign project to this subsidiary.")

            proj = form.save(commit=False)
            proj.updated_by = request.user
            proj.save()

            log_auth_event(
                AuthAuditLog.EventType.PROJECT_UPDATED,
                request=request,
                user=request.user,
                resource_accessed=f"Project:{proj.id} ({proj.code})",
                details=f"Updated project '{proj.name}'.",
                success=True,
            )
            messages.success(request, f"Project '{proj.name}' updated successfully.")
            return redirect("core:org_project_detail", project_id=proj.id)
    else:
        form = ProjectForm(instance=project, user=request.user)

    context = {
        "page_title": f"Edit Project: {project.name}",
        "page_subtitle": f"Code: {project.code}",
        "active_nav": "entities",
        "form": form,
        "project": project,
        "is_create": False,
    }
    return render(request, "organization/project_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def project_deactivate_view(request, project_id):
    """Safely archive / deactivate a project."""
    project = get_object_or_404(Project, id=project_id)
    if not user_can_manage_project(request.user, project=project):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Project:{project.id}/deactivate/",
            details="Unauthorized attempt to deactivate project.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to deactivate this project.")

    if request.method == "POST":
        safe_deactivate_entity(project, user=request.user, request=request)
        messages.warning(request, f"Project '{project.name}' has been archived and marked Inactive.")
        return redirect("core:org_project_list")

    context = {
        "page_title": f"Archive Project: {project.name}",
        "entity": project,
        "entity_type": "Infrastructure Project",
        "child_count": project.sites.count(),
        "child_type": "Operational Sites",
        "cancel_url": reverse("core:org_project_detail", kwargs={"project_id": project.id}),
    }
    return render(request, "organization/confirm_deactivate.html", context)


# -----------------------------------------------------------------------------
# 5. SITE VIEWS
# -----------------------------------------------------------------------------

@login_required
def site_list_view(request):
    """List accessible operational sites."""
    user = request.user
    sites = get_accessible_sites(user)
    projects = get_accessible_projects(user)
    subsidiaries = get_accessible_subsidiaries(user)

    search_q = request.GET.get("q", "").strip()
    proj_filter = request.GET.get("project", "").strip()
    sub_filter = request.GET.get("subsidiary", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if search_q:
        sites = sites.filter(
            Q(name__icontains=search_q)
            | Q(code__icontains=search_q)
            | Q(location__icontains=search_q)
            | Q(facility_type__icontains=search_q)
        )
    if proj_filter:
        sites = sites.filter(project_id=proj_filter)
    if sub_filter:
        sites = sites.filter(project__subsidiary_id=sub_filter)
    if status_filter:
        sites = sites.filter(status=status_filter)

    can_create = user_can_manage_site(user)

    context = {
        "page_title": "Operational Sites & Facilities",
        "page_subtitle": "Primary ESG Data Collection Boundaries, Metering Points & Telemetry Hubs",
        "active_nav": "site_list" if user.has_role(Role.Code.SITE_MANAGER) else "entities",
        "sites": sites,
        "projects": projects,
        "subsidiaries": subsidiaries,
        "search_q": search_q,
        "proj_filter": proj_filter,
        "sub_filter": sub_filter,
        "status_filter": status_filter,
        "statuses": OrganizationStatus.choices,
        "can_create": can_create,
    }
    return render(request, "organization/site_list.html", context)


@login_required
def site_detail_view(request, site_id):
    """Operational site detail view with full breadcrumb hierarchy, assigned managers & metadata."""
    site = get_object_or_404(Site, id=site_id)
    if not user_can_access_site(request.user, site):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Site:{site.id} ({site.code})",
            details="IDOR violation attempt on Site detail.",
            success=False,
        )
        raise PermissionDenied(f"Access Denied: Unassigned operational site '{site.code}'.")

    can_edit = user_can_manage_site(request.user, site=site)

    # Phase 04 Reporting Period Integration
    reporting_periods = ReportingPeriod.objects.filter(
        company=site.company
    ).filter(
        Q(subsidiary__isnull=True) | Q(subsidiary=site.subsidiary)
    ).order_by("-start_date")

    # Phase 02/05 Site Manager Assignment Transparency
    assigned_managers = site.assigned_users.all().select_related("user")

    context = {
        "page_title": f"Site: {site.name}",
        "page_subtitle": f"Code: {site.code} | Project: {site.project.name} | Division: {site.project.subsidiary.name}",
        "active_nav": "site_dashboard" if request.user.has_role(Role.Code.SITE_MANAGER) else "entities",
        "site": site,
        "reporting_periods": reporting_periods,
        "assigned_managers": assigned_managers,
        "can_edit": can_edit,
    }
    return render(request, "organization/site_detail.html", context)


@login_required
def site_create_view(request):
    """Create new operational site within user's authorized scope."""
    if not user_can_manage_site(request.user):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed="/organization/sites/create/",
            details="Unauthorized attempt to create site.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to create operational sites.")

    initial = {}
    proj_id = request.GET.get("project_id")
    if proj_id:
        proj = Project.objects.filter(id=proj_id).first()
        if proj and user_can_access_project(request.user, proj):
            initial["project"] = proj

    if request.method == "POST":
        # Check submitted project against user's authorized scope
        proj_id = request.POST.get("project")
        if proj_id:
            try:
                target_proj = Project.objects.filter(id=proj_id).first()
                if target_proj and not user_can_manage_site(request.user, project=target_proj):
                    log_auth_event(
                        AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
                        request=request,
                        user=request.user,
                        resource_accessed=f"Project:{target_proj.id} ({target_proj.code})",
                        details="Attempted to create site under unauthorized project scope.",
                        success=False,
                    )
                    raise PermissionDenied("You cannot create a site under this project.")
            except (ValueError, TypeError):
                pass

        form = SiteForm(request.POST, user=request.user)
        if form.is_valid():
            selected_proj = form.cleaned_data.get("project")
            if not user_can_manage_site(request.user, project=selected_proj):
                raise PermissionDenied("You cannot create a site under this project.")

            site = form.save(commit=False)
            site.created_by = request.user
            site.updated_by = request.user
            site.save()

            log_auth_event(
                AuthAuditLog.EventType.SITE_CREATED,
                request=request,
                user=request.user,
                resource_accessed=f"Site:{site.id} ({site.code})",
                details=f"Created operational site '{site.name}'.",
                success=True,
            )
            messages.success(request, f"Operational site '{site.name}' created successfully.")
            return redirect("core:org_site_detail", site_id=site.id)
    else:
        form = SiteForm(initial=initial, user=request.user)

    context = {
        "page_title": "Register Operational Site",
        "page_subtitle": "Define a facility boundary for ESG telemetry, metering, and emissions accounting",
        "active_nav": "entities",
        "form": form,
        "is_create": True,
    }
    return render(request, "organization/site_form.html", context)


@login_required
def site_edit_view(request, site_id):
    """Edit existing operational site."""
    site = get_object_or_404(Site, id=site_id)
    if not user_can_manage_site(request.user, site=site):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Site:{site.id}/edit/",
            details="Unauthorized attempt to edit site.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to edit this site.")

    if request.method == "POST":
        form = SiteForm(request.POST, instance=site, user=request.user)
        if form.is_valid():
            selected_proj = form.cleaned_data.get("project")
            if not user_can_manage_site(request.user, project=selected_proj):
                raise PermissionDenied("You cannot assign site to this project.")

            st = form.save(commit=False)
            st.updated_by = request.user
            st.save()

            log_auth_event(
                AuthAuditLog.EventType.SITE_UPDATED,
                request=request,
                user=request.user,
                resource_accessed=f"Site:{st.id} ({st.code})",
                details=f"Updated operational site '{st.name}'.",
                success=True,
            )
            messages.success(request, f"Operational site '{st.name}' updated successfully.")
            return redirect("core:org_site_detail", site_id=st.id)
    else:
        form = SiteForm(instance=site, user=request.user)

    context = {
        "page_title": f"Edit Site: {site.name}",
        "page_subtitle": f"Code: {site.code}",
        "active_nav": "entities",
        "form": form,
        "site": site,
        "is_create": False,
    }
    return render(request, "organization/site_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def site_deactivate_view(request, site_id):
    """Safely archive / deactivate an operational site."""
    site = get_object_or_404(Site, id=site_id)
    if not user_can_manage_site(request.user, site=site):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Site:{site.id}/deactivate/",
            details="Unauthorized attempt to deactivate site.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to deactivate this site.")

    if request.method == "POST":
        safe_deactivate_entity(site, user=request.user, request=request)
        messages.warning(request, f"Operational site '{site.name}' has been archived and marked Inactive.")
        return redirect("core:org_site_list")

    context = {
        "page_title": f"Archive Operational Site: {site.name}",
        "entity": site,
        "entity_type": "Operational Site",
        "child_count": 0,
        "child_type": "Child Assets",
        "cancel_url": reverse("core:org_site_detail", kwargs={"site_id": site.id}),
    }
    return render(request, "organization/confirm_deactivate.html", context)
