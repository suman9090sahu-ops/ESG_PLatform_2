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

### 11. Activity Submission Workflow Routes (`/submissions/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/data-entry/<id>/submit/` | `apps.core.submission_views.activity_record_submit_view` | `core:activity_record_submit` | `SITE_MANAGER`, `MEIL_OPERATOR` (POST only) | Formal record submission; validates period, locks record, emits Submission #1 | Phase 12 |
| `/submissions/` | `apps.core.submission_views.submission_list_view` | `core:submission_list` | Scoped Roles (`SITE_MGR`, `SUB_MGR`, `OPERATOR`, `ESG_MGR`, `AUDITOR`) | Submission ledger filtered by status, site, and period | Phase 12 |
| `/site-manager/submissions/` | `apps.core.submission_views.submission_list_view` | `core:site_manager_submission_list` | `SITE_MANAGER`, `MEIL_OPERATOR` | Site Manager focused submission ledger | Phase 12 |
| `/submissions/<id>/` | `apps.core.submission_views.submission_detail_view` | `core:submission_detail` | Scoped Roles (IDOR Protected) | Comprehensive submission audit page with evidence, OCR, and history | Phase 12 |
| `/site-manager/submissions/<id>/` | `apps.core.submission_views.submission_detail_view` | `core:site_manager_submission_detail` | `SITE_MANAGER`, `MEIL_OPERATOR` (IDOR Protected) | Site Manager view of submission record | Phase 12 |
| `/submissions/<id>/withdraw/` | `apps.core.submission_views.submission_withdraw_view` | `core:submission_withdraw` | `SITE_MANAGER`, `MEIL_OPERATOR` (POST only) | Recall pending submission prior to reviewer action; resets record to READY | Phase 12 |

