# MEIL ESG CONTROL TOWER — Database Architecture Specification
## Phase 03: Organization Hierarchy & Data Ownership Scope

---

## 1. Executive Summary

The **MEIL ESG CONTROL TOWER** organizational hierarchy serves as the universal **scope foundation** for the entire platform. Every ESG telemetry record, utility invoice, fuel meter reading, OCR upload, anomaly flag, calculation step, and SEBI BRSR Core indicator resolves directly to this hierarchy.

Rather than independent tables, the architecture implements a normalized four-tiered relational hierarchy:

```text
MEIL ENTERPRISE GROUP (Company)
           │
           └── SUBSIDIARY DIVISION (Subsidiary)
                   │
                   └── INFRASTRUCTURE PROJECT (Project)
                           │
                           └── OPERATIONAL SITE (Site)
```

---

## 2. Conceptual Hierarchy & Entities

```text
+-------------------------------------------------------+
|                       Company                         |
|  - id (BigAutoField, PK)                              |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255), UNIQUE)                        |
|  - legal_name (VARCHAR(255))                          |
|  - country (VARCHAR(100), default='India')            |
|  - registered_address (TEXT)                          |
|  - description (TEXT)                                 |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - is_active (BOOLEAN, default=True)                  |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
                           │ 1
                           │ has many
                           ▼ N (on_delete=models.PROTECT)
+-------------------------------------------------------+
|                      Subsidiary                       |
|  - id (BigAutoField, PK)                              |
|  - company_id (FK -> Company.id, PROTECT)             |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255))                                |
|  - legal_name (VARCHAR(255))                          |
|  - short_name (VARCHAR(100))                          |
|  - industry (VARCHAR(100))                            |
|  - country (VARCHAR(100), default='India')            |
|  - registered_address (TEXT)                          |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - is_active (BOOLEAN, default=True)                  |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
                           │ 1
                           │ has many
                           ▼ N (on_delete=models.PROTECT)
+-------------------------------------------------------+
|                        Project                        |
|  - id (BigAutoField, PK)                              |
|  - subsidiary_id (FK -> Subsidiary.id, PROTECT)       |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255))                                |
|  - description (TEXT)                                 |
|  - location (VARCHAR(255))                            |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - start_date, end_date (DATE, NULL)                  |
|  - is_active (BOOLEAN, default=True)                  |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
                           │ 1
                           │ has many
                           ▼ N (on_delete=models.PROTECT)
+-------------------------------------------------------+
|                         Site                          |
|  - id (BigAutoField, PK)                              |
|  - project_id (FK -> Project.id, PROTECT)             |
|  - code (VARCHAR(50), UNIQUE, INDEX)                 |
|  - name (VARCHAR(255))                                |
|  - facility_type (VARCHAR(100))                       |
|  - location (VARCHAR(255))                            |
|  - latitude, longitude (DECIMAL(9,6), NULL)           |
|  - contact_person (VARCHAR(150))                      |
|  - contact_email (VARCHAR(254))                       |
|  - description (TEXT)                                 |
|  - status (VARCHAR(20), ACTIVE/INACTIVE/CLOSED, INDEX)|
|  - is_active (BOOLEAN, default=True)                  |
|  - created_at, updated_at (TIMESTAMPTZ)               |
+-------------------------------------------------------+
```

---

## 3. Relational Organizational Scope Assignments

Fine-grained authorization links authenticated users to distinct organizational levels through relational models:

```text
User ──┬── CompanyAssignment     ──► Company (Enterprise Group Scope)
       ├── SubsidiaryAssignment  ──► Subsidiary (Division Review Scope)
       ├── ProjectAssignment     ──► Project (Infrastructure Scope)
       └── SiteAssignment        ──► Site (Operational Data Entry Scope)
```

Each assignment table enforces a compound database unique constraint:
- `core_siteassignment`: `UNIQUE(user_id, site_id)`
- `core_subsidiaryassignment`: `UNIQUE(user_id, subsidiary_id)`
- `core_projectassignment`: `UNIQUE(user_id, project_id)`
- `core_companyassignment`: `UNIQUE(user_id, company_id)`

---

## 4. Referential Integrity & Deletion Policy

### Foreign Key Protection Axiom
All downward hierarchical relationships utilize `on_delete=models.PROTECT`.
- A `Company` cannot be deleted while child `Subsidiary` records exist.
- A `Subsidiary` cannot be deleted while child `Project` records exist.
- A `Project` cannot be deleted while child `Site` records exist.
- A `Site` cannot be deleted while child activity, invoice, or evidence records reference it in future phases.

### Safe Deactivation / Archiving Policy
Historical ESG disclosures under SEBI BRSR and GHG Protocol regulations require permanent audit lineage. Hard deletes of organizational entities that have reported telemetry are strictly prohibited.
- When an entity is decommissioned, its lifecycle state is changed to `INACTIVE` or `CLOSED` via `safe_deactivate_entity()`.
- The `is_active` boolean is synchronized to `False`.
- The operation writes an `ORGANIZATION_DEACTIVATED` event to `core_authauditlog`.
- Inactive entities remain queryable for historical reporting periods and assurance audits, but are filtered out of active operational data collection.

---

## 5. Organizational Inheritance Traversal

The ORM models provide explicit property traversals:

```python
# Site level
site.project           # -> Project
site.subsidiary        # -> Subsidiary (site.project.subsidiary)
site.company           # -> Company (site.project.subsidiary.company)

# Project level
project.subsidiary     # -> Subsidiary
project.company        # -> Company (project.subsidiary.company)

# Subsidiary level
subsidiary.company     # -> Company
subsidiary.parent_company # -> Company
```

---

## 6. Database Migrations

1. `core.0001_initial`: Initial User, Role, Company, Subsidiary, Project, Site, Assignments, and AuthAuditLog.
2. `core.0002_company_country_company_legal_name_and_more`:
   - Adds `OrganizationStatus` lifecycle state choices (`ACTIVE`, `INACTIVE`, `CLOSED`) with database indexes.
   - Adds legal names, short names, countries, registered addresses, facility types, GPS coordinates, timelines, and contact attributes.
   - Enriches `AuthAuditLog` with `ORGANIZATION_CREATED`, `ORGANIZATION_UPDATED`, `ORGANIZATION_DEACTIVATED` event types.
