"""
URL patterns for apps.core.
Includes Phase 01 Core & UI showcase routes, Phase 02 Authentication & RBAC routes.
"""

from django.urls import path
from apps.core import (
    activity_views,
    anomaly_views,
    auth_views,
    calculation_views,
    correction_views,
    data_entry_views,
    evidence_views,
    ocr_views,
    org_views,
    period_views,
    procurement_views,
    reporting_views,
    review_views,
    scope3_views,
    submission_views,
    transport_views,
    validation_views,
    views,
)

app_name = "core"

urlpatterns = [
    # -------------------------------------------------------------------------
    # Phase 01 Core Endpoints
    # -------------------------------------------------------------------------
    path("", views.landing_page_view, name="index"),
    path("landing/", views.landing_page_view, name="landing"),
    path("dashboard/", views.control_tower_dashboard, name="control_tower_dashboard"),
    path("dashboard/control-tower/", views.control_tower_dashboard, name="control_tower_dashboard_alias"),
    path("control-tower/", views.control_tower_dashboard, name="control_tower"),
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
    path("subsidiary-manager/dashboard/", review_views.subsidiary_manager_dashboard_view, name="subsidiary_manager_dashboard"),
    path("dashboard/subsidiary-manager/", auth_views.subsidiary_manager_dashboard_redirect, name="subsidiary_manager_dashboard_alias"),
    path("subsidiary-manager/subsidiaries/<int:subsidiary_id>/", auth_views.subsidiary_detail_view, name="subsidiary_detail"),
    path("esg-manager/dashboard/", auth_views.esg_manager_dashboard, name="esg_manager_dashboard"),
    path("dashboard/esg-manager/", auth_views.esg_manager_dashboard_redirect, name="esg_manager_dashboard_alias"),
    path("auditor/dashboard/", auth_views.auditor_dashboard, name="auditor_dashboard"),
    path("dashboard/auditor/", auth_views.auditor_dashboard_redirect, name="auditor_dashboard_alias"),
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

    # -------------------------------------------------------------------------
    # Phase 11 OCR Engine & Document Extraction Routes (/evidence/<id>/ocr/...)
    # -------------------------------------------------------------------------
    path("evidence/<int:evidence_id>/ocr/process/", ocr_views.evidence_ocr_process_view, name="evidence_ocr_process"),
    path("evidence/<int:evidence_id>/ocr/status/", ocr_views.evidence_ocr_status_api, name="evidence_ocr_status"),
    path("evidence/<int:evidence_id>/ocr/runs/<int:run_id>/", ocr_views.ocr_run_detail_view, name="ocr_run_detail"),
    path("evidence/<int:evidence_id>/ocr/runs/<int:run_id>/retry/", ocr_views.ocr_run_retry_view, name="ocr_run_retry"),

    # -------------------------------------------------------------------------
    # Phase 12 Activity Submission Workflow Routes (/submissions/... & /data-entry/<id>/submit/)
    # -------------------------------------------------------------------------
    path("data-entry/<int:record_id>/submit/", submission_views.activity_record_submit_view, name="activity_record_submit"),
    path("submissions/", submission_views.submission_list_view, name="submission_list"),
    path("submissions/<int:submission_id>/", submission_views.submission_detail_view, name="submission_detail"),
    path("submissions/<int:submission_id>/withdraw/", submission_views.submission_withdraw_view, name="submission_withdraw"),
    path("site-manager/submissions/", submission_views.submission_list_view, name="site_manager_submission_list"),
    path("site-manager/submissions/<int:submission_id>/", submission_views.submission_detail_view, name="site_manager_submission_detail"),

    # -------------------------------------------------------------------------
    # Phase 13 Subsidiary Manager Review Workflow Routes (/subsidiary-manager/...)
    # -------------------------------------------------------------------------
    path("subsidiary-manager/inbox/", review_views.submission_inbox_view, name="subsidiary_submission_inbox"),
    path("submissions/inbox/", review_views.submission_inbox_view, name="submission_inbox"),
    path("subsidiary-manager/submissions/", review_views.submission_inbox_view, name="subsidiary_submission_list"),
    path("subsidiary-manager/submissions/<int:submission_id>/review/", review_views.submission_review_detail_view, name="submission_review_detail"),
    path("subsidiary-manager/submissions/<int:submission_id>/verify/", review_views.submission_verify_view, name="submission_verify"),
    path("subsidiary-manager/submissions/<int:submission_id>/request-correction/", review_views.submission_request_correction_view, name="submission_request_correction"),
    path("subsidiary-manager/submissions/<int:submission_id>/explain/", review_views.submission_explain_view, name="submission_explain"),
    path("subsidiary-manager/submissions/<int:submission_id>/escalate/", review_views.submission_escalate_view, name="submission_escalate"),

    # -------------------------------------------------------------------------
    # Phase 14 Corrections, Explanations & Resubmission Routes (/corrections/...)
    # -------------------------------------------------------------------------
    path("corrections/", correction_views.correction_inbox_view, name="correction_inbox"),
    path("site-manager/corrections/", correction_views.correction_inbox_view, name="site_manager_correction_inbox"),
    path("corrections/<int:correction_id>/", correction_views.correction_detail_view, name="correction_detail"),
    path("corrections/<int:correction_id>/edit/", correction_views.correction_edit_view, name="correction_edit"),
    path("corrections/<int:correction_id>/validate/", correction_views.correction_validate_view, name="correction_validate"),
    path("corrections/<int:correction_id>/resubmit/", correction_views.correction_resubmit_view, name="correction_resubmit"),

    # -------------------------------------------------------------------------
    # Phase 15 ESG Anomaly Detection Engine Routes (/anomalies/...)
    # -------------------------------------------------------------------------
    path("anomalies/", anomaly_views.anomaly_list_view, name="anomaly_list"),
    path("anomalies/desk/", anomaly_views.anomaly_list_view, name="anomaly_desk"),
    path("anomalies/<int:anomaly_id>/", anomaly_views.anomaly_detail_view, name="anomaly_detail"),
    path("anomalies/<int:anomaly_id>/action/", anomaly_views.anomaly_review_action_view, name="anomaly_review_action"),
    path("data-entry/<int:record_id>/run-anomaly-detection/", anomaly_views.anomaly_run_detection_view, name="record_run_anomaly_detection"),

    # -------------------------------------------------------------------------
    # Phase 16 Supplier & Procurement Routes (/suppliers/... & /procurement/...)
    # -------------------------------------------------------------------------
    path("suppliers/", procurement_views.supplier_list_view, name="supplier_list"),
    path("suppliers/create/", procurement_views.supplier_create_view, name="supplier_create"),
    path("suppliers/<int:supplier_id>/", procurement_views.supplier_detail_view, name="supplier_detail"),
    path("suppliers/<int:supplier_id>/edit/", procurement_views.supplier_edit_view, name="supplier_edit"),
    path("suppliers/<int:supplier_id>/archive/", procurement_views.supplier_archive_view, name="supplier_archive"),

    # Aliases under /procurement/suppliers/
    path("procurement/suppliers/", procurement_views.supplier_list_view, name="procurement_supplier_list"),
    path("procurement/suppliers/create/", procurement_views.supplier_create_view, name="procurement_supplier_create"),
    path("procurement/suppliers/<int:supplier_id>/", procurement_views.supplier_detail_view, name="procurement_supplier_detail"),
    path("procurement/suppliers/<int:supplier_id>/edit/", procurement_views.supplier_edit_view, name="procurement_supplier_edit"),
    path("procurement/suppliers/<int:supplier_id>/archive/", procurement_views.supplier_archive_view, name="procurement_supplier_archive"),

    path("procurement/", procurement_views.procurement_list_view, name="procurement_list"),
    path("procurement/create/", procurement_views.procurement_create_view, name="procurement_create"),
    path("procurement/inbox/", procurement_views.procurement_review_inbox_view, name="procurement_review_inbox"),
    path("procurement/<int:procurement_id>/", procurement_views.procurement_detail_view, name="procurement_detail"),
    path("procurement/<int:procurement_id>/edit/", procurement_views.procurement_edit_view, name="procurement_edit"),
    path("procurement/<int:procurement_id>/delete/", procurement_views.procurement_delete_view, name="procurement_delete"),
    path("procurement/<int:procurement_id>/items/create/", procurement_views.procurement_item_create_view, name="procurement_item_create"),
    path("procurement/<int:procurement_id>/items/add/", procurement_views.procurement_item_create_view, name="procurement_item_add"),
    path("procurement/<int:procurement_id>/items/<int:item_id>/delete/", procurement_views.procurement_item_delete_view, name="procurement_item_delete"),
    path("procurement/<int:procurement_id>/evidence/upload/", procurement_views.procurement_evidence_upload_view, name="procurement_evidence_upload"),
    path("procurement/<int:procurement_id>/validate/", procurement_views.procurement_validate_view, name="procurement_validate"),
    path("procurement/<int:procurement_id>/anomalies/detect/", procurement_views.procurement_anomaly_detect_view, name="procurement_anomaly_detect"),
    path("procurement/<int:procurement_id>/submit/", procurement_views.procurement_submit_view, name="procurement_submit"),
    path("procurement/<int:procurement_id>/review/", procurement_views.procurement_review_view, name="procurement_review"),
    path("procurement/<int:procurement_id>/correction/", procurement_views.procurement_correction_view, name="procurement_correction"),
    path("procurement/<int:procurement_id>/ocr-compare/<int:evidence_id>/", procurement_views.procurement_ocr_compare_view, name="procurement_ocr_compare"),

    # -------------------------------------------------------------------------
    # Phase 17 Transport & Logistics Routes (/carriers/... /vehicles/... /transport/...)
    # -------------------------------------------------------------------------
    path("carriers/", transport_views.carrier_list_view, name="carrier_list"),
    path("carriers/create/", transport_views.carrier_create_view, name="carrier_create"),
    path("carriers/<int:carrier_id>/", transport_views.carrier_detail_view, name="carrier_detail"),
    path("carriers/<int:carrier_id>/edit/", transport_views.carrier_edit_view, name="carrier_edit"),
    path("carriers/<int:carrier_id>/archive/", transport_views.carrier_archive_view, name="carrier_archive"),

    path("vehicles/", transport_views.vehicle_list_view, name="vehicle_list"),
    path("vehicles/create/", transport_views.vehicle_create_view, name="vehicle_create"),
    path("vehicles/<int:vehicle_id>/", transport_views.vehicle_detail_view, name="vehicle_detail"),
    path("vehicles/<int:vehicle_id>/edit/", transport_views.vehicle_edit_view, name="vehicle_edit"),
    path("vehicles/<int:vehicle_id>/archive/", transport_views.vehicle_archive_view, name="vehicle_archive"),

    path("transport/", transport_views.transport_list_view, name="transport_list"),
    path("transport/create/", transport_views.transport_create_view, name="transport_create"),
    path("transport/inbox/", transport_views.transport_review_inbox_view, name="transport_review_inbox"),
    path("transport/<int:transport_id>/", transport_views.transport_detail_view, name="transport_detail"),
    path("transport/<int:transport_id>/edit/", transport_views.transport_edit_view, name="transport_edit"),
    path("transport/<int:transport_id>/delete/", transport_views.transport_delete_view, name="transport_delete"),
    path("transport/<int:transport_id>/evidence/upload/", transport_views.transport_evidence_upload_view, name="transport_evidence_upload"),
    path("transport/<int:transport_id>/validate/", transport_views.transport_validate_view, name="transport_validate"),
    path("transport/<int:transport_id>/anomalies/detect/", transport_views.transport_anomaly_detect_view, name="transport_anomaly_detect"),
    path("transport/<int:transport_id>/submit/", transport_views.transport_submit_view, name="transport_submit"),
    path("transport/<int:transport_id>/review/", transport_views.transport_review_view, name="transport_review"),
    path("transport/<int:transport_id>/correction/", transport_views.transport_correction_view, name="transport_correction"),
    path("transport/<int:transport_id>/ocr-compare/<int:evidence_id>/", transport_views.transport_ocr_compare_view, name="transport_ocr_compare"),

    # Logistics aliases
    path("logistics/", transport_views.transport_list_view, name="logistics_list"),
    path("logistics/carriers/", transport_views.carrier_list_view, name="logistics_carrier_list"),
    path("logistics/vehicles/", transport_views.vehicle_list_view, name="logistics_vehicle_list"),

    # -------------------------------------------------------------------------
    # Phase 20 Governed Reporting, Consolidation & Trace This Number Routes
    # -------------------------------------------------------------------------
    path("reports/", reporting_views.reports_overview_view, name="reports_overview"),
    path("reports/consolidation/", reporting_views.reports_overview_view, name="reports_consolidation"),
    path("reports/trace/", reporting_views.trace_selector_view, name="trace_selector"),
    path("reports/trace/<int:record_id>/", reporting_views.trace_number_view, name="trace_number_detail"),
    path("reports/trace-record/<int:record_id>/", reporting_views.trace_number_view, name="trace_record"),
    path("trace/<int:record_id>/", reporting_views.trace_number_view, name="trace_direct"),
    path("auditor/reports/", reporting_views.reports_overview_view, name="auditor_reports"),
    path("auditor/trace/", reporting_views.trace_selector_view, name="auditor_trace_selector"),
    path("auditor/trace/<int:record_id>/", reporting_views.trace_number_view, name="auditor_trace_detail"),

    # -------------------------------------------------------------------------
    # Phase 24 ESG Calculation Engine & Emission Factor Routes
    # -------------------------------------------------------------------------
    path("calculations/<int:calculation_id>/", calculation_views.calculation_detail_view, name="calculation_detail"),
    path("calculations/record/<int:record_id>/", calculation_views.calculation_record_detail_view, name="calculation_record_detail"),
    path("calculations/quality/", calculation_views.calculation_desk_view, name="calculation_desk"),
    path("calculations/desk/", calculation_views.calculation_desk_view, name="calculation_desk_alias"),
    path("calculations/recalculate/<int:record_id>/", calculation_views.recalculate_record_action_view, name="record_recalculate"),
    path("emission-factors/", calculation_views.emission_factor_list_view, name="emission_factor_list"),
    path("emission-factors/create/", calculation_views.emission_factor_create_view, name="emission_factor_create"),
    path("emission-factors/<int:factor_id>/", calculation_views.emission_factor_detail_view, name="emission_factor_detail"),
    path("emission-factors/<int:factor_id>/edit/", calculation_views.emission_factor_edit_view, name="emission_factor_edit"),

    # -------------------------------------------------------------------------
    # Phase 23 Scope 3 Value Chain Emissions Engine Routes (/scope3/...)
    # -------------------------------------------------------------------------
    path("scope3/", scope3_views.scope3_inventory_view, name="scope3_inventory"),
    path("scope3/inventory/", scope3_views.scope3_inventory_view, name="scope3_inventory_alias"),
    path("scope3/category/<int:category_number>/", scope3_views.scope3_category_detail_view, name="scope3_category_detail"),
    path("calculations/scope3/", scope3_views.scope3_inventory_view, name="scope3_calculations_alias"),
    path("auditor/scope3/", scope3_views.scope3_inventory_view, name="auditor_scope3"),
]


