# MEIL ESG CONTROL TOWER — Route Map & Endpoint Architecture

This document tracks all active URL endpoints in **Phase 01 & Phase 02** as well as the planned route architecture for subsequent ESG business phases.

---

## Active Phase 01 & Phase 02 Endpoints

### 1. Platform & Showcase Routes

| URL Pattern | View Function | Route Name | Purpose | Method | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/` | `apps.core.views.index_view` | `core:index` | Executive ESG Control Tower Dashboard Shell | `GET` | Phase 01 |
| `/ui-preview/` | `apps.core.views.ui_preview` | `core:ui_preview` | Internal UI Design System & Reusable Components Gallery | `GET` | Phase 01 |
| `/components/` | `apps.core.views.components_showcase` | `core:components_showcase` | Preserved Phase 00 UI Showcase Endpoint | `GET` | Phase 00/01 |
| `/health/` | `apps.core.views.health_check` | `core:health_check` | Production Health Probe & Telemetry Status (JSON) | `GET` | Phase 00 |
| `/admin/` | `django.contrib.admin.site.urls` | `admin:index` | Django Enterprise Administration Console | `GET`, `POST` | Core / Phase 02 |

### 2. Authentication & Password Management Routes (`/auth/...`)

| URL Pattern | View Function | Route Name | Purpose | Method | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/auth/` | `apps.core.auth_views.login_view` | `core:auth_root` | Authentication Root (Routes to Sign In) | `GET` | Phase 02 |
| `/auth/login/` | `apps.core.auth_views.login_view` | `core:login` | Enterprise Sign In with Role-Based Redirection | `GET`, `POST` | Phase 02 |
| `/auth/logout/` | `apps.core.auth_views.logout_view` | `core:logout` | Invalidate Session & Secure Sign Out | `GET`, `POST` | Phase 02 |
| `/auth/password-change/` | `apps.core.auth_views.password_change_view` | `core:password_change` | Authenticated Password Change Form | `GET`, `POST` | Phase 02 |
| `/auth/password-change/done/` | `apps.core.auth_views.password_change_done_view` | `core:password_change_done` | Password Change Confirmation Screen | `GET` | Phase 02 |
| `/auth/password-reset/` | `apps.core.auth_views.CustomPasswordResetView` | `core:password_reset` | Password Reset Request by Email | `GET`, `POST` | Phase 02 |
| `/auth/password-reset/done/` | `apps.core.auth_views.CustomPasswordResetDoneView` | `core:password_reset_done` | Reset Email Dispatched Notice | `GET` | Phase 02 |
| `/auth/reset/<uidb64>/<token>/`| `apps.core.auth_views.CustomPasswordResetConfirmView`| `core:password_reset_confirm`| Token-Validated New Password Form | `GET`, `POST` | Phase 02 |
| `/auth/reset/done/` | `apps.core.auth_views.CustomPasswordResetCompleteView`| `core:password_reset_complete`| Password Reset Completed Screen | `GET` | Phase 02 |

### 3. Role-Based Dashboards & Object-Access Verification Routes

| URL Pattern | View Function | Route Name | Authorized Roles | Access Scope |
| :--- | :--- | :--- | :--- | :--- |
| `/site-manager/dashboard/` | `apps.core.auth_views.site_manager_dashboard` | `core:site_manager_dashboard` | `SITE_MANAGER`, `MEIL_OPERATOR` | Assigned operational sites (Phase 07 Operational Dashboard) |
| `/dashboard/site-manager/` | `apps.core.auth_views.site_manager_dashboard_redirect` | `core:site_manager_dashboard_alias` | Authenticated | Canonical alias redirecting to `/site-manager/dashboard/` |
| `/site-manager/sites/<int:site_id>/` | `apps.core.auth_views.site_detail_view` | `core:site_detail` | `SITE_MANAGER`, `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER`, `AUDITOR` | Verified object access (IDOR protected) |
| `/subsidiary-manager/dashboard/` | `apps.core.auth_views.subsidiary_manager_dashboard` | `core:subsidiary_manager_dashboard` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR` | Assigned subsidiary divisions |
| `/subsidiary-manager/subsidiaries/<int:subsidiary_id>/` | `apps.core.auth_views.subsidiary_detail_view` | `core:subsidiary_detail` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER`, `AUDITOR` | Verified subsidiary object access |
| `/esg-manager/dashboard/` | `apps.core.auth_views.esg_manager_dashboard` | `core:esg_manager_dashboard` | `ESG_MANAGER`, `MEIL_OPERATOR` | Corporate ESG & BRSR Governance |
| `/auditor/dashboard/` | `apps.core.auth_views.auditor_dashboard` | `core:auditor_dashboard` | `AUDITOR`, `MEIL_OPERATOR` | Independent assurance (Read-Only) |
| `/meil-operator/dashboard/` | `apps.core.auth_views.meil_operator_dashboard` | `core:meil_operator_dashboard` | `MEIL_OPERATOR` | Platform operations & security logs |

