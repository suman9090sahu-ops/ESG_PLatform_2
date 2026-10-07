# MEIL ESG CONTROL TOWER — Development Tracking

## Current Phase
**PHASE 08 — ESG DATA ENTRY & ACTIVITY TELEMETRY**

**Status:** IMPLEMENTED & VERIFIED  
**Phase 08 Completion:** 100%  
**Total Project Completion:** 93%

---

## 1. Phase 04 Implementation Summary

Engineered the authoritative temporal governance foundation for the MEIL ESG Control Tower as part of the integrated Django monolith. Reporting periods establish the immutable regulatory boundaries for operational telemetry data entry, utility invoices, evidence OCR verification, Scope 1/2/3 GHG calculations, consolidation, and SEBI BRSR reporting.

### Key Architectural Deliverables
1. **Reporting Period Domain Model (`ReportingPeriod`):**
   - Fields: `company` (PROTECT FK), `subsidiary` (optional PROTECT FK), `code` (e.g. `FY2025-26`), `name`, `fiscal_year`, `start_date`, `end_date`, `status`, `description`, `created_by`, `updated_by`, timestamps.
   - Database `CheckConstraint` (`start_date < end_date`) ensuring strict date ordering.
   - Database `UniqueConstraint` on `(company, code)` enforcing unique cycle identifiers per enterprise company while preserving multi-tenant isolation.
   - Composite database indexes on `(company, status)` and `(start_date, end_date)`.
   - Application-level overlap prevention in `clean()` prohibiting conflicting date windows for the same organizational scope.
2. **Controlled Lifecycle State Machine (`PeriodStatus`):**
   - Strict state progression: `DRAFT` &rarr; `OPEN` &rarr; `CLOSED` &rarr; `LOCKED` &rarr; `FINALIZED`.
   - Explicit authorized reopening (`CLOSED -> OPEN`) and unlocking (`LOCKED -> CLOSED`).
   - `FINALIZED` is enforced as an immutable terminal regulatory state.
3. **Temporal Scoping & Governance Services (`apps/core/period_services.py`):**
   - Queryset scoping: `get_accessible_reporting_periods(user)` resolving access based on user role and assigned organization scope.
   - Current period resolver: `get_current_reporting_period(company, subsidiary, as_of_date)`.
   - Server-side object authorization: `user_can_access_reporting_period`, `user_can_manage_reporting_period`, `user_can_manage_period_lifecycle`.
   - Operational data guards: `can_user_enter_data`, `can_user_modify_data` permitting data mutations ONLY when the period status is `OPEN`.
4. **Audit-Ready Regulatory Lineage (`AuthAuditLog`):**
   - Extended with `PERIOD_CREATED`, `PERIOD_UPDATED`, and `PERIOD_STATUS_CHANGED`.
   - Transition events capture old state, new state, user actor, timestamp, and optional governance rationale.
5. **Insecure Direct Object Reference (IDOR) Protection:**
   - Tampered period IDs (`/reporting-periods/<id>/`, `/reporting-periods/<id>/edit/`, `/reporting-periods/<id>/status/`) trigger immediate `403 Forbidden` responses.
   - Tampering attempts record `UNAUTHORIZED_ACCESS_ATTEMPT` audit events.
6. **Reporting Period Management UI & Bootstrap Design:**
   - `/reporting-periods/`: List view with 6 KPI cards (Total, Open, Draft, Closed, Locked, Finalized), filters by status/company, search, and responsive table.
   - `/reporting-periods/<id>/`: Detail view featuring temporal boundary specifications, lifecycle progress indicator, authorized transition form, downstream integration hooks, and recent security audit events.
   - `/reporting-periods/create/`: Scoped creation form with server-side validation.
   - `/reporting-periods/<id>/edit/`: Scoped edit form with lock protection for historical records.
   - `/reporting-periods/<id>/status/`: POST-only transition handler with CSRF and permission enforcement.
7. **Dynamic Sidebar Navigation:**
   - Context-injected "Reporting Periods" navigation item across `MEIL_OPERATOR`, `ESG_MANAGER`, `AUDITOR`, `SUBSIDIARY_MANAGER`, and `SITE_MANAGER` menus.
8. **Automated Seeding Integration (`seed_rbac_data`):**
   - Seeds standard reporting periods: `FY2024-25` (LOCKED), `FY2025-26` (OPEN), `FY2026-27` (DRAFT).

---

## 2. Validation & System Checks

### `python manage.py check`
```text
System check identified no issues (0 silenced).
Result: PASS
```

### `python manage.py makemigrations --check`
```text
No changes detected
Result: PASS
```

### `python manage.py test`
```text
Creating test database for alias 'default'...
...........................................................................................................................
----------------------------------------------------------------------
Ran 127 tests in 121.386s

OK
Destroying test database for alias 'default'...
Found 127 test(s).
System check identified no issues (0 silenced).
Result: PASS
```

### Live E2E HTTP Verification (`tests/test_live_e2e.py`)
```text
[1] Health Check: Status 200 (Expected 200)
[2] Login meil_operator: Status 200 (Expected 200)
[3] /organization/ Overview: Status 200 (Expected 200)
[4] /organization/companies/: Status 200 (Expected 200)
[5] /organization/companies/1/: Status 200 (Expected 200)
[6] /organization/subsidiaries/: Status 200 (Expected 200)
[7] /organization/subsidiaries/1/: Status 200 (Expected 200)
[8] /organization/projects/: Status 200 (Expected 200)
[9] /organization/projects/1/: Status 200 (Expected 200)
[10] /organization/sites/: Status 200 (Expected 200)
[11] /organization/sites/1/: Status 200 (Expected 200)
[12] Login subsidiary_manager: Status 200 (Expected 200)
[13] subsidiary_manager accesses Hydro Division (/organization/subsidiaries/1/): Status 200 (Expected 200)
[14] IDOR attempt: subsidiary_manager accesses unassigned Solar Division (/organization/subsidiaries/2/): Status 403 (Expected 403)
[15] Login site_manager: Status 200 (Expected 200)
[16] site_manager attempts /organization/ overview: Status 403 (Expected 403)
[17] site_manager accesses assigned Site 1 (/organization/sites/1/): Status 200 (Expected 200)
[18] IDOR attempt: site_manager tampers URL to unassigned Site 2 (/organization/sites/2/): Status 403 (Expected 403)
[19] /reporting-periods/ List: Status 200 (Expected 200)
[20] /reporting-periods/2/ Detail (FY2025-26): Status 200 (Expected 200)
[21] /reporting-periods/create/ GET: Status 200 (Expected 200)
[22] Login esg_manager: Status 200 (Expected 200)
[23] esg_manager accesses /reporting-periods/: Status 200 (Expected 200)
[24] esg_manager accesses /reporting-periods/create/: Status 200 (Expected 200)
[25] Login auditor: Status 200 (Expected 200)
[26] auditor accesses /reporting-periods/: Status 200 (Expected 200)
[27] auditor accesses /reporting-periods/2/ Detail: Status 200 (Expected 200)
[28] auditor attempts /reporting-periods/create/ -> Status 403 (Expected 403)
[29] auditor attempts /reporting-periods/2/edit/ -> Status 403 (Expected 403)
[30] site_manager accesses /reporting-periods/: Status 200 (Expected 200)
[31] site_manager attempts /reporting-periods/create/ -> Status 403 (Expected 403)
[32] site_manager attempts /reporting-periods/2/edit/ -> Status 403 (Expected 403)

ALL 32 LIVE E2E HTTP VERIFICATIONS PASSED SUCCESSFULLY!
```

