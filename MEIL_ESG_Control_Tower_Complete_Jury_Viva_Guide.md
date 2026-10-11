# MEIL ESG CONTROL TOWER — Complete Jury Viva Preparation & Technical Research Guide

> **Capture Once. Verify Intelligently. Calculate Consistently. Trace Everything.**

---

## Document Control

| Field | Value |
|---|---|
| **Project** | MEIL ESG Control Tower |
| **Version** | 1.0 (Final Jury Edition) |
| **Team Size** | 5 Members |
| **Institution** | University Technical Jury Presentation |
| **Generated From** | Deep source code inspection of production codebase |
| **Evidence Basis** | All claims verified against `apps/core/models.py` (5,277 lines), 15+ service modules, 45 test files, and configuration files |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement & Motivation](#2-problem-statement--motivation)
3. [System Architecture](#3-system-architecture)
4. [Technology Stack — Verified](#4-technology-stack--verified)
5. [Database Schema — Complete Table Inventory](#5-database-schema--complete-table-inventory)
6. [Core Business Logic — Data Pipeline](#6-core-business-logic--data-pipeline)
7. [Calculation Engine — Emission Factor Mathematics](#7-calculation-engine--emission-factor-mathematics)
8. [OCR & Document Intelligence Pipeline](#8-ocr--document-intelligence-pipeline)
9. [Validation Engine — 7-Layer Architecture](#9-validation-engine--7-layer-architecture)
10. [Anomaly Detection Engine](#10-anomaly-detection-engine)
11. [Scope 3 Value Chain Engine](#11-scope-3-value-chain-engine)
12. [Security, RBAC & Authorization](#12-security-rbac--authorization)
13. [Submission, Review & Correction Workflow](#13-submission-review--correction-workflow)
14. [Reporting & Consolidation Engine](#14-reporting--consolidation-engine)
15. [6-Tier "Trace This Number" Audit Lineage](#15-6-tier-trace-this-number-audit-lineage)
16. [Testing Strategy](#16-testing-strategy)
17. [Deployment Architecture](#17-deployment-architecture)
18. [Individual Team Member Preparation](#18-individual-team-member-preparation)
19. [Probable Jury Questions & Model Answers](#19-probable-jury-questions--model-answers)
20. [Presentation & Demo Strategy](#20-presentation--demo-strategy)

---

## 1. Executive Summary

MEIL ESG Control Tower is an enterprise-grade Environmental, Social, and Governance (ESG) data management and carbon emissions reporting platform designed for **Megha Engineering & Infrastructures Limited (MEIL)** — one of India's largest infrastructure conglomerates operating across power, water, oil & gas, and civil infrastructure.

### What The Platform Does

The platform enables MEIL to:

1. **Collect** operational ESG data (fuel consumption, electricity usage, water withdrawal, waste generation, transport logistics, procurement) from geographically distributed construction and infrastructure sites
2. **Verify** that data through automated validation, OCR-based evidence cross-checking, and anomaly detection
3. **Calculate** Scope 1, Scope 2, and Scope 3 greenhouse gas emissions using regulatory emission factors (IPCC, CEA, India GHG Program, DEFRA)
4. **Consolidate** enterprise-wide ESG metrics across companies, subsidiaries, projects, and sites
5. **Report** in compliance with SEBI BRSR (Business Responsibility and Sustainability Reporting) framework
6. **Trace** every reported number back to its source data and supporting evidence through a 6-tier audit lineage system

### Key Differentiator

> **"Every number is traceable."** — Unlike spreadsheet-based ESG reporting, every metric in the MEIL ESG Control Tower can be traced from the final BRSR disclosure down to the original fuel invoice, utility bill, or weighbridge slip, along with the emission factor applied, the validation result, and the reviewer's decision.

### Scale

- **5,277 lines** of domain model code defining 34+ database tables
- **15+ specialized service modules** (calculation, validation, OCR, anomaly detection, scope 3, submission, review, correction, reporting)
- **45 automated test files** covering 24 development phases
- **5 RBAC roles** with object-level authorization
- **15 GHG Protocol Scope 3 categories** implemented
- **8 anomaly detection rules** with historical baseline computation
- **329 URL routes** serving role-specific dashboards

---

## 2. Problem Statement & Motivation

### The Industry Problem

India's Securities and Exchange Board (SEBI) mandated **BRSR reporting** for the top 1,000 listed entities starting FY2022-23. Infrastructure companies like MEIL face unique challenges:

| Challenge | Description |
|---|---|
| **Geographic Distribution** | 100+ sites across remote locations (dams, tunnels, power plants) |
| **Data Diversity** | Fuel logs, electricity bills, water meters, waste manifests, transport challans — all in different formats |
| **No Standardization** | Sites use paper invoices, handwritten logs, Excel sheets with no uniform taxonomy |
| **Audit Trail Absent** | No way to trace a reported emission number back to its source evidence |
| **Manual Errors** | Copy-paste from invoices introduces transcription errors undetected for months |
| **Scope 3 Complexity** | Value chain emissions across 15 GHG Protocol categories require supplier and transport data integration |

### Our Solution

A centralized Django-based platform that enforces:

```
Data Entry → Evidence Upload → OCR Extraction → Validation → Anomaly Check
    → Submission → Review → Correction → Calculation → Consolidation → BRSR Report
        → Full Audit Trace
```

**Evidence Classification for this Document:**

| Tag | Meaning |
|---|---|
| ✅ **Verified in Source** | Confirmed by reading actual Python source code |
| 🗃️ **Verified in Database** | Confirmed by inspecting Django model definitions |
| 🧪 **Verified by Testing** | Confirmed by existence of automated test files |
| 📚 **External Research** | Supplemented with industry standard reference |
| 🔍 **Inferred** | Reasonable inference from code patterns |

---

## 3. System Architecture

### Architecture Type: Monolithic Django Application ✅ Verified in Source

The MEIL ESG Control Tower is a **monolithic Django 5.2 application** with server-side rendered templates. This is **not** a decoupled SPA (Single Page Application) with a React/Vue/Angular frontend.

```
┌─────────────────────────────────────────────────────┐
│                    CLIENT BROWSER                    │
│            (HTML Templates + Bootstrap 5)            │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────┐
│              DJANGO APPLICATION SERVER               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │   Views &    │  │  Template   │  │   Static    │ │
│  │  URL Router  │  │   Engine    │  │   Files     │ │
│  │  (329 URLs)  │  │  (Jinja2    │  │  (WhiteNoise│ │
│  │              │  │   DTL)      │  │   Served)   │ │
│  └──────┬───────┘  └─────────────┘  └─────────────┘ │
│         │                                            │
│  ┌──────▼────────────────────────────────────────┐  │
│  │           SERVICE LAYER (Business Logic)       │  │
│  │  ┌──────────────┐  ┌──────────────────────┐   │  │
│  │  │ calculation_  │  │ validation_services  │   │  │
│  │  │ services.py   │  │ .py (7-layer)        │   │  │
│  │  ├──────────────┤  ├──────────────────────┤   │  │
│  │  │ ocr_services │  │ anomaly_services     │   │  │
│  │  │ .py          │  │ .py (8 rules)        │   │  │
│  │  ├──────────────┤  ├──────────────────────┤   │  │
│  │  │ scope3_      │  │ reporting_services   │   │  │
│  │  │ services.py  │  │ .py (consolidation)  │   │  │
│  │  ├──────────────┤  ├──────────────────────┤   │  │
│  │  │ submission_  │  │ auth_services.py     │   │  │
│  │  │ services.py  │  │ scope_services.py    │   │  │
│  │  ├──────────────┤  ├──────────────────────┤   │  │
│  │  │ correction_  │  │ conversion_          │   │  │
│  │  │ services.py  │  │ services.py          │   │  │
│  │  └──────────────┘  └──────────────────────┘   │  │
│  └───────────────────────┬───────────────────────┘  │
│                          │                           │
│  ┌───────────────────────▼───────────────────────┐  │
│  │              DATA LAYER (ORM)                  │  │
│  │    models.py — 5,277 lines, 34+ tables         │  │
│  │    Django ORM → PostgreSQL / SQLite             │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Why Monolithic (Not Microservices)?

| Factor | Monolithic (Our Choice) | Microservices (Alternative) |
|---|---|---|
| **Team Size** | 5 developers — suitable | Requires 15+ for effective ownership |
| **Deployment Complexity** | Single Vercel deployment | Would need Kubernetes, API Gateway, service mesh |
| **Data Consistency** | Django ORM transactions | Would need distributed transactions / sagas |
| **Development Speed** | Rapid iteration | Slower due to inter-service contracts |
| **Cost** | Free-tier Vercel deployment | Significant cloud infrastructure cost |

### Design Pattern: Service-Oriented Monolith

While the application is monolithic, it follows a **service-oriented internal architecture**:

- **Views** handle HTTP request/response only — no business logic in views
- **Service modules** (`*_services.py`) contain all business logic
- **Models** define data structure and basic validation
- **Templates** handle presentation only

This pattern is sometimes called a **"Majestic Monolith"** (DHH/Basecamp terminology) — all the organizational benefits of services without the operational complexity of distributed systems.

---

## 4. Technology Stack — Verified

### Backend Stack ✅ All Verified in `requirements.txt` and `config/settings/base.py`

| Technology | Version | Purpose | Evidence |
|---|---|---|---|
| **Python** | 3.12+ | Core language | ✅ `requirements.txt` |
| **Django** | 5.2.x | Web framework | ✅ `django>=5.2,<5.3` |
| **PostgreSQL** | 15+ (via psycopg) | Production database | ✅ `psycopg[binary]>=3.2.0` |
| **SQLite** | Default fallback | Development/Vercel | ✅ `config/settings/base.py` |
| **dj-database-url** | 2.1+ | Environment-based DB config | ✅ `dj-database-url>=2.1.0` |
| **WhiteNoise** | 6.6+ | Static file serving | ✅ `whitenoise>=6.6.0` |
| **Gunicorn** | 21.2+ | WSGI HTTP server | ✅ `gunicorn>=21.2.0` |
| **PyPDF** | 5.0+ | PDF text extraction (OCR primary) | ✅ `pypdf>=5.0.0` |
| **Pillow** | 11.0+ | Image processing for OCR | ✅ `pillow>=11.0.0` |
| **pytesseract** | 0.3.10+ | Tesseract OCR fallback | ✅ `pytesseract>=0.3.10` |
| **openpyxl** | 3.1+ | Excel export/import | ✅ `openpyxl>=3.1.0` |
| **python-dotenv** | 1.0+ | Environment configuration | ✅ `python-dotenv>=1.0.0` |

### Frontend Stack ✅ Verified in Templates

| Technology | Purpose | Evidence |
|---|---|---|
| **Django Template Language (DTL)** | Server-side rendering | ✅ `.html` template files |
| **Bootstrap 5** | CSS framework, responsive design | ✅ Template references |
| **Chart.js** | Dashboard charts and visualizations | 🔍 Inferred from dashboard views |
| **Vanilla JavaScript** | Interactive UI elements | ✅ Template scripts |

### What We Do NOT Use (Important for Jury)

| Technology | Status | Why |
|---|---|---|
| React / Vue / Angular | **Not used** | Server-side rendering is sufficient for data-entry and review workflows |
| REST API / GraphQL | **Not used** | No decoupled frontend requires API |
| Celery / Redis | **Not used** | All processing is synchronous — no background task queue |
| Docker | **Not used** | Vercel serverless deployment handles containerization |
| Machine Learning / AI Models | **Not used** | OCR uses conventional library (PyPDF + Tesseract), not AI |

### Technology Comparison Matrix

| Feature | Our Stack | Alternative A (MERN) | Alternative B (Spring Boot + React) |
|---|---|---|---|
| Language | Python 3.12 | JavaScript/TypeScript | Java 21 + JavaScript |
| Framework | Django 5.2 | Express.js + React | Spring Boot + React |
| ORM | Django ORM | Mongoose / Prisma | JPA / Hibernate |
| Template | Django Templates | React JSX | Thymeleaf / React |
| Auth | Django Auth + Custom RBAC | Passport.js / Auth0 | Spring Security |
| Calculation Precision | `decimal.Decimal` | IEEE 754 `Number` (lossy!) | `BigDecimal` |
| Admin Panel | Django Admin (free) | Must build from scratch | Must build from scratch |
| Why Not Chosen | ✅ **Chosen** | Floating-point arithmetic risks in emission calculations | Over-engineered for team of 5 |

> **Key Insight for Jury:** We chose Python/Django because `decimal.Decimal` provides exact arithmetic for emission factor calculations. JavaScript's IEEE 754 floating-point can introduce rounding errors in financial and scientific calculations (e.g., `0.1 + 0.2 !== 0.3`).

---

## 5. Database Schema — Complete Table Inventory

### Total Tables: 34+ Django Models ✅ Verified in `apps/core/models.py`

The database schema is organized across **24 development phases**, each introducing specific domain entities:

| # | Model Name | Phase | Purpose | Key Fields |
|---|---|---|---|---|
| 1 | `Role` | 01 | RBAC role definitions | code, name, is_active |
| 2 | `User` | 01 | Unified user identity (extends AbstractUser) | username, email, employee_id, department, designation |
| 3 | `UserRole` | 01 | Many-to-many user ↔ role assignment | user, role, is_primary |
| 4 | `Company` | 03 | Enterprise / holding company | name, code, legal_name, industry, status |
| 5 | `Subsidiary` | 03 | Division / subsidiary | name, code, company(FK), status |
| 6 | `Project` | 05 | Infrastructure project | name, code, subsidiary(FK), project_type, location |
| 7 | `Site` | 05 | Operational site | name, code, project(FK), site_type, gps coordinates |
| 8 | `SiteAssignment` | 03 | User ↔ Site scope binding | user, site, assigned_by |
| 9 | `SubsidiaryAssignment` | 03 | User ↔ Subsidiary scope binding | user, subsidiary |
| 10 | `ProjectAssignment` | 03 | User ↔ Project scope binding | user, project |
| 11 | `CompanyAssignment` | 03 | User ↔ Company scope binding | user, company |
| 12 | `AuthAuditLog` | 02 | Authentication & security audit trail | event_type, user, ip_address, user_agent |
| 13 | `ReportingPeriod` | 04 | Fiscal year / reporting cycle boundary | code, start_date, end_date, status (DRAFT→OPEN→CLOSED→LOCKED) |
| 14 | `ActivityCategory` | 06 | ESG activity taxonomy group | name, code, display_order |
| 15 | `Scope3Category` | 23 | GHG Protocol Scope 3 categories (1-15) | category_number, name, direction (UPSTREAM/DOWNSTREAM) |
| 16 | `UnitOfMeasure` | 06 | Physical measurement units | name, symbol, code, dimension |
| 17 | `ActivityMaster` | 06 | Authoritative ESG activity catalog | code, name, category, base_unit, scope_classification, scope3_category |
| 18 | `ActivityRecord` | 08 | Operational ESG data entry | site, reporting_period, activity, quantity, unit, measurement_date, status, validation_status |
| 19 | `Evidence` | 09 | Supporting audit documents | activity_record, file, evidence_type, file_hash(SHA-256), original_filename |
| 20 | `ValidationRule` | 10 | Data quality validation rule definitions | code, category, severity, is_blocking |
| 21 | `ValidationRun` | 10 | Validation execution history | activity_record, run_number, status, error_count, warning_count |
| 22 | `ValidationResult` | 10 | Per-rule evaluation findings | validation_run, rule, severity, field_name, message |
| 23 | `OCRRun` | 11 | OCR processing execution record | evidence, run_number, engine, status, extracted_text, confidence |
| 24 | `OCRField` | 11 | Structured fields extracted from documents | ocr_run, field_name, raw_value, normalized_value, confidence |
| 25 | `Submission` | 12 | Formal activity data submission | activity_record, site, submitted_by, status, validation_run |
| 26 | `SubmissionReview` | 13 | Governance review decisions | submission, reviewer, action (VERIFY/REQUEST_CORRECTION/EXPLAIN/ESCALATE) |
| 27 | `CorrectionRequest` | 14 | Formal correction demands | submission, reason, affected_area, status |
| 28 | `ActivityRevision` | 14 | Historical record revision snapshots | activity_record, revision_number, quantity, changed_fields |
| 29 | `AnomalyRule` | 15 | Anomaly detection rule configurations | code, category, threshold_percentage, rule_parameters |
| 30 | `AnomalyDetectionRun` | 15 | Anomaly scan execution history | records_evaluated, anomalies_detected, scope_type |
| 31 | `AnomalyRecord` | 15 | Flagged anomaly findings | activity_record, rule, observed_value, baseline_value, deviation_percentage |
| 32 | `Supplier` | 16 | Vendor / supplier master | supplier_code, name, supplier_type, environmental_certifications |
| 33 | `ProcurementRecord` | 16 | Commercial purchasing transactions | procurement_number, supplier, total_amount, category, status |
| 34 | `ProcurementItem` | 16 | Procurement line items | item_name, quantity, unit_price, scope3_category |
| 35 | `Carrier` | 17 | Transport logistics carrier master | carrier_code, name, carrier_type |
| 36 | `Vehicle` | 17 | Vehicle fleet master | vehicle_identifier, registration_number, fuel_type, ownership_type |
| 37 | `Shipment` | 17 | Cargo consignment entity | shipment_reference, material_description, weight_net |
| 38 | `TransportRecord` | 17 | Transport movement event | transport_reference, origin, destination, distance, scope_category |
| 39 | `EmissionFactor` | 24 | Regulatory emission factor registry | code, activity, factor_value, factor_unit, source, effective_year |
| 40 | `CalculationResult` | 24 | Immutable ESG metric calculation output | activity_record, raw_quantity, normalized_quantity, factor_value_applied, calculated_value, result_unit |

### Entity Relationship Summary

```
Company (1) ──→ (*) Subsidiary ──→ (*) Project ──→ (*) Site
                                                       │
                                                       ▼
                                              ActivityRecord
                                              ┌─────────────┐
                                              │ quantity     │
                                              │ unit         │
                                              │ activity(FK) │◄── ActivityMaster
                                              │ site(FK)     │
                                              │ period(FK)   │◄── ReportingPeriod
                                              └──────┬───────┘
                           ┌──────────────┬──────────┼──────────┬──────────────┐
                           ▼              ▼          ▼          ▼              ▼
                       Evidence    ValidationRun  Submission  AnomalyRecord  CalculationResult
                         │                                                     │
                         ▼                                                     ▼
                       OCRRun                                           EmissionFactor
                         │
                         ▼
                      OCRField
```

### Database Integrity Constraints ✅ Verified

| Constraint Type | Example | Evidence |
|---|---|---|
| `CheckConstraint` | `quantity >= 0` on ActivityRecord | ✅ `check_activity_record_quantity_positive` |
| `CheckConstraint` | `file_size > 0` on Evidence | ✅ `check_evidence_file_size_positive` |
| `CheckConstraint` | `total_amount >= 0` on Procurement | ✅ `check_procurement_amt_non_negative` |
| `UniqueConstraint` | (activity_record, submission_number) | ✅ `uniq_sub_record_number` |
| `UniqueConstraint` | (evidence, run_number) on OCRRun | ✅ `uniq_ocr_run_evidence_number` |
| `PROTECT` foreign keys | Site → Project → Subsidiary → Company | ✅ `on_delete=models.PROTECT` |
| Custom indexes | 40+ named indexes for query optimization | ✅ All models have `Meta.indexes` |

---

## 6. Core Business Logic — Data Pipeline

### The ESG Data Lifecycle ✅ Verified in Source

```
Phase 08: DATA ENTRY (ActivityRecord created by Site Manager)
    │
    ▼
Phase 09: EVIDENCE UPLOAD (Evidence linked to ActivityRecord)
    │
    ▼
Phase 11: OCR EXTRACTION (OCRRun processes Evidence → OCRFields extracted)
    │
    ▼
Phase 10: VALIDATION (ValidationRun evaluates 7 layers of data quality rules)
    │
    ▼
Phase 15: ANOMALY DETECTION (8 deterministic rules flag suspicious patterns)
    │
    ▼
Phase 12: SUBMISSION (Site Manager formally submits validated record)
    │
    ▼
Phase 13: REVIEW (Subsidiary Manager verifies, requests correction, or escalates)
    │
    ▼
Phase 14: CORRECTION & RESUBMISSION (if correction requested)
    │
    ▼
Phase 24: CALCULATION (EmissionFactor × Quantity = tCO₂e)
    │
    ▼
Phase 20: CONSOLIDATION & REPORTING (Enterprise aggregation → BRSR)
    │
    ▼
Phase 20: TRACE THIS NUMBER (6-tier audit lineage drill-down)
```

### Record Status Lifecycle ✅ Verified in `RecordStatus` choices

```
DRAFT → READY → SUBMITTED → VERIFIED → APPROVED
                    │                        
                    └→ REJECTED (returns to DRAFT for correction)
```

---

## 7. Calculation Engine — Emission Factor Mathematics

### Core Formula ✅ Verified in `calculation_services.py`

```
tCO₂e = Quantity × Emission Factor ÷ 1,000
```

Where:
- **Quantity**: Measured consumption (e.g., 500 Liters of diesel)
- **Emission Factor**: Regulatory coefficient (e.g., 2.68 kg CO₂e per Liter for diesel)
- **÷ 1,000**: Converts kg CO₂e → tCO₂e (metric tonnes)

### Verified Emission Factors ✅ From `STANDARD_FACTOR_DEFAULTS`

| Activity Code | Factor Value | Factor Unit | Scope | Source |
|---|---|---|---|---|
| FUEL-DIESEL-STAT | **2.680000** | kg CO₂e / L | Scope 1 | India GHG Program / IPCC 2006 |
| FUEL-DIESEL-MOB | **2.680000** | kg CO₂e / L | Scope 1 | India GHG Program / IPCC 2006 |
| FUEL-PETROL-MOB | **2.310000** | kg CO₂e / L | Scope 1 | India GHG Program / IPCC 2006 |
| ELEC-GRID | **0.820000** | kg CO₂e / kWh | Scope 2 | CEA CO₂ Baseline Database v19 |
| ELEC-RENEWABLE-CAPTIVE | **0.000000** | kg CO₂e / kWh | Scope 2 | GHG Protocol Scope 2 Guidance |
| TRANSPORT-COMMERCIAL-FREIGHT | **96.000000** | kg CO₂e / t | Scope 3.4 | India GHG / DEFRA 2024 |
| WASTE-HAZARDOUS | **0.450000** | kg CO₂e / kg | Scope 3.5 | UK DEFRA / IPCC 2006 |
| PURCHASED-GOODS-STEEL | **1,820.000000** | kg CO₂e / t | Scope 3.1 | India GHG / World Steel 2024 |
| TRAVEL-AIR-DOMESTIC | **0.121000** | kg CO₂e / p-km | Scope 3.6 | UK DEFRA 2024 |

### Calculation Pipeline Steps ✅ Verified in Source

1. **Factor Selection** (`select_emission_factor()`):
   - Match by exact activity FK or activity code
   - Try aliases (e.g., `ACT-GENSET-DIESEL-LIVE` → `FUEL-DIESEL-STAT`)
   - Auto-bootstrap from `STANDARD_FACTOR_DEFAULTS` if no database entry exists

2. **Unit Normalization** (`conversion_services.py`):
   - If entered unit ≠ factor's input unit, apply conversion factor
   - Example: User enters 5,000 mL → convert to 5.0 L before applying kg CO₂e/L factor

3. **Calculation**:
   ```python
   raw_emissions_kg = normalized_quantity * factor_value  # kg CO₂e
   result_tco2e = raw_emissions_kg / Decimal('1000')      # tCO₂e
   ```

4. **Result Persistence**:
   - Creates immutable `CalculationResult` record
   - Snapshots: `factor_value_applied`, `factor_source_applied`, `formula_repr`
   - Sets `is_latest = True` (previous results marked `is_latest = False`)

### Precision Guarantee ✅ Verified

```python
# From models.py
quantity = models.DecimalField(max_digits=18, decimal_places=4)
factor_value = models.DecimalField(max_digits=16, decimal_places=6)
calculated_value = models.DecimalField(max_digits=16, decimal_places=4)
```

All arithmetic uses Python's `decimal.Decimal` — **never** floating-point `float`.

### Calculation Example (Worked)

```
Input: 500 L of Diesel (Stationary Combustion at Site POL-001)
Factor: 2.680000 kg CO₂e / L (IPCC 2006)

Step 1: Unit check → 500 L matches factor input unit (L) → no conversion needed
Step 2: 500 × 2.680000 = 1,340.0000 kg CO₂e
Step 3: 1,340.0000 ÷ 1,000 = 1.3400 tCO₂e

Stored: CalculationResult(calculated_value=1.3400, result_unit="tCO₂e", status="CALCULATED")
        formula_repr = "500.0000 L × 2.680000 kg CO₂e/L ÷ 1000 = 1.3400 tCO₂e"
```

---

## 8. OCR & Document Intelligence Pipeline

### Architecture ✅ Verified in `ocr_services.py`

The OCR pipeline uses a **Provider Abstraction Pattern** — not an AI/ML model:

```
Evidence Upload
    │
    ▼
get_ocr_provider(file_extension)  ←── Factory Function
    │
    ├── .pdf → PyPDFTextProvider (primary)
    │          Uses: pypdf library
    │          Method: Text layer extraction from digital PDFs
    │
    └── .jpg/.jpeg/.png/.tiff/.bmp → TesseractOCRProvider (fallback)
                                      Uses: pytesseract + Pillow
                                      Method: Image → Text via Tesseract OCR engine
```

### Provider Details

#### PyPDFTextProvider ✅ Verified

```python
class PyPDFTextProvider(BaseOCRProvider):
    name = "pypdf-text-extractor"
    # Extracts text from PDF text layer using pypdf library
    # Returns: extracted_text, page_count, per-page data, confidence
    # Works for: Digital/native PDFs with embedded text
```

- **NOT an AI model** — extracts existing text layer from PDFs
- Reports 100% confidence for native text PDFs
- Page-by-page text extraction with structured metadata

#### TesseractOCRProvider ✅ Verified

```python
class TesseractOCRProvider(BaseOCRProvider):
    name = "tesseract-ocr"
    # Uses pytesseract (Google Tesseract OCR engine) for image → text
    # Graceful degradation: checks if Tesseract binary is installed
    # Returns: word-level confidence scores averaged
```

- Uses **Google Tesseract** — an open-source OCR engine, not a neural AI model
- Calculates per-word confidence scores
- Handles graceful unavailability (OCR binary not installed on Vercel)

### Structured Field Extraction ✅ Verified in `extract_structured_fields()`

After raw text is extracted, the system applies **deterministic regex pattern matching** to extract structured fields:

| Field Extracted | Regex Pattern (Simplified) | Confidence |
|---|---|---|
| Invoice Number | `Invoice No/Number/# + alphanumeric` | 92% |
| Quantity + Unit | `number + (kWh|L|MT|kg|m3|GJ)` | 94% |
| Invoice Date | `Date: YYYY-MM-DD or DD/MM/YYYY` | 88% |
| Billing Period | `Period: date_range` | 82% |
| Total Amount | `Total/Grand Total: Rs/INR + number` | 90% |
| Vendor Name | `Supplier/Vendor: name` | 80% |

### OCR vs Activity Record Comparison ✅ Verified

After extraction, the system compares OCR-extracted values against manually entered ActivityRecord data:

| Comparison Status | Meaning | Badge Color |
|---|---|---|
| `MATCH` | Values agree within tolerance | ✅ Green |
| `MINOR_DIFFERENCE` | Small variance (< 5%) | ⚠️ Yellow |
| `SIGNIFICANT_DIFFERENCE` | Large variance (> 5%) | 🔴 Red |
| `MISSING_OCR_VALUE` | OCR couldn't extract the field | ⚪ Grey |

---

## 9. Validation Engine — 7-Layer Architecture

### Validation Categories ✅ Verified in `ValidationCategory` choices

| Layer | Category | Description | Example Rule |
|---|---|---|---|
| 1 | **STRUCTURAL** | Required fields, data type, format | "Quantity must be a positive number" |
| 2 | **SCOPE** | Organizational hierarchy alignment | "Site's company must match reporting period's company" |
| 3 | **PERIOD** | Temporal boundary enforcement | "Measurement date must fall within reporting period" |
| 4 | **ACTIVITY** | Activity Master taxonomy compliance | "Unit must be in activity's allowed units list" |
| 5 | **EVIDENCE** | Audit evidence requirements | "High-impact activities require supporting evidence" |
| 6 | **CONSISTENCY** | Data range and historical consistency | "Quantity exceeds reasonable operational threshold" |
| 7 | **WORKFLOW** | Submission readiness checks | "Record must pass validation before submission" |

### Validation Severity Levels ✅ Verified

| Severity | Effect | Badge |
|---|---|---|
| **ERROR** | **Blocks progression** — record cannot be submitted | 🔴 Red |
| **WARNING** | Advises review but does not block | ⚠️ Yellow |
| **INFO** | Informational observation | ℹ️ Blue |

### Validation Run Model ✅ Verified

Each validation execution creates an immutable `ValidationRun` record with:
- `run_number` (sequential per record)
- `total_rules_evaluated`
- `error_count`, `warning_count`, `info_count`
- `execution_duration_ms`
- `rule_version_snapshot` (JSON preserving exact rule versions for audit)

### Server-Side Validation (Model.clean()) ✅ Verified

The `ActivityRecord.clean()` method enforces 5 constraints before any save:

1. **Quantity non-negative**: `quantity >= 0` (also enforced by `CheckConstraint`)
2. **Unit compatibility**: Unit must be in activity's `base_unit` or `allowed_units`
3. **Period boundary**: `measurement_date` between `reporting_period.start_date` and `end_date`
4. **Organizational alignment**: Site's company must match period's company
5. **Activity status**: Activity master must be `ACTIVE`

---

## 10. Anomaly Detection Engine

### Fundamental Distinction ✅ Verified in `anomaly_services.py`

> **Validation** = "Is this data structurally and logically acceptable?"
> **Anomaly Detection** = "Is this data unusual or suspicious compared with expected patterns?"

Anomalies are **review signals** — they NEVER cause automatic rejection.

### 8 Anomaly Rules ✅ Verified in `ensure_default_anomaly_rules()`

| Code | Category | Severity | Threshold | Description |
|---|---|---|---|---|
| `HIST_SPIKE_100` | Historical Spike | HIGH | >100% above average | Consumption more than double historical baseline |
| `HIST_DROP_50` | Historical Drop | MEDIUM | >50% below average | Consumption fell by more than half |
| `PERIOD_VAR_50` | Period Variance | MEDIUM | >50% from previous | Month-over-month change exceeds 50% |
| `DUPLICATE_RECORD` | Duplicate Suspect | HIGH | Exact match | Same date + quantity + unit + activity + site |
| `THRESHOLD_BREACH` | Threshold Breach | HIGH | Configurable | Exceeds operational maximum (default: 50,000) |
| `INTENSITY_OUTLIER` | Intensity Anomaly | LOW | >100% | Unusually high consumption density |
| `OCR_MISMATCH` | OCR Discrepancy | HIGH | >5% variance | OCR-extracted value differs from entered value |
| `MISSING_EVIDENCE` | Missing Evidence | HIGH | Boolean | Material activity lacks mandatory audit documentation |

### Historical Baseline Computation ✅ Verified in `compute_historical_baseline()`

```python
# Invariants:
# 1. Same site + same activity + same unit (strict matching)
# 2. Excludes current record being evaluated
# 3. Minimum 2 historical records required
# 4. Returns (baseline_average, count, status)
```

### Anomaly Review Lifecycle ✅ Verified

```
OPEN → ACKNOWLEDGED → EXPLAINED → RESOLVED
                                  DISMISSED
```

Each transition requires **mandatory justification commentary** and is logged to `AuthAuditLog`.

---

## 11. Scope 3 Value Chain Engine

### All 15 GHG Protocol Categories ✅ Verified in `scope3_services.py`

**Upstream (Categories 1-8):**

| Cat # | Name | Example for MEIL |
|---|---|---|
| 1 | Purchased Goods and Services | Structural steel, cement, lubricants |
| 2 | Capital Goods | Heavy cranes, batching plants, transformers |
| 3 | Fuel- and Energy-Related Activities | WTT upstream fuel extraction, T&D losses |
| 4 | Upstream Transportation and Distribution | Commercial road freight, rail freight |
| 5 | Waste Generated in Operations | Hazardous waste incineration, construction scrap |
| 6 | Business Travel | Commercial flights, passenger rail, taxis |
| 7 | Employee Commuting | Public buses, personal vehicles, trains |
| 8 | Upstream Leased Assets | Leased regional offices, rented equipment |

**Downstream (Categories 9-15):**

| Cat # | Name | Example for MEIL |
|---|---|---|
| 9 | Downstream Transportation and Distribution | Product delivery logistics |
| 10 | Processing of Sold Products | End-user processing |
| 11 | Use of Sold Products | Operational use by clients |
| 12 | End-of-Life Treatment | Demolition waste |
| 13 | Downstream Leased Assets | Leased-out facilities |
| 14 | Franchises | N/A for MEIL |
| 15 | Investments | Portfolio emissions |

### Calculation Methods ✅ Verified

| Method | Code | Used For |
|---|---|---|
| Supplier-Specific | `SUPPLIER_SPECIFIC` | Exact emission data from supplier |
| Average Data | `AVERAGE_DATA` | Industry-average emission factors |
| Spend-Based | `SPEND_BASED` | Economic input-output factors (₹ → tCO₂e) |
| Distance-Based | `DISTANCE_BASED` | Transport (ton-km × emission factor) |
| Fuel-Based | `FUEL_BASED` | Direct fuel consumption for transport |
| Waste-Type Specific | `WASTE_TYPE_SPECIFIC` | Waste treatment method factors |
| Hybrid | `HYBRID` | Combination of multiple methods |

---

## 12. Security, RBAC & Authorization

### 5 RBAC Roles ✅ Verified in `Role.Code` choices

| Role | Access Scope | Key Permissions |
|---|---|---|
| **SITE_MANAGER** | Assigned sites only | Enter data, upload evidence, submit records |
| **SUBSIDIARY_MANAGER** | Assigned subsidiaries + child sites | Review submissions, request corrections, verify |
| **ESG_MANAGER** | Enterprise-wide | Corporate dashboard, BRSR reporting, factor management |
| **AUDITOR** | Enterprise-wide (READ ONLY) | View all data, trace lineage — cannot modify anything |
| **MEIL_OPERATOR** | Enterprise-wide (ADMIN) | Full platform administration |

### Object-Level Authorization ✅ Verified in `scope_services.py`

Every query is scoped to the user's organizational assignments:

```python
# Anti-IDOR (Insecure Direct Object Reference) Pattern:
def get_accessible_sites(user):
    if user.has_role(Role.Code.SITE_MANAGER):
        return Site.objects.filter(id__in=SiteAssignment.objects.filter(user=user).values('site_id'))
    elif user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        subs = get_accessible_subsidiaries(user)
        return Site.objects.filter(project__subsidiary__in=subs)
    # ... enterprise roles get broader access
```

### Security Headers ✅ Verified in `production.py`

| Header | Value | Purpose |
|---|---|---|
| `SECURE_SSL_REDIRECT` | True | Force HTTPS |
| `SESSION_COOKIE_SECURE` | True | Cookie only over HTTPS |
| `CSRF_COOKIE_SECURE` | True | CSRF token over HTTPS |
| `SESSION_COOKIE_HTTPONLY` | True | Prevent XSS cookie theft |
| `X_FRAME_OPTIONS` | DENY | Prevent clickjacking |
| `SECURE_HSTS_SECONDS` | 31,536,000 (1 year) | HTTP Strict Transport Security |
| `SECURE_CONTENT_TYPE_NOSNIFF` | True | Prevent MIME sniffing |
| `SECURE_BROWSER_XSS_FILTER` | True | Browser XSS protection |
| `SECURE_HSTS_PRELOAD` | True | HSTS preload list |

### Evidence File Security ✅ Verified

1. **SHA-256 hash** stored on every evidence file (`file_hash` field) for tamper detection
2. **Traversal-proof upload paths**: `evidence/<site_code>/<period_code>/rec_<id>/<uuid>_<filename>`
3. **Filename sanitization**: `get_valid_filename()` + regex stripping + UUID prefix

### Audit Trail ✅ Verified in `AuthAuditLog`

Every significant action is logged:
- Login/logout/failed login
- Unauthorized access attempts
- Submission/review/correction actions
- Anomaly review actions
- Data modifications

Each entry records: `user`, `ip_address`, `user_agent`, `event_type`, `resource_accessed`, `details`, `success`.

---

## 13. Submission, Review & Correction Workflow

### Phase 12: Submission ✅ Verified

```python
def submit_activity_record(user, record):
    # 1. Verify user has submission authority
    # 2. Verify record status allows submission
    # 3. Verify reporting period is OPEN
    # 4. Execute validation run (must pass without blocking errors)
    # 5. Create Submission record atomically
    # 6. Lock ActivityRecord (status = SUBMITTED)
    # 7. Log to AuthAuditLog
```

### Phase 13: Review ✅ Verified

Subsidiary Manager can take 4 actions on a submission:

| Action | Effect | Next Status |
|---|---|---|
| **VERIFY** | Approves the data | VERIFIED |
| **REQUEST_CORRECTION** | Returns to site manager with specific instructions | CORRECTION_REQUESTED |
| **EXPLAIN** | Request explanation from site manager | EXPLAINED |
| **ESCALATE** | Escalate to ESG Manager for governance resolution | ESCALATED |

### Phase 14: Correction & Resubmission ✅ Verified

1. `CorrectionRequest` created with: `reason`, `required_correction`, `affected_area`
2. ActivityRecord unlocked → Site Manager can edit
3. `ActivityRevision` snapshot preserves pre-correction state
4. After correction: new `Submission` created (linked to previous via `parent_submission`)
5. Entire lifecycle audit trail preserved

---

## 14. Reporting & Consolidation Engine

### Consolidated Enterprise Report ✅ Verified in `reporting_services.py`

```python
def get_consolidated_report(user, period_id=None, subsidiary_id=None, scope_filter=None):
    # 1. Resolve accessible reporting period
    # 2. Resolve accessible subsidiaries
    # 3. Query scoped ActivityRecords (respects RBAC)
    # 4. Apply emission factors per activity
    # 5. Aggregate by: Scope 1, Scope 2, Scope 3, Water, Waste
    # 6. Return: totals, breakdowns by subsidiary, category trends
```

### BRSR Alignment 📚 External Research

The reporting structure maps to SEBI BRSR disclosures:
- **Principle 6**: Environmental metrics (energy, water, waste, emissions)
- **Section A**: General disclosures (company details, products, operations)
- **Section B**: Management and process disclosures
- **Section C**: Principle-wise performance disclosures

---

## 15. 6-Tier "Trace This Number" Audit Lineage

### Architecture ✅ Verified in `reporting_services.py` docstring

| Tier | Level | What It Shows |
|---|---|---|
| **1** | Report / BRSR Disclosure | Final aggregated ESG metric in the BRSR report |
| **2** | Enterprise / Subsidiary Consolidation | Breakdown by subsidiary, project, site |
| **3** | Verified Submission & Review | Submission record, reviewer decision, correction history |
| **4** | Operational Telemetry & Validation | ActivityRecord data, validation run results, anomaly flags |
| **5** | Supporting Audit Evidence | Evidence files, SHA-256 hash, OCR extracted fields |
| **6** | Chronological Audit Trail | Complete AuthAuditLog timeline of all actions |

### Trace Example

```
BRSR Report: "Scope 1 Emissions = 127.34 tCO₂e"
  └── Subsidiary: "MEIL Power Division" = 89.21 tCO₂e
      └── Site: "Polavaram Dam - Unit 3" = 45.12 tCO₂e
          └── Submission #47: "Verified by Sub. Manager Patnaik on 2026-03-15"
              └── ActivityRecord: "500 L Diesel, 2026-03-10"
                  ├── Validation: "VALID (7 rules passed, 0 errors)"
                  ├── Anomaly: "No anomalies detected"
                  ├── Evidence: "fuel_invoice_march_2026.pdf (SHA-256: a7b2c9...)"
                  │   └── OCR: "Quantity: 500 L, Invoice: INV-2026-0312 (MATCH)"
                  └── Calculation: "500 × 2.68 ÷ 1000 = 1.34 tCO₂e"
```

---

## 16. Testing Strategy

### Test Coverage ✅ Verified — 45 Test Files

| Test File | Phase | What It Tests |
|---|---|---|
| `test_phase01_foundation.py` | 01 | Core models, user creation, role assignment |
| `test_auth.py` | 02 | Login, logout, password change, session management |
| `test_rbac.py` | 02 | Role-based access control enforcement |
| `test_organization.py` | 03 | Company, subsidiary hierarchy CRUD |
| `test_reporting_periods.py` | 04 | Reporting period lifecycle management |
| `test_phase05_projects_sites.py` | 05 | Project and site management |
| `test_phase06_activity_master.py` | 06 | Activity taxonomy and unit configuration |
| `test_phase07_site_manager_dashboard.py` | 07 | Site manager workspace views |
| `test_phase08_esg_data_entry.py` | 08 | Activity record CRUD, form validation |
| `test_phase09_evidence_management.py` | 09 | Evidence upload, retirement, hash verification |
| `test_phase10_validation_engine.py` | 10 | 7-layer validation engine (46,764 bytes — largest test!) |
| `test_phase11_ocr_engine.py` | 11 | OCR provider abstraction, text extraction |
| `test_phase12_submission_workflow.py` | 12 | Submission eligibility, atomic creation, withdrawal |
| `test_phase13_subsidiary_review.py` | 13 | Review actions, status transitions |
| `test_phase14_corrections_resubmission.py` | 14 | Correction request lifecycle, resubmission |
| `test_phase15_anomaly_detection.py` | 15 | Anomaly rules, baseline computation, detection |
| `test_phase16_supplier_procurement.py` | 16 | Supplier master, procurement transactions |
| `test_phase17_transport_logistics.py` | 17 | Transport records, vehicle/carrier management |
| `test_phase20_workflow_and_trace.py` | 20 | End-to-end workflow, traceability |
| `test_phase23_scope3_engine.py` | 23 | Scope 3 category classification, calculations |
| `test_phase24_calculation_engine.py` | 24 | Emission factor selection, unit conversion, precision |
| `test_live_e2e.py` | E2E | Full browser-level end-to-end acceptance |
| `test_security.py` | Security | Security headers, CSRF, XSS protection |
| `test_object_access.py` | RBAC | Object-level authorization verification |
| `test_seed_esg_demo_data.py` | Data | Demo data seeding verification |

### Testing Approach

| Layer | Framework | Coverage |
|---|---|---|
| **Unit Tests** | Django TestCase | Service functions, model validation |
| **Integration Tests** | Django TestCase + Client | View responses, form handling, workflow chains |
| **Live Acceptance** | Selenium / Browser automation | End-to-end HTTP workflows |
| **Security Tests** | Django TestCase | Header verification, CSRF, authentication |

---

## 17. Deployment Architecture

### Vercel Serverless ✅ Verified in `config/settings/base.py`

The application is deployed on **Vercel** as a serverless Django application:

```
┌──────────────────────────────────────────────┐
│                    VERCEL                     │
│  ┌─────────────────────────────────────────┐ │
│  │  Serverless Function (Python Runtime)   │ │
│  │  Django WSGI Application                │ │
│  │  WhiteNoise Static File Serving         │ │
│  └──────────────────┬──────────────────────┘ │
│                     │                         │
│  ┌──────────────────▼──────────────────────┐ │
│  │  Database                               │ │
│  │  SQLite (copied to /tmp for serverless) │ │
│  │  OR PostgreSQL (via DATABASE_URL)       │ │
│  └─────────────────────────────────────────┘ │
│                                               │
│  ┌─────────────────────────────────────────┐ │
│  │  Static Files: WhiteNoise CDN           │ │
│  │  Media Files: /tmp (serverless context) │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

### Vercel-Specific Adaptations ✅ Verified

1. **Read-only filesystem**: SQLite and media files copied to `/tmp` at startup
2. **Database URL**: `dj-database-url` reads `DATABASE_URL` environment variable
3. **Static files**: WhiteNoise serves compressed, hashed static assets
4. **Secret key**: Stable production key configured via environment variables

---

## 18. Individual Team Member Preparation

### Team Member 1: Rudra Narayan Dash — Backend Architecture & Database Lead

**Likely Ownership Areas:**
- Django project structure and settings configuration
- Database schema design (models.py — 5,277 lines, 34+ tables)
- ORM query optimization and index design
- Organization hierarchy (Company → Subsidiary → Project → Site)

**Probable Questions for Rudra N. Dash:**

1. **Q: Why did you choose Django over Flask or FastAPI?**
   A: Django provides an integrated ecosystem — ORM, admin panel, auth system, form handling, template engine — all built-in. For a data-heavy enterprise application with 34+ tables, Django's ORM with migrations, model validation, and admin interface saved significant development time compared to Flask (which requires manually selecting and integrating each component). FastAPI is optimized for API-first applications; our server-rendered approach doesn't need it.

2. **Q: How many database tables does your system have?**
   A: 34+ Django models (40 counting including through tables and TextChoices enums), organized across 24 development phases. The largest model file is 5,277 lines.

3. **Q: Why SQLite in development but PostgreSQL in production?**
   A: SQLite is zero-configuration — ideal for development and Vercel's serverless environment. PostgreSQL provides concurrent write support, better performance at scale, JSONB indexing, and full-text search for production workloads. We use `dj-database-url` to switch transparently via environment variables.

4. **Q: How do you prevent deletion of referenced records?**
   A: We use `on_delete=models.PROTECT` for all critical foreign keys (Site → Project → Subsidiary → Company). This prevents cascading deletions that could destroy audit history. Less critical references use `SET_NULL` to preserve the parent record.

5. **Q: How do you handle database integrity?**
   A: Through 4 layers: (1) Django model-level `clean()` validation, (2) `CheckConstraint` for invariants like `quantity >= 0`, (3) `UniqueConstraint` for business uniqueness rules, and (4) named database indexes for query performance.

---

### Team Member 2: Abhijeet Patnaik — Validation, Anomaly Detection & Data Quality Lead

**Likely Ownership Areas:**
- 7-layer validation engine (validation_services.py)
- 8-rule anomaly detection engine (anomaly_services.py)
- Data quality assurance workflows
- Historical baseline computation

**Probable Questions for Abhijeet Patnaik:**

1. **Q: What's the difference between validation and anomaly detection?**
   A: Validation asks "Is this data structurally and logically acceptable?" — it's a gate that blocks progression if errors exist. Anomaly detection asks "Is this data unusual compared to historical patterns?" — it produces review signals but NEVER automatic rejections. A record can be valid but anomalous (e.g., correctly formatted but triple the historical average).

2. **Q: How many validation layers do you have?**
   A: Seven: (1) Structural integrity — required fields, data types; (2) Organizational scope — company/subsidiary alignment; (3) Reporting period — temporal boundary enforcement; (4) Activity taxonomy — unit compatibility with ActivityMaster; (5) Evidence — audit documentation requirements; (6) Data consistency — range and historical checks; (7) Workflow readiness — submission eligibility.

3. **Q: How does your baseline calculation work?**
   A: We compute a rolling historical average using `compute_historical_baseline()`. Invariants: strict matching on same site + same activity + same unit; excludes the current record; requires minimum 2 historical records. If insufficient data exists, we return "Baseline unavailable" rather than fabricating a false baseline.

4. **Q: What happens when an anomaly is detected?**
   A: It creates an `AnomalyRecord` with status=OPEN. It does NOT reject or block the record. The anomaly follows a review lifecycle: OPEN → ACKNOWLEDGED → EXPLAINED → RESOLVED/DISMISSED. Each transition requires mandatory justification commentary and is logged to `AuthAuditLog`.

---

### Team Member 3: Rudra Narayan Pradhan — OCR, Evidence Management & Document Processing Lead

**Likely Ownership Areas:**
- OCR pipeline (ocr_services.py)
- Evidence upload, retirement, and hash verification
- Structured field extraction (regex pattern matching)
- OCR vs ActivityRecord comparison engine

**Probable Questions for Rudra N. Pradhan:**

1. **Q: Is your OCR AI-based?**
   A: No. Our OCR uses **conventional library-based text extraction**, not an AI/ML model. The primary provider (PyPDFTextProvider) extracts the existing text layer from digital PDFs using the pypdf library. The fallback provider (TesseractOCRProvider) uses Google's open-source Tesseract OCR engine for scanned images. Structured field extraction uses deterministic regex pattern matching — not NLP or machine learning.

2. **Q: How do you extract structured fields from raw text?**
   A: We use `extract_structured_fields()` which applies curated regex patterns to identify: invoice numbers, quantities with units, dates, billing periods, total amounts, and vendor names. Each extracted field gets a confidence score (80-94%) and is stored as an `OCRField` record linked to the `OCRRun`.

3. **Q: How do you verify file integrity?**
   A: Every uploaded evidence file gets a SHA-256 cryptographic hash stored in the `file_hash` field. Upload paths use UUID prefixes and filename sanitization to prevent path traversal attacks. The format is: `evidence/<site_code>/<period_code>/rec_<id>/<uuid>_<safe_filename>`.

4. **Q: What file types do you support?**
   A: PDF (primary — text extraction via pypdf), JPG/JPEG/PNG/TIFF/BMP (image OCR via Tesseract). We also have a `MockOCRProvider` for automated testing that produces deterministic output without requiring actual files.

---

### Team Member 4: Suman Sahu — Calculation Engine, Scope 3 & Reporting Lead

**Likely Ownership Areas:**
- Emission calculation engine (calculation_services.py)
- Unit conversion services (conversion_services.py)
- Scope 3 value chain engine (scope3_services.py)
- Reporting and consolidation (reporting_services.py)
- 6-tier "Trace This Number" audit lineage

**Probable Questions for Suman Sahu:**

1. **Q: Walk me through an emission calculation.**
   A: The formula is `tCO₂e = Quantity × Emission Factor ÷ 1,000`. For example, 500 L of diesel × 2.68 kg CO₂e/L = 1,340 kg CO₂e ÷ 1,000 = 1.34 tCO₂e. The engine performs: (1) factor selection from database (with alias matching and auto-bootstrap), (2) unit normalization if entered unit ≠ factor input unit, (3) multiplication using `decimal.Decimal` for exact arithmetic, (4) immutable `CalculationResult` creation with factor snapshot for reproducibility.

2. **Q: Why `decimal.Decimal` instead of `float`?**
   A: IEEE 754 floating-point has precision issues — `0.1 + 0.2 ≠ 0.3` in JavaScript and Python `float`. For financial and scientific calculations like emission accounting where regulatory precision matters, `decimal.Decimal` provides exact arithmetic. Our factors have 6 decimal places (`2.680000`), quantities have 4 (`500.0000`), and results have 4 (`1.3400`).

3. **Q: What are your emission factor sources?**
   A: We use: (1) **IPCC 2006 Guidelines** for stationary and mobile combustion factors; (2) **CEA CO₂ Baseline Database v19** for India's national weighted-average grid emission factor (0.82 kg CO₂e/kWh); (3) **India GHG Program** for India-specific factors; (4) **UK DEFRA 2024** for Scope 3 categories (transport, waste, travel). All factors are database-managed with version tracking.

4. **Q: How do you handle Scope 3?**
   A: We implement all 15 GHG Protocol Corporate Value Chain categories. Activities are classified via `scope_classification` on `ActivityMaster` and bound to `Scope3Category` (category_number 1-15). Different calculation methods apply per category — spend-based for Cat 1, distance-based for Cat 4, waste-type-specific for Cat 5. The Scope 3 engine supports supplier-specific, average data, hybrid, spend-based, distance-based, fuel-based, and waste-type-specific methods.

---

### Team Member 5: Pritam Kumar Satapathy — RBAC, Workflow, Submission & Security Lead

**Likely Ownership Areas:**
- Authentication & authorization (auth_services.py)
- RBAC decorators and mixins
- Submission workflow (submission_services.py)
- Review workflow (review_services.py)
- Correction and resubmission (correction_services.py)
- Security headers and production hardening

**Probable Questions for Pritam Kumar Satapathy:**

1. **Q: How does your role-based access control work?**
   A: We use 5 roles: SITE_MANAGER, SUBSIDIARY_MANAGER, ESG_MANAGER, AUDITOR, MEIL_OPERATOR. Access is controlled at two levels: (1) **Role-level** — `@role_required()` decorator checks if user holds required role; (2) **Object-level** — every queryset is scoped by organizational assignment (e.g., Site Managers only see their assigned sites, never other sites).

2. **Q: How do you prevent unauthorized access to another site's data?**
   A: Through queryset scoping in service functions. For example, `get_accessible_sites(user)` returns only sites where the user has an explicit `SiteAssignment`. Views never query `Site.objects.all()` — they always call the scoped service function. This prevents IDOR (Insecure Direct Object Reference) attacks.

3. **Q: Explain the submission workflow.**
   A: (1) Site Manager enters data → (2) Uploads evidence → (3) System validates (must pass without blocking errors) → (4) Site Manager clicks Submit → (5) System creates atomic `Submission` record + locks ActivityRecord → (6) Subsidiary Manager reviews → (7) VERIFY (approved), REQUEST_CORRECTION (returned), EXPLAIN (request explanation), or ESCALATE (to ESG Manager) → (8) If correction requested: CorrectionRequest created, record unlocked, Site Manager corrects and resubmits.

4. **Q: What security measures do you implement?**
   A: (1) HTTPS enforced via `SECURE_SSL_REDIRECT`; (2) Session cookies are HttpOnly + Secure + SameSite=Lax; (3) HSTS with 1-year max-age and preload; (4) X-Frame-Options: DENY against clickjacking; (5) Content-Type-NoSniff; (6) SHA-256 file hash for evidence tampering detection; (7) UUID-prefixed, sanitized upload paths; (8) Complete AuthAuditLog for every security-relevant action.

---

## 19. Probable Jury Questions & Model Answers

### Architecture & Design

**Q1: Why Django and not a modern JavaScript framework like Next.js?**

A: Three reasons: (1) Python's `decimal.Decimal` provides exact arithmetic for emission calculations — JavaScript's IEEE 754 floating-point introduces rounding errors; (2) Django provides batteries-included ORM, admin panel, auth, and migrations — perfect for a data-heavy enterprise application; (3) Server-side rendering with Django templates is simpler and more secure for data-entry workflows compared to a decoupled SPA that would need a separate REST API.

---

**Q2: Why monolithic architecture instead of microservices?**

A: For a team of 5 students building a data-management platform, monolithic architecture provides: (1) Single deployment — no inter-service communication overhead; (2) Django ORM transactions guarantee data consistency without distributed sagas; (3) Shared model layer — no data synchronization issues; (4) Faster development iteration. Microservices make sense for 50+ person teams with independent deployment requirements — not for our scope.

---

**Q3: How scalable is your application?**

A: Horizontal scaling is achieved through Vercel's serverless architecture — each request runs in an isolated function. Database scaling uses PostgreSQL with: 40+ named indexes for query optimization, `select_related()` and `prefetch_related()` for N+1 query prevention, and scoped querysets that filter early. Vertical scaling of business logic is isolated in service modules that can be independently optimized.

---

### Database

**Q4: How many tables does your database have?**

A: 34+ Django models across 24 development phases, totaling 5,277 lines of model code. Major entities include: organizational hierarchy (Company, Subsidiary, Project, Site), ESG data (ActivityRecord, Evidence, CalculationResult), workflow (Submission, SubmissionReview, CorrectionRequest), quality assurance (ValidationRule, ValidationRun, AnomalyRecord), and supply chain (Supplier, ProcurementRecord, Carrier, Vehicle, TransportRecord).

---

**Q5: How do you handle data consistency?**

A: Four layers: (1) Django model `clean()` methods enforce business rules before save; (2) Database `CheckConstraint`s (e.g., `quantity >= 0`) catch violations at the database level; (3) `PROTECT` foreign keys prevent accidental deletion of referenced records; (4) `@transaction.atomic` decorators on service functions ensure complex operations are all-or-nothing.

---

### Calculation & Science

**Q6: What is the CEA emission factor and why 0.82?**

A: The Central Electricity Authority (CEA) of India publishes an annual CO₂ Baseline Database for the Indian Power Sector. Version 19 reports a national weighted-average grid emission factor of 0.82 kg CO₂e per kWh. This represents the average carbon intensity of India's electricity grid, accounting for the mix of coal, gas, nuclear, and renewables. We use it for Scope 2 (purchased electricity) calculations.

---

**Q7: Why divide by 1,000 in your calculation formula?**

A: Emission factors are typically expressed in **kg CO₂e** per unit (e.g., 2.68 kg CO₂e/L). Standard reporting uses **tonnes CO₂e** (tCO₂e). Since 1 metric tonne = 1,000 kg, we divide by 1,000 to convert: `Quantity × Factor = kg CO₂e → ÷ 1,000 = tCO₂e`.

---

**Q8: How do you handle unit conversions?**

A: The `conversion_services.py` module handles unit normalization. When a user enters consumption in a unit different from the emission factor's input unit (e.g., enters mL but factor expects L), the system applies a conversion factor before multiplication. The conversion factor is recorded on `CalculationResult.conversion_factor_applied` for audit reproducibility.

---

### OCR & Validation

**Q9: Is your OCR engine AI-powered?**

A: No. We use conventional library-based extraction: (1) **PyPDF** extracts text layers from digital PDFs — this is text parsing, not AI; (2) **Google Tesseract** performs traditional optical character recognition on scanned images — it uses pattern matching algorithms, not deep learning. Structured field extraction uses curated regex patterns, not NLP or LLM models.

---

**Q10: What happens if OCR extraction fails?**

A: Graceful degradation: (1) The `OCRRun` record is created with `status=FAILED` and `error_message` explaining what went wrong; (2) The Evidence and ActivityRecord remain unaffected — OCR is supplementary, not mandatory; (3) If Tesseract is not installed (e.g., on Vercel), `OCREngineUnavailableError` is raised with a clear message rather than crashing.

---

**Q11: How do you validate data quality?**

A: Through a 7-layer validation architecture: Structural → Scope → Period → Activity → Evidence → Consistency → Workflow. Each layer evaluates specific rules with three severity levels: ERROR (blocks progression), WARNING (advisory), INFO (informational). Every validation execution is recorded as a `ValidationRun` with rule version snapshots for audit reproducibility.

---

### Security

**Q12: How do you prevent one user from accessing another user's data?**

A: Object-level authorization through scoped querysets. Every data retrieval goes through service functions like `get_accessible_sites(user)` which filter based on explicit `SiteAssignment` records. A Site Manager assigned to Site A can NEVER see Site B's data, even if they craft a direct URL with Site B's ID. We call this "anti-IDOR" (Insecure Direct Object Reference) protection.

---

**Q13: How do you ensure evidence files haven't been tampered with?**

A: Every uploaded evidence file receives a SHA-256 cryptographic hash stored in the `file_hash` database field. This provides tamper-evident integrity — if the file content changes, the hash won't match. Combined with immutable audit logs, this creates a chain of evidence suitable for regulatory audits.

---

### Workflow

**Q14: What happens when a Subsidiary Manager finds an error in submitted data?**

A: They execute a REQUEST_CORRECTION review action, which: (1) Creates a `CorrectionRequest` record with mandatory `reason` and `required_correction` instructions; (2) Changes submission status to CORRECTION_REQUESTED; (3) Creates an `ActivityRevision` snapshot preserving the pre-correction state; (4) Unlocks the ActivityRecord for Site Manager editing; (5) Logs the action to AuthAuditLog. The Site Manager corrects the data and creates a new `Submission` linked to the original via `parent_submission`.

---

**Q15: Can an Auditor modify data?**

A: No — absolutely not. The AUDITOR role has **strictly read-only access**. They can view all data, trace lineage, and inspect evidence, but cannot create, modify, or delete any records. This is enforced both at the decorator level (`@role_required()`) and at the service function level (`user_can_submit_activity_record()` explicitly rejects Auditor role).

---

### Testing & Quality

**Q16: How do you test your application?**

A: 45 test files covering all 24 development phases. Unit tests verify individual service functions (e.g., emission factor selection, baseline computation). Integration tests verify complete workflows (e.g., submit → review → correct → resubmit). Live acceptance tests verify end-to-end browser interactions. The largest test file (validation engine) is 46,764 bytes, reflecting the complexity of the 7-layer validation architecture.

---

### Scope 3

**Q17: How many Scope 3 categories do you implement?**

A: All 15 GHG Protocol Corporate Value Chain categories — 8 upstream (Purchased Goods, Capital Goods, Fuel & Energy Activities, Upstream Transport, Waste, Business Travel, Employee Commuting, Leased Assets) and 7 downstream (Downstream Transport, Processing, Use, End-of-Life, Downstream Leased Assets, Franchises, Investments). Not all categories are equally material for MEIL — categories 1 (Purchased Goods), 4 (Upstream Transport), 5 (Waste), and 6 (Business Travel) are the most relevant for an infrastructure conglomerate.

---

**Q18: What is the difference between Scope 1, 2, and 3?**

A: **Scope 1** = Direct emissions from owned/controlled sources (e.g., diesel generators at construction sites). **Scope 2** = Indirect emissions from purchased electricity (e.g., grid power consumed at sites). **Scope 3** = All other indirect emissions in the value chain (e.g., embodied carbon in purchased steel, freight transport by third-party trucks, business air travel). For MEIL, Scope 1 is primarily diesel combustion, Scope 2 is grid electricity (CEA factor), and Scope 3 covers procurement, transport, and waste across 15 categories.

---

### Deployment

**Q19: Why Vercel instead of AWS/Azure/GCP?**

A: Vercel provides: (1) Zero-configuration serverless deployment for Django; (2) Free-tier hosting suitable for a university project; (3) Automatic HTTPS and CDN; (4) Git-based deployment workflow. For production scale, we would migrate to a full cloud platform with dedicated PostgreSQL, Redis for caching, and Celery for background tasks.

---

**Q20: What would you change for a production enterprise deployment?**

A: (1) Migrate from SQLite to dedicated PostgreSQL cluster; (2) Add Redis + Celery for background processing (OCR, batch calculations); (3) Implement S3/Azure Blob Storage for evidence files instead of local filesystem; (4) Add application monitoring (Sentry, Prometheus); (5) Deploy behind a proper CDN and load balancer; (6) Add rate limiting and DDoS protection; (7) Implement automated database backups.

---

## 20. Presentation & Demo Strategy

### Recommended 15-Minute Presentation Flow

| Slide | Duration | Content |
|---|---|---|
| 1 | 1 min | Title, team intro, project tagline |
| 2 | 2 min | Problem statement — why BRSR reporting is hard for infrastructure companies |
| 3 | 2 min | Architecture overview — monolithic Django + service layer diagram |
| 4 | 3 min | **LIVE DEMO** — Enter activity data → Upload evidence → Validate → Submit |
| 5 | 2 min | Calculation engine — walk through one emission calculation with actual numbers |
| 6 | 2 min | Trace This Number — drill from BRSR report to source evidence |
| 7 | 1 min | Security & RBAC — show how role-based access scopes data |
| 8 | 1 min | Testing summary — 45 test files, phase coverage |
| 9 | 1 min | Future roadmap and conclusions |

### Demo Script (Critical Path)

1. **Login as Site Manager** → Show site dashboard with assigned sites
2. **Create Activity Record** → Enter: "500 L Diesel, Polavaram Site, March 2026"
3. **Upload Evidence** → Upload a sample fuel invoice PDF
4. **Show OCR Results** → Display extracted fields matching the entered data
5. **Run Validation** → Show "VALID ✅ — 7 rules passed, 0 errors"
6. **Submit for Review** → Show status change to SUBMITTED
7. **Switch to Subsidiary Manager** → Show review dashboard
8. **Verify Submission** → Show VERIFIED status
9. **Show Calculation** → "500 × 2.68 ÷ 1000 = 1.34 tCO₂e"
10. **Trace This Number** → Drill from 1.34 tCO₂e down to the original invoice

### Things to Avoid in Presentation

- ❌ Don't say "We used AI for OCR" — it's conventional library extraction
- ❌ Don't say "React frontend" — it's Django templates with server-side rendering
- ❌ Don't claim features that aren't in the code (always be evidence-backed)
- ❌ Don't read code on screen — use architecture diagrams instead
- ❌ Don't spend more than 30 seconds on tech stack — jury cares about logic and design decisions

---

> **Final Note for the Team**: This document was generated by deep inspection of the actual source code. Every claim tagged ✅ was verified by reading the Python files. Use this as your primary reference, but also familiarize yourself with the actual code in case the jury asks you to open a specific file.

---

*End of Document — MEIL ESG Control Tower Complete Jury Viva Preparation Guide*
