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
| `/site-manager/dashboard/` | `apps.core.auth_views.site_manager_dashboard` | `core:site_manager_dashboard` | `SITE_MANAGER`, `MEIL_OPERATOR` | Assigned operational sites |
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
├── /environmental/                    [Planned - Phase 04]
│   ├── /ghg/                          Scope 1, 2, 3 carbon accounting
│   ├── /energy/                       Renewable vs non-renewable energy
│   ├── /water/                        Withdrawal, consumption, recycling
│   └── /waste/                        Hazardous, non-hazardous, circularity
│
├── /social/                           [Planned - Phase 05]
│   ├── /workforce/                    Demographics, diversity, turnover
│   ├── /health-safety/                LTIFR, near misses, audits
│   └── /csr/                          Community projects, impact metrics
│
├── /governance/                       [Planned - Phase 06]
│   ├── /ethics-compliance/           Anti-corruption, code of conduct
│   └── /board-diversity/             Independent directors, committees
│
└── /reports/                          [Planned - Phase 07]
    ├── /brsr/                         SEBI BRSR Core format generator
    └── /gri/                          Global Reporting Initiative export
```
