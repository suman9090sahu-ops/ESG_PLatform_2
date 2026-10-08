# MEIL ESG CONTROL TOWER — Developer Guide
## Phase 02: Authentication & Role-Based Access Control (RBAC)

This document details the developer workflow, environment setup, architecture, and standards for the **MEIL ESG CONTROL TOWER** platform.

---

## Technical Stack

| Component | Technology | Version |
| :--- | :--- | :--- |
| **Framework** | Django LTS | `5.2.x` |
| **Runtime** | Python | `3.12+` (tested on `3.13`) |
| **Database** | PostgreSQL / SQLite fallback | `psycopg` v3 driver with SQLite local fallback |
| **User Identity** | Single Unified Custom User | `apps.core.models.User` (AbstractUser) |
| **Frontend Framework** | Bootstrap | `5.3.x` |
| **Design System** | Stellar Admin + MEIL ESG Tokens | Production Vanilla CSS / JS |
| **Static Serving** | WhiteNoise | `6.x` |
| **Timezone** | Asia/Kolkata | `UTC+05:30` |

---

## Directory Architecture

```text
c:\ESG_PLatform_2\
├── config/
│   ├── settings/
│   │   ├── base.py                 # Core settings, AUTH_USER_MODEL, login redirects
│   │   ├── development.py          # Development defaults
│   │   ├── production.py           # Hardened production cookies, SSL, HSTS
│   │   └── testing.py              # In-memory SQLite, MD5PasswordHasher
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   └── core/
│       ├── models.py               # User, Role, Company, Subsidiary, Project, Site, Assignments, AuthAuditLog
│       ├── auth_services.py        # RBAC helpers, user_can_access_site, decorators, menu builder
│       ├── auth_views.py           # Login, Logout, Password management, Role dashboards
│       ├── forms.py                # LoginForm, Password change/reset forms
│       ├── views.py                # Core dashboard shell, ui_preview, health_check, error handlers
│       ├── admin.py                # Django admin for Users, Roles, Assignments, Audit log
│       ├── context_processors.py   # Injects role initials, titles, dynamic sidebar menu
│       ├── urls.py                 # Core and /auth/ routes
│       └── management/commands/
│           └── seed_rbac_data.py   # Management command to seed hierarchy, roles, and test users
├── templates/
│   ├── base/                       # Reusable shell (navbar, sidebar, head, footer, scripts)
│   ├── layouts/                    # Layout templates (dashboard.html, auth.html, blank.html)
│   ├── auth/                       # Login, password change, password reset templates
│   ├── dashboards/                 # Role-specific dashboard placeholders (site, sub, esg, auditor, operator)
│   ├── components/                 # Phase 01 modular component library (buttons, cards, forms, badges)
│   └── errors/                     # 400, 403, 404, 500 error pages
├── static/
├── docs/
│   ├── RBAC.md                     # Comprehensive RBAC & object authorization specification
│   ├── ROUTE_MAP.md                # Complete active & planned URL registry
│   ├── DEVELOPMENT.md              # Developer workflows & seed data
│   └── HOW_TO_USE_UI_COMPONENTS.md # Design system component guide
├── tests/
│   ├── test_auth.py                # Login, logout, session security, password management (10 tests)
│   ├── test_rbac.py                # Server-side role authorization & cross-role denial (12 tests)
│   ├── test_object_access.py       # Object-level authorization & IDOR defense (10 tests)
│   ├── test_phase01_foundation.py  # Layouts, components, badges, indicators (64 tests)
│   ├── test_settings.py            # Environment configurations (5 tests)
│   ├── test_security.py            # Security headers & CSRF (2 tests)
│   ├── test_health.py              # Health check API telemetry (2 tests)
│   └── test_error_pages.py         # Custom HTTP error pages (5 tests)
├── DEV.md                          # Phase tracking & verification report
└── manage.py
```

---

## RBAC Test Accounts

The platform includes seed users with defined operational scopes:

| Persona | Username | Default Password | Primary Scope | Permitted Access |
| :--- | :--- | :--- | :--- | :--- |
| **Site Manager** | `site_manager` | `SiteManagerPass123!` | Site 101 (`SITE-POL-101`) | Operational data for Site 101 only |
| **Site Manager (Other)** | `unassigned_site_manager`| `OtherSitePass123!` | Site 102 (`SITE-POL-102`) | Operational data for Site 102 only |
| **Subsidiary Manager** | `subsidiary_manager` | `SubManagerPass123!` | `MEIL-HYDRO` Division | Hydro division projects & child sites |
| **ESG Manager** | `esg_manager` | `ESGManagerPass123!` | `MEIL-ENT` Enterprise | Corporate GHG accounting & BRSR finalization |
| **Auditor** | `auditor` | `AuditorPass123!` | `MEIL-ENT` Enterprise | Read-only assurance across all governed data |
| **MEIL Operator** | `meil_operator` | `OperatorPass123!` | `MEIL-ENT` Enterprise | Platform operations hub & security audit log |
| **Superuser** | `admin` | `AdminPass123!` | Platform Administrative | Django `/admin/` and full access |

---

## Quickstart Commands

### 1. Seed RBAC Data & Demo Users
```powershell
.\python.bat manage.py seed_rbac_data
```

### 2. Validation & System Checks
```powershell
.\python.bat manage.py check
.\python.bat manage.py makemigrations --check
.\python.bat manage.py test
```

### 3. Run Specific Test Suites
```powershell
# Authentication tests
.\python.bat manage.py test tests.test_auth

# RBAC tests
.\python.bat manage.py test tests.test_rbac

# Object-level authorization & IDOR tests
.\python.bat manage.py test tests.test_object_access

# Phase 03 Organization Hierarchy & Scoping tests
.\python.bat manage.py test tests.test_organization

# Phase 12 Submission Workflow tests
.\python.bat manage.py test tests.test_phase12_submission_workflow

# Phase 13 Subsidiary Review tests
.\python.bat manage.py test tests.test_phase13_subsidiary_review

# Phase 14 Corrections & Resubmission tests
.\python.bat manage.py test tests.test_phase14_corrections_resubmission

# Phase 15 Anomaly Detection Engine tests
.\python.bat manage.py test tests.test_phase15_anomaly_detection

# Phase 15 Live End-to-End Verification
.\python.bat tests\verify_phase15_live.py

# Live End-to-End HTTP Verification against running server
.\python.bat tests\test_live_e2e.py
```

### 4. Run Development Server
```powershell
.\python.bat manage.py runserver 127.0.0.1:8000
```

---

## Phase 15 — Anomaly Detection Engine Developer Guide

### Default Rule Seeding
Ensure standard deterministic anomaly rules are present in the environment:
```python
from apps.core.anomaly_services import ensure_default_anomaly_rules

rules = ensure_default_anomaly_rules()
# Seeds/verifies:
# - DIESEL_SPIKE (+100.0% vs historical baseline)
# - DIESEL_DROP (-50.0% vs historical baseline)
# - ELEC_PERIOD_SPIKE (+50.0% vs prior reporting period)
# - DUPLICATE_TELEMETRY (exact match on site, activity, measurement date, quantity, unit)
# - FUEL_THRESHOLD_BREACH (upper bound operational telemetry limits)
# - ENERGY_INTENSITY_ANOMALY (consumption intensity ratios)
```

### Running Anomaly Evaluation Programmatically
```python
from apps.core.anomaly_services import detect_anomalies_for_record, run_batch_anomaly_detection

# Single Record Evaluation (Idempotent)
detected_anomalies = detect_anomalies_for_record(activity_record, actor=request.user)

# Batch Evaluation across a Site / Period Scope
results = run_batch_anomaly_detection(
    reporting_period=period,
    site=site,
    actor=request.user,
    triggered_by="ESG_MANAGER_BATCH"
)
print(f"Evaluated {results['evaluated']} records, flagged {results['flagged']} anomalies.")
```

### Anomaly Review Actions
```python
from apps.core.anomaly_services import execute_anomaly_review_action

# Execute review action (ACKNOWLEDGE, EXPLAIN, RESOLVE, DISMISS)
updated_record = execute_anomaly_review_action(
    anomaly=anomaly,
    action="EXPLAIN",
    actor=user,
    notes="High fuel usage was driven by round-the-clock emergency dewatering operations.",
    ip_address=request.META.get("REMOTE_ADDR")
)
```