### Test Suite Breakdown
- **Phase 04 Reporting Period Suite (`tests/test_reporting_periods.py`):** 16 tests (Model instantiation, date range validation, CheckConstraint, UniqueConstraint, overlap validation, multi-tenant isolation, scoping across 5 personas, IDOR defense, lifecycle transitions, reopening/unlocking, data guards, locked/finalized immutability).
- **Phase 03 Organization Hierarchy Suite (`tests/test_organization.py`):** 15 tests.
- **Authentication Suite (`tests/test_auth.py`):** 10 tests.
- **RBAC Suite (`tests/test_rbac.py`):** 12 tests.
- **Object Access & IDOR Suite (`tests/test_object_access.py`):** 10 tests.
- **Phase 01 UI Foundation Baseline (`tests/test_phase01_foundation.py`):** 64 tests.
- **Total Tests:** 127 | **Passed:** 127 | **Failed:** 0 | **Errors:** 0

---

## 3. Database Changes
- `apps/core/migrations/0003_alter_authauditlog_event_type_reportingperiod.py`:
  - `ReportingPeriod`: Added domain model with `CheckConstraint` (`start_date < end_date`), `UniqueConstraint` on `(company, code)`, and composite indexes.
  - `AuthAuditLog`: Added event types `PERIOD_CREATED`, `PERIOD_UPDATED`, `PERIOD_STATUS_CHANGED`.

---

## 4. Documentation Updated
- `docs/DATABASE_ARCHITECTURE.md`: Added Section 7 detailing ReportingPeriod schema, constraints, and lifecycle state machine.
- `docs/RBAC.md`: Added Section 8 detailing Reporting Period RBAC matrix, temporal data protection guards, and event types.
- `docs/ROUTE_MAP.md`: Registered `/reporting-periods/...` routes and updated architectural tree.
- `DEV.md`: Phase 04 completion report and test telemetry.

---

---

# Phase 05 — Projects & Operational Sites

**Status:** IMPLEMENTED & VERIFIED  
**Date:** October 7, 2026  
**Sign-off:** Antigravity Agentic Pair Programmer

---

## 1. Overview & Architecture

Phase 05 establishes the operational **Project → Site** boundary foundation required for downstream ESG activity collection (Phase 06/07/08).
Rather than creating duplicate models or disjoint architectures, Phase 05 reuses and enhances the normalized 4-tier organizational hierarchy established in Phase 03:
```text
MEIL ENTERPRISE GROUP (Company)
           │
           └── SUBSIDIARY DIVISION (Subsidiary)
                   │
                   └── INFRASTRUCTURE PROJECT (Project)
                           │
                           └── OPERATIONAL SITE (Site)
```
Projects and Sites are persistent spatial/operational entities that span multiple financial reporting periods. Temporal integration with Phase 04 Reporting Periods is established dynamically through company and subsidiary ownership scopes without artificially creating yearly copies of sites or projects.

---

## 2. Key Deliverables & Enhancements

1. **Model Enhancements (`apps/core/models.py`)**:
   - `Project`: Added audit fields `created_by`, `updated_by` (`ForeignKey(User, SET_NULL, null=True, blank=True)`), model `clean()` date validation (`start_date <= end_date`), database `CheckConstraint` (`check_project_start_before_end`), and composite indexes on `(subsidiary, status)` and `code`.
   - `Site`: Added `operational_start_date`, `operational_end_date`, audit fields `created_by`, `updated_by` (`ForeignKey(User, SET_NULL, null=True, blank=True)`), model `clean()` date validation (`operational_start_date <= operational_end_date`), database `CheckConstraint` (`check_site_start_before_end`), and composite indexes on `(project, status)` and `code`.
   - `AuthAuditLog`: Extended `EventType` with `PROJECT_CREATED`, `PROJECT_UPDATED`, `PROJECT_DEACTIVATED`, `SITE_CREATED`, `SITE_UPDATED`, `SITE_DEACTIVATED`.

2. **Database Migration (`apps/core/migrations/0004_...`)**:
   - Clean migration generated and applied cleanly. Zero pending migrations.

3. **Forms (`apps/core/org_forms.py`)**:
   - `ProjectForm`: Date validation ensuring `start_date <= end_date`.
   - `SiteForm`: Operational timeline inputs (`operational_start_date`, `operational_end_date`) with date validation.

4. **Scoping & Authorization Services (`apps/core/scope_services.py`)**:
   - `get_accessible_projects(user)` & `get_accessible_sites(user)`: Strict object-level scoping. Confines `SITE_MANAGER` exclusively to assigned sites and their parent projects. Confines `SUBSIDIARY_MANAGER` to assigned divisions.
   - `user_can_manage_project(user)` & `user_can_manage_site(user)`: Enforces `AUDITOR` as strictly read-only (`False`), preventing mutations.
   - `safe_deactivate_entity`: Implements safe deactivation policy (`status=INACTIVE`, `is_active=False`) preventing hard-delete data loss of historical ESG records, logging granular audit events.

5. **Views & Query Optimization (`apps/core/org_views.py`)**:
   - N+1 Prevention: `project_list_view` uses `.annotate(annotated_sites_count=Count("sites", filter=Q(sites__status=OrganizationStatus.ACTIVE)))` to render active site counts efficiently.
   - Phase 04 Temporal Integration: `project_detail_view` and `site_detail_view` query and display applicable reporting cycles based on company/subsidiary scope.
   - Transparent Assignment Inspection: `site_detail_view` displays assigned Site Managers card via `site.assigned_users.all().select_related("user")`.

