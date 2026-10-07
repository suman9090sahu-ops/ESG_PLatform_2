"""
Management command to seed RBAC roles, organizational hierarchy, and test users
for MEIL ESG CONTROL TOWER development and testing.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import (
    Company,
    CompanyAssignment,
    Project,
    Role,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    User,
    UserRole,
    PeriodStatus,
    ReportingPeriod,
    ActivityCategory,
    UnitOfMeasure,
    ActivityMaster,
    MasterStatus,
    UnitDimension,
    ScopeClassification,
    CollectionFrequency,
)


class Command(BaseCommand):
    help = "Seed initial RBAC roles, organizational hierarchy, and demo test accounts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing RBAC demo data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Initializing MEIL ESG RBAC Seeding..."))

        # 1. Create Roles
        roles_data = [
            (Role.Code.SITE_MANAGER, "Site Manager", "Operational site data entry, evidence, and submissions."),
            (Role.Code.SUBSIDIARY_MANAGER, "Subsidiary Manager", "Subsidiary-level review, validation anomaly desk, verification."),
            (Role.Code.ESG_MANAGER, "ESG Governance Manager", "Corporate GHG accounting, emission factors, and SEBI BRSR finalization."),
            (Role.Code.AUDITOR, "ESG Assurance Auditor", "Independent read-only assurance, calculation lineage, and audit trail."),
            (Role.Code.MEIL_OPERATOR, "MEIL Operations Lead", "System operations, telemetry sync pipelines, and administrative control."),
        ]

        roles = {}
        for code, name, desc in roles_data:
            role, created = Role.objects.get_or_create(
                code=code,
                defaults={"name": name, "description": desc, "is_active": True},
            )
            roles[code] = role
            status = "Created" if created else "Exists"
            self.stdout.write(f"  Role [{code}]: {status}")

        # 2. Create Organizational Hierarchy
        meil_company, _ = Company.objects.get_or_create(
            code="MEIL-ENT",
            defaults={
                "name": "MEIL Enterprise Group",
                "legal_name": "Megha Engineering & Infrastructures Limited",
                "country": "India",
                "registered_address": "S-2, Technocrat Industrial Estate, Balanagar, Hyderabad, Telangana 500037",
                "description": "Megha Engineering & Infrastructures Limited Enterprise Holding & Operating Scope",
                "status": "ACTIVE",
            },
        )

        hydro_sub, _ = Subsidiary.objects.get_or_create(
            code="MEIL-HYDRO",
            defaults={
                "name": "MEIL Hydro & Infrastructure Division",
                "legal_name": "MEIL Hydro Power & Civil Infrastructure Division Ltd",
                "short_name": "Hydro Division",
                "company": meil_company,
                "industry": "Hydroelectric & Water Infrastructure",
                "country": "India",
                "registered_address": "Polavaram Project Division Camp, West Godavari, Andhra Pradesh",
                "status": "ACTIVE",
            },
        )

        solar_sub, _ = Subsidiary.objects.get_or_create(
            code="MEIL-SOLAR",
            defaults={
                "name": "MEIL Clean Energy Division",
                "legal_name": "MEIL Renewable & Clean Energy Generation Ltd",
                "short_name": "Clean Energy",
                "company": meil_company,
                "industry": "Renewable Power & Solar PV",
                "country": "India",
                "registered_address": "Gani Solar Park Office, Kurnool District, Andhra Pradesh",
                "status": "ACTIVE",
            },
        )

        polavaram_proj, _ = Project.objects.get_or_create(
            code="PRJ-POL-01",
            defaults={
                "name": "Polavaram National Irrigation Project",
                "subsidiary": hydro_sub,
                "description": "Multi-purpose irrigation, hydroelectric powerhouse (960 MW), and water management national project.",
                "location": "Godavari River Basin, Eluru District, Andhra Pradesh",
                "status": "ACTIVE",
            },
        )

        kurnool_proj, _ = Project.objects.get_or_create(
            code="PRJ-KRN-01",
            defaults={
                "name": "Kurnool Ultra Mega Solar Park",
                "subsidiary": solar_sub,
                "description": "Grid-connected 1,000 MW capacity utility solar photovoltaic power plant installation.",
                "location": "Gani & Sakunala Villages, Kurnool District, Andhra Pradesh",
                "status": "ACTIVE",
            },
        )

        # Operational Sites
        site_101, _ = Site.objects.get_or_create(
            code="SITE-POL-101",
            defaults={
                "name": "Polavaram Dam Headworks Site",
                "project": polavaram_proj,
                "facility_type": "Hydroelectric Dam & Earth-cum-Rockfill Barrier",
                "location": "Polavaram, Eluru District, Andhra Pradesh",
                "latitude": 17.258600,
                "longitude": 81.657800,
                "contact_person": "Er. Ramesh Kumar",
                "contact_email": "site.manager@meilgroup.com",
                "description": "Headworks civil construction boundary, heavy diesel generator telemetry, concrete batching plant.",
                "status": "ACTIVE",
            },
        )

        site_102, _ = Site.objects.get_or_create(
            code="SITE-POL-102",
            defaults={
                "name": "Polavaram Spillway & Powerhouse Site",
                "project": polavaram_proj,
                "facility_type": "Hydel Powerhouse & 48-Gate Spillway Channel",
                "location": "Polavaram, Eluru District, Andhra Pradesh",
                "latitude": 17.264200,
                "longitude": 81.662100,
                "contact_person": "Er. Suresh Reddy",
                "contact_email": "site102.manager@meilgroup.com",
                "description": "Hydro powerhouse turbine gallery, auxiliary power monitoring, intake channel telemetry.",
                "status": "ACTIVE",
            },
        )

        site_201, _ = Site.objects.get_or_create(
            code="SITE-KRN-201",
            defaults={
                "name": "Kurnool Array 1 Solar Inverter Station",
                "project": kurnool_proj,
                "facility_type": "Solar PV Inverter Station & Substation Interconnect",
                "location": "Gani Solar Park, Kurnool, Andhra Pradesh",
                "latitude": 15.683400,
                "longitude": 78.291700,
                "contact_person": "Er. Amit Verma",
                "contact_email": "kurnool.solar@meilgroup.com",
                "description": "150 MW inverter array feeding 400 kV pooling substation; auxiliary metering point.",
                "status": "ACTIVE",
            },
        )

        self.stdout.write(self.style.SUCCESS(f"  Organizational Hierarchy seeded: 1 Company, 2 Subsidiaries, 2 Projects, 3 Sites."))

        # 3. Create Seed Users
        users_config = [
            {
                "username": "site_manager",
                "email": "site.manager@meilgroup.com",
                "password": "SiteManagerPass123!",
                "first_name": "Ramesh",
                "last_name": "Kumar",
                "department": "Hydro Operations",
                "designation": "Operational Site In-Charge",
                "role_code": Role.Code.SITE_MANAGER,
                "sites": [site_101],
            },
            {
                "username": "unassigned_site_manager",
                "email": "site102.manager@meilgroup.com",
                "password": "OtherSitePass123!",
                "first_name": "Suresh",
                "last_name": "Reddy",
                "department": "Civil Infrastructure",
                "designation": "Spillway Site Engineer",
                "role_code": Role.Code.SITE_MANAGER,
                "sites": [site_102],
            },
            {
                "username": "subsidiary_manager",
                "email": "sub.manager@meilgroup.com",
                "password": "SubManagerPass123!",
                "first_name": "Priya",
                "last_name": "Sharma",
                "department": "Infrastructure Governance",
                "designation": "Subsidiary ESG Review Lead",
                "role_code": Role.Code.SUBSIDIARY_MANAGER,
                "subsidiaries": [hydro_sub],
            },
            {
                "username": "esg_manager",
                "email": "esg.manager@meilgroup.com",
                "password": "ESGManagerPass123!",
                "first_name": "Ananya",
                "last_name": "Iyer",
                "department": "Corporate Sustainability",
                "designation": "Chief ESG Governance Officer",
                "role_code": Role.Code.ESG_MANAGER,
                "companies": [meil_company],
            },
            {
                "username": "auditor",
                "email": "auditor@assurance-partners.com",
                "password": "AuditorPass123!",
                "first_name": "Vikram",
                "last_name": "Mehta",
                "department": "External ESG Assurance",
                "designation": "Senior Assurance Auditor",
                "role_code": Role.Code.AUDITOR,
                "companies": [meil_company],
            },
            {
                "username": "meil_operator",
                "email": "operator@meilgroup.com",
                "password": "OperatorPass123!",
                "first_name": "Kiran",
                "last_name": "Varma",
                "department": "Digital Operations",
                "designation": "Platform Operations Lead",
                "role_code": Role.Code.MEIL_OPERATOR,
                "companies": [meil_company],
            },
            {
                "username": "admin",
                "email": "admin@meilgroup.com",
                "password": "AdminPass123!",
                "first_name": "System",
                "last_name": "Administrator",
                "department": "IT Infrastructure",
                "designation": "Superuser",
                "is_staff": True,
                "is_superuser": True,
                "role_code": Role.Code.MEIL_OPERATOR,
                "companies": [meil_company],
            },
        ]

        for uconf in users_config:
            username = uconf["username"]
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": uconf["email"],
                    "first_name": uconf.get("first_name", ""),
                    "last_name": uconf.get("last_name", ""),
                    "department": uconf.get("department", ""),
                    "designation": uconf.get("designation", ""),
                    "is_staff": uconf.get("is_staff", False),
                    "is_superuser": uconf.get("is_superuser", False),
                    "is_active": True,
                },
            )
            user.set_password(uconf["password"])
            user.save()

            role = roles.get(uconf["role_code"])
            if role:
                UserRole.objects.update_or_create(
                    user=user,
                    role=role,
                    defaults={"is_primary": True},
                )

            # Assign sites
            for s in uconf.get("sites", []):
                SiteAssignment.objects.get_or_create(user=user, site=s)

            # Assign subsidiaries
            for sub in uconf.get("subsidiaries", []):
                SubsidiaryAssignment.objects.get_or_create(user=user, subsidiary=sub)

            # Assign companies
            for co in uconf.get("companies", []):
                CompanyAssignment.objects.get_or_create(user=user, company=co)

            status = "Created" if created else "Updated"
            self.stdout.write(f"  User [{username}]: {status} (Role: {uconf['role_code']})")

        # 4. Seed Standard Reporting Periods
        self.stdout.write(self.style.NOTICE("Seeding Reporting Periods..."))
        operator_user = User.objects.filter(username="meil_operator").first()

        periods_data = [
            {
                "company": meil_company,
                "code": "FY2024-25",
                "name": "FY 2024-25 Regulatory ESG & BRSR Reporting Cycle",
                "fiscal_year": "FY 2024-25",
                "start_date": "2024-04-01",
                "end_date": "2025-03-31",
                "status": PeriodStatus.LOCKED,
                "description": "Audited and verified historical annual ESG reporting period. Protected from active edits.",
            },
            {
                "company": meil_company,
                "code": "FY2025-26",
                "name": "FY 2025-26 Operational Annual ESG Reporting Cycle",
                "fiscal_year": "FY 2025-26",
                "start_date": "2025-04-01",
                "end_date": "2026-03-31",
                "status": PeriodStatus.OPEN,
                "description": "Active operational ESG data collection, meter telemetry, fuel tracking, and BRSR governance.",
            },
            {
                "company": meil_company,
                "code": "FY2026-27",
                "name": "FY 2026-27 Forthcoming ESG Reporting Cycle",
                "fiscal_year": "FY 2026-27",
                "start_date": "2026-04-01",
                "end_date": "2027-03-31",
                "status": PeriodStatus.DRAFT,
                "description": "Draft configuration for future ESG compliance and materiality assessment cycle.",
            },
        ]

        for pdata in periods_data:
            period, created = ReportingPeriod.objects.get_or_create(
                company=pdata["company"],
                code=pdata["code"],
                defaults={
                    "name": pdata["name"],
                    "fiscal_year": pdata["fiscal_year"],
                    "start_date": pdata["start_date"],
                    "end_date": pdata["end_date"],
                    "status": pdata["status"],
                    "description": pdata["description"],
                    "created_by": operator_user,
                    "updated_by": operator_user,
                },
            )
            p_status = "Created" if created else "Exists"
            self.stdout.write(f"  Reporting Period [{pdata['code']}]: {p_status} ({pdata['status']})")

        # 5. Seed Activity Master Catalog (Phase 06)
        self.stdout.write(self.style.NOTICE("Seeding Phase 06 Activity Master Catalog..."))

        # 5a. Categories
        categories_data = [
            ("FUEL", "Fuel & Combustion", "Direct fossil fuel combustion for stationary generators, boilers, and machinery.", 1),
            ("ENERGY", "Electricity & Energy", "Grid electricity, renewable energy, and purchased thermal energy.", 2),
            ("WATER", "Water Resources", "Groundwater withdrawal, municipal supplies, and wastewater recycling.", 3),
            ("WASTE", "Waste Management", "Hazardous, non-hazardous, and construction scrap waste handling.", 4),
            ("TRANSPORT", "Vehicle & Transport", "Company logistics, heavy earth-moving fleet, and transport freight.", 5),
            ("TRAVEL", "Business Travel", "Commercial flights, rail, and employee business travel emissions.", 6),
            ("OTHER", "Other ESG Activities", "Safety incidents, CSR operational metrics, and governance indicators.", 7),
        ]
        categories = {}
        for c_code, c_name, c_desc, c_order in categories_data:
            cat, created = ActivityCategory.objects.get_or_create(
                code=c_code,
                defaults={
                    "name": c_name,
                    "description": c_desc,
                    "display_order": c_order,
                    "status": MasterStatus.ACTIVE,
                    "created_by": operator_user,
                    "updated_by": operator_user,
                },
            )
            categories[c_code] = cat
            c_status = "Created" if created else "Exists"
            self.stdout.write(f"  Activity Category [{c_code}]: {c_status}")

        # 5b. Units of Measure
        units_data = [
            ("LITRE", "Litre", "L", UnitDimension.VOLUME, "Standard liquid fuel volume."),
            ("KWH", "Kilowatt Hour", "kWh", UnitDimension.ENERGY, "Electrical energy unit."),
            ("MWH", "Megawatt Hour", "MWh", UnitDimension.ENERGY, "Bulk grid electrical energy unit."),
            ("KL", "Kilolitre", "kL", UnitDimension.VOLUME, "Water extraction and storage volume."),
            ("M3", "Cubic Metre", "m³", UnitDimension.VOLUME, "Bulk water or gas volume."),
            ("KG", "Kilogram", "kg", UnitDimension.MASS, "Standard weight and hazardous waste unit."),
            ("TONNE", "Metric Tonne", "t", UnitDimension.MASS, "Bulk materials and construction waste."),
            ("KM", "Kilometre", "km", UnitDimension.DISTANCE, "Fleet travel and freight transport distance."),
            ("PASSENGER_KM", "Passenger-Kilometre", "p-km", UnitDimension.DISTANCE, "Business travel commercial flights."),
        ]
        units = {}
        for u_code, u_name, u_sym, u_dim, u_desc in units_data:
            uom, created = UnitOfMeasure.objects.get_or_create(
                code=u_code,
                defaults={
                    "name": u_name,
                    "symbol": u_sym,
                    "dimension": u_dim,
                    "description": u_desc,
                    "status": MasterStatus.ACTIVE,
                    "created_by": operator_user,
                    "updated_by": operator_user,
                },
            )
            units[u_code] = uom
            u_status = "Created" if created else "Exists"
            self.stdout.write(f"  Unit [{u_code}]: {u_status} ({u_sym})")

        # 5c. Master Activities
        activities_data = [
            {
                "code": "FUEL-DIESEL-STAT",
                "name": "Diesel Consumption (Stationary Generators & Equipment)",
                "category": categories["FUEL"],
                "activity_type": "Stationary Combustion",
                "base_unit": units["LITRE"],
                "allowed_units": [units["LITRE"], units["KL"]],
                "scope_classification": ScopeClassification.SCOPE_1,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "Fuel Delivery Challan / DG Log Book / Tax Invoice",
                "description": "Diesel fuel consumed by on-site diesel generators, static concrete batching equipment, and pumps.",
                "applicability_notes": "Applicable across all construction, dam, and headwork sites operating diesel generators.",
            },
            {
                "code": "FUEL-PETROL-MOB",
                "name": "Petrol Consumption (Company Fleet & Site Vehicles)",
                "category": categories["FUEL"],
                "activity_type": "Mobile Combustion",
                "base_unit": units["LITRE"],
                "allowed_units": [units["LITRE"]],
                "scope_classification": ScopeClassification.SCOPE_1,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "Fuel Purchase Card Receipt / Vehicle Log Book / Tax Invoice",
                "description": "Petrol fuel consumed by project inspection utility vehicles and site management cars.",
                "applicability_notes": "Applicable to site management vehicle fleets.",
            },
            {
                "code": "ELEC-GRID",
                "name": "Grid Electricity Consumption (State Discom Supply)",
                "category": categories["ENERGY"],
                "activity_type": "Purchased Electricity",
                "base_unit": units["KWH"],
                "allowed_units": [units["KWH"], units["MWH"]],
                "scope_classification": ScopeClassification.SCOPE_2,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "Monthly Electricity Discom Utility Bill / HT Meter Reading Record",
                "description": "Grid electricity supplied by state power distribution utilities for camp offices, powerhouse, and site yards.",
                "applicability_notes": "All sites with dedicated HT or LT electrical utility connections.",
            },
            {
                "code": "ELEC-RENEWABLE-CAPTIVE",
                "name": "Captive Solar / Renewable Power Generation & Consumption",
                "category": categories["ENERGY"],
                "activity_type": "Renewable Energy",
                "base_unit": units["KWH"],
                "allowed_units": [units["KWH"], units["MWH"]],
                "scope_classification": ScopeClassification.SCOPE_2,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "Solar Inverter SCADA Log / Generation Meter Reading Record",
                "description": "On-site solar PV generation consumed for site operations and auxiliary loads.",
                "applicability_notes": "Solar project sites and facilities with rooftop or ground-mount captive solar.",
            },
            {
                "code": "WATER-GROUND",
                "name": "Groundwater Extraction (Borewell Telemetry)",
                "category": categories["WATER"],
                "activity_type": "Water Withdrawal",
                "base_unit": units["KL"],
                "allowed_units": [units["KL"], units["M3"]],
                "scope_classification": ScopeClassification.NON_GHG,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "Borewell Flow Meter Digital Log / Water Extraction Register",
                "description": "Groundwater extracted from licensed on-site borewells for batching, curing, and worker camp utilities.",
                "applicability_notes": "Construction sites with operational groundwater abstraction permissions.",
            },
            {
                "code": "WATER-MUNICIPAL",
                "name": "Purchased / Municipal Water Supply",
                "category": categories["WATER"],
                "activity_type": "Purchased Water",
                "base_unit": units["KL"],
                "allowed_units": [units["KL"], units["M3"]],
                "scope_classification": ScopeClassification.NON_GHG,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "Municipal Water Tanker Challan / Water Utility Tax Invoice",
                "description": "Water delivered via municipal supply pipelines or verified water tanker contracts.",
                "applicability_notes": "Sites purchasing bulk water for operations or drinking water treatment.",
            },
            {
                "code": "WASTE-HAZARDOUS",
                "name": "Hazardous Industrial & Chemical Waste Generation",
                "category": categories["WASTE"],
                "activity_type": "Hazardous Waste",
                "base_unit": units["KG"],
                "allowed_units": [units["KG"], units["TONNE"]],
                "scope_classification": ScopeClassification.SCOPE_3,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "State Pollution Control Board Manifest (Form 10) / Authorized Recycler Receipt",
                "description": "Used machinery lube oil, oily rags, chemical drums, and hazardous maintenance residues.",
                "applicability_notes": "All mechanical workshop and heavy equipment maintenance bays.",
            },
            {
                "code": "WASTE-NON-HAZARDOUS",
                "name": "Non-Hazardous Solid Waste / Construction Scrap",
                "category": categories["WASTE"],
                "activity_type": "Solid Waste",
                "base_unit": units["TONNE"],
                "allowed_units": [units["TONNE"], units["KG"]],
                "scope_classification": ScopeClassification.SCOPE_3,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "Weighbridge Manifest / Scrap Disposal Gate Pass / Recycling Certificate",
                "description": "Construction debris, rebar scrap, packaging timber, and municipal solid waste from labor colonies.",
                "applicability_notes": "All civil construction, dam, and solar park sites.",
            },
            {
                "code": "TRAVEL-AIR-DOMESTIC",
                "name": "Domestic Commercial Air Travel",
                "category": categories["TRAVEL"],
                "activity_type": "Business Travel",
                "base_unit": units["PASSENGER_KM"],
                "allowed_units": [units["PASSENGER_KM"], units["KM"]],
                "scope_classification": ScopeClassification.SCOPE_3,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "Corporate Travel Desk Report / Flight E-Ticket / Invoice",
                "description": "Domestic airline flights undertaken by engineers, project managers, and executives for project business.",
                "applicability_notes": "Corporate and divisional project management personnel.",
            },
            {
                "code": "TRANSPORT-COMMERCIAL-FREIGHT",
                "name": "Upstream / Downstream Heavy Freight Transport",
                "category": categories["TRANSPORT"],
                "activity_type": "Third-Party Logistics",
                "base_unit": units["TONNE"],
                "allowed_units": [units["TONNE"], units["KG"]],
                "scope_classification": ScopeClassification.SCOPE_3,
                "collection_frequency": CollectionFrequency.MONTHLY,
                "evidence_requirement_hint": "Transporter Lorry Receipt (LR) / Weighbridge Slip / Delivery Challan",
                "description": "Heavy freight hauling of steel, cement, turbine components, and PV modules by third-party logistics.",
                "applicability_notes": "Project material inward logistics.",
            },
        ]

        for adata in activities_data:
            allowed = adata.pop("allowed_units")
            act, created = ActivityMaster.objects.get_or_create(
                code=adata["code"],
                defaults={
                    **adata,
                    "status": MasterStatus.ACTIVE,
                    "created_by": operator_user,
                    "updated_by": operator_user,
                },
            )
            act.allowed_units.set(allowed)

            # Phase 10 validation metadata enrichment
            if act.code in ["FUEL-DIESEL-STAT", "ELEC-GRID", "WASTE-HAZARDOUS"]:
                evid_types = ["INVOICE"]
                if act.code == "FUEL-DIESEL-STAT":
                    evid_types = ["INVOICE", "FUEL_CHALLAN"]
                elif act.code == "ELEC-GRID":
                    evid_types = ["UTILITY_BILL", "INVOICE", "METER_READING"]
                elif act.code == "WASTE-HAZARDOUS":
                    evid_types = ["WASTE_MANIFEST", "INVOICE"]
                act.validation_rules = {
                    "evidence_required": True,
                    "required_evidence_types": evid_types,
                }
                act.save(update_fields=["validation_rules"])

            a_status = "Created" if created else "Exists"
            self.stdout.write(f"  Activity Master [{adata['code']}]: {a_status}")

        # 6. Phase 10 Standard Validation Rules Seeding
        self.stdout.write(self.style.NOTICE("\n--- Seeding Phase 10 Standard Validation Rules ---"))
        from apps.core.validation_services import seed_standard_validation_rules
        rules_created = seed_standard_validation_rules(user=operator_user)
        self.stdout.write(f"  Standard Validation Rules: {rules_created} new rules seeded.")

        self.stdout.write(self.style.SUCCESS("MEIL ESG RBAC, Activity Master, and Validation Engine Seeding successfully completed."))

