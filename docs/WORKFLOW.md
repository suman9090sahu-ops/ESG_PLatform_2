# MEIL ESG CONTROL TOWER — Organizational Governance & Data Ownership Workflow
## Phase 03: Organization Hierarchy Integration

---

## 1. Operating Governance Model

The **MEIL ESG CONTROL TOWER** operates across four tiers of governance:

```text
+-----------------------------------------------------------------------------------------+
| LEVEL 1: MEIL ENTERPRISE GROUP                                                          |
| Roles: MEIL_OPERATOR, ESG_MANAGER, AUDITOR                                              |
| Responsibilities: Enterprise GHG consolidation, BRSR Core disclosures, assurance audit  |
+-----------------------------------------------------------------------------------------+
                                           │
                                           ▼
+-----------------------------------------------------------------------------------------+
| LEVEL 2: SUBSIDIARY DIVISION (e.g. MEIL Hydro, MEIL Solar)                             |
| Roles: SUBSIDIARY_MANAGER                                                               |
| Responsibilities: Division review desk, validation anomaly triage, escalation governance|
+-----------------------------------------------------------------------------------------+
                                           │
                                           ▼
+-----------------------------------------------------------------------------------------+
| LEVEL 3: INFRASTRUCTURE PROJECT (e.g. Polavaram Irrigation, Kurnool Solar Park)         |
| Roles: Project Engineers, Operations Team                                               |
| Responsibilities: Project asset tracking, boundary management, milestone compliance     |
+-----------------------------------------------------------------------------------------+
                                           │
                                           ▼
+-----------------------------------------------------------------------------------------+
| LEVEL 4: OPERATIONAL SITE (e.g. Dam Headworks, Array 1 Inverter Station)                |
| Roles: SITE_MANAGER                                                                     |
| Responsibilities: Raw fuel/power telemetry, utility invoice uploads, OCR verification  |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Upward Data Flow & Review Lineage

```text
[SITE MANAGER] ──► Submits raw activity entry + evidence doc
                          │
                          ▼
               [AUTOMATED VALIDATION] ──► Sanity check & anomaly flags
                          │
                          ▼
            [SUBSIDIARY MANAGER REVIEW] ──► Verify division accuracy or request revision
                          │
                          ▼
              [ESG MANAGER CONSOLIDATION] ──► Enterprise Scope 1, 2, 3 carbon accounting
                          │
                          ▼
              [INDEPENDENT ASSURANCE] ──► AUDITOR traces formula lineage to raw site evidence
```

---

## 3. Server-Side Scoping Boundaries

| Persona | Permitted Organizational Scope | Organization Management Authority |
| :--- | :--- | :--- |
| **`SITE_MANAGER`** | Explicitly assigned sites only | Strictly denied organization CRUD or hierarchy overview. Can only view assigned site profile. |
| **`SUBSIDIARY_MANAGER`** | Assigned subsidiary divisions, child projects, and child sites | Can view assigned division tree. Can create/edit projects and sites **only** within assigned subsidiary. Denied access to other divisions. |
| **`ESG_MANAGER`** | Universal Enterprise Read Scope | Read-only access to complete organizational hierarchy. Structural modifications restricted to MEIL_OPERATOR. |
| **`AUDITOR`** | Universal Enterprise Assurance Scope | Strictly **read-only**. Blocked from create, edit, or deactivation operations across all organizational entities. |
| **`MEIL_OPERATOR`** | Full Enterprise Operational Scope | Full CRUD authority across Companies, Subsidiaries, Projects, and Operational Sites. |