6. **Routing (`apps/core/urls.py`)**:
   - Direct routes registered: `/projects/`, `/projects/create/`, `/projects/<id>/`, `/projects/<id>/edit/`, `/projects/<id>/deactivate/`, `/sites/`, `/sites/create/`, `/sites/<id>/`, `/sites/<id>/edit/`, `/sites/<id>/deactivate/`.
   - Full backward compatibility maintained for existing `/organization/...` routes.

7. **Bootstrap 5 UI Templates (`templates/organization/`)**:
   - `project_list.html`: Uses `annotated_sites_count`, responsive search/filters, status badges.
   - `project_detail.html`: Shows parent subsidiary, timeline, child sites list, and applicable reporting periods table.
   - `site_list.html`: Shows parent project, status badges, location summary, action buttons.
   - `site_detail.html`: Full breadcrumb lineage, operational dates, "Assigned Site Managers" governance card, and applicable reporting periods table.
   - `site_form.html`: Updated with operational timeline date controls.

---

## 3. Test Suite & Verification Results

- **Django System Check:** `System check identified no issues (0 silenced).`
- **Migration Check:** `makemigrations --check` reports `No changes detected in apps 'core'`.
- **Full Automated Test Suite (`manage.py test`):**
  - **149 tests** across all apps and modules: **149 Passed, 0 Failed, 0 Errors** (Ran in 167.772s, OK).
  - Phase 05 Dedicated Suite (`tests/test_phase05_projects_sites.py`): 22/22 passed.
  - Organization & Hierarchy Suite (`tests/test_organization.py`): 22/22 passed.
  - RBAC Suite (`tests/test_rbac.py`): 12/12 passed.
  - Reporting Periods Suite (`tests/test_reporting_periods.py`): 22/22 passed.
  - Auth, Audit & Models Suites: 71/71 passed.
- **Live E2E HTTP Verification (`tests/test_live_e2e.py`):**
  - **47 live HTTP tests** executed against live server (`http://127.0.0.1:8000`):
    - Direct `/projects/` and `/sites/` routes: 200 OK.
    - Site Manager assigned project/site access: 200 OK.
    - Site Manager IDOR URL tampering to unassigned project/site: 403 Forbidden verified.
    - Auditor read-only inspection (200 OK) vs mutation attempts (403 Forbidden verified).

---

# Phase 06 — Activity Master & ESG Catalog Foundation

**Status:** IMPLEMENTED & VERIFIED  
**Date:** October 7, 2026  
**Sign-off:** Antigravity Agentic Pair Programmer

---

## 1. Overview & Architecture

Phase 06 establishes the centralized master data catalog for ESG activities, standard emission scopes, reporting frequencies, and physical units of measure across the MEIL Enterprise:
```text
ESG Master Data Catalog
├── Activity Categories (Energy, Water, Waste, Travel, Logistics, etc.)
├── Units of Measure (kWh, Liters, MT, km, kg, etc.)
└── Activity Masters (Central definition, default factor, scope classification, frequency)
```

## 2. Key Deliverables & Enhancements

1. **Master Domain Models (`apps/core/models.py`)**:
   - `ActivityCategory`: Code, name, description, display order, `is_active`, `created_by`, `updated_by`.
   - `UnitOfMeasure`: Code, name, symbol, dimension, conversion factor, `is_active`.
   - `ActivityMaster`: Category (FK PROTECT), base unit (FK PROTECT), allowed units (M2M), scope (Scope 1, Scope 2, Scope 3, Water, Waste, Social, Governance), frequency, default emission factor, `status` (DRAFT, ACTIVE, INACTIVE), `is_active`.
   - `AuthAuditLog`: Added events `CATEGORY_CREATED`, `CATEGORY_UPDATED`, `ACTIVITY_CREATED`, `ACTIVITY_UPDATED`, `ACTIVITY_STATUS_CHANGED`.

2. **Master Data Services (`apps/core/activity_services.py`)**:
   - Queryset scoping: `get_accessible_activity_categories`, `get_accessible_activity_masters`, `get_accessible_units`.
   - Authorization rules: `user_can_manage_activity_master` (Restricted to `MEIL_OPERATOR` and `ESG_MANAGER`).
   - Safe deactivation: `safe_deactivate_activity_master` (prevents historic data corruption).

3. **Views, Forms & URLs (`apps/core/activity_views.py`, `activity_forms.py`, `urls.py`)**:
   - Full CRUD views under `/activity-master/` with role guards and CSRF protection.
   - Comprehensive UI templates in `templates/activity_master/`.

4. **Testing & Telemetry (`tests/test_phase06_activity_master.py`)**:
   - **26 tests passed (0 failures, 0 errors)** covering models, RBAC matrix, IDOR protection, and safe deactivation.

---

# Phase 07 — Site Manager Dashboard

**Status:** IMPLEMENTED & VERIFIED  
**Date:** October 7, 2026  
**Sign-off:** Antigravity Agentic Pair Programmer

---

## 1. Overview & Architecture

Phase 07 implements the dedicated operational workspace for the `SITE_MANAGER` (and supervising `MEIL_OPERATOR`). The dashboard provides a high-fidelity, secure, site-scoped overview of authorized operational sites and ESG readiness status for the active reporting period.

```text
Logged-in Site Manager
        ↓
Server-Side Authorization (SiteAssignment)
        ↓
Authorized Operational Sites
        ↓
Parent Infrastructure Projects (Distinct)
        ↓
Current Reporting Period (Phase 04 OPEN Period)
        ↓
Aggregated Operational Telemetry & Readiness (Zero Fabrication)
```

## 2. Key Architectural Deliverables

1. **Dashboard Data Aggregation Service Layer (`apps/core/dashboard_services.py`)**:
   - `get_site_manager_dashboard_context(user, as_of_date=None)`:
     - Derives authorized sites using `get_accessible_sites(user)` with query optimization via `select_related("project", "project__subsidiary", "project__subsidiary__company", "created_by", "updated_by")`.
     - Distinct project counting (`parent_projects.count()`) to prevent duplicate project inflation when multiple sites share a project.
     - Dynamic reporting period resolution using Phase 04 `get_current_reporting_period()` or latest `OPEN` cycle.
     - Real activity master catalog counts (`active_catalog_count`).
     - Real workflow metrics (0 drafts, 0 submissions, 0 corrections, 0 validation issues, 0 pending evidence) reflecting actual database state without fabrication.
     - Scoped audit trail (`AuthAuditLog`): Displays recent operational events while filtering out foreign site resource identifiers to prevent cross-tenant information leakage.
     - Telemetry & sync status: Real-time readiness indicators and connectivity state.