### 4. Organization Hierarchy & Scoped Management Routes (`/organization/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/organization/` | `apps.core.org_views.org_overview` | `core:org_overview` | `MEIL_OPERATOR`, `ESG_MANAGER`, `AUDITOR`, `SUBSIDIARY_MANAGER` | Multi-tier Hierarchy Tree Explorer | Phase 03 |
| `/organization/companies/` | `apps.core.org_views.company_list_view` | `core:org_company_list` | Scoped Roles | Enterprise Company Entities List | Phase 03 |
| `/organization/companies/<id>/` | `apps.core.org_views.company_detail_view` | `core:org_company_detail` | Scoped Roles (IDOR Protected) | Company Specification & Division Rollup | Phase 03 |
| `/organization/subsidiaries/` | `apps.core.org_views.subsidiary_list_view` | `core:org_subsidiary_list` | Scoped Roles | Subsidiaries & Divisions Registry | Phase 03 |
| `/organization/subsidiaries/create/` | `apps.core.org_views.subsidiary_create_view` | `core:org_subsidiary_create` | `MEIL_OPERATOR` | Register New Subsidiary Entity | Phase 03 |
| `/organization/subsidiaries/<id>/` | `apps.core.org_views.subsidiary_detail_view` | `core:org_subsidiary_detail` | Scoped Roles (IDOR Protected) | Division Scope, Projects & Child Sites | Phase 03 |
| `/organization/subsidiaries/<id>/edit/` | `apps.core.org_views.subsidiary_edit_view` | `core:org_subsidiary_edit` | `MEIL_OPERATOR` | Edit Subsidiary Entity Metadata | Phase 03 |
| `/organization/subsidiaries/<id>/deactivate/` | `apps.core.org_views.subsidiary_deactivate_view` | `core:org_subsidiary_deactivate` | `MEIL_OPERATOR` | Safe Archiving & Status Inactivation | Phase 03 |
| `/organization/projects/` | `apps.core.org_views.project_list_view` | `core:org_project_list` | Scoped Roles | Infrastructure Projects Registry | Phase 03 |
| `/organization/projects/create/` | `apps.core.org_views.project_create_view` | `core:org_project_create` | `MEIL_OPERATOR`, `SUBSIDIARY_MANAGER` (scoped) | Register New Infrastructure Project | Phase 03 |
| `/organization/projects/<id>/` | `apps.core.org_views.project_detail_view` | `core:org_project_detail` | Scoped Roles (IDOR Protected) | Project Metadata & Facility Boundaries | Phase 03 |
| `/organization/projects/<id>/edit/` | `apps.core.org_views.project_edit_view` | `core:org_project_edit` | `MEIL_OPERATOR`, `SUBSIDIARY_MANAGER` (scoped) | Edit Infrastructure Project | Phase 03 |
| `/organization/projects/<id>/deactivate/` | `apps.core.org_views.project_deactivate_view` | `core:org_project_deactivate` | `MEIL_OPERATOR`, `SUBSIDIARY_MANAGER` (scoped) | Safe Archiving of Project Asset | Phase 03 |
| `/organization/sites/` | `apps.core.org_views.site_list_view` | `core:org_site_list` | Scoped Roles | Operational Sites Registry | Phase 03 |
| `/organization/sites/create/` | `apps.core.org_views.site_create_view` | `core:org_site_create` | `MEIL_OPERATOR`, `SUBSIDIARY_MANAGER` (scoped) | Register Operational Site Boundary | Phase 03 |
| `/organization/sites/<id>/` | `apps.core.org_views.site_detail_view` | `core:org_site_detail` | Scoped Roles (IDOR Protected) | Site Telemetry Boundary & Lineage | Phase 03 |
| `/organization/sites/<id>/edit/` | `apps.core.org_views.site_edit_view` | `core:org_site_edit` | `MEIL_OPERATOR`, `SUBSIDIARY_MANAGER` (scoped) | Edit Operational Site Boundary | Phase 03 |
| `/organization/sites/<id>/deactivate/` | `apps.core.org_views.site_deactivate_view` | `core:org_site_deactivate` | `MEIL_OPERATOR`, `SUBSIDIARY_MANAGER` (scoped) | Safe Archiving of Operational Site | Phase 03 |

