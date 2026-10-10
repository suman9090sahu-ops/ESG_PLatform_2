# MEIL ESG CONTROL TOWER — Demo Data Seeder Usage & Testing Manual

## 1. Overview

The `seed_esg_demo_data` Django management command populates all **50 database tables** of the MEIL ESG Control Tower with coherent, realistic synthetic ESG demo data derived from the comprehensive 36-sheet Excel workbook:

`MEIL_BRSR_45_Entities_FY2025-26_Comprehensive_Demo.xlsx`

The data is strictly tagged as `[SYNTHETIC DEMO]` and is designed for browser testing, demonstration, and workflow validation across all operational modules.

---

## 2. Command Usage & Syntax

Run the seeder from the project root using the virtual environment:

### A. Dry-Run Simulation (Default / Safe Mode)
Simulates all 10 ingestion steps, validates workbook integrity, computes table metrics, and rolls back the database transaction with **zero data modifications**:

```powershell
python manage.py seed_esg_demo_data --dry-run
```

### B. Live Application (Commit Mode)
Executes all 10 ingestion steps inside an atomic transaction and commits all synthetic demo records:

```powershell
python manage.py seed_esg_demo_data --apply
```

### C. Live Application with Markdown Audit Report
Executes the live commit and automatically generates or updates `docs/demo_data/DEMO_DATA_IMPORT_REPORT.md`:

```powershell
python manage.py seed_esg_demo_data --apply --report
```

### D. Custom Workbook Path
To specify an alternative workbook file:

```powershell
python manage.py seed_esg_demo_data --workbook path/to/custom_workbook.xlsx --apply
```

---

## 3. Idempotency & Protection Guarantees

1. **Idempotent by Design:** Running the command repeatedly will **not create duplicate records**. It uses Django ORM `get_or_create` with natural composite keys (e.g. `site + activity + measurement_date` for activity records).
2. **Organizational Scope Protection:** The workbook contains 45 entities. However, the approved MEIL operational hierarchy consists strictly of:
   - **1 Enterprise Company:** `MEIL-ENT`
   - **2 Operating Subsidiaries:** `MEIL-HYDRO`, `MEIL-SOLAR`
   - **2 Projects:** `PRJ-POL-01` (Polavaram Hydro Project), `PRJ-KRN-01` (Kurnool Ultra Solar Project)
   - **3 Sites:** `SITE-POL-101` (Polavaram Headworks), `SITE-POL-102` (Spillway Channel), `SITE-KRN-201` (Kurnool Solar Array 1)
   The seeder unambiguously maps compatible workbook entities (`E01`, `E03`, `E09`) and safely flags the remaining 42 entities as `SKIPPED_UNMAPPED_ENTITY` without altering database boundaries.
3. **No Fabricated System Records:** Framework tables (`auth_group`, `django_admin_log`, join tables) remain legitimately empty because authentication utilizes the custom RBAC role model (`core_role`, `core_userrole`).

---

## 4. Authorized Demo User Credentials for Browser Testing

All demo users share standard local development credentials:

| Role | Username | Password | Assigned Scope & Responsibilities |
| :--- | :--- | :--- | :--- |
| **Site Manager** | `site_manager` | `DemoPass123!` | Assigned to `SITE-POL-101`. Manages daily meter logs, fuel dockets, invoice OCR, and record submissions. |
| **Subsidiary Manager** | `subsidiary_manager` | `DemoPass123!` | Assigned to `MEIL-HYDRO` & `MEIL-SOLAR`. Reviews submissions, requests corrections, approves divisional data. |
| **ESG Manager** | `esg_manager` | `DemoPass123!` | Enterprise-wide governance. Runs calculations, manages emission factors, reviews anomalies, consolidates BRSR. |
| **ESG Auditor** | `auditor` | `DemoPass123!` | Read-only inspection. Traces calculation lineage, verifies tamper-evident SHA-256 evidence hashes. |
| **Administrator** | `admin` | `DemoPass123!` | Superuser access to Django Admin and system maintenance. |

---

## 5. End-to-End Browser Testing Walkthrough

Start the development server:

```powershell
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in your browser.

### 1. Site Manager Dashboard (`/site-manager/dashboard/`)
- Log in as `site_manager`.
- Observe 30 monthly operational consumption records across Diesel, Grid Electricity, Water Withdrawal, and C&D Waste.
- Verify status distribution: `APPROVED`, `VERIFIED`, `SUBMITTED`, `READY`, `DRAFT`, `REJECTED`.
- Verify reporting period filter (`FY 2025-26`).

### 2. Evidence Management & OCR Engine (`/evidence/`)
- Navigate to Evidence Management.
- View 18 attached tamper-evident supporting documents (Fuel invoices, APCPDCL electricity bills).
- Inspect SHA-256 integrity hashes and click through to view OCR extraction results (96.8% confidence, line-item extractions).

### 3. Layer 1–7 Deterministic Validation Engine (`/validation/`)
- Inspect automated validation runs.
- View validation status flags: 22 rules evaluated across temporal boundaries, unit compliance, and spike limits.

### 4. Subsidiary Review & Corrections Desk (`/submissions/`, `/corrections/`)
- Log in as `subsidiary_manager`.
- View 23 formal submissions pending review or verified.
- Inspect the correction request for the rejected fuel log (`IOCL-INV-2025-07-104`).
- Review the immutable historical revision snapshot created on `ActivityRevision`.

### 5. GHG Protocol Calculations & Traceability (`/calculations/`)
- Log in as `esg_manager`.
- View 30 deterministic GHG Protocol calculation results for Scope 1 (Stationary & Mobile Diesel) and Scope 2 (Grid Electricity).
- Verify standard output units (`tCO2e`).
- Click "Trace This Number" to view audit lineage connecting calculation result &rarr; emission factor vintage &rarr; activity record &rarr; supporting invoice evidence.

### 6. Scope 3 Procurement & Transport Logistics (`/procurement/`, `/transport/`)
- Review commercial purchasing records from Tata Steel and UltraTech Cement.
- Inspect freight movements executed by VRL Logistics and TCI Freight (`AP-07-TJ-4819`).
- Verify Scope 3 Category 4 (Upstream Transportation) allocation.

### 7. Statistical Anomaly Detection Desk (`/anomalies/`)
- Inspect monthly anomaly screening run (`AnomalyRun #1`).
- View the flagged 60.7% diesel consumption spike on Polavaram Headworks with the documented engineering explanation (24/7 cofferdam dewatering pumps during peak river discharge).

---

## 6. Running Automated Tests

To run the automated test suite verifying the seeder and its safety constraints:

```powershell
python manage.py test tests.test_seed_esg_demo_data
```