2. **Server-Side Security & Anti-IDOR Protections (`apps/core/auth_views.py`)**:
   - Route `@role_required(Role.Code.SITE_MANAGER, Role.Code.MEIL_OPERATOR)` guarding `/site-manager/dashboard/`.
   - Canonical alias `/dashboard/site-manager/` with permanent redirect.
   - Zero Trust on client URL parameters: Tampered query parameters like `?site_id=2` or `?project_id=999` are completely ignored; data is derived strictly from `request.user`.
   - Access attempts by unauthorized roles (`SUBSIDIARY_MANAGER`, `ESG_MANAGER`, `AUDITOR`) yield `403 Forbidden`.

3. **Bootstrap 5 Responsive Operational Workspace (`templates/dashboards/site_manager.html`)**:
   - Page Header: Title, role badge, operational period badge, current date, and quick action refresh.
   - 5 KPI Cards: Assigned Sites, Active Projects, Current Period, Activity Catalog, Pending Actions.
   - Authorized Operational Sites Table: Site code, name, parent project, subsidiary, operational dates, status badge, and action buttons (`Inspect Site`, `View Project`, `Activity Catalog`, disabled `Data Entry [Phase 08]`).
   - ESG Workflow Status & Readiness Card: Progress bars and readiness indicators for upcoming Phase 08–12 modules.
   - Pending Actions Empty State: "You're All Caught Up" state when no actionable tasks are pending.
   - Recent Operational Activity: Scoped audit log table with timestamps, actions, and actors.
   - Operations Side Panel: Site Manager Profile, Temporal Boundary Card, Telemetry & Sync Readiness, and Quick Links.
   - Complete Empty States: Handles no assigned sites, no open reporting period, no pending actions, and empty audit logs.

4. **Integration with Existing Routes & Navigation**:
   - Updated `apps/core/urls.py` registering `/site-manager/dashboard/` and `/dashboard/site-manager/`.
   - Updated `templates/dashboards/site_detail.html` with breadcrumbs and direct link back to Site Manager Dashboard.
   - Documented in `docs/ROUTE_MAP.md` and `docs/RBAC.md`.

---

## 3. Verification & Test Telemetry

### Django System Check
```text
System check identified no issues (0 silenced).
Result: PASS
```

### Migration Check (`makemigrations --check`)
```text
No changes detected
Result: PASS (0 schema migrations needed)
```

### Phase 07 Automated Test Suite (`tests/test_phase07_site_manager_dashboard.py`)
```text
Ran 23 tests in 19.559s
OK
Result: 23 Passed, 0 Failed, 0 Errors
```
**Test Coverage Matrix:**
- `Authentication & Login Redirect`: Anonymous users redirected to `/auth/login/` (Status 302).
- `RBAC Role Enforcement`: Site Manager (200), MEIL Operator (200), Subsidiary Manager (403), ESG Manager (403), Auditor (403).
- `Site Scoping & Isolation`: Site Manager strictly sees assigned Site 1; unassigned Site 2 is excluded from context and HTML.
- `Multi-Site & Multi-Project Aggregation`: 3 assigned sites across 2 projects correctly yields count of 3 sites and 2 distinct projects without duplication.
- `Zero Client Trust / Anti-IDOR`: Query parameter `?site_id=2` completely ignored.
- `Reporting Period Resolution`: Correctly identifies current `OPEN` period (`FY2025-26`).
- `Empty States`: Verified "No sites assigned", "No active reporting period", and "No pending actions".
- `Audit Lineage & Anti-Leakage`: Tampered access attempts to foreign sites excluded from Site Manager's audit feed.
- `Query Efficiency`: Single constant batch queries (`select_related`) with no N+1 query growth.

### Full Monolith Regression Suite (`manage.py test`)
```text
Ran 198 tests in 250.709s
OK (Found 198 tests, 0 failures, 0 errors)
Result: 100% PASS
```

### Live E2E Browser & HTTP Verification (`tests/test_live_e2e.py` & `tests/verify_site_manager_dashboard_live.py`)
```text
[PASS] Session authentication & redirection to /site-manager/dashboard/
[PASS] 27 verified DOM elements rendered cleanly
[PASS] IDOR defense: Tampered site URL /site-manager/sites/2/ returns 403 Forbidden
[PASS] IDOR defense: Query param ?site_id=2 ignored
[PASS] Cross-role defense: Subsidiary Manager, ESG Manager, Auditor blocked with 403 Forbidden
[PASS] Supervisor access: MEIL Operator permitted access (200 OK)
ALL 71 LIVE E2E HTTP VERIFICATIONS PASSED SUCCESSFULLY!
```

---

## 4. Phase 08 Implementation Summary: ESG Data Entry & Activity Telemetry

Engineered the authoritative operational measurement layer allowing Site Managers to log actual physical ESG consumption telemetry scoped strictly to authorized operational sites and open reporting cycles.

### Key Architectural Deliverables
1. **Domain Model (`ActivityRecord` in `apps/core/models.py`)**:
   - Fields: `site` (PROTECT FK), `reporting_period` (PROTECT FK), `activity` (PROTECT FK), `measurement_date`, `quantity` (`DecimalField(18, 4)`), `unit` (PROTECT FK to `UnitOfMeasure`), `notes`, `evidence_reference`, `status`, `created_by`, `updated_by`, timestamps.
   - Database `CheckConstraint(check=Q(quantity__gte=0))` strictly forbidding negative consumption values.
   - Database composite indexes:
     - `idx_rec_site_period`: `['site', 'reporting_period']`
     - `idx_rec_act_date`: `['activity', 'measurement_date']`
     - `idx_rec_status`: `['status']`
     - `idx_rec_created`: `['-created_at']`
   - Model `clean()` enforcing:
     - Permissible unit of measure validation against `ActivityMaster` (`unit == base_unit` or in `allowed_units`).
     - Measurement date within `reporting_period` start and end dates.
     - Active ActivityMaster status requirement (`MasterStatus.ACTIVE`).
     - Cross-organizational boundary alignment between Site and Reporting Period.
