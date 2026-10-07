"""
URL patterns for apps.core.
Includes Phase 01 Core & UI showcase routes, Phase 02 Authentication & RBAC routes.
"""

from django.urls import path
from apps.core import (
    activity_views,
    auth_views,
    data_entry_views,
    evidence_views,
    org_views,
    period_views,
    validation_views,
    views,
)

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
    # Phase 02 & Phase 07 Role-Based Dashboards & Object-Access Verification Routes
    # -------------------------------------------------------------------------
    path("site-manager/dashboard/", auth_views.site_manager_dashboard, name="site_manager_dashboard"),
    path("dashboard/site-manager/", auth_views.site_manager_dashboard_redirect, name="site_manager_dashboard_alias"),
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

    # -------------------------------------------------------------------------
    # Phase 04 Reporting Period Management Routes (/reporting-periods/...)
    # -------------------------------------------------------------------------
    path("reporting-periods/", period_views.period_list_view, name="period_list"),
    path("reporting-periods/create/", period_views.period_create_view, name="period_create"),
    path("reporting-periods/<int:period_id>/", period_views.period_detail_view, name="period_detail"),
    path("reporting-periods/<int:period_id>/edit/", period_views.period_edit_view, name="period_edit"),
    path("reporting-periods/<int:period_id>/status/", period_views.period_status_transition_view, name="period_status_transition"),

    # -------------------------------------------------------------------------
    # Phase 05 Projects & Operational Sites Direct Routes (/projects/... & /sites/...)
    # -------------------------------------------------------------------------
    path("projects/", org_views.project_list_view, name="project_list"),
    path("projects/create/", org_views.project_create_view, name="project_create"),
    path("projects/<int:project_id>/", org_views.project_detail_view, name="project_detail"),
    path("projects/<int:project_id>/edit/", org_views.project_edit_view, name="project_edit"),
    path("projects/<int:project_id>/deactivate/", org_views.project_deactivate_view, name="project_deactivate"),
    path("sites/", org_views.site_list_view, name="site_list"),
    path("sites/create/", org_views.site_create_view, name="site_create"),
    path("sites/<int:site_id>/", org_views.site_detail_view, name="site_direct_detail"),
    path("sites/<int:site_id>/edit/", org_views.site_edit_view, name="site_edit"),
    path("sites/<int:site_id>/deactivate/", org_views.site_deactivate_view, name="site_deactivate"),

    # -------------------------------------------------------------------------
    # Phase 06 Activity Master & ESG Data Catalog Routes (/activity-master/...)
    # -------------------------------------------------------------------------
    path("activity-master/", activity_views.activity_list_view, name="activity_list"),
    path("activity-master/create/", activity_views.activity_create_view, name="activity_create"),
    path("activity-master/<int:activity_id>/", activity_views.activity_detail_view, name="activity_detail"),
    path("activity-master/<int:activity_id>/edit/", activity_views.activity_edit_view, name="activity_edit"),
    path("activity-master/<int:activity_id>/deactivate/", activity_views.activity_deactivate_view, name="activity_deactivate"),
    path("activity-master/categories/", activity_views.category_list_view, name="category_list"),
    path("activity-master/categories/create/", activity_views.category_create_view, name="category_create"),
    path("activity-master/categories/<int:category_id>/", activity_views.category_detail_view, name="category_detail"),
    path("activity-master/units/", activity_views.unit_list_view, name="unit_list"),
    path("activity-master/units/create/", activity_views.unit_create_view, name="unit_create"),

    # -------------------------------------------------------------------------
    # Phase 08 ESG Data Entry & Activity Telemetry Routes (/data-entry/...)
    # -------------------------------------------------------------------------
    path("data-entry/", data_entry_views.activity_record_list_view, name="activity_record_list"),
    path("data-entry/create/", data_entry_views.activity_record_create_view, name="activity_record_create"),
    path("data-entry/<int:record_id>/", data_entry_views.activity_record_detail_view, name="activity_record_detail"),
    path("data-entry/<int:record_id>/edit/", data_entry_views.activity_record_edit_view, name="activity_record_edit"),
    path("data-entry/<int:record_id>/delete/", data_entry_views.activity_record_delete_view, name="activity_record_delete"),
    path("data-entry/api/activity-units/", data_entry_views.activity_units_api_view, name="activity_units_api"),

    # -------------------------------------------------------------------------
    # Phase 09 Evidence Management Routes (/evidence/... & /data-entry/<id>/evidence/...)
    # -------------------------------------------------------------------------
    path("evidence/", evidence_views.evidence_list_view, name="evidence_list"),
    path("evidence/<int:evidence_id>/", evidence_views.evidence_detail_view, name="evidence_detail"),
    path("evidence/<int:evidence_id>/download/", evidence_views.evidence_download_view, name="evidence_download"),
    path("evidence/<int:evidence_id>/preview/", evidence_views.evidence_preview_view, name="evidence_preview"),
    path("evidence/<int:evidence_id>/retire/", evidence_views.evidence_retire_view, name="evidence_retire"),
    path("data-entry/<int:record_id>/evidence/upload/", evidence_views.evidence_upload_view, name="evidence_upload"),
    path("data-entry/<int:record_id>/evidence/<int:evidence_id>/delete/", evidence_views.evidence_delete_view, name="evidence_delete"),

    # -------------------------------------------------------------------------
    # Phase 10 Validation Engine Routes (/data-entry/<id>/validate/ & /validation/...)
    # -------------------------------------------------------------------------
    path("data-entry/<int:record_id>/validate/", validation_views.record_validate_view, name="activity_record_validate"),
    path("data-entry/<int:record_id>/run-validation/", validation_views.record_validate_view, name="record_validate"),
    path("data-entry/validate-batch/", validation_views.record_batch_validate_view, name="activity_record_batch_validate"),
    path("data-entry/batch-validate/", validation_views.record_batch_validate_view, name="record_batch_validate"),
    path("validation/runs/<int:run_id>/", validation_views.validation_run_detail_view, name="validation_run_detail"),
    path("validation/rules/", validation_views.validation_rule_list_view, name="validation_rule_list"),
    path("validation/rules/<int:rule_id>/", validation_views.validation_rule_detail_view, name="validation_rule_detail"),
    path("validation/rules/<int:rule_id>/toggle/", validation_views.validation_rule_toggle_view, name="validation_rule_toggle"),
    path("validation/rules/<int:rule_id>/edit/", validation_views.validation_rule_edit_view, name="validation_rule_edit"),
]