### 5. Reporting Period Management Routes (`/reporting-periods/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/reporting-periods/` | `apps.core.period_views.period_list_view` | `core:period_list` | Scoped Roles | Regulatory Cycles & Temporal Boundaries Registry | Phase 04 |
| `/reporting-periods/create/` | `apps.core.period_views.period_create_view` | `core:period_create` | `MEIL_OPERATOR`, `ESG_MANAGER` | Configure New Reporting Cycle | Phase 04 |
| `/reporting-periods/<id>/` | `apps.core.period_views.period_detail_view` | `core:period_detail` | Scoped Roles (IDOR Protected) | Temporal Boundary, Lifecycle Timeline & Lineage | Phase 04 |
| `/reporting-periods/<id>/edit/` | `apps.core.period_views.period_edit_view` | `core:period_edit` | `MEIL_OPERATOR`, `ESG_MANAGER` | Edit Period Configuration (Draft/Open/Closed) | Phase 04 |
| `/reporting-periods/<id>/status/` | `apps.core.period_views.period_status_transition_view` | `core:period_status_transition` | `MEIL_OPERATOR`, `ESG_MANAGER` | Controlled Status Lifecycle Transition (POST) | Phase 04 |

### Custom HTTP Error Handlers

| Error Code | Handler Function | Template | Status |
| :--- | :--- | :--- | :--- |
| **400** | `apps.core.views.handler400` | `templates/errors/400.html` | Bad Request |
| **403** | `apps.core.views.handler403` | `templates/errors/403.html` | Forbidden / Access Denied |
| **404** | `apps.core.views.handler404` | `templates/errors/404.html` | Page Not Found |
| **500** | `apps.core.views.handler500` | `templates/errors/500.html` | Internal Server Error |

---

## Architectural Route Map

