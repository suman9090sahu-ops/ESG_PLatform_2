"""
URL patterns for apps.core.
Includes Phase 01 Core & UI showcase routes, Phase 02 Authentication & RBAC routes.
"""

from django.urls import path
from apps.core import auth_views, org_views, views

app_name = "core"

urlpatterns = [
    # -------------------------------------------------------------------------
    # Phase 01 Core Endpoints
    # -------------------------------------------------------------------------
    path("", views.index_view, name="index"),
    path("health/", views.health_check, name="health_check"),
    path("ui-preview/", views.ui_preview, name="ui_preview"),
    path("components/", views.components_showcase, name="components_showcase"),

    # -------------------------------------------------------------------------
    # Phase 02 Authentication Routes (/auth/...)
    # -------------------------------------------------------------------------
    path("auth/", auth_views.login_view, name="auth_root"),
    path("auth/login/", auth_views.login_view, name="login"),
    path("auth/logout/", auth_views.logout_view, name="logout"),
    path("auth/password-change/", auth_views.password_change_view, name="password_change"),
    path("auth/password-change/done/", auth_views.password_change_done_view, name="password_change_done"),
    path("auth/password-reset/", auth_views.CustomPasswordResetView.as_view(), name="password_reset"),
    path("auth/password-reset/done/", auth_views.CustomPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("auth/reset/<uidb64>/<token>/", auth_views.CustomPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("auth/reset/done/", auth_views.CustomPasswordResetCompleteView.as_view(), name="password_reset_complete"),

    # -------------------------------------------------------------------------
    # Phase 02 Role-Based Dashboards & Object-Access Verification Routes
    # -------------------------------------------------------------------------
    path("site-manager/dashboard/", auth_views.site_manager_dashboard, name="site_manager_dashboard"),
    path("site-manager/sites/<int:site_id>/", auth_views.site_detail_view, name="site_detail"),
    path("subsidiary-manager/dashboard/", auth_views.subsidiary_manager_dashboard, name="subsidiary_manager_dashboard"),
    path("subsidiary-manager/subsidiaries/<int:subsidiary_id>/", auth_views.subsidiary_detail_view, name="subsidiary_detail"),
    path("esg-manager/dashboard/", auth_views.esg_manager_dashboard, name="esg_manager_dashboard"),
    path("auditor/dashboard/", auth_views.auditor_dashboard, name="auditor_dashboard"),
    path("meil-operator/dashboard/", auth_views.meil_operator_dashboard, name="meil_operator_dashboard"),

    # -------------------------------------------------------------------------
    # Phase 03 Organization Hierarchy & Scoped Management Routes (/organization/...)
    # -------------------------------------------------------------------------
    path("organization/", org_views.org_overview, name="org_overview"),
    path("organization/companies/", org_views.company_list_view, name="org_company_list"),
    path("organization/companies/<int:company_id>/", org_views.company_detail_view, name="org_company_detail"),
    path("organization/subsidiaries/", org_views.subsidiary_list_view, name="org_subsidiary_list"),
    path("organization/subsidiaries/create/", org_views.subsidiary_create_view, name="org_subsidiary_create"),
    path("organization/subsidiaries/<int:subsidiary_id>/", org_views.subsidiary_detail_view, name="org_subsidiary_detail"),
    path("organization/subsidiaries/<int:subsidiary_id>/edit/", org_views.subsidiary_edit_view, name="org_subsidiary_edit"),
    path("organization/subsidiaries/<int:subsidiary_id>/deactivate/", org_views.subsidiary_deactivate_view, name="org_subsidiary_deactivate"),
    path("organization/projects/", org_views.project_list_view, name="org_project_list"),
    path("organization/projects/create/", org_views.project_create_view, name="org_project_create"),
    path("organization/projects/<int:project_id>/", org_views.project_detail_view, name="org_project_detail"),
    path("organization/projects/<int:project_id>/edit/", org_views.project_edit_view, name="org_project_edit"),
    path("organization/projects/<int:project_id>/deactivate/", org_views.project_deactivate_view, name="org_project_deactivate"),
    path("organization/sites/", org_views.site_list_view, name="org_site_list"),
    path("organization/sites/create/", org_views.site_create_view, name="org_site_create"),
    path("organization/sites/<int:site_id>/", org_views.site_detail_view, name="org_site_detail"),
    path("organization/sites/<int:site_id>/edit/", org_views.site_edit_view, name="org_site_edit"),
    path("organization/sites/<int:site_id>/deactivate/", org_views.site_deactivate_view, name="org_site_deactivate"),
]