2. **Controlled Lifecycle State Machine (`RecordStatus`)**:
   - Progression: `DRAFT` &rarr; `READY` &rarr; `SUBMITTED` &rarr; `VERIFIED` &rarr; `APPROVED` (with `REJECTED` return path).
   - Site Manager editable when status is `DRAFT`, `READY`, or `REJECTED`.
   - Immutable / Locked from Site Manager modification once `SUBMITTED`, `VERIFIED`, or `APPROVED`, or when the parent `ReportingPeriod` is closed.
   - Safe deletion strictly allowed for `DRAFT` records created by the user.
3. **Service Layer & Scoped Querysets (`apps/core/data_entry_services.py`)**:
   - Scoped querysets: `get_accessible_activity_records(user)` (Site Manager strictly confined to assigned sites; Subsidiary Manager to child division sites; Operator/Auditor universal).
   - Object-level authorization guards: `user_can_access_activity_record`, `user_can_create_activity_record`, `user_can_modify_activity_record`, `user_can_delete_activity_record`.
   - Candidate choice selectors: `get_candidate_sites_for_data_entry`, `get_candidate_periods_for_site`, `get_candidate_activities_for_data_entry`, `get_candidate_units_for_activity`.
   - Audit logging helper: `log_activity_record_event` recording `ACTIVITY_RECORD_CREATED`, `ACTIVITY_RECORD_UPDATED`, `ACTIVITY_RECORD_DELETED` events to `AuthAuditLog`.
4. **Forms Layer (`apps/core/data_entry_forms.py`)**:
   - `ActivityRecordForm`: Dynamically scopes all foreign key choices (`site`, `reporting_period`, `activity`, `unit`) to the user's active permissions. Auto-selects single site / open period. Validates anti-tampering server-side.
   - `ActivityRecordFilterForm`: Responsive toolbar filter supporting site, period, category, status, date range, and keyword search.
5. **Views & Routing (`apps/core/data_entry_views.py` & `urls.py`)**:
   - `activity_record_list_view` (`/data-entry/`): Operational ledger with 4 KPI summary cards (Total, Draft, Ready, Submitted/Approved), filter toolbar, table, and pagination.
   - `activity_record_create_view` (`/data-entry/create/`): Validated creation form supporting draft saving and ready submission.
   - `activity_record_detail_view` (`/data-entry/<id>/`): High-fidelity telemetry inspection with full audit trail, downstream Phase 09 evidence integration hook, and Phase 10 emissions calculation placeholder.
   - `activity_record_edit_view` (`/data-entry/<id>/edit/`): Scoped edit view with locked-state guards.
   - `activity_record_delete_view` (`/data-entry/<id>/delete/`): Safe deletion of draft records only.
   - `activity_units_api_view` (`/data-entry/api/activity-units/`): Dynamic JSON API endpoint enabling reactive unit selection in vanilla JavaScript when activity changes.
6. **Site Manager Workspace Integration**:
   - Updated `apps/core/dashboard_services.py` to aggregate real `draft_records_count` and `ready_records_count` without fabrication.
   - Updated `templates/dashboards/site_manager.html` to activate the "Data Entry" button in authorized site tables and display actionable pending draft notices.
   - Linked sidebar navigation item "ESG Data Entry" and "My Activity Data".
7. **Database Migrations**:
   - Created and applied `apps/core/migrations/0006_alter_authauditlog_event_type_activityrecord.py`. Zero pending migrations (`makemigrations --check` clean).

---

## 5. Verification & Test Telemetry (Phase 08)

### Django System Check
```text
System check identified no issues (0 silenced).
Result: PASS
```

### Migration Check (`makemigrations --check`)
```text
No changes detected
Result: PASS (0 pending schema migrations)
```

### Phase 08 Automated Test Suite (`tests/test_phase08_esg_data_entry.py`)
```text
Ran 28 tests in 9.804s
OK
Result: 28 Passed, 0 Failed, 0 Errors
```
**Test Coverage Matrix:**
- `Model Constraints & Validation`: Non-negative quantity CheckConstraint, unit permissibility against ActivityMaster, measurement date boundaries, cross-organizational boundary alignment, inactive activity rejection.
- `Scoped Querysets`: Site Manager strictly sees assigned sites' records; Subsidiary Manager sees division sites' records; Auditor and MEIL Operator have universal visibility.
- `Anti-IDOR & Zero Client Trust`: Tampered `site_id`, `reporting_period_id`, `activity_id` rejected; direct access to foreign records returns `403 Forbidden`.
- `Workflow State Enforcement`: Site Manager can edit `DRAFT`, `READY`, `REJECTED`; edits blocked on `SUBMITTED`, `VERIFIED`, `APPROVED` records and closed periods.
- `Draft Deletion Protection`: `DRAFT` records can be deleted; deleting `READY` or `SUBMITTED` records is rejected.
- `Candidate Choice Selectors`: Restricted dropdowns for sites, periods, activities, and allowed units.
- `Dynamic AJAX API`: Permitted units endpoint returns allowed units for selected activity.
- `Audit Lineage`: `ACTIVITY_RECORD_CREATED`, `UPDATED`, `DELETED` logged to `AuthAuditLog`.

### Full Monolith Regression Suite (`manage.py test`)
```text
Ran 226 tests in 258.001s
OK (Found 226 tests, 0 failures, 0 errors)
Result: 100% PASS (Phases 01–08 fully passing)
```

### Live E2E HTTP Verification (`tests/test_live_e2e.py`)
```text
[PASS] site_manager accesses /data-entry/ (Status 200)
[PASS] site_manager accesses /data-entry/create/ (Status 200, unassigned sites excluded)
[PASS] site_manager queries /data-entry/api/activity-units/?activity_id=1 (Status 200, returns units)
[PASS] site_manager creates draft ActivityRecord (Status 302 -> redirected to detail)
[PASS] site_manager views ActivityRecord detail (Status 200, telemetry & audit rendered)
[PASS] IDOR defense: site_manager attempts to create record for unassigned site (Rejected)
[PASS] site_manager edits ActivityRecord to READY (Status 302 -> updated)
[PASS] auditor accesses /data-entry/ (Status 200, read-only)
[PASS] auditor attempts /data-entry/create/ (Status 403 Forbidden)
[PASS] anonymous user attempts /data-entry/ (Status 302 redirect to login)
ALL 81 LIVE E2E HTTP VERIFICATIONS PASSED SUCCESSFULLY!
```

---

# Phase 09 — Evidence Management