```text
/
├── /health/                           [Active - Phase 00]
├── /ui-preview/                       [Active - Phase 01]
├── /components/                       [Active - Phase 00/01]
├── /admin/                            [Active - Phase 02]
│
├── /auth/                             [Active - Phase 02]
│   ├── /login/                        Sign In (Role-Routed)
│   ├── /logout/                       Secure Sign Out
│   ├── /password-change/              Password Change
│   └── /password-reset/               Password Reset
│
├── /site-manager/                     [Active - Phase 02]
│   ├── /dashboard/                    Operational Site Dashboard
│   └── /sites/<id>/                   Object-Level Inspection (IDOR Protected)
│
├── /subsidiary-manager/               [Active - Phase 02]
│   ├── /dashboard/                    Subsidiary Review Dashboard
│   └── /subsidiaries/<id>/            Division Projects Inspection
│
├── /esg-manager/                      [Active - Phase 02]
│   └── /dashboard/                    Corporate BRSR & GHG Consolidation Hub
│
├── /auditor/                          [Active - Phase 02]
│   └── /dashboard/                    Read-Only Independent Assurance
│
├── /meil-operator/                    [Active - Phase 02]
│   └── /dashboard/                    Operations Command & Audit Log Telemetry
│
├── /organization/                     [Active - Phase 03]
│   ├── /                              Multi-Tier Hierarchy Tree Explorer
│   ├── /companies/                    Enterprise Companies Registry
│   ├── /companies/<id>/               Company Specification & Scope
│   ├── /subsidiaries/                 Subsidiaries Registry
│   ├── /subsidiaries/create/          Register Subsidiary (MEIL_OPERATOR)
│   ├── /subsidiaries/<id>/            Division Scope & Child Projects
│   ├── /subsidiaries/<id>/edit/       Edit Division (MEIL_OPERATOR)
│   ├── /subsidiaries/<id>/deactivate/ Safe Division Archiving (MEIL_OPERATOR)
│   ├── /projects/                     Infrastructure Projects Registry
│   ├── /projects/create/              Register Project (Scoped)
│   ├── /projects/<id>/                Project Scope & Child Sites
│   ├── /projects/<id>/edit/           Edit Project (Scoped)
│   ├── /projects/<id>/deactivate/     Safe Project Archiving (Scoped)
│   ├── /sites/                        Operational Sites Registry
│   ├── /sites/create/                 Register Facility Boundary (Scoped)
│   ├── /sites/<id>/                   Site Boundary & Hierarchy Lineage
│   ├── /sites/<id>/edit/              Edit Site Boundary (Scoped)
│   └── /sites/<id>/deactivate/        Safe Site Archiving (Scoped)
│
├── /reporting-periods/                [Active - Phase 04]
│   ├── /                              Reporting Periods & Cycles Registry
│   ├── /create/                       Configure New Reporting Period (Scoped)
│   ├── /<id>/                         Temporal Boundary Specification & Status Timeline
│   ├── /<id>/edit/                    Edit Period Configuration (Scoped)
│   └── /<id>/status/                  Controlled Lifecycle Transition (POST)
│
├── /projects/                         [Active - Phase 05]
│   ├── /                              Direct Infrastructure Projects Registry
│   ├── /create/                       Register Project (Scoped)
│   ├── /<id>/                         Project Scope, Child Sites & Reporting Cycles
│   ├── /<id>/edit/                    Edit Project Specification (Scoped)
│   └── /<id>/deactivate/              Safe Project Archiving (Scoped)
│
├── /sites/                            [Active - Phase 05]
│   ├── /                              Direct Operational Sites Registry
│   ├── /create/                       Register Operational Boundary (Scoped)
│   ├── /<id>/                         Site Boundary, Assigned Managers & Reporting Cycles
│   ├── /<id>/edit/                    Edit Site Boundary (Scoped)
│   └── /<id>/deactivate/              Safe Site Archiving (Scoped)
│
### 6. ESG Activity Master Routes (`/activity-master/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/activity-master/` | `apps.core.activity_views.activity_list_view` | `core:activity_list` | Scoped Roles | Central ESG Activity Master Catalog | Phase 06 |
| `/activity-master/create/` | `apps.core.activity_views.activity_create_view` | `core:activity_create` | `MEIL_OPERATOR`, `ESG_MANAGER` | Create New Activity Master Definition | Phase 06 |
| `/activity-master/<id>/` | `apps.core.activity_views.activity_detail_view` | `core:activity_detail` | Scoped Roles | Activity Metadata, Units & Audit Lineage | Phase 06 |
| `/activity-master/<id>/edit/` | `apps.core.activity_views.activity_edit_view` | `core:activity_edit` | `MEIL_OPERATOR`, `ESG_MANAGER` | Edit Activity Master Definition | Phase 06 |
| `/activity-master/categories/` | `apps.core.activity_views.category_list_view` | `core:activity_category_list` | Scoped Roles | ESG Taxonomy Categories Registry | Phase 06 |
| `/activity-master/categories/<id>/` | `apps.core.activity_views.category_detail_view` | `core:activity_category_detail` | Scoped Roles | Category Taxonomy Details & Child Activities | Phase 06 |
| `/activity-master/units/` | `apps.core.activity_views.unit_list_view` | `core:unit_list` | Scoped Roles | Standard Physical Units of Measure Registry | Phase 06 |

### 7. ESG Data Entry & Activity Telemetry Routes (`/data-entry/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/data-entry/` | `apps.core.data_entry_views.activity_record_list_view` | `core:activity_record_list` | Scoped Roles | Scoped ESG Activity Telemetry Ledger | Phase 08 |
| `/data-entry/create/` | `apps.core.data_entry_views.activity_record_create_view` | `core:activity_record_create` | `SITE_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER` | Operational Data Entry Form (Draft / Ready) | Phase 08 |
| `/data-entry/<id>/` | `apps.core.data_entry_views.activity_record_detail_view` | `core:activity_record_detail` | Scoped Roles (IDOR Protected) | Telemetry Inspection, Lineage & Evidence Hook | Phase 08 |
| `/data-entry/<id>/edit/` | `apps.core.data_entry_views.activity_record_edit_view` | `core:activity_record_edit` | Scoped Roles (IDOR Protected) | Edit Telemetry Record (Draft / Ready States) | Phase 08 |
| `/data-entry/<id>/delete/` | `apps.core.data_entry_views.activity_record_delete_view` | `core:activity_record_delete` | Scoped Roles (IDOR Protected) | Safe Deletion of Draft Telemetry Records | Phase 08 |
| `/data-entry/api/activity-units/` | `apps.core.data_entry_views.activity_units_api_view` | `core:activity_units_api` | Authenticated | Dynamic AJAX permitted units for selected activity | Phase 08 |
### 8. Evidence Management & Audit Traceability Routes (`/evidence/...` & `/data-entry/.../evidence/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/evidence/` | `apps.core.evidence_views.evidence_list_view` | `core:evidence_list` | Scoped Roles (`SITE_MGR`, `SUB_MGR`, `OPERATOR`, `ESG_MGR`, `AUDITOR`) | Audit Evidence Repository with KPI summaries & filters | Phase 09 |
| `/evidence/<id>/` | `apps.core.evidence_views.evidence_detail_view` | `core:evidence_detail` | Scoped Roles (IDOR Protected) | Document Profile, SHA-256 Checksum, OCR/Validation & Lineage | Phase 09 |
| `/evidence/<id>/download/` | `apps.core.evidence_views.evidence_download_view` | `core:evidence_download` | Scoped Roles (IDOR Protected) | Authenticated File Download with Audit Log | Phase 09 |
| `/evidence/<id>/preview/` | `apps.core.evidence_views.evidence_preview_view` | `core:evidence_preview` | Scoped Roles (IDOR Protected) | Authenticated Inline Preview (PDF, PNG, JPEG) | Phase 09 |
| `/evidence/<id>/retire/` | `apps.core.evidence_views.evidence_retire_view` | `core:evidence_retire` | Scoped Roles (IDOR Protected) | Controlled Evidence Retirement with Audit Justification | Phase 09 |
| `/data-entry/<id>/evidence/upload/` | `apps.core.evidence_views.evidence_upload_view` | `core:evidence_upload` | `SITE_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER` (IDOR Protected) | Upload Supporting Document for Activity Record | Phase 09 |
| `/data-entry/<id>/evidence/<ev_id>/delete/` | `apps.core.evidence_views.evidence_delete_view` | `core:evidence_delete` | Scoped Roles (IDOR Protected; Draft Records Only) | Hard Deletion of Attached Evidence (Draft Records Only) | Phase 09 |

### 9. ESG Validation Engine & Quality Gate Routes (`/validation/...` & `/data-entry/.../validate/`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/data-entry/<id>/validate/` | `apps.core.validation_views.activity_record_validate_view` | `core:activity_record_validate` | Scoped Roles (POST only; IDOR Protected) | Execute Layer 1-7 Validation Engine for Record | Phase 10 |
| `/data-entry/batch-validate/` | `apps.core.validation_views.activity_record_batch_validate_view` | `core:activity_record_batch_validate` | Scoped Roles (POST only) | Batch validate unvalidated records in user scope | Phase 10 |
| `/validation/runs/<id>/` | `apps.core.validation_views.validation_run_detail_view` | `core:validation_run_detail` | Scoped Roles (`SITE_MGR`, `SUB_MGR`, `OPERATOR`, `ESG_MGR`, `AUDITOR`) | Immutable Validation Run report & granular findings | Phase 10 |
| `/validation/rules/` | `apps.core.validation_views.validation_rule_list_view` | `core:validation_rule_list` | `MEIL_OPERATOR`, `ESG_MANAGER`, `AUDITOR` (Read-only) | Governed catalog of validation rules across Layers 1-7 | Phase 10 |
| `/validation/rules/create/` | `apps.core.validation_views.validation_rule_create_view` | `core:validation_rule_create` | `MEIL_OPERATOR`, `ESG_MANAGER` | Create new deterministic validation rule definition | Phase 10 |
| `/validation/rules/<id>/` | `apps.core.validation_views.validation_rule_detail_view` | `core:validation_rule_detail` | `MEIL_OPERATOR`, `ESG_MANAGER`, `AUDITOR` (Read-only) | View rule parameters, version, and execution stats | Phase 10 |
| `/validation/rules/<id>/edit/` | `apps.core.validation_views.validation_rule_edit_view` | `core:validation_rule_edit` | `MEIL_OPERATOR`, `ESG_MANAGER` | Edit rule parameters, severity, and blocking flag | Phase 10 |
### 10. OCR Document Intelligence & Extraction Routes (`/evidence/.../ocr/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/evidence/<id>/ocr/process/` | `apps.core.ocr_views.ocr_process_view` | `core:ocr_process` | `SITE_MGR`, `SUB_MGR`, `OPERATOR`, `ESG_MGR` (IDOR Protected, POST only) | Trigger synchronous OCR run and structured field extraction | Phase 11 |
| `/evidence/<id>/ocr/status/` | `apps.core.ocr_views.ocr_status_api_view` | `core:ocr_status_api` | Scoped Roles (`SITE_MGR`, `SUB_MGR`, `OPERATOR`, `ESG_MGR`, `AUDITOR`) | Telemetry JSON status endpoint for OCR run polling | Phase 11 |
| `/evidence/<id>/ocr/runs/<run_id>/` | `apps.core.ocr_views.ocr_run_detail_view` | `core:ocr_run_detail` | Scoped Roles (`SITE_MGR`, `SUB_MGR`, `OPERATOR`, `ESG_MGR`, `AUDITOR`) | Dedicated immutable OCR Run Audit Ledger & entity inspection | Phase 11 |
| `/evidence/<id>/ocr/runs/<run_id>/retry/` | `apps.core.ocr_views.ocr_run_retry_view` | `core:ocr_run_retry` | `SITE_MGR`, `SUB_MGR`, `OPERATOR`, `ESG_MGR` (IDOR Protected, POST only) | Reprocess document creating new versioned OCRRun attempt | Phase 11 |

