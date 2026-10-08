# MEIL ESG CONTROL TOWER

> **Capture Once. Verify Intelligently. Calculate Consistently. Trace Everything.**

MEIL ESG Control Tower is an integrated enterprise ESG and SEBI BRSR governance platform designed to manage ESG data from operational sites through verification, calculation, consolidation, reporting, and audit traceability.

The platform is designed around **evidence-backed ESG data lineage** so that reported ESG metrics can be traced back to their operational source data and supporting evidence.

---

## 1. Project Overview

The MEIL ESG Control Tower provides a centralized platform for:

* ESG data collection
* Operational activity recording
* Evidence/document management
* OCR-based document extraction
* Data validation
* Anomaly detection
* Review and verification
* Emission factor management
* Scope 1, Scope 2 and Scope 3 calculations
* ESG consolidation
* SEBI BRSR reporting
* Audit trail
* Data lineage
* "TRACE THIS NUMBER" audit functionality
* Offline Site Manager data collection and synchronization

The system is designed for geographically distributed projects, operational sites, subsidiaries and corporate ESG governance.

---

# 2. Core Principle

The platform follows this fundamental data lineage:

```text
Operational Activity
        ↓
Evidence
        ↓
OCR / Extraction
        ↓
Validation
        ↓
Anomaly Detection
        ↓
Review / Verification
        ↓
Emission Factors
        ↓
Calculation
        ↓
Scope 1 / Scope 2 / Scope 3
        ↓
Consolidation
        ↓
BRSR
        ↓
Audit Trail
        ↓
TRACE THIS NUMBER
```

The objective is to ensure that ESG numbers are not merely reported, but are **traceable, explainable and evidence-backed**.

---

# 3. User Roles

The platform uses a centralized RBAC architecture.

## SITE MANAGER

Responsible for operational ESG data collection at assigned sites.

Main responsibilities:

* View assigned sites
* Enter ESG activity data
* Save drafts
* Upload evidence
* View OCR results
* Resolve validation issues
* Submit ESG data
* Manage corrections
* Monitor synchronization status
* Work offline when supported

---

## SUBSIDIARY MANAGER

Responsible for first-line ESG operational review.

Main responsibilities:

* View assigned subsidiaries/projects/sites
* Review submissions
* Review evidence
* Review OCR results
* Review validation results
* Review anomalies
* Request corrections
* Provide explanations
* Verify data
* Escalate exceptions

---

## ESG MANAGER

Responsible for corporate ESG governance.

Main responsibilities:

* Corporate ESG dashboard
* Verified data
* Activity classification
* Scope classification
* Emission factors
* Factor sources and versions
* Methodologies
* Unit conversion
* Calculations
* Scope 1
* Scope 2
* Scope 3
* Exceptions
* Consolidation
* BRSR reporting
* Finalization

---

## AUDITOR / MEIL OPERATOR

Responsible for governance, audit and operational oversight according to assigned permissions.

Main responsibilities:

* Audit dashboard
* Report review
* Metric exploration
* Calculation review
* Factor review
* Methodology review
* Raw data review
* Evidence review
* OCR review
* Validation review
* Approval history
* Audit trail
* Data lineage
* TRACE THIS NUMBER
* Audit findings

---

# 4. Technology Stack

The project is built as a single integrated Django application.

### Backend

* Python 3.12+
* Django 5.2 LTS
* PostgreSQL

### Frontend

* Django Templates
* Bootstrap 5.x
* HTML5
* CSS3
* Vanilla JavaScript where appropriate

### Architecture

* Django monolith
* Server-side authorization
* PostgreSQL relational data model
* Evidence-backed lineage
* Reusable template/component system
* Service/query layers where appropriate

The project does **not** use React, Vue, Angular or another frontend framework unless an existing repository requirement explicitly introduces one.

---

# 5. High-Level Architecture

```text
MEIL ENTERPRISE
        │
        ▼
COMPANY / SUBSIDIARY
        │
        ▼
INFRASTRUCTURE PROJECT
        │
        ▼
OPERATIONAL SITE
        │
        ▼
REPORTING PERIOD
        │
        ▼
ACTIVITY MASTER
        │
        ▼
ACTIVITY RECORD
        │
        ▼
EVIDENCE
        │
        ▼
OCR
        │
        ▼
VALIDATION
        │
        ▼
ANOMALY DETECTION
        │
        ▼
REVIEW / VERIFICATION
        │
        ▼
CALCULATION
        │
        ├──────────────► SCOPE 1
        │
        ├──────────────► SCOPE 2
        │
        └──────────────► SCOPE 3
        │
        ▼
CONSOLIDATION
        │
        ▼
BRSR
        │
        ▼
AUDIT / ASSURANCE
        │
        ▼
TRACE THIS NUMBER
```

---