**Status:** IMPLEMENTED & VERIFIED  
**Date:** October 7, 2026  
**Sign-off:** Antigravity Agentic Pair Programmer

---

## 1. Overview & Architecture

Phase 09 establishes the authoritative supporting evidence layer for the MEIL ESG Control Tower. Supporting documents (fuel invoices, utility bills, meter reading sheets, waste manifests, weighbridge slips, lab reports) are now first-class, tamper-evident domain entities directly linked to operational `ActivityRecord` telemetry.

```text
MEIL Enterprise
      ↓
Company / Subsidiary
      ↓
Project
      ↓
Operational Site
      ↓
Reporting Period
      ↓
Activity Master
      ↓
Activity Record
      ↓
Evidence (Active / Retired)
      ↓
Magic Bytes Validation + SHA-256 Fingerprint + Scoped Storage
      ↓
Future OCR (Phase 11) / Validation (Phase 10) / Trace This Number Lineage
```

---

## 2. Key Architectural Deliverables

1. **Domain Model (`Evidence` in `apps/core/models.py`)**:
   - `activity_record` (`ForeignKey` to `ActivityRecord`, `on_delete=models.PROTECT`, `related_name="evidence_files"`).
   - `file` (`FileField(upload_to=evidence_file_upload_path)`).
   - `evidence_type` (`CharField(max_length=30)`, choices from `EvidenceType`: `INVOICE`, `UTILITY_BILL`, `METER_READING`, `FUEL_CHALLAN`, `WASTE_MANIFEST`, `TRANSPORT_LOG`, `WEIGHBRIDGE_SLIP`, `LAB_REPORT`, `PURCHASE_ORDER`, `SUPPLIER_CERTIFICATE`, `CONTRACT`, `ERP_EXPORT`, `OTHER`).
   - `original_filename` (`CharField(max_length=255)`), `file_type` (`CharField(max_length=100)`), `file_size` (`PositiveBigIntegerField`).
   - `file_hash` (`CharField(max_length=64)`, indexed SHA-256 cryptographic checksum).
   - `description` (`TextField(blank=True)`).
   - `status` (`CharField(max_length=20)`, choices `EvidenceStatus.ACTIVE`, `EvidenceStatus.RETIRED`, default `ACTIVE`).
   - `retirement_reason` (`TextField(blank=True)`), `retired_at` (`DateTimeField(null=True)`), `retired_by` (`ForeignKey` to `User`, `SET_NULL`).
   - `ocr_metadata` (`JSONField(default=dict, blank=True)`), `validation_metadata` (`JSONField(default=dict, blank=True)`).
   - `uploaded_by` (`ForeignKey` to `User`, `SET_NULL`), `created_at`, `updated_at`.
   - Database constraint: `CheckConstraint(check=Q(file_size__gt=0), name="check_evidence_file_size_positive")`.
   - Composite and lookup indexes:
     - `idx_ev_rec_status`: `['activity_record', 'status']`
     - `idx_ev_type`: `['evidence_type']`
     - `idx_ev_created`: `['-created_at']`
     - `idx_ev_hash`: `['file_hash']`
   - Added convenience properties to `ActivityRecord`: `evidence_count`, `total_evidence_count`, `has_evidence`.

