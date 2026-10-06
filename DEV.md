# MEIL ESG CONTROL TOWER — Development Tracking

## Current Phase
**PHASE 04 — REPORTING PERIODS & TEMPORAL GOVERNANCE**

**Status:** COMPLETED  
**Phase 04 Completion:** 100%  
**Total Project Completion:** 75%

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

## 5. Next Recommended Phase
**PHASE 05 — SITES / PROJECTS INTEGRATION & OPERATIONAL BOUNDARIES**
- Bind reporting periods to operational site boundaries and activity data entry workflows.
- Provide data collection initiation desk per reporting period.
- Connect facility equipment meters and telemetry channels to active reporting periods.