---

### Custom HTTP Error Handlers

| Error Code | Handler Function | Template | Status |
| :--- | :--- | :--- | :--- |
| **400** | `apps.core.views.handler400` | `templates/errors/400.html` | Bad Request |
| **403** | `apps.core.views.handler403` | `templates/errors/403.html` | Forbidden / Access Denied |
| **404** | `apps.core.views.handler404` | `templates/errors/404.html` | Page Not Found |
| **500** | `apps.core.views.handler500` | `templates/errors/500.html` | Internal Server Error |

---

## Architectural Route Map

```text
/
├── /health/                           [Active - Phase 00]
├── /ui-preview/                       [Active - Phase 01]
├── /components/                       [Active - Phase 00/01]
├── /admin/                            [Active - Phase 02]
│
├── /auth/                             [Active - Phase 02]
│   ├── /login/                        Sign In (Role-Routed)
│   ├── /logout/                       Sign Out
│   ├── /password-change/              Password Change
│   └── /password-reset/               Password Reset
│
├── /site-manager/dashboard/           [Active - Phase 07]
├── /subsidiary-manager/dashboard/     [Active - Phase 02]
├── /esg-manager/dashboard/            [Active - Phase 02]
├── /auditor/dashboard/                [Active - Phase 02]
├── /meil-operator/dashboard/          [Active - Phase 02]
│
├── /organization/                     [Active - Phase 03]
│   ├── /                              Multi-Tier Enterprise Hierarchy Explorer
│   ├── /companies/<id>/               Company Entity Profile
│   ├── /subsidiaries/                 Subsidiaries Registry
│   ├── /projects/                     Infrastructure Projects Registry
│   └── /sites/                        Operational Sites Boundary Registry
│
├── /reporting-periods/                [Active - Phase 04]
│   ├── /                              Reporting Periods & Cycles Registry
│   ├── /create/                       Configure New Reporting Period (Scoped)
│   ├── /<id>/                         Temporal Boundary Specification & Status Timeline
│   ├── /<id>/edit/                    Edit Period Configuration (Scoped)
│   └── /<id>/status/                  Controlled Lifecycle Transition (POST)
│
├── /projects/                         [Active - Phase 05]
│   ├── /                              Direct Infrastructure Projects Registry
│   ├── /create/                       Register Project (Scoped)
│   ├── /<id>/                         Project Scope, Child Sites & Reporting Cycles
│   ├── /<id>/edit/                    Edit Project Specification (Scoped)
│   └── /<id>/deactivate/              Safe Project Archiving (Scoped)
│
├── /sites/                            [Active - Phase 05]
│   ├── /                              Direct Operational Sites Registry
│   ├── /create/                       Register Operational Boundary (Scoped)
│   ├── /<id>/                         Site Boundary, Assigned Managers & Reporting Cycles
│   ├── /<id>/edit/                    Edit Site Boundary (Scoped)
│   └── /<id>/deactivate/              Safe Site Archiving (Scoped)
│
├── /activity-master/                  [Active - Phase 06]
│   ├── /                              Activity Master Catalog
│   ├── /create/                       Create Activity Definition (Scoped)
│   ├── /<id>/                         Activity Details, Scopes & Audit Trail
│   ├── /<id>/edit/                    Edit Activity Definition (Scoped)
│   ├── /categories/                   Taxonomy Categories Registry
│   └── /units/                        Standard Physical Units of Measure Registry
│
├── /data-entry/                       [Active - Phase 08]
│   ├── /                              Scoped ESG Activity Telemetry Ledger
│   ├── /create/                       Operational Data Entry (Draft / Ready)
│   ├── /<id>/                         Telemetry Detail, Audit Lineage & Evidence Hook
│   ├── /<id>/edit/                    Edit Telemetry Record (Draft / Ready States)
│   ├── /<id>/delete/                  Safe Deletion of Draft Telemetry Records
│   └── /api/activity-units/           AJAX Endpoint for Permitted Unit Options
│
├── /evidence/                         [Active - Phase 09 Evidence Management]
│   ├── /                              Audit Evidence Repository & Filter Explorer
│   ├── /<id>/                         Evidence Metadata, SHA-256 Checksum, OCR & Lineage
│   ├── /<id>/download/                Secure Authenticated Attachment Download
│   ├── /<id>/preview/                 Secure Authenticated Inline Preview (PDF, Images)
│   ├── /<id>/retire/                  Controlled Evidence Retirement with Audit Justification
│   ├── /<id>/ocr/process/             [Active - Phase 11] Synchronous OCR Execution
│   ├── /<id>/ocr/status/              [Active - Phase 11] Telemetry Status JSON API
│   ├── /<id>/ocr/runs/<run_id>/       [Active - Phase 11] Immutable OCR Run Audit Ledger
│   └── /<id>/ocr/runs/<run_id>/retry/ [Active - Phase 11] Re-run & History Preservation
│
├── /validation/                       [Active - Phase 10 Validation Engine]
│   ├── /runs/<id>/                    Immutable Validation Run Ledger & Rule Results
│   └── /rules/                        Governed Validation Rule Catalog & Configuration
│
└── /reports/                          [Planned - Phase 12+ Calculations & BRSR]
    ├── /brsr/                         SEBI BRSR Core format generator
    └── /gri/                          Global Reporting Initiative export
```