### 12. Subsidiary Manager Review Workflow Routes (`/subsidiary-manager/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/subsidiary-manager/inbox/` | `apps.core.review_views.submission_inbox_view` | `core:subsidiary_submission_inbox` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR` | Division Review Inbox for pending telemetry submissions | Phase 13 |
| `/submissions/inbox/` | `apps.core.review_views.submission_inbox_view` | `core:submission_inbox` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR` | Canonical alias for division review inbox | Phase 13 |
| `/subsidiary-manager/submissions/` | `apps.core.review_views.submission_inbox_view` | `core:subsidiary_submission_list` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR` | Filterable submissions list under division jurisdiction | Phase 13 |
| `/subsidiary-manager/submissions/<id>/review/` | `apps.core.review_views.submission_review_detail_view` | `core:submission_review_detail` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR` (IDOR Protected) | Review workspace with evidence, OCR, validation, delta ledger, and timeline | Phase 13 |
| `/subsidiary-manager/submissions/<id>/verify/` | `apps.core.review_views.submission_verify_view` | `core:submission_verify` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR` (POST only) | Verify submission; transitions Submission & Record to VERIFIED | Phase 13 |
| `/subsidiary-manager/submissions/<id>/request-correction/` | `apps.core.review_views.submission_request_correction_view` | `core:submission_request_correction` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR` (POST only) | Request revision; transitions to CORRECTION_REQUESTED, creates CorrectionRequest | Phase 13 |
| `/subsidiary-manager/submissions/<id>/explain/` | `apps.core.review_views.submission_explain_view` | `core:submission_explain` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR` (POST only) | Record operating explanation without altering telemetry data | Phase 13 |
| `/subsidiary-manager/submissions/<id>/escalate/` | `apps.core.review_views.submission_escalate_view` | `core:submission_escalate` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR` (POST only) | Escalate ambiguous telemetry to corporate ESG_MANAGER | Phase 13 |

### 13. Corrections, Explanations & Resubmission Routes (`/corrections/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/corrections/` | `apps.core.correction_views.correction_inbox_view` | `core:correction_inbox` | `SITE_MANAGER`, `MEIL_OPERATOR` | Site Manager Correction Inbox displaying active correction requests | Phase 14 |
| `/site-manager/corrections/` | `apps.core.correction_views.correction_inbox_view` | `core:site_manager_correction_inbox` | `SITE_MANAGER`, `MEIL_OPERATOR` | Canonical alias for Site Manager correction inbox | Phase 14 |
| `/corrections/<id>/` | `apps.core.correction_views.correction_detail_view` | `core:correction_detail` | Scoped Roles (IDOR Protected) | Correction detail workspace with original values, reviewer notes, and revision form | Phase 14 |
| `/corrections/<id>/edit/` | `apps.core.correction_views.correction_edit_view` | `core:correction_edit` | `SITE_MANAGER`, `MEIL_OPERATOR` (POST only) | Save operational telemetry revisions and trigger mandatory Phase 10 revalidation | Phase 14 |
| `/corrections/<id>/validate/` | `apps.core.correction_views.correction_validate_view` | `core:correction_validate` | `SITE_MANAGER`, `MEIL_OPERATOR` (POST only) | On-demand validation run against revised telemetry | Phase 14 |
| `/corrections/<id>/resubmit/` | `apps.core.correction_views.correction_resubmit_view` | `core:correction_resubmit` | `SITE_MANAGER`, `MEIL_OPERATOR` (POST only) | Authoritative resubmission; creates Submission #2+ and ActivityRevision #2+, resolves correction | Phase 14 |

### 14. ESG Anomaly Detection Engine Routes (`/anomalies/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/anomalies/` | `apps.core.anomaly_views.anomaly_list_view` | `core:anomaly_list` | `SUBSIDIARY_MANAGER`, `ESG_MANAGER`, `AUDITOR`, `MEIL_OPERATOR`, `SITE_MANAGER` | Anomaly Desk: Multi-dimensional anomaly findings, risk KPIs, and filter matrix | Phase 15 |
| `/subsidiary-manager/anomalies/` | `apps.core.anomaly_views.anomaly_list_view` | `core:anomaly_desk` | `SUBSIDIARY_MANAGER`, `ESG_MANAGER`, `AUDITOR`, `MEIL_OPERATOR` | Canonical alias for Subsidiary Manager Anomaly Desk | Phase 15 |
| `/anomalies/<id>/` | `apps.core.anomaly_views.anomaly_detail_view` | `core:anomaly_detail` | Scoped Roles (IDOR Protected) | Detailed Anomaly Audit View: Observed vs baseline, percentage deviation, explainable rationale, review action modals | Phase 15 |
| `/anomalies/<id>/action/` | `apps.core.anomaly_views.anomaly_review_action_view` | `core:anomaly_review_action` | `SUBSIDIARY_MANAGER`, `ESG_MANAGER`, `MEIL_OPERATOR` (POST only) | Execute controlled review lifecycle action (ACKNOWLEDGE, EXPLAIN, RESOLVE, DISMISS) with mandatory explanation | Phase 15 |
| `/data-entry/<id>/run-anomaly-detection/` | `apps.core.anomaly_views.anomaly_run_detection_view` | `core:record_run_anomaly_detection` | Scoped Roles (POST only) | On-demand manual anomaly evaluation trigger for an ActivityRecord | Phase 15 |

### 15. Supplier & Procurement Management Routes (`/procurement/...` & `/suppliers/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/procurement/suppliers/` | `apps.core.procurement_views.supplier_list_view` | `core:supplier_list` | Scoped Roles | Central Supplier / Vendor Master Directory | Phase 16 |
| `/suppliers/` | `apps.core.procurement_views.supplier_list_view` | `core:supplier_list_alias` | Scoped Roles | Canonical alias for Supplier Directory | Phase 16 |
| `/procurement/suppliers/create/` | `apps.core.procurement_views.supplier_create_view` | `core:supplier_create` | `MEIL_OPERATOR`, `ESG_MANAGER` | Register New Supplier / Vendor Entity | Phase 16 |
| `/procurement/suppliers/<id>/` | `apps.core.procurement_views.supplier_detail_view` | `core:supplier_detail` | Scoped Roles (IDOR Protected) | Vendor Specification, Procurement History & ESG Info | Phase 16 |
| `/procurement/suppliers/<id>/edit/` | `apps.core.procurement_views.supplier_edit_view` | `core:supplier_edit` | `MEIL_OPERATOR`, `ESG_MANAGER` | Edit Supplier Details & ESG Declaration | Phase 16 |
| `/procurement/suppliers/<id>/archive/` | `apps.core.procurement_views.supplier_archive_view` | `core:supplier_archive` | `MEIL_OPERATOR`, `ESG_MANAGER` (POST only) | Soft-Archive Supplier (Preserves historical purchases) | Phase 16 |
| `/procurement/` | `apps.core.procurement_views.procurement_list_view` | `core:procurement_list` | Scoped Roles | Commercial Procurement Transaction Ledger | Phase 16 |
| `/procurement/create/` | `apps.core.procurement_views.procurement_create_view` | `core:procurement_create` | `SITE_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER` | Create New Commercial Procurement Record | Phase 16 |
| `/procurement/<id>/` | `apps.core.procurement_views.procurement_detail_view` | `core:procurement_detail` | Scoped Roles (IDOR Protected) | Comprehensive Procurement Audit Workspace | Phase 16 |
| `/procurement/<id>/edit/` | `apps.core.procurement_views.procurement_edit_view` | `core:procurement_edit` | Scoped Roles (IDOR Protected) | Edit Procurement Record (DRAFT / CORRECTION) | Phase 16 |
| `/procurement/<id>/delete/` | `apps.core.procurement_views.procurement_delete_view` | `core:procurement_delete` | Scoped Roles (IDOR Protected; Draft Only) | Safe Deletion of Draft Commercial Records | Phase 16 |
| `/procurement/<id>/items/add/` | `apps.core.procurement_views.procurement_item_create_view` | `core:procurement_item_create` | Scoped Roles (IDOR Protected) | Add Line Item with Scope 3 Category & Units | Phase 16 |
| `/procurement/<id>/items/<item_id>/delete/` | `apps.core.procurement_views.procurement_item_delete_view` | `core:procurement_item_delete` | Scoped Roles (IDOR Protected; Draft Only) | Delete Line Item and Recalculate Total | Phase 16 |
| `/procurement/<id>/evidence/upload/` | `apps.core.procurement_views.procurement_evidence_upload_view` | `core:procurement_evidence_upload` | Scoped Roles (IDOR Protected) | Upload Supporting Invoice / PO Evidence | Phase 16 |
| `/procurement/<id>/submit/` | `apps.core.procurement_views.procurement_submit_view` | `core:procurement_submit` | Scoped Roles (IDOR Protected; POST only) | Formal Submission of Procurement Record | Phase 16 |
| `/procurement/inbox/` | `apps.core.procurement_views.procurement_review_inbox_view` | `core:procurement_inbox` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER` | Division Procurement Review Inbox | Phase 16 |
| `/procurement/<id>/review/` | `apps.core.procurement_views.procurement_review_view` | `core:procurement_review` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER` (POST only) | Review Action (VERIFY / REQUEST_CORRECTION / REJECT) | Phase 16 |
| `/procurement/<id>/correct/` | `apps.core.procurement_views.procurement_correction_view` | `core:procurement_correction` | `SITE_MANAGER`, `MEIL_OPERATOR` | Site Manager Correction & Resubmission Workspace | Phase 16 |
| `/procurement/<id>/ocr-compare/<evidence_id>/` | `apps.core.procurement_views.procurement_ocr_compare_view` | `core:procurement_ocr_compare` | Scoped Roles (IDOR Protected) | OCR Side-by-Side Reconciliation Analysis | Phase 16 |

### 16. Transport & Logistics Management Routes (`/transport/...`, `/carriers/...`, `/vehicles/...`)

| URL Pattern | View Function | Route Name | Authorized Roles | Purpose | Phase |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/carriers/` | `apps.core.transport_views.carrier_list_view` | `core:carrier_list` | Scoped Roles | Transport Carrier Master Directory | Phase 17 |
| `/carriers/create/` | `apps.core.transport_views.carrier_create_view` | `core:carrier_create` | `MEIL_OPERATOR`, `ESG_MANAGER`, `SUBSIDIARY_MANAGER` | Register New Transport Carrier Entity | Phase 17 |
| `/carriers/<id>/` | `apps.core.transport_views.carrier_detail_view` | `core:carrier_detail` | Scoped Roles (IDOR Protected) | Carrier Profile, Fleet Assets, & Trip Ledger | Phase 17 |
| `/carriers/<id>/edit/` | `apps.core.transport_views.carrier_edit_view` | `core:carrier_edit` | `MEIL_OPERATOR`, `ESG_MANAGER`, `SUBSIDIARY_MANAGER` | Edit Carrier Master Details | Phase 17 |
| `/carriers/<id>/archive/` | `apps.core.transport_views.carrier_archive_view` | `core:carrier_archive` | `MEIL_OPERATOR`, `ESG_MANAGER`, `SUBSIDIARY_MANAGER` (POST) | Soft-Archive Carrier (Preserves historical trips) | Phase 17 |
| `/vehicles/` | `apps.core.transport_views.vehicle_list_view` | `core:vehicle_list` | Scoped Roles | Vehicle & Fleet Asset Registry (Scope 1 & 3) | Phase 17 |
| `/vehicles/create/` | `apps.core.transport_views.vehicle_create_view` | `core:vehicle_create` | `MEIL_OPERATOR`, `ESG_MANAGER`, `SUBSIDIARY_MANAGER`, `SITE_MANAGER` | Register Fleet Vehicle Asset | Phase 17 |
| `/vehicles/<id>/` | `apps.core.transport_views.vehicle_detail_view` | `core:vehicle_detail` | Scoped Roles (IDOR Protected) | Vehicle Asset Profile, Payload, Fuel, & Trips | Phase 17 |
| `/vehicles/<id>/edit/` | `apps.core.transport_views.vehicle_edit_view` | `core:vehicle_edit` | Scoped Roles (IDOR Protected) | Edit Vehicle Asset Parameters | Phase 17 |
| `/vehicles/<id>/archive/` | `apps.core.transport_views.vehicle_archive_view` | `core:vehicle_archive` | Scoped Roles (IDOR Protected, POST) | Soft-Archive Vehicle (Preserves historical movements) | Phase 17 |
| `/transport/` | `apps.core.transport_views.transport_list_view` | `core:transport_list` | Scoped Roles | Authoritative Transport & Logistics Movement Ledger | Phase 17 |
| `/transport/create/` | `apps.core.transport_views.transport_create_view` | `core:transport_create` | `SITE_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER` | Record Physical Transportation Movement | Phase 17 |
| `/transport/inbox/` | `apps.core.transport_views.transport_review_inbox_view` | `core:transport_review_inbox` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER` | Subsidiary Review Desk for Transport Submissions | Phase 17 |
| `/transport/<id>/` | `apps.core.transport_views.transport_detail_view` | `core:transport_detail` | Scoped Roles (IDOR Protected) | Comprehensive Transport Movement Detail & Audit Trace | Phase 17 |
| `/transport/<id>/edit/` | `apps.core.transport_views.transport_edit_view` | `core:transport_edit` | Scoped Roles (IDOR Protected) | Edit Transport Record (DRAFT / CORRECTION_REQUESTED) | Phase 17 |
| `/transport/<id>/delete/` | `apps.core.transport_views.transport_delete_view` | `core:transport_delete` | Scoped Roles (IDOR Protected; Draft Only) | Safe Deletion of Draft Movement Record | Phase 17 |
| `/transport/<id>/evidence/upload/` | `apps.core.transport_views.transport_evidence_upload_view` | `core:transport_evidence_upload` | Scoped Roles (IDOR Protected) | Attach Lorry Receipt / Weighbridge Slip / Manifest | Phase 17 |
| `/transport/<id>/validate/` | `apps.core.transport_views.transport_validate_view` | `core:transport_validate` | Scoped Roles (IDOR Protected, POST) | Trigger On-demand Deterministic Validation | Phase 17 |
| `/transport/<id>/anomalies/detect/` | `apps.core.transport_views.transport_anomaly_detect_view` | `core:transport_anomaly_detect` | Scoped Roles (IDOR Protected, POST) | Trigger Anomaly Detection Engine (Route/Payload/Duplicates) | Phase 17 |
| `/transport/<id>/submit/` | `apps.core.transport_views.transport_submit_view` | `core:transport_submit` | Scoped Roles (IDOR Protected, POST) | Formal Submission for Subsidiary Governance Review | Phase 17 |
| `/transport/<id>/review/` | `apps.core.transport_views.transport_review_view` | `core:transport_review` | `SUBSIDIARY_MANAGER`, `MEIL_OPERATOR`, `ESG_MANAGER` (POST) | Governance Review (VERIFY / REQUEST_CORRECTION / REJECT) | Phase 17 |
| `/transport/<id>/correction/` | `apps.core.transport_views.transport_correction_view` | `core:transport_correction` | `SITE_MANAGER`, `MEIL_OPERATOR` | Site Manager Remediation & Resubmission Workspace | Phase 17 |
| `/transport/<id>/ocr-compare/<ev_id>/` | `apps.core.transport_views.transport_ocr_compare_view` | `core:transport_ocr_compare` | Scoped Roles (IDOR Protected) | Side-by-Side OCR Extraction Comparison Analysis | Phase 17 |
| `/logistics/` | `apps.core.transport_views.transport_list_view` | `core:logistics_list` | Scoped Roles | Canonical Alias for Transport Ledger | Phase 17 |
| `/logistics/carriers/` | `apps.core.transport_views.carrier_list_view` | `core:logistics_carrier_list` | Scoped Roles | Canonical Alias for Carriers Directory | Phase 17 |
| `/logistics/vehicles/` | `apps.core.transport_views.vehicle_list_view` | `core:logistics_vehicle_list` | Scoped Roles | Canonical Alias for Vehicles Registry | Phase 17 |

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
├── /subsidiary-manager/dashboard/     [Active - Phase 02 / Phase 13]
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
│   ├── /<id>/submit/                  [Active - Phase 12] Formal Activity Submission
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
├── /submissions/                      [Active - Phase 12 Formal Submission Workflow]
│   ├── /                              Submissions Ledger
│   ├── /<id>/                         Submission Audit Page & Snapshot Inspection
│   └── /<id>/withdraw/                Recall Pending Submission (POST)
│
├── /subsidiary-manager/               [Active - Phase 13 Subsidiary Review Desk]
│   ├── /inbox/                        Review Queue Filtered by Jurisdiction
│   ├── /submissions/<id>/review/      Interactive Review Workspace & Findings
│   ├── /submissions/<id>/verify/      Sign-off and Verification Decision (POST)
│   ├── /submissions/<id>/request-correction/ Request Operational Revision (POST)
│   ├── /submissions/<id>/explain/     Record Operating Explanation (POST)
│   └── /submissions/<id>/escalate/    Route Governance Ambiguity to ESG_MANAGER (POST)
│
├── /corrections/                      [Active - Phase 14 Corrections & Resubmission]
│   ├── /                              Site Manager Correction Request Inbox
│   ├── /<id>/                         Correction Workspace, Original vs Revised Values
│   ├── /<id>/edit/                    Save Revised Telemetry & Trigger Revalidation (POST)
│   ├── /<id>/validate/                On-demand Validation Re-run (POST)
│   └── /<id>/resubmit/                Authoritative Resubmission & Revision Ledger (POST)
│
├── /anomalies/                        [Active - Phase 15 Anomaly Detection Engine]
│   ├── /                              Enterprise / Division Anomaly Desk & Filtering Matrix
│   ├── /<id>/                         Detailed Anomaly Investigation & Telemetry Delta View
│   └── /<id>/action/                  Review Lifecycle Mutations (ACKNOWLEDGE, EXPLAIN, RESOLVE, DISMISS)
│
├── /procurement/                      [Active - Phase 16 Supplier & Procurement Management]
│   ├── /suppliers/                    Supplier & Vendor Directory
│   ├── /suppliers/create/             Register Supplier (MEIL_OPERATOR, ESG_MANAGER)
│   ├── /suppliers/<id>/               Supplier Specification, Purchases & ESG Notes
│   ├── /suppliers/<id>/edit/          Edit Supplier Details
│   ├── /suppliers/<id>/archive/       Soft-Archive Supplier (POST)
│   ├── /                              Commercial Procurement Transaction Ledger
│   ├── /create/                       Create Procurement Record (Scoped)
│   ├── /<id>/                         Procurement Workspace, Line Items, Evidence, OCR
│   ├── /<id>/edit/                    Edit Procurement Header
│   ├── /<id>/delete/                  Safe Deletion of Draft Records
│   ├── /<id>/items/add/               Add Procurement Line Item
│   ├── /<id>/items/<item_id>/delete/  Delete Procurement Line Item
│   ├── /<id>/evidence/upload/         Attach Supporting Invoices / POs
│   ├── /<id>/submit/                  Formal Commercial Submission (POST)
│   ├── /inbox/                        Subsidiary Review Inbox for Procurements
│   ├── /<id>/review/                  Review Action (VERIFY / REQUEST_CORRECTION / REJECT)
│   ├── /<id>/correct/                 Site Manager Remediation & Resubmission
│   └── /<id>/ocr-compare/<ev_id>/     OCR Side-by-Side Reconciliation Analysis
│
├── /carriers/                         [Active - Phase 17 Transport & Logistics Management]
│   ├── /                              Carrier Master Directory & Fleet Filter
│   ├── /create/                       Register New Carrier Partner (MEIL_OP, ESG_MGR, SUB_MGR)
│   ├── /<id>/                         Carrier Dossier, Linked Fleet & Haulage Ledger
│   ├── /<id>/edit/                    Edit Carrier Registration Details
│   └── /<id>/archive/                 Soft-Archive Carrier Master (POST)
│
├── /vehicles/                         [Active - Phase 17 Transport & Logistics Management]
│   ├── /                              Fleet Asset Catalog (Scope 1 Owned vs Scope 3 3rd-Party)
│   ├── /create/                       Register Fleet Vehicle Asset
│   ├── /<id>/                         Vehicle Asset Profile, Rated Payload & Trip History
│   ├── /<id>/edit/                    Edit Vehicle Asset Parameters
│   └── /<id>/archive/                 Soft-Archive Vehicle Asset (POST)
│
├── /transport/                        [Active - Phase 17 Transport & Logistics Management]
│   ├── /                              Movement Ledger with Filter Toolbar (Modalities, Scopes)
│   ├── /create/                       Record Transport Movement & Embedded Cargo Shipment
│   ├── /inbox/                        Subsidiary Review Inbox for Transport Submissions
│   ├── /<id>/                         Comprehensive Transport Dossier & Full Lineage
│   ├── /<id>/edit/                    Edit Movement Record (Draft / Correction States)
│   ├── /<id>/delete/                  Safe Deletion of Draft Records
│   ├── /<id>/evidence/upload/         Attach Lorry Receipt / Weighbridge Slip
│   ├── /<id>/validate/                On-demand Deterministic Validation Run (POST)
│   ├── /<id>/anomalies/detect/        Evaluate Route, Payload & Duplicate Anomalies (POST)
│   ├── /<id>/submit/                  Formal Submission for Subsidiary Review (POST)
│   ├── /<id>/review/                  Governance Decision (VERIFY / REQUEST_CORRECTION / REJECT)
│   ├── /<id>/correction/              Site Manager Remediation & Resubmission
│   └── /<id>/ocr-compare/<ev_id>/     Side-by-Side OCR Extraction Comparison Analysis
│
└── /reports/                          [Planned - Scope 3 & BRSR Calculation Phase]
    ├── /brsr/                         SEBI BRSR Core format generator
    └── /gri/                          Global Reporting Initiative export
```