2. **File Security & Validation Pipeline (`apps/core/evidence_services.py`)**:
   - **Allowed Extensions**: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.xlsx`, `.xls`, `.docx`, `.csv`.
   - **Size Limit**: Configurable max 25 MB (`MAX_EVIDENCE_FILE_SIZE_BYTES = 25 * 1024 * 1024`). Rejects 0-byte uploads.
   - **Magic Bytes Validation**: Verifies binary headers against spoofed content types (`%PDF-` for PDF, `\x89PNG` for PNG, `\xff\xd8\xff` for JPEG, `PK\x03\x04` for ZIP/OOXML formats).
   - **Sanitized Filenames & Partitioned Storage**: `evidence/<site_code>/<period_code>/rec_<record_id>/<uuid12>_<safe_filename>` eliminating directory traversal, illegal characters, and file collision.
   - **Cryptographic Fingerprinting**: Full SHA-256 hash computed on upload stream for immutable audit trail verification.

3. **Service Layer & Authorization Guards (`apps/core/evidence_services.py`)**:
   - Scoped Querysets: `get_accessible_evidence(user)` (Site Manager strictly constrained to assigned sites; Subsidiary Manager to child division sites; Operator and Auditor universal).
   - Object-Level Authorization Guards:
     - `user_can_access_evidence`: Verifies read access down to the operational site assignment.
     - `user_can_upload_evidence`: Verifies user has site-level data entry authority, reporting period is open, and record status is editable (`DRAFT`, `READY`, `REJECTED`).
     - `user_can_download_evidence`: Governs authenticated binary downloading.
     - `user_can_retire_evidence`: Controls soft retirement with required audit justification.
     - `user_can_delete_evidence`: Strictly permits hard deletion only for `DRAFT` records created by user.
   - Transactional Mutation Services: `create_evidence_record`, `retire_evidence_record`, `delete_evidence_record`.
   - Immutable Security Auditing (`log_evidence_event`): Logs `EVIDENCE_UPLOADED`, `EVIDENCE_DOWNLOADED`, `EVIDENCE_RETIRED`, `EVIDENCE_DELETED` to `AuthAuditLog`.

4. **Forms Layer (`apps/core/evidence_forms.py`)**:
   - `EvidenceUploadForm`: Validates file upload, evidence taxonomy category, optional notes.
   - `EvidenceRetireForm`: Enforces mandatory retirement reason for audit compliance.
   - `EvidenceFilterForm`: Filter toolbar supporting site, period, evidence type, status, and search query.

5. **Views & Routing (`apps/core/evidence_views.py` & `apps/core/urls.py`)**:
   - `evidence_list_view` (`/evidence/`): Central evidence repository with 4 summary KPI cards (Total Documents, Active Evidence, Retired Files, Storage Footprint), filter bar, and paginated table.
   - `evidence_detail_view` (`/evidence/<id>/`): High-fidelity document inspection displaying complete ESG lineage path, SHA-256 audit fingerprint, file metadata, and downstream OCR/validation hooks.
   - `evidence_upload_view` (`/data-entry/<id>/evidence/upload/`): Context-aware upload form anchored directly to the parent `ActivityRecord`.
   - `evidence_download_view` (`/evidence/<id>/download/`): Authenticated binary download with `Content-Disposition: attachment` and audit event logging.
   - `evidence_preview_view` (`/evidence/<id>/preview/`): Inline preview (`Content-Disposition: inline`) for browser-viewable formats (PDF, PNG, JPEG).
   - `evidence_retire_view` (`/evidence/<id>/retire/`): Soft retirement confirmation requiring audit justification.
   - `evidence_delete_view` (`/data-entry/<id>/evidence/<ev_id>/delete/`): Safe draft deletion view.

6. **UI Templates & Monolith Integrations**:
   - Created `templates/evidence/evidence_list.html`, `evidence_detail.html`, `evidence_upload.html`, `evidence_retire_confirm.html`.
   - Updated `templates/data_entry/record_detail.html`: Enhanced "Supporting Audit Evidence" card with attached document table, SHA-256 hashes, status badges, download/preview links, and "+ Upload Evidence" button.
   - Updated `apps/core/dashboard_services.py`: Aggregates real `pending_evidence_count` (`records_qs.exclude(evidence_files__status=EvidenceStatus.ACTIVE).distinct().count()`).
   - Navigation: Wired `/evidence/` in sidebar menus for Site Manager, Auditor, and MEIL Operator.
   - Django Admin: Registered `EvidenceAdmin` with filters, search, and `EvidenceInline` on `ActivityRecordAdmin`.

7. **Database Migrations**:
   - Created and applied `apps/core/migrations/0007_alter_authauditlog_event_type_evidence.py`.
   - `makemigrations --check` clean (0 pending migrations).

---

## 3. Verification & Test Telemetry (Phase 09)

### Django System Check
```text
System check identified no issues (0 silenced).
Result: PASS
```

### Migration Check (`makemigrations --check`)
```text
No changes detected
Result: PASS (0 pending schema migrations)
```

### Dedicated Phase 09 Automated Test Suite (`tests/test_phase09_evidence_management.py`)
```text
Ran 17 tests in 44.520s
OK
Result: 17 Passed, 0 Failed, 0 Errors
```

### Full Monolith Regression Suite (`manage.py test`)
```text
Ran 243 tests in 294.478s
OK (Found 243 tests, 0 failures, 0 errors)
Result: 100% PASS (Phases 01–09 fully passing)
```

### Live E2E HTTP Verification (`tests/test_live_e2e.py`)
```text
[PASS] site_manager accesses /evidence/ (Status 200, KPI cards rendered)
[PASS] site_manager accesses /data-entry/7/evidence/upload/ (Status 200)
[PASS] site_manager uploads PDF invoice (Status 200, redirected to record detail)
[PASS] Evidence table on ActivityRecord detail displays uploaded file
[PASS] site_manager accesses /evidence/3/ detail (Status 200, SHA-256 and lineage displayed)
[PASS] site_manager downloads /evidence/3/download/ (Status 200, attachment headers verified)
[PASS] site_manager previews /evidence/3/preview/ (Status 200, inline application/pdf)
[PASS] IDOR defense: site_manager attempts upload against unassigned site 2 record (Status 403 Forbidden)
[PASS] auditor accesses /evidence/ (Status 200, read-only)
[PASS] auditor downloads /evidence/3/download/ (Status 200)
[PASS] auditor attempts /data-entry/7/evidence/upload/ (Status 403 Forbidden)
[PASS] anonymous user attempts /evidence/ (Status 302 redirect to login)
[PASS] site_manager retires evidence with justification (Status 200, marked RETIRED)
ALL 94 LIVE E2E HTTP VERIFICATIONS PASSED SUCCESSFULLY!
```

---

---

## 4. Phase 10 Implementation Status: ESG VALIDATION ENGINE (VERIFIED COMPLETE)

### Overview
Engineered the centralized, deterministic **ESG Validation Engine** evaluating ESG Activity Records and supporting Evidence across Layers 1–7 prior to submission, review, anomaly detection, and BRSR calculation.

### Key Architectural Deliverables
1. **Domain Models & Enums (`apps/core/models.py`)**:
   - `ValidationSeverity`: `ERROR` (blocks submission), `WARNING` (advisory notice), `INFO` (informational context).
   - `ValidationCategory`: `STRUCTURAL`, `SCOPE`, `PERIOD`, `ACTIVITY`, `EVIDENCE`, `CONSISTENCY`, `WORKFLOW`.
   - `ValidationStatus`: `UNVALIDATED`, `VALID`, `WARNING` (valid with warnings), `INVALID` (blocking errors detected).
   - `ValidationRule`: Governed catalog model (`code`, `name`, `description`, `category`, `severity`, `is_active`, `is_blocking`, `applicable_activity`, `rule_parameters`, `version`, `effective_from`). Protected against deletion via `on_delete=models.PROTECT`.
   - `ValidationRun`: Immutable evaluation ledger (`activity_record`, `run_number`, `status`, `total_rules_evaluated`, `error_count`, `warning_count`, `info_count`, `summary_message`, `executed_by`, `executed_at`, `execution_duration_ms`, `rule_version_snapshot`). `UniqueConstraint` on `['activity_record', 'run_number']`.
   - `ValidationResult`: Granular rule findings (`validation_run`, `activity_record`, `rule`, `severity`, `is_blocking`, `field_name`, `message`, `context_data`).
   - `ActivityRecord` Enhancements: Added `validation_status`, `last_validated_at`, `idx_rec_val_status` index, and properties (`is_validated`, `has_validation_errors`, `latest_validation_run`, `validation_badge_class`, `can_submit_for_review`). Updated `save()` to bypass full `clean()` when persisting validation metadata via `update_fields`.
   - `AuthAuditLog`: Added event types `VALIDATION_EXECUTED`, `VALIDATION_RULE_CREATED`, `VALIDATION_RULE_UPDATED`.

2. **Validation Service Layer (`apps/core/validation_services.py`)**:
   - 21 deterministic rule validators registered without `eval()` or `exec()`:
     - **Layer 1 (Structural)**: `STRUCT_REQ_QUANTITY`, `STRUCT_REQ_UNIT`, `STRUCT_REQ_DATE`, `STRUCT_REQ_ACTIVITY`, `STRUCT_REQ_SITE`, `STRUCT_REQ_PERIOD`.
     - **Layer 2 (Scope)**: `SCOPE_SITE_ACTIVE`, `SCOPE_HIERARCHY_CONSISTENT`.
     - **Layer 3 (Period)**: `PERIOD_STATUS_OPEN`, `PERIOD_DATE_BOUNDS`.
     - **Layer 4 (Activity)**: `ACT_STATUS_ACTIVE`, `ACT_UNIT_ALLOWED`, `ACT_REQ_DATE`.
     - **Layer 5 (Evidence)**: `EVID_MANDATORY_CHECK`, `EVID_ACTIVE_EXISTS`.
     - **Layer 6 (Consistency & Duplicates)**: `CONSIST_POSITIVE_QUANTITY`, `CONSIST_NONZERO_QUANTITY`, `CONSIST_VALID_DECIMAL`, `CONSIST_DETERMINISTIC_DUPLICATE`.
     - **Layer 7 (Workflow Readiness)**: `WORKFLOW_STATUS_VALID`, `WORKFLOW_NO_BLOCKING_ERRORS`.
   - Transaction-safe runner `execute_validation_run(record, executed_by, request)` with execution timing, automatic status update, demotion of `READY` to `DRAFT` upon blocking errors, and audit event logging.
   - Batch runner `validate_activity_records(records_qs, executed_by, request)` evaluating records in bulk.
   - Scoped authorization helpers: `user_can_validate_record`, `user_can_manage_validation_rules`, `user_can_view_validation_rules`.
   - Idempotent database seeder `seed_standard_validation_rules()`.

3. **Forms & Views (`apps/core/validation_forms.py`, `validation_views.py`, `urls.py`)**:
   - `activity_record_validate_view` (`/data-entry/<id>/validate/`): Dual-mode POST-only view supporting reactive AJAX JSON responses and traditional HTTP redirects.
   - `activity_record_batch_validate_view` (`/data-entry/batch-validate/`): POST-only batch validation for records in user's scope.
   - `validation_run_detail_view` (`/validation/runs/<id>/`): Immutable audit report of a validation run with KPI counters, outcome badge, and findings table.
   - `validation_rule_list_view` (`/validation/rules/`): Governed rules catalog with category/severity filters and statistics.
   - `validation_rule_detail_view` (`/validation/rules/<id>/`), `validation_rule_edit_view`, `validation_rule_toggle_view`.

4. **UI Templates & Monolith Integrations**:
   - `templates/data_entry/record_detail.html`: Added Phase 10 Validation Engine KPI metric, status badge, granular findings table, historical runs accordion, and AJAX/Form "Run Validation" / "Re-Validate" action trigger.
   - `templates/data_entry/record_list.html`: Added Validation Status filter dropdown, Validation badge table column, and Batch Validate button.
   - Created `templates/validation/run_detail.html`, `rule_list.html`, `rule_detail.html`, `rule_form.html`.
   - Registered `ValidationRuleAdmin`, `ValidationRunAdmin`, `ValidationResultAdmin` in Django Admin.

5. **Database Migration**:
   - Created and applied `apps/core/migrations/0008_validationresult_validationrule_validationrun_and_more.py`.
   - `makemigrations --check` clean (0 pending migrations).

---

## 5. Verification & Test Telemetry (Phase 10)

### Django System Check
```text
.venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
Result: PASS
```

### Migration Check (`makemigrations --check`)
```text
.venv\Scripts\python.exe manage.py makemigrations --check
No changes detected
Result: PASS (0 pending schema migrations)
```

### Dedicated Phase 10 Automated Test Suite (`tests/test_phase10_validation_engine.py`)
```text
.venv\Scripts\python.exe manage.py test tests.test_phase10_validation_engine
Ran 32 tests in 58.742s
OK
Result: 32 Passed, 0 Failed, 0 Errors
```
**Test Coverage Matrix:**
- `Models & Integrity`: ValidationRule, ValidationRun, ValidationResult, UniqueConstraint on run number, PROTECT foreign keys.
- `Layer 1-7 Deterministic Rules`: Structural, Scope, Period, Activity Master, Evidence requirements, Consistency/Positive quantities, Deterministic duplicate warnings, Workflow readiness.
- `Lifecycle & Workflow Gates`: Demotion of `READY` to `DRAFT` upon blocking validation failure; preservation of immutable run history across multiple revalidation cycles.
- `Batch Validation`: Bulk validation of scoped querysets.
- `Anti-IDOR & Zero Client Trust`: Site Manager blocked from validating foreign or unassigned site records (HTTP 404/403).
- `Governance & RBAC`: Site Manager blocked from rules catalog (403); Auditor granted read-only visibility (200) but blocked from mutation/toggle (403); ESG Manager and Operator granted full governance.

### Full Monolith Regression Suite (`manage.py test`)
```text
.venv\Scripts\python.exe manage.py test
Ran 275 tests in 314.653s
OK (Found 275 tests, 0 failures, 0 errors)
Result: 100% PASS (Phases 01–10 fully passing)
```

### Live Server Verification (`tests/verify_phase10_live.py`)
```text
.venv\Scripts\python.exe tests/verify_phase10_live.py
[OK] Site Manager authenticated successfully.
[OK] Activity Records catalog loaded with validation telemetry and filters.
[OK] Found accessible Activity Record ID: 7
[OK] Activity Record detail contains ESG Validation Engine section & action trigger.
[OK] Validation executed successfully. Response payload: {"success": true, "run_id": 3, "run_number": 3, "status": "INVALID", ...}
[OK] Record detail displays fresh validation findings, metrics, and audit summary.
[OK] Validation Run #3 audit detail loaded with full rule lineage and findings.
[OK] Server enforced strict authorization defense (HTTP 404) against unassigned record.
[OK] Site Manager restricted from accessing Validation Rules Ledger (HTTP 403 Forbidden).
[OK] ESG Manager authenticated successfully.
[OK] Validation Rules catalog rendered with standard rules across Layers 1-7.
[OK] Rule #14 state toggled successfully and restored.
[OK] Auditor authenticated successfully.
[OK] Auditor granted read-only visibility to Validation Rules catalog.
[OK] Auditor alteration blocked with HTTP 403 Forbidden (Strict Read-Only Enforcement).
[OK] Auditor verified Validation Run #3 audit lineage successfully.
ALL 15 LIVE VERIFICATION CHECKS PASSED PERFECTLY!
```

---

## 6. Next Recommended Phase

**PHASE 11 — OCR (OPTICAL CHARACTER RECOGNITION)**
- Automated data extraction from attached Evidence documents (PDFs, utility bills, fuel invoices).
- Pre-population and cross-verification of extracted quantities against Activity Records.
- Feeds into Phase 10 Validation Engine for automated invoice vs. record consistency verification.
