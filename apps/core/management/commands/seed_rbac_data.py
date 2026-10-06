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

        self.stdout.write(self.style.SUCCESS("MEIL ESG RBAC Seeding successfully completed."))