# 6. Repository Structure

The repository follows a modular Django architecture.

A representative structure is:

```text
meil_esg_control_tower/
│
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   ├── production.py
│   │   └── testing.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/
│   ├── accounts/
│   ├── organization/
│   ├── reporting/
│   ├── sites/
│   ├── activities/
│   ├── evidence/
│   ├── ocr/
│   ├── validation/
│   ├── anomalies/
│   ├── reviews/
│   ├── suppliers/
│   ├── transport/
│   ├── travel/
│   ├── waste/
│   ├── emission_factors/
│   ├── calculations/
│   ├── scope1/
│   ├── scope2/
│   ├── scope3/
│   ├── consolidation/
│   ├── brsr/
│   ├── assurance/
│   ├── audit/
│   └── dashboard/
│
├── templates/
│   ├── base/
│   ├── components/
│   ├── layouts/
│   ├── site_manager/
│   ├── subsidiary_manager/
│   ├── esg_manager/
│   └── auditor/
│
├── static/
│   ├── css/
│   ├── js/
│   ├── img/
│   └── vendor/
│
├── media/
│
├── docs/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── permissions/
│   ├── workflows/
│   └── e2e/
│
├── manage.py
├── requirements/
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── README.md
└── DEV.md
```

**Important:** The actual repository structure is authoritative. This README should not be interpreted as permission to create modules that do not yet exist.

---

# 7. Module Architecture

The project is developed incrementally through coordinated phases.

| Phase | Module                       |
| ----- | ---------------------------- |
| 00    | Foundation                   |
| 01    | UI / Bootstrap Design System |
| 02    | Authentication + RBAC        |
| 03    | Organization Hierarchy       |
| 04    | Reporting Periods            |
| 05    | Projects / Sites             |
| 06    | Activity Master              |
| 07    | Site Manager Dashboard       |
| 08    | ESG Data Entry               |
| 09    | Evidence Management          |
| 10    | Validation Engine            |
| 11    | OCR Engine                   |
| 12    | Submission Workflow          |
| 13    | Subsidiary Review            |
| 14    | Corrections / Explanations   |
| 15    | Anomaly Engine               |
| 16    | Supplier / Procurement       |
| 17    | Transport / Logistics        |
| 18    | Travel                       |
| 19    | Waste Contractor             |
| 20    | Emission Factor Engine       |
| 21    | Scope 1                      |
| 22    | Scope 2                      |
| 23    | Scope 3                      |
| 24    | Calculation Engine           |
| 25    | ESG Manager Dashboard        |
| 26    | Consolidation                |
| 27    | BRSR Section C               |
| 28    | BRSR Reporting               |
| 29    | Finalization                 |
| 30    | Auditor Workspace            |
| 31    | TRACE THIS NUMBER            |
| 32    | Audit Trail / Data Lineage   |
| 33    | Offline / Synchronization    |
| 34    | Security Hardening           |
| 35    | End-to-End Testing           |
| 36    | Production Deployment        |

The actual implementation status must be checked in `DEV.md`.

---

# 8. Current Development Methodology

Development follows this sequence:

```text
INSPECT
   ↓
PLAN
   ↓
IMPLEMENT
   ↓
MIGRATE
   ↓
CHECK
   ↓
TEST
   ↓
BROWSER VERIFY
   ↓
DEBUG
   ↓
RECHECK
   ↓
DOCUMENT
   ↓
REPORT
```

No phase should be considered complete merely because files were generated.

A feature is considered complete only after the relevant checks, tests and browser verification have been performed.

---

# 9. Important Development Rules

## 9.1 Inspect Before Modifying

Before modifying the repository, inspect:

* existing architecture
* models
* migrations
* views
* forms
* services
* templates
* static files
* URLs
* RBAC
* tests
* documentation
* current Git changes

Do not blindly overwrite existing work.

---

## 9.2 Reuse Existing Architecture

Before creating a new:

* model
* service
* form
* component
* permission helper
* workflow
* storage system

search the repository first.

If an equivalent implementation already exists:

```text
reuse
    ↓
extend if necessary
    ↓
avoid duplication
```

---

## 9.3 One Integrated Application

This project is a single integrated Django application.

Do not create:

```text
separate Site Manager application
separate ESG Manager application
separate Auditor application
```

Roles are authorization/context layers over the same domain architecture.

---

## 9.4 Server-Side Authorization

Never trust IDs supplied by the browser.

Examples:

```text
company_id
subsidiary_id
project_id
site_id
activity_id
reporting_period_id
evidence_id
user_id
```

All object access must be authorized server-side.

UI hiding is not a security mechanism.

---

## 9.5 Historical Data Protection

Do not casually delete or overwrite important historical ESG data.

Approved, verified, locked or finalized records should use appropriate:

* correction
* revision
* versioning
* audit trail

mechanisms.

---

# 10. ESG Activity Architecture

The platform distinguishes between:

### Activity Master

Defines what an ESG activity means.

Examples:

```text
Diesel Consumption
Grid Electricity Consumption
Purchased Water
Municipal Solid Waste
```

### Activity Record

Represents actual operational data.

Example:

```text
Site: Project Alpha Site 01
Reporting Period: FY 2025-26
Activity: Diesel Consumption
Date: 2026-04-15
Quantity: 250
Unit: litre
```

The Activity Master is reference data.

The Activity Record is operational data.

Do not mix the two.

---

# 11. Evidence Architecture

Evidence is a first-class part of ESG data lineage.

Conceptually:

```text
Activity Record
      ↓
Evidence
      ↓
OCR
      ↓
Validation
      ↓
Review
      ↓
Calculation
      ↓
BRSR
```

Examples of evidence include:

* invoices
* bills
* meter records
* ERP extracts
* supplier documents
* certificates
* laboratory reports
* fuel records
* electricity bills
* water bills
* waste documentation

The original evidence file must be preserved.

---

# 12. OCR Principle

OCR output is **extracted information, not automatically verified truth**.

The correct conceptual flow is:

```text
Evidence
   ↓
OCR
   ↓
Raw Extracted Text
   ↓
Structured Fields
   ↓
Validation / Comparison
   ↓
Review
   ↓
Verified Data
```

OCR must never silently overwrite the authoritative Activity Record.

---

# 13. Validation Principle

Validation is deterministic rule-based checking.

Examples:

```text
Required fields
Valid quantity
Valid unit
Valid date
Valid reporting period
Authorized site
Authorized activity
Evidence requirements
Cross-field consistency
```

Validation is different from anomaly detection.

A value can be unusual without being invalid.

---

# 14. Future Calculation Architecture

Future calculation processing will use verified operational activity data.

Conceptually:

```text
Verified Activity
       ↓
Emission Factor
       ↓
Calculation
       ↓
Emission Result
       ↓
Scope
```

Emission factor versions must be preserved so historical calculations remain reproducible.

---

# 15. Scope Architecture

The platform is intended to support:

## Scope 1

Examples:

* stationary combustion
* mobile combustion
* process emissions
* fugitive emissions

## Scope 2

Examples:

* grid electricity
* renewable electricity
* wheeled electricity
* green tariff
* purchased steam/heat/cooling

## Scope 3

The architecture is intended to support all relevant Scope 3 categories.

Scope classification and calculations must remain evidence-backed and reproducible.

---

# 16. BRSR Architecture

The platform is intended to support SEBI BRSR reporting.

The future reporting flow is:

```text
Operational Data
       ↓
Validated Data
       ↓
Verified Data
       ↓
Calculated Metrics
       ↓
Consolidation
       ↓
BRSR
       ↓
Finalization
       ↓
Audit
```

BRSR reporting should not bypass the underlying data lineage.

---

# 17. TRACE THIS NUMBER

A core future capability is:

> **TRACE THIS NUMBER**

An auditor should eventually be able to start from a reported metric and trace it backward.

Example:

```text
BRSR Metric
     ↓
Calculation Run
     ↓
Emission Factor
     ↓
Activity Record
     ↓
Operational Site
     ↓
Evidence
     ↓
Original Document
```

The final system should make the origin and calculation of reported ESG values explainable.

---

# 18. Offline Site Manager

The final platform is expected to support offline operation for Site Managers.

The intended architecture is:

```text
Prior Authorized Login
        ↓
Local Data Entry
        ↓
Local Draft / Pending Upload
        ↓
Network Available
        ↓
Synchronization
        ↓
Server Validation
        ↓
Server Activity Record
```

Important future requirements include:

* offline use after prior authorized login;
* pending records survive logout;
* attachments survive logout;
* authorized offline re-authentication on the same device;
* synchronization authorization separate from UI login;
* automatic retry;
* resume after application reopening;
* Pending Uploads screen;
* pending / synced / failed states.

The dedicated offline/synchronization phase should implement this fully.

Do not assume normal browser login persistence is sufficient.

---

# 19. Security Philosophy

Security must be enforced at the backend.

Important requirements include:

* authentication;
* RBAC;
* object-level authorization;
* IDOR protection;
* CSRF protection;
* secure file handling;
* secure secrets management;
* validation of uploaded files;
* safe database access;
* audit logging;
* historical record protection.

Never rely solely on:

* hidden fields;
* disabled buttons;
* frontend checks;
* URL obscurity.

---

# 20. Testing Strategy

The project should maintain multiple levels of testing.

## Unit Tests

Test:

* models
* services
* calculations
* validation rules
* OCR processing
* permissions

## Integration Tests

Test:

* workflow transitions
* evidence relationships
* calculations
* consolidation
* BRSR generation

## Permission Tests

Test:

* role boundaries
* organization boundaries
* site boundaries
* IDOR attacks
* unauthorized direct URLs

## End-to-End Tests

Test complete business workflows.

Example:

```text
Login
 ↓
Site Manager
 ↓
Site
 ↓
Activity Entry
 ↓
Evidence
 ↓
OCR
 ↓
Validation
 ↓
Submission
 ↓
Review
 ↓
Verification
 ↓
Calculation
 ↓
BRSR
 ↓
Audit Trace
```

---

# 21. Development Commands

Use the project's configured Python environment.

Typical Django commands include:

```bash
python manage.py check
```

```bash
python manage.py makemigrations
```

```bash
python manage.py migrate
```

```bash
python manage.py makemigrations --check
```

```bash
python manage.py test
```

Run commands using the project's virtual environment if required.

On Windows, if `python` is not available, use the executable configured by the project's virtual environment or an appropriate Python launcher command.

Do not change the environment merely to make a command appear successful.

---

# 22. Environment Configuration

Environment-specific values should not be hard-coded.

Use:

```text
.env
.env.example
```

for configuration such as:

* database credentials
* database host
* database port
* secret key
* debug settings
* external provider credentials

Never commit real secrets.

---

# 23. Documentation

Important project documentation should live under:

```text
docs/
```

Expected documents include:

```text
docs/
├── DEVELOPMENT.md
├── MODULE_INTEGRATION.md
├── ROUTE_MAP.md
├── DATABASE_ARCHITECTURE.md
├── RBAC.md
├── WORKFLOW.md
├── AUDIT_LINEAGE.md
└── HOW_TO_USE_UI_COMPONENTS.md
```

Not every document must exist yet.

Create/update documentation as phases are implemented.

---

# 24. Project Status

The authoritative implementation status is maintained in:

```text
DEV.md
```

Do not use this README as a substitute for actual development status.

`DEV.md` should contain:

* completed phases;
* current phase;
* implementation percentage where meaningful;
* tests;
* browser verification;
* known issues;
* known limitations;
* next phase.

Only report verified facts.

---

# 25. Current Phase

The current development sequence should be determined from the actual repository state.

Before implementing a phase:

1. inspect the repository;
2. inspect `DEV.md`;
3. inspect previous phase documentation;
4. inspect existing code;
5. determine what is actually implemented;
6. continue from the real state.

Do not assume a phase is complete simply because its prompt exists.

---

# 26. Git Safety

Before making changes:

```bash
git status
```

Review existing changes.

Do not:

* reset unrelated work;
* delete user changes;
* force checkout;
* overwrite unrelated files;
* rewrite project history without explicit instruction.

After implementation, report:

```text
Files Created
Files Modified
Files Deleted
```

---

# 27. Agent / AI Development Rules

This repository may be worked on using multiple AI coding agents.

Every agent must:

1. inspect the repository first;
2. inspect project documentation;
3. inspect current Git status;
4. understand existing architecture;
5. reuse existing implementation;
6. avoid duplicate models;
7. avoid duplicate services;
8. avoid duplicate workflows;
9. avoid breaking existing modules;
10. run tests after modifications;
11. browser-verify relevant functionality;
12. fix discovered issues;
13. rerun checks;
14. update documentation;
15. report actual results.

Agents must not assume that another agent's work is correct without verification.

---

# 28. Definition of Production-Ready Work

A feature should not be considered production-ready simply because:

```text
the code compiles
```

or:

```text
the page loads
```

A feature should be considered ready only after applicable:

```text
Architecture Review
        ↓
Implementation
        ↓
Database Migration
        ↓
System Checks
        ↓
Automated Tests
        ↓
Security Tests
        ↓
Browser Verification
        ↓
Bug Fixing
        ↓
Regression Testing
        ↓
Documentation
```

has been completed.

---

# 29. Contribution Workflow

Before implementing a feature:

```text
1. Inspect
2. Understand
3. Plan
4. Implement
5. Test
6. Browser Verify
7. Debug
8. Re-test
9. Document
10. Report
```

Keep changes focused on the requested phase.

Do not prematurely implement future modules.

---

# 30. Important Reminder

This README describes the **overall project architecture and development principles**.

It is not a replacement for detailed phase-specific implementation prompts.

For phase work, agents should also inspect:

```text
DEV.md
docs/
existing source code
tests/
```

The actual repository state always takes precedence over this README.

---

# 31. Project Tagline

> **Capture Once. Verify Intelligently. Calculate Consistently. Trace Everything.**

---

# 32. License / Internal Use

This project is an internal enterprise ESG/BRSR platform.

Add the organization's actual licensing and distribution policy here when formally defined.

---

# END OF README
