"""
Core Models for MEIL ESG CONTROL TOWER.

Establishes:
1. Unified Custom User Model (AbstractUser)
2. Centralized RBAC Role Models (Role, UserRole)
3. Organizational Hierarchy Foundation (Company, Subsidiary, Project, Site)
4. Relational User Scope Assignments (SiteAssignment, SubsidiaryAssignment, ProjectAssignment, CompanyAssignment)
5. Audit-Ready Authentication and Authorization Event Logging (AuthAuditLog)
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.Model):
    """
    Centralized RBAC Role definition.
    Roles act as a permission and context layer across the platform.
    """

    class Code(models.TextChoices):
        SITE_MANAGER = "SITE_MANAGER", "Site Manager"
        SUBSIDIARY_MANAGER = "SUBSIDIARY_MANAGER", "Subsidiary Manager"
        ESG_MANAGER = "ESG_MANAGER", "ESG Manager"
        AUDITOR = "AUDITOR", "Auditor"
        MEIL_OPERATOR = "MEIL_OPERATOR", "MEIL Operator"

    code = models.CharField(
        max_length=50,
        choices=Code.choices,
        unique=True,
        help_text="Machine-readable unique role identifier.",
    )
    name = models.CharField(max_length=100, help_text="Human-readable role title.")
    description = models.TextField(blank=True, help_text="Detailed description of responsibilities.")
    is_active = models.BooleanField(default=True, help_text="Whether this role is currently enabled.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    Unified User Identity Model for MEIL ESG CONTROL TOWER.
    One single identity model for all roles in the organization.
    """

    phone_number = models.CharField(max_length=32, blank=True, help_text="Contact telephone number.")
    employee_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        help_text="MEIL Enterprise Employee or Contractor ID.",
    )
    department = models.CharField(max_length=128, blank=True, help_text="Assigned business unit or department.")
    designation = models.CharField(max_length=128, blank=True, help_text="Official job designation.")

    roles = models.ManyToManyField(
        Role,
        through="UserRole",
        through_fields=("user", "role"),
        related_name="users",
        blank=True,
        help_text="Assigned functional roles.",
    )

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["username"]

    def __str__(self):
        full_name = self.get_full_name()
        return f"{full_name} ({self.username})" if full_name else self.username

    def get_assigned_roles(self):
        """Returns QuerySet of active roles assigned to this user."""
        return self.roles.filter(is_active=True)

    def get_primary_role(self):
        """
        Deterministic primary role resolver.
        Priority:
        1. Role marked is_primary=True in UserRole
        2. Superuser -> MEIL_OPERATOR context
        3. Deterministic hierarchy: MEIL_OPERATOR > ESG_MANAGER > SUBSIDIARY_MANAGER > SITE_MANAGER > AUDITOR
        4. None
        """
        if not self.is_authenticated:
            return None

        # Check explicit primary role flag
        primary_link = self.user_roles.filter(is_primary=True, role__is_active=True).select_related("role").first()
        if primary_link:
            return primary_link.role.code

        # Next check priority order
        active_codes = set(self.get_assigned_roles().values_list("code", flat=True))
        if self.is_superuser and not active_codes:
            return Role.Code.MEIL_OPERATOR

        priority_order = [
            Role.Code.MEIL_OPERATOR,
            Role.Code.ESG_MANAGER,
            Role.Code.SUBSIDIARY_MANAGER,
            Role.Code.SITE_MANAGER,
            Role.Code.AUDITOR,
        ]
        for role_code in priority_order:
            if role_code in active_codes:
                return role_code

        # Fallback to any assigned role if custom roles are added in future
        first_role = self.get_assigned_roles().first()
        return first_role.code if first_role else None

    def has_role(self, role_code):
        """Check whether user holds a specific role (or is superuser)."""
        if not self.is_authenticated or not self.is_active:
            return False
        if self.is_superuser:
            return True
        return self.get_assigned_roles().filter(code=role_code).exists()

    @property
    def is_site_manager(self):
        return self.has_role(Role.Code.SITE_MANAGER)

    @property
    def is_subsidiary_manager(self):
        return self.has_role(Role.Code.SUBSIDIARY_MANAGER)

    @property
    def is_esg_manager(self):
        return self.has_role(Role.Code.ESG_MANAGER)

    @property
    def is_auditor(self):
        return self.has_role(Role.Code.AUDITOR)

    @property
    def is_meil_operator(self):
        return self.has_role(Role.Code.MEIL_OPERATOR)

    @property
    def role_display_title(self):
        """Friendly title for navbar / sidebar."""
        primary = self.get_primary_role()
        mapping = {
            Role.Code.SITE_MANAGER: "Site Manager",
            Role.Code.SUBSIDIARY_MANAGER: "Subsidiary Manager",
            Role.Code.ESG_MANAGER: "ESG Governance Manager",
            Role.Code.AUDITOR: "ESG Assurance Auditor",
            Role.Code.MEIL_OPERATOR: "MEIL Operations Lead",
        }
        if primary in mapping:
            return mapping[primary]
        if self.is_superuser:
            return "Platform Superuser"
        return "Control Tower User"

    @property
    def role_display_subtitle(self):
        primary = self.get_primary_role()
        mapping = {
            Role.Code.SITE_MANAGER: "Operational Site ESG Telemetry",
            Role.Code.SUBSIDIARY_MANAGER: "Subsidiary Data Review & Verification",
            Role.Code.ESG_MANAGER: "Corporate BRSR & GHG Accounting",
            Role.Code.AUDITOR: "Independent Assurance & Traceability",
            Role.Code.MEIL_OPERATOR: "Enterprise Operations & Administration",
        }
        return mapping.get(primary, "Governance & Compliance")

    @property
    def role_initials(self):
        primary = self.get_primary_role()
        mapping = {
            Role.Code.SITE_MANAGER: "SM",
            Role.Code.SUBSIDIARY_MANAGER: "SMG",
            Role.Code.ESG_MANAGER: "ESG",
            Role.Code.AUDITOR: "AUD",
            Role.Code.MEIL_OPERATOR: "OP",
        }
        if primary in mapping:
            return mapping[primary]
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}{self.last_name[0]}".upper()
        return self.username[:2].upper() if self.username else "CT"


class UserRole(models.Model):
    """
    Through model linking User and Role with assignment metadata.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="user_roles")
    is_primary = models.BooleanField(
        default=False,
        help_text="Flag indicating whether this is the user's primary operational role.",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_user_roles",
    )

    class Meta:
        verbose_name = "User Role Assignment"
        verbose_name_plural = "User Role Assignments"
        unique_together = ("user", "role")

    def __str__(self):
        primary_badge = " (Primary)" if self.is_primary else ""
        return f"{self.user.username} -> {self.role.name}{primary_badge}"


# -----------------------------------------------------------------------------
# ORGANIZATIONAL HIERARCHY FOUNDATION
# -----------------------------------------------------------------------------

class OrganizationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    CLOSED = "CLOSED", "Closed"


class Company(models.Model):
    """
    Top-level enterprise entity (e.g. MEIL Enterprise Group).
    Root of the organizational hierarchy.
    """

    name = models.CharField(max_length=255, unique=True, help_text="Enterprise group or operating company title.")
    code = models.CharField(max_length=50, unique=True, help_text="Unique enterprise code (e.g. MEIL-ENT).")
    legal_name = models.CharField(max_length=255, blank=True, help_text="Full registered legal entity name.")
    country = models.CharField(max_length=100, default="India", help_text="Country of incorporation / operations.")
    registered_address = models.TextField(blank=True, help_text="Corporate headquarters or registered address.")
    description = models.TextField(blank=True, help_text="Enterprise operating description.")
    status = models.CharField(
        max_length=20,
        choices=OrganizationStatus.choices,
        default=OrganizationStatus.ACTIVE,
        db_index=True,
        help_text="Operational lifecycle state.",
    )
    is_active = models.BooleanField(default=True, help_text="Quick boolean status indicator.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        self.is_active = (self.status == OrganizationStatus.ACTIVE)
        super().save(*args, **kwargs)

    @property
    def subsidiaries_count(self):
        return self.subsidiaries.filter(status=OrganizationStatus.ACTIVE).count()

    @property
    def total_projects_count(self):
        return Project.objects.filter(subsidiary__company=self, status=OrganizationStatus.ACTIVE).count()

    @property
    def total_sites_count(self):
        return Site.objects.filter(project__subsidiary__company=self, status=OrganizationStatus.ACTIVE).count()


class Subsidiary(models.Model):
    """
    Subsidiary company / operating division under Enterprise (e.g. MEIL Hydro Division, MEIL Solar Division).
    """

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="subsidiaries", help_text="Parent Enterprise Entity.")
    name = models.CharField(max_length=255, help_text="Subsidiary division or company title.")
    code = models.CharField(max_length=50, unique=True, help_text="Unique subsidiary code (e.g. MEIL-HYDRO).")
    legal_name = models.CharField(max_length=255, blank=True, help_text="Official registered corporate name.")
    short_name = models.CharField(max_length=100, blank=True, help_text="Abbreviated business unit moniker.")
    industry = models.CharField(max_length=100, blank=True, help_text="Industry sector, e.g. Hydro / Solar / EPC / Water Infrastructure.")
    country = models.CharField(max_length=100, default="India", help_text="Operating country.")
    registered_address = models.TextField(blank=True, help_text="Division office or registered address.")
    status = models.CharField(
        max_length=20,
        choices=OrganizationStatus.choices,
        default=OrganizationStatus.ACTIVE,
        db_index=True,
        help_text="Operational lifecycle state.",
    )
    is_active = models.BooleanField(default=True, help_text="Quick boolean status indicator.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subsidiary"
        verbose_name_plural = "Subsidiaries"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        self.is_active = (self.status == OrganizationStatus.ACTIVE)
        super().save(*args, **kwargs)

    @property
    def parent_company(self):
        return self.company

    @property
    def projects_count(self):
        return self.projects.filter(status=OrganizationStatus.ACTIVE).count()

    @property
    def sites_count(self):
        return Site.objects.filter(project__subsidiary=self, status=OrganizationStatus.ACTIVE).count()


class Project(models.Model):
    """
    Infrastructure project under a subsidiary company (e.g. Polavaram Irrigation Project).
    """

    subsidiary = models.ForeignKey(Subsidiary, on_delete=models.PROTECT, related_name="projects", help_text="Parent Subsidiary Division.")
    name = models.CharField(max_length=255, help_text="Infrastructure project title.")
    code = models.CharField(max_length=50, unique=True, help_text="Unique project identifier (e.g. PRJ-POL-01).")
    description = models.TextField(blank=True, help_text="Project scope and engineering description.")
    location = models.CharField(max_length=255, blank=True, help_text="Geographic city, state, or regional location.")
    status = models.CharField(
        max_length=20,
        choices=OrganizationStatus.choices,
        default=OrganizationStatus.ACTIVE,
        db_index=True,
        help_text="Project lifecycle state.",
    )
    start_date = models.DateField(null=True, blank=True, help_text="Official construction or commissioning date.")
    end_date = models.DateField(null=True, blank=True, help_text="Estimated or actual completion date.")
    is_active = models.BooleanField(default=True, help_text="Quick boolean status indicator.")
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
        help_text="User who registered this infrastructure project.",
    )
    updated_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_projects",
        help_text="User who last updated this infrastructure project.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(start_date__isnull=True)
                | models.Q(end_date__isnull=True)
                | models.Q(start_date__lte=models.F("end_date")),
                name="check_project_start_before_end",
            ),
        ]
        indexes = [
            models.Index(fields=["subsidiary", "status"], name="idx_proj_sub_status"),
            models.Index(fields=["code"], name="idx_proj_code"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError({
                    "end_date": "Project end date must be on or after start date."
                })

    def save(self, *args, **kwargs):
        self.clean()
        self.is_active = (self.status == OrganizationStatus.ACTIVE)
        super().save(*args, **kwargs)

    @property
    def company(self):
        return self.subsidiary.company

    @property
    def project_code(self):
        return self.code

    @property
    def project_name(self):
        return self.name

    @property
    def sites_count(self):
        return self.sites.filter(status=OrganizationStatus.ACTIVE).count()


class Site(models.Model):
    """
    Operational site where ESG activities, metering, fuel/power readings, and telemetry occur.
    Primary operational boundary for emissions accounting and evidence verification.
    """

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="sites", help_text="Parent Infrastructure Project.")
    name = models.CharField(max_length=255, help_text="Operational facility or site name.")
    code = models.CharField(max_length=50, unique=True, help_text="Unique site boundary identifier (e.g. SITE-POL-DAM-01).")
    facility_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Facility type: e.g. Hydroelectric Dam, Solar Array, Thermal Plant, Pumping Station, Substation.",
    )
    location = models.CharField(max_length=255, blank=True, help_text="Geographic city, state, or physical address.")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text="GPS latitude coordinate.")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text="GPS longitude coordinate.")
    contact_person = models.CharField(max_length=150, blank=True, help_text="Site in-charge or contact engineer.")
    contact_email = models.EmailField(blank=True, help_text="Site operational correspondence email.")
    description = models.TextField(blank=True, help_text="Operational ESG boundary details.")
    status = models.CharField(
        max_length=20,
        choices=OrganizationStatus.choices,
        default=OrganizationStatus.ACTIVE,
        db_index=True,
        help_text="Site operational state.",
    )
    operational_start_date = models.DateField(
        null=True, blank=True, help_text="Commissioning or operational start date."
    )
    operational_end_date = models.DateField(
        null=True, blank=True, help_text="Decommissioning or operational closure date."
    )
    is_active = models.BooleanField(default=True, help_text="Quick boolean status indicator.")
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_sites",
        help_text="User who registered this operational site.",
    )
    updated_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_sites",
        help_text="User who last updated this operational site.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Operational Site"
        verbose_name_plural = "Operational Sites"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(operational_start_date__isnull=True)
                | models.Q(operational_end_date__isnull=True)
                | models.Q(operational_start_date__lte=models.F("operational_end_date")),
                name="check_site_start_before_end",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "status"], name="idx_site_proj_status"),
            models.Index(fields=["code"], name="idx_site_code"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.operational_start_date and self.operational_end_date:
            if self.operational_start_date > self.operational_end_date:
                raise ValidationError({
                    "operational_end_date": "Operational end date must be on or after start date."
                })

    def save(self, *args, **kwargs):
        self.clean()
        self.is_active = (self.status == OrganizationStatus.ACTIVE)
        super().save(*args, **kwargs)

    @property
    def subsidiary(self):
        return self.project.subsidiary

    @property
    def company(self):
        return self.project.subsidiary.company

    @property
    def site_code(self):
        return self.code

    @property
    def site_name(self):
        return self.name


# -----------------------------------------------------------------------------
# RELATIONAL ORGANIZATIONAL SCOPE ASSIGNMENTS
# -----------------------------------------------------------------------------

class SiteAssignment(models.Model):
    """
    Assigns a user (typically Site Manager) to specific operational site(s).
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="site_assignments")
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="assigned_users")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Site Assignment"
        verbose_name_plural = "Site Assignments"
        unique_together = ("user", "site")

    def __str__(self):
        return f"{self.user.username} -> Site: {self.site.name}"


class SubsidiaryAssignment(models.Model):
    """
    Assigns a user (typically Subsidiary Manager) to specific subsidiary(ies).
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subsidiary_assignments")
    subsidiary = models.ForeignKey(Subsidiary, on_delete=models.PROTECT, related_name="assigned_users")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Subsidiary Assignment"
        verbose_name_plural = "Subsidiary Assignments"
        unique_together = ("user", "subsidiary")

    def __str__(self):
        return f"{self.user.username} -> Subsidiary: {self.subsidiary.name}"


class ProjectAssignment(models.Model):
    """
    Assigns a user to a specific project.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_assignments")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="assigned_users")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Project Assignment"
        verbose_name_plural = "Project Assignments"
        unique_together = ("user", "project")

    def __str__(self):
        return f"{self.user.username} -> Project: {self.project.name}"


class CompanyAssignment(models.Model):
    """
    Assigns a user to the top enterprise company scope.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="company_assignments")
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="assigned_users")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Company Assignment"
        verbose_name_plural = "Company Assignments"
        unique_together = ("user", "company")

    def __str__(self):
        return f"{self.user.username} -> Company: {self.company.name}"


# -----------------------------------------------------------------------------
# AUDIT-READY AUTHENTICATION & ACCESS EVENT LOGGING
# -----------------------------------------------------------------------------

class AuthAuditLog(models.Model):
    """
    Tracks authentication and authorization security events for compliance,
    BRSR governance, and audit readiness.
    """

    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "LOGIN_SUCCESS", "Login Success"
        LOGIN_FAILURE = "LOGIN_FAILURE", "Login Failure"
        LOGOUT = "LOGOUT", "Logout"
        PASSWORD_CHANGE = "PASSWORD_CHANGE", "Password Changed"
        PASSWORD_RESET_REQUEST = "PASSWORD_RESET_REQUEST", "Password Reset Requested"
        PASSWORD_RESET_SUCCESS = "PASSWORD_RESET_SUCCESS", "Password Reset Completed"
        ACCOUNT_DISABLED = "ACCOUNT_DISABLED", "Account Disabled"
        ROLE_CHANGED = "ROLE_CHANGED", "Role Changed"
        ASSIGNMENT_CHANGED = "ASSIGNMENT_CHANGED", "Assignment Changed"
        UNAUTHORIZED_ACCESS_ATTEMPT = "UNAUTHORIZED_ACCESS_ATTEMPT", "Unauthorized Access Attempt"
        ORGANIZATION_CREATED = "ORGANIZATION_CREATED", "Organization Entity Created"
        ORGANIZATION_UPDATED = "ORGANIZATION_UPDATED", "Organization Entity Updated"
        ORGANIZATION_DEACTIVATED = "ORGANIZATION_DEACTIVATED", "Organization Entity Deactivated"
        PROJECT_CREATED = "PROJECT_CREATED", "Project Created"
        PROJECT_UPDATED = "PROJECT_UPDATED", "Project Updated"
        PROJECT_DEACTIVATED = "PROJECT_DEACTIVATED", "Project Deactivated"
        SITE_CREATED = "SITE_CREATED", "Site Created"
        SITE_UPDATED = "SITE_UPDATED", "Site Updated"
        SITE_DEACTIVATED = "SITE_DEACTIVATED", "Site Deactivated"
        PERIOD_CREATED = "PERIOD_CREATED", "Reporting Period Created"
        PERIOD_UPDATED = "PERIOD_UPDATED", "Reporting Period Updated"
        PERIOD_STATUS_CHANGED = "PERIOD_STATUS_CHANGED", "Reporting Period Status Changed"
        ACTIVITY_MASTER_CREATED = "ACTIVITY_MASTER_CREATED", "Activity Master Created"
        ACTIVITY_MASTER_UPDATED = "ACTIVITY_MASTER_UPDATED", "Activity Master Updated"
        ACTIVITY_MASTER_DEACTIVATED = "ACTIVITY_MASTER_DEACTIVATED", "Activity Master Deactivated"
        ACTIVITY_CATEGORY_CREATED = "ACTIVITY_CATEGORY_CREATED", "Activity Category Created"
        ACTIVITY_CATEGORY_UPDATED = "ACTIVITY_CATEGORY_UPDATED", "Activity Category Updated"
        UNIT_CREATED = "UNIT_CREATED", "Unit of Measure Created"
        UNIT_UPDATED = "UNIT_UPDATED", "Unit of Measure Updated"
        ACTIVITY_RECORD_CREATED = "ACTIVITY_RECORD_CREATED", "Activity Record Created"
        ACTIVITY_RECORD_UPDATED = "ACTIVITY_RECORD_UPDATED", "Activity Record Updated"
        ACTIVITY_RECORD_DELETED = "ACTIVITY_RECORD_DELETED", "Activity Record Deleted"
        EVIDENCE_UPLOADED = "EVIDENCE_UPLOADED", "Evidence Document Uploaded"
        EVIDENCE_DOWNLOADED = "EVIDENCE_DOWNLOADED", "Evidence Document Downloaded"
        EVIDENCE_RETIRED = "EVIDENCE_RETIRED", "Evidence Document Retired"
        EVIDENCE_DELETED = "EVIDENCE_DELETED", "Evidence Document Deleted"
        VALIDATION_EXECUTED = "VALIDATION_EXECUTED", "Validation Run Executed"
        VALIDATION_RULE_CREATED = "VALIDATION_RULE_CREATED", "Validation Rule Created"
        VALIDATION_RULE_UPDATED = "VALIDATION_RULE_UPDATED", "Validation Rule Updated"

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    username_attempted = models.CharField(max_length=150, blank=True)
    event_type = models.CharField(max_length=50, choices=EventType.choices, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    resource_accessed = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Authentication Audit Log"
        verbose_name_plural = "Authentication Audit Logs"
        ordering = ["-created_at"]

    def __str__(self):
        status = "SUCCESS" if self.success else "FAILURE"
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {self.event_type} - {self.username_attempted or (self.user.username if self.user else 'Anonymous')} ({status})"


# -----------------------------------------------------------------------------
# PHASE 04: REPORTING PERIODS & TEMPORAL GOVERNANCE
# -----------------------------------------------------------------------------

class PeriodStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"
    LOCKED = "LOCKED", "Locked"
    FINALIZED = "FINALIZED", "Finalized"


class ReportingPeriod(models.Model):
    """
    Reporting Period Domain Model for MEIL ESG CONTROL TOWER.

    Establishes the authoritative temporal boundary for:
    - ESG Activity Data Entry
    - Evidence Ingestion & Verification
    - Scope 1, Scope 2, Scope 3 Emission Accounting
    - Consolidation & SEBI BRSR Reporting
    - Audit Assurance & Data Lineage
    """

    ALLOWED_TRANSITIONS = {
        PeriodStatus.DRAFT: [PeriodStatus.OPEN],
        PeriodStatus.OPEN: [PeriodStatus.CLOSED],
        PeriodStatus.CLOSED: [PeriodStatus.OPEN, PeriodStatus.LOCKED],
        PeriodStatus.LOCKED: [PeriodStatus.CLOSED, PeriodStatus.FINALIZED],
        PeriodStatus.FINALIZED: [],
    }

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="reporting_periods",
        help_text="Organizational enterprise company scope.",
    )
    subsidiary = models.ForeignKey(
        Subsidiary,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reporting_periods",
        help_text="Optional subsidiary division scope (if null, applies enterprise-wide across company).",
    )
    code = models.CharField(
        max_length=50,
        help_text="Stable period identifier (e.g. FY2025-26 or FY2025-Q1).",
    )
    name = models.CharField(
        max_length=150,
        help_text="Descriptive period label (e.g. FY 2025-26 Annual ESG Cycle).",
    )
    fiscal_year = models.CharField(
        max_length=50,
        help_text="Fiscal year label (e.g. FY 2025-26).",
    )
    start_date = models.DateField(
        help_text="Period start date (inclusive). Authoritative temporal boundary.",
    )
    end_date = models.DateField(
        help_text="Period end date (inclusive). Authoritative temporal boundary.",
    )
    status = models.CharField(
        max_length=20,
        choices=PeriodStatus.choices,
        default=PeriodStatus.DRAFT,
        db_index=True,
        help_text="Controlled lifecycle state.",
    )
    description = models.TextField(
        blank=True,
        help_text="Operational notes or compliance reporting guidelines.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_reporting_periods",
        help_text="User who initiated this reporting cycle.",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_reporting_periods",
        help_text="User who last updated or transitioned this period.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Reporting Period"
        verbose_name_plural = "Reporting Periods"
        ordering = ["-start_date", "code"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(start_date__lt=models.F("end_date")),
                name="check_period_start_before_end",
            ),
            models.UniqueConstraint(
                fields=["company", "code"],
                name="unique_company_period_code",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="idx_period_company_status"),
            models.Index(fields=["start_date", "end_date"], name="idx_period_dates"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError({
                    "end_date": "End date must be strictly after start date."
                })

            # Overlapping period validation:
            # Prevent conflicting reporting periods within the same organizational scope
            if self.company_id:
                qs = ReportingPeriod.objects.filter(company_id=self.company_id)
                if self.pk:
                    qs = qs.exclude(pk=self.pk)

                if self.subsidiary_id:
                    qs = qs.filter(
                        models.Q(subsidiary_id=self.subsidiary_id) | models.Q(subsidiary__isnull=True)
                    )
                else:
                    # Enterprise period covers all subsidiaries or other enterprise periods
                    pass

                conflicting = qs.filter(
                    start_date__lte=self.end_date,
                    end_date__gte=self.start_date,
                ).first()

                if conflicting:
                    raise ValidationError(
                        f"Reporting period dates ({self.start_date} to {self.end_date}) overlap with "
                        f"existing period '{conflicting.name}' ({conflicting.code}: {conflicting.start_date} to {conflicting.end_date})."
                    )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_draft(self):
        return self.status == PeriodStatus.DRAFT

    @property
    def is_open(self):
        return self.status == PeriodStatus.OPEN

    @property
    def is_closed(self):
        return self.status == PeriodStatus.CLOSED

    @property
    def is_locked(self):
        return self.status == PeriodStatus.LOCKED

    @property
    def is_finalized(self):
        return self.status == PeriodStatus.FINALIZED

    @property
    def allows_data_entry(self):
        """Operational data entry is permitted ONLY when period is explicitly OPEN."""
        return self.status == PeriodStatus.OPEN

    @property
    def allows_data_modification(self):
        """Data modifications are permitted ONLY when period is OPEN."""
        return self.status == PeriodStatus.OPEN

    @property
    def allows_metadata_edit(self):
        """Period configuration can be edited in DRAFT, OPEN, or CLOSED state, but NOT once LOCKED or FINALIZED."""
        return self.status in [PeriodStatus.DRAFT, PeriodStatus.OPEN, PeriodStatus.CLOSED]

    def get_allowed_transitions(self):
        return self.ALLOWED_TRANSITIONS.get(self.status, [])

    def can_transition_to(self, target_status):
        return target_status in self.get_allowed_transitions()

    @property
    def status_badge_class(self):
        badge_map = {
            PeriodStatus.DRAFT: "badge-secondary",
            PeriodStatus.OPEN: "badge-success",
            PeriodStatus.CLOSED: "badge-warning",
            PeriodStatus.LOCKED: "badge-danger",
            PeriodStatus.FINALIZED: "badge-info",
        }
        return badge_map.get(self.status, "badge-secondary")


# -----------------------------------------------------------------------------
# PHASE 06: ACTIVITY MASTER & ESG DATA CATALOG FOUNDATION
# -----------------------------------------------------------------------------

class MasterStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"


class UnitDimension(models.TextChoices):
    VOLUME = "VOLUME", "Volume"
    ENERGY = "ENERGY", "Energy"
    MASS = "MASS", "Mass"
    DISTANCE = "DISTANCE", "Distance"
    TIME = "TIME", "Time"
    AREA = "AREA", "Area"
    COUNT = "COUNT", "Count / Unit"
    OTHER = "OTHER", "Other"


class ScopeClassification(models.TextChoices):
    SCOPE_1 = "SCOPE_1", "Scope 1 (Direct Emissions)"
    SCOPE_2 = "SCOPE_2", "Scope 2 (Indirect - Purchased Energy)"
    SCOPE_3 = "SCOPE_3", "Scope 3 (Value Chain / Other Indirect)"
    NON_GHG = "NON_GHG", "Non-GHG / ESG Only"
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT", "Context Dependent"


class CollectionFrequency(models.TextChoices):
    DAILY = "DAILY", "Daily"
    WEEKLY = "WEEKLY", "Weekly"
    MONTHLY = "MONTHLY", "Monthly"
    QUARTERLY = "QUARTERLY", "Quarterly"
    ANNUAL = "ANNUAL", "Annual"
    AS_REQUIRED = "AS_REQUIRED", "As Required"


class ActivityCategory(models.Model):
    """
    Centralized ESG Activity Category grouping.
    Defines logical ESG operational groupings:
    - Fuel
    - Electricity & Energy
    - Water
    - Waste
    - Vehicle / Transport
    - Travel
    - Other ESG Activities
    """

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Machine-readable unique category identifier (e.g. FUEL, ENERGY, WATER).",
    )
    name = models.CharField(
        max_length=150,
        help_text="Human-readable category title.",
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed category description and boundary guidelines.",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Sorting sequence for UI catalog presentation.",
    )
    status = models.CharField(
        max_length=20,
        choices=MasterStatus.choices,
        default=MasterStatus.ACTIVE,
        db_index=True,
        help_text="Lifecycle state of the category.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Fast lookup flag matching status == ACTIVE.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_activity_categories",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_activity_categories",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Activity Category"
        verbose_name_plural = "Activity Categories"
        ordering = ["display_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip().upper()

    def save(self, *args, **kwargs):
        self.clean()
        self.is_active = (self.status == MasterStatus.ACTIVE)
        super().save(*args, **kwargs)

    @property
    def status_badge_class(self):
        return "badge-success" if self.status == MasterStatus.ACTIVE else "badge-secondary"


class UnitOfMeasure(models.Model):
    """
    Controlled Measurement Unit definition for MEIL ESG CONTROL TOWER.
    Provides the standardized basis for future telemetry validation, conversion, and calculations.
    """

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Machine-readable standard unit identifier (e.g. LITRE, KWH, MWH, KL, KG, TONNE, KM).",
    )
    name = models.CharField(
        max_length=100,
        help_text="Human-readable unit title (e.g. Litre, Kilowatt Hour, Kilolitre).",
    )
    symbol = models.CharField(
        max_length=20,
        help_text="Short unit symbol (e.g. L, kWh, kL, t, km).",
    )
    dimension = models.CharField(
        max_length=30,
        choices=UnitDimension.choices,
        default=UnitDimension.VOLUME,
        help_text="Physical dimension/type of measurement.",
    )
    description = models.TextField(
        blank=True,
        help_text="Standard measurement notes or conversion references.",
    )
    status = models.CharField(
        max_length=20,
        choices=MasterStatus.choices,
        default=MasterStatus.ACTIVE,
        db_index=True,
        help_text="Lifecycle state of the unit.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Fast lookup flag matching status == ACTIVE.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_units",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_units",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Unit of Measure"
        verbose_name_plural = "Units of Measure"
        ordering = ["dimension", "name"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip().upper()

    def save(self, *args, **kwargs):
        self.clean()
        self.is_active = (self.status == MasterStatus.ACTIVE)
        super().save(*args, **kwargs)

    @property
    def status_badge_class(self):
        return "badge-success" if self.status == MasterStatus.ACTIVE else "badge-secondary"


class ActivityMaster(models.Model):
    """
    Authoritative ESG Activity Master Catalog for MEIL ESG CONTROL TOWER.

    Defines WHAT ESG activity types can be recorded across the enterprise:
    - Fuel consumption, electricity, water extraction, waste disposal, transport, travel.
    - Controlled units, allowed unit sets.
    - Scope classification metadata (Scope 1, 2, 3, Non-GHG, Context-Dependent).
    - Evidence attachment requirements guidance.
    - Validation and calculation metadata integration points for downstream modules.

    CRITICAL: This is master reference data, NOT an operational observation record.
    """

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Stable unique activity identifier (e.g. FUEL-DIESEL, ELEC-GRID, WATER-MUNICIPAL).",
    )
    name = models.CharField(
        max_length=200,
        help_text="Human-readable activity name (e.g. Diesel Consumption - Stationary & Equipment).",
    )
    category = models.ForeignKey(
        ActivityCategory,
        on_delete=models.PROTECT,
        related_name="activities",
        help_text="Governing ESG activity category.",
    )
    activity_type = models.CharField(
        max_length=100,
        help_text="Specific operational classification (e.g. Stationary Combustion, Mobile Combustion, Purchased Electricity).",
    )
    base_unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="base_activities",
        help_text="Standard primary reporting unit of measure.",
    )
    allowed_units = models.ManyToManyField(
        UnitOfMeasure,
        blank=True,
        related_name="allowed_activities",
        help_text="Permissible units allowed for operational telemetry data entry.",
    )
    scope_classification = models.CharField(
        max_length=30,
        choices=ScopeClassification.choices,
        default=ScopeClassification.SCOPE_1,
        db_index=True,
        help_text="Regulatory GHG Scope classification metadata.",
    )
    collection_frequency = models.CharField(
        max_length=30,
        choices=CollectionFrequency.choices,
        default=CollectionFrequency.MONTHLY,
        help_text="Standard expected data reporting cadence.",
    )
    evidence_requirement_hint = models.CharField(
        max_length=255,
        blank=True,
        help_text="Regulatory audit evidence expectation (e.g. Fuel Log / Tax Invoice / Meter Reading).",
    )
    description = models.TextField(
        blank=True,
        help_text="Operational definition, boundary rules, and guidance for site managers.",
    )
    applicability_notes = models.TextField(
        blank=True,
        help_text="Site applicability guidance (e.g. Applicable to all civil and plant sites with diesel generators).",
    )
    validation_rules = models.JSONField(
        default=dict,
        blank=True,
        help_text="Future validation rule definitions (e.g. positive quantity, evidence mandatory, thresholds).",
    )
    calculation_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Future GHG calculation and emission factor lineage metadata.",
    )
    status = models.CharField(
        max_length=20,
        choices=MasterStatus.choices,
        default=MasterStatus.ACTIVE,
        db_index=True,
        help_text="Lifecycle state (ACTIVE/INACTIVE). Deactivation preserves historical references.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Fast lookup flag matching status == ACTIVE.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_activities",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_activities",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Activity Master"
        verbose_name_plural = "Activity Master Entries"
        ordering = ["category__display_order", "category__name", "name"]
        indexes = [
            models.Index(fields=["category", "status"], name="idx_act_cat_status"),
            models.Index(fields=["code"], name="idx_act_code"),
            models.Index(fields=["scope_classification"], name="idx_act_scope"),
        ]

    def __str__(self):
        return f"{self.name} [{self.code}]"

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip().upper()

    def save(self, *args, **kwargs):
        self.clean()
        self.is_active = (self.status == MasterStatus.ACTIVE)
        super().save(*args, **kwargs)

    @property
    def status_badge_class(self):
        return "badge-success" if self.status == MasterStatus.ACTIVE else "badge-secondary"

    @property
    def scope_badge_class(self):
        scope_map = {
            ScopeClassification.SCOPE_1: "badge-danger",
            ScopeClassification.SCOPE_2: "badge-warning",
            ScopeClassification.SCOPE_3: "badge-info",
            ScopeClassification.NON_GHG: "badge-success",
            ScopeClassification.CONTEXT_DEPENDENT: "badge-secondary",
        }
        return scope_map.get(self.scope_classification, "badge-secondary")


# -----------------------------------------------------------------------------
# PHASE 08: ESG DATA ENTRY & ACTIVITY RECORDS
# -----------------------------------------------------------------------------

class RecordStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    READY = "READY", "Ready for Submission"
    SUBMITTED = "SUBMITTED", "Submitted"
    VERIFIED = "VERIFIED", "Verified"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Revision Requested"


# -----------------------------------------------------------------------------
# PHASE 10: VALIDATION ENGINE CHOICES
# -----------------------------------------------------------------------------

class ValidationSeverity(models.TextChoices):
    ERROR = "ERROR", "Error"
    WARNING = "WARNING", "Warning"
    INFO = "INFO", "Information"


class ValidationCategory(models.TextChoices):
    STRUCTURAL = "STRUCTURAL", "Structural Integrity"
    SCOPE = "SCOPE", "Organizational Scope & Hierarchy"
    PERIOD = "PERIOD", "Reporting Period & Temporal"
    ACTIVITY = "ACTIVITY", "Activity Master & Taxonomy"
    EVIDENCE = "EVIDENCE", "Audit Evidence Verification"
    CONSISTENCY = "CONSISTENCY", "Data Consistency & Range"
    WORKFLOW = "WORKFLOW", "Workflow & Submission Readiness"


class ValidationStatus(models.TextChoices):
    UNVALIDATED = "UNVALIDATED", "Not Validated"
    VALID = "VALID", "Valid"
    WARNING = "WARNING", "Valid with Warnings"
    INVALID = "INVALID", "Invalid / Errors Detected"


class ActivityRecord(models.Model):
    """
    Authoritative ESG Activity Telemetry & Operational Data Record.

    Captures actual operational activity and consumption data recorded by Site Managers:
    - Fuel consumption, electricity, water extraction, waste generated, logistics, etc.
    - Explicit relational binding to Site, ReportingPeriod, ActivityMaster, and UnitOfMeasure.
    - Server-side domain constraints: positive quantity, valid units, period date boundary.
    - Controlled lifecycle: DRAFT -> READY -> SUBMITTED (Phase 08 focuses on entry/draft/edit).
    - Future integration hooks for Evidence (Phase 09), OCR (Phase 11), Calculations (Phase 10), and Submissions (Phase 12).
    """

    site = models.ForeignKey(
        Site,
        on_delete=models.PROTECT,
        related_name="activity_records",
        help_text="Operational site where activity occurred.",
    )
    reporting_period = models.ForeignKey(
        ReportingPeriod,
        on_delete=models.PROTECT,
        related_name="activity_records",
        help_text="Governing reporting cycle boundary.",
    )
    activity = models.ForeignKey(
        ActivityMaster,
        on_delete=models.PROTECT,
        related_name="activity_records",
        help_text="Approved ESG Activity Master definition.",
    )
    measurement_date = models.DateField(
        help_text="Date of operational activity measurement, meter reading, or invoice.",
    )
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        help_text="Measured consumption or operational quantity.",
    )
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="activity_records",
        help_text="Physical unit of measure corresponding to quantity.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Operational notes, invoice number, vehicle/meter identifier, or batch description.",
    )
    evidence_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Document reference, invoice/challan number, or future Phase 09 attachment ID.",
    )
    status = models.CharField(
        max_length=30,
        choices=RecordStatus.choices,
        default=RecordStatus.DRAFT,
        db_index=True,
        help_text="Workflow status of this activity record.",
    )
    validation_status = models.CharField(
        max_length=30,
        choices=ValidationStatus.choices,
        default=ValidationStatus.UNVALIDATED,
        db_index=True,
        help_text="Deterministic data quality status evaluated by Phase 10 Validation Engine.",
    )
    last_validated_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Timestamp when this record was last evaluated by the validation engine.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_activity_records",
        help_text="User who entered this record.",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_activity_records",
        help_text="User who last updated this record.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Activity Record"
        verbose_name_plural = "Activity Records"
        ordering = ["-measurement_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gte=0),
                name="check_activity_record_quantity_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["site", "reporting_period"], name="idx_rec_site_period"),
            models.Index(fields=["activity", "measurement_date"], name="idx_rec_act_date"),
            models.Index(fields=["status"], name="idx_rec_status"),
            models.Index(fields=["validation_status"], name="idx_rec_val_status"),
            models.Index(fields=["created_at"], name="idx_rec_created"),
        ]

    def __str__(self):
        return f"{self.activity.name} @ {self.site.name}: {self.quantity} {self.unit.symbol} ({self.measurement_date})"

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()

        if self.quantity is not None and self.quantity < 0:
            raise ValidationError({"quantity": "Consumption quantity cannot be negative."})

        # Validate Unit against ActivityMaster
        if self.activity_id and self.unit_id:
            from apps.core.activity_services import validate_activity_unit
            if not validate_activity_unit(self.activity, self.unit):
                allowed_symbols = [self.activity.base_unit.symbol] + [u.symbol for u in self.activity.allowed_units.all()]
                allowed_str = ", ".join(dict.fromkeys(allowed_symbols))
                raise ValidationError({
                    "unit": f"Unit '{self.unit.name} ({self.unit.symbol})' is not permissible for activity '{self.activity.name}'. Allowed units: {allowed_str}."
                })

        # Validate Reporting Period boundary
        if self.reporting_period_id and self.measurement_date:
            if self.measurement_date < self.reporting_period.start_date or self.measurement_date > self.reporting_period.end_date:
                raise ValidationError({
                    "measurement_date": (
                        f"Measurement date ({self.measurement_date}) must fall within the reporting period boundary: "
                        f"{self.reporting_period.start_date} to {self.reporting_period.end_date}."
                    )
                })

        # Validate Site and Reporting Period organizational alignment
        if self.site_id and self.reporting_period_id:
            site_company = self.site.project.subsidiary.company
            site_subsidiary = self.site.project.subsidiary
            if self.reporting_period.company_id != site_company.id:
                raise ValidationError({
                    "reporting_period": f"Reporting period company '{self.reporting_period.company.name}' does not match site's enterprise company '{site_company.name}'."
                })
            if self.reporting_period.subsidiary_id and self.reporting_period.subsidiary_id != site_subsidiary.id:
                raise ValidationError({
                    "reporting_period": f"Reporting period subsidiary '{self.reporting_period.subsidiary.name}' does not match site's division '{site_subsidiary.name}'."
                })

        # Validate Activity is ACTIVE
        if self.activity_id and not self.activity.is_active:
            raise ValidationError({
                "activity": f"Activity '{self.activity.name}' is inactive and cannot accept new telemetry entries."
            })

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        # Only run full model clean if saving the whole model or modifying core operational attributes
        if update_fields is None or any(
            f in update_fields
            for f in [
                "quantity", "unit", "unit_id", "measurement_date", "site",
                "site_id", "activity", "activity_id", "reporting_period", "reporting_period_id"
            ]
        ):
            self.clean()
        super().save(*args, **kwargs)

    @property
    def is_draft(self):
        return self.status == RecordStatus.DRAFT

    @property
    def is_ready(self):
        return self.status == RecordStatus.READY

    @property
    def is_submitted(self):
        return self.status == RecordStatus.SUBMITTED

    @property
    def is_editable_by_site_manager(self):
        """
        Site Manager can edit records in DRAFT, READY, or REJECTED state,
        provided the reporting period is currently OPEN.
        Once SUBMITTED, VERIFIED, or APPROVED, records are locked from Site Manager editing.
        """
        editable_statuses = [RecordStatus.DRAFT, RecordStatus.READY, RecordStatus.REJECTED]
        return (
            self.status in editable_statuses
            and self.reporting_period.allows_data_modification
        )

    @property
    def status_badge_class(self):
        badge_map = {
            RecordStatus.DRAFT: "badge-secondary",
            RecordStatus.READY: "badge-info",
            RecordStatus.SUBMITTED: "badge-primary",
            RecordStatus.VERIFIED: "badge-warning",
            RecordStatus.APPROVED: "badge-success",
            RecordStatus.REJECTED: "badge-danger",
        }
        return badge_map.get(self.status, "badge-secondary")

    @property
    def evidence_count(self):
        """Returns the number of active supporting evidence documents attached."""
        return self.evidence_files.filter(status=EvidenceStatus.ACTIVE).count()

    @property
    def total_evidence_count(self):
        """Returns total count of attached evidence documents including retired."""
        return self.evidence_files.count()

    @property
    def has_evidence(self):
        """Boolean indicator whether active supporting evidence is present."""
        return self.evidence_files.filter(status=EvidenceStatus.ACTIVE).exists()

    @property
    def is_validated(self):
        """Returns True if the record was evaluated and passed without blocking errors."""
        return self.validation_status in [ValidationStatus.VALID, ValidationStatus.WARNING]

    @property
    def has_validation_errors(self):
        """Returns True if the record was evaluated and has blocking errors."""
        return self.validation_status == ValidationStatus.INVALID

    @property
    def latest_validation_run(self):
        """Returns the most recent ValidationRun instance."""
        return self.validation_runs.order_by("-executed_at", "-run_number").first()

    @property
    def validation_badge_class(self):
        badge_map = {
            ValidationStatus.UNVALIDATED: "badge-secondary",
            ValidationStatus.VALID: "badge-success",
            ValidationStatus.WARNING: "badge-warning",
            ValidationStatus.INVALID: "badge-danger",
        }
        return badge_map.get(self.validation_status, "badge-secondary")

    @property
    def can_submit_for_review(self):
        """Record can be advanced to READY/SUBMITTED only if it has been validated without blocking errors."""
        return self.validation_status in [ValidationStatus.VALID, ValidationStatus.WARNING]


# -----------------------------------------------------------------------------
# PHASE 09: EVIDENCE MANAGEMENT & AUDIT VERIFICATION
# -----------------------------------------------------------------------------

def evidence_file_upload_path(instance, filename):
    """
    Computes a deterministic, collision-safe, traversal-proof storage path for uploaded evidence.
    Format: evidence/<site_code>/<period_code>/rec_<record_id>/<uuid_prefix>_<safe_filename>
    """
    import os
    import re
    from uuid import uuid4
    from django.utils.text import get_valid_filename

    clean_name = get_valid_filename(os.path.basename(filename))
    base, ext = os.path.splitext(clean_name)
    safe_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", base)[:50]
    safe_filename = f"{uuid4().hex[:12]}_{safe_base}{ext.lower()}"

    site_code = "unscoped_site"
    period_code = "unscoped_period"
    record_id = "0"

    if instance and instance.activity_record_id:
        record = instance.activity_record
        site_code = re.sub(r"[^a-zA-Z0-9_\-]", "_", record.site.code.lower())
        period_code = re.sub(r"[^a-zA-Z0-9_\-]", "_", record.reporting_period.code.lower())
        record_id = str(record.id)

    return f"evidence/{site_code}/{period_code}/rec_{record_id}/{safe_filename}"


class EvidenceType(models.TextChoices):
    INVOICE = "INVOICE", "Tax / Commercial Invoice"
    UTILITY_BILL = "UTILITY_BILL", "Utility Bill (Electricity / Water / Gas)"
    METER_READING = "METER_READING", "Meter Reading / Calibration Log"
    FUEL_CHALLAN = "FUEL_CHALLAN", "Fuel Delivery Challan / DG Log"
    WASTE_MANIFEST = "WASTE_MANIFEST", "Waste Manifest / Weighbridge Slip"
    TRANSPORT_RECORD = "TRANSPORT_RECORD", "Transport / Logistics Record"
    TRAVEL_RECORD = "TRAVEL_RECORD", "Business Travel Record"
    PURCHASE_DOCUMENT = "PURCHASE_DOCUMENT", "Purchase Order / Goods Receipt Note"
    SUPPLIER_CERTIFICATE = "SUPPLIER_CERTIFICATE", "Supplier Certificate / Spec Sheet"
    ERP_EXTRACT = "ERP_EXTRACT", "ERP / Financial System Export"
    LAB_REPORT = "LAB_REPORT", "Lab Test Report / Emission Test"
    RENEWABLE_CERTIFICATE = "RENEWABLE_CERTIFICATE", "Renewable Energy Certificate (REC/PPA)"
    OTHER = "OTHER", "Other ESG Supporting Document"


class EvidenceStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    RETIRED = "RETIRED", "Retired"


class Evidence(models.Model):
    """
    Authoritative ESG Supporting Evidence Document.

    Links operational physical documentation (fuel invoices, utility bills, weighbridge slips,
    meter logs, lab certifications) directly to ActivityRecord operational telemetry.
    Establishes the evidence foundation for future Phase 10 Validation, Phase 11 OCR,
    and Phase 14 Auditor Trace-This-Number lineage.
    """

    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.PROTECT,
        related_name="evidence_files",
        help_text="Operational activity record supported by this evidence document.",
    )
    file = models.FileField(
        upload_to=evidence_file_upload_path,
        max_length=255,
        help_text="Stored evidence document file.",
    )
    evidence_type = models.CharField(
        max_length=50,
        choices=EvidenceType.choices,
        default=EvidenceType.INVOICE,
        db_index=True,
        help_text="Document classification category.",
    )
    original_filename = models.CharField(
        max_length=255,
        help_text="Original filename as provided by the client during upload.",
    )
    file_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Verified MIME / Content type (e.g. application/pdf, image/jpeg).",
    )
    file_size = models.PositiveBigIntegerField(
        help_text="File size in bytes.",
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA-256 cryptographic hash of the file payload for tamper-evident audit integrity.",
    )
    description = models.TextField(
        blank=True,
        help_text="Document description, invoice/challan number, or operational commentary.",
    )
    status = models.CharField(
        max_length=30,
        choices=EvidenceStatus.choices,
        default=EvidenceStatus.ACTIVE,
        db_index=True,
        help_text="Lifecycle state of this evidence document.",
    )
    retirement_reason = models.TextField(
        blank=True,
        help_text="Audit explanation when this evidence document is retired or replaced.",
    )
    retired_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this evidence was marked retired.",
    )
    retired_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retired_evidence",
        help_text="User who retired this evidence.",
    )
    ocr_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Future Phase 11 OCR ingestion pipeline metadata (extracted entities, confidence, status).",
    )
    validation_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Future Phase 10 automated validation rule execution metadata.",
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_evidence",
        help_text="User who uploaded this evidence file.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Supporting Evidence"
        verbose_name_plural = "Supporting Evidence Documents"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(file_size__gt=0),
                name="check_evidence_file_size_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["activity_record", "status"], name="idx_evid_rec_status"),
            models.Index(fields=["evidence_type"], name="idx_evid_type"),
            models.Index(fields=["created_at"], name="idx_evid_created"),
            models.Index(fields=["file_hash"], name="idx_evid_hash"),
        ]

    def __str__(self):
        return f"{self.get_evidence_type_display()}: {self.original_filename} (Record #{self.activity_record_id})"

    @property
    def is_active(self):
        return self.status == EvidenceStatus.ACTIVE

    @property
    def is_retired(self):
        return self.status == EvidenceStatus.RETIRED

    @property
    def site(self):
        return self.activity_record.site

    @property
    def project(self):
        return self.activity_record.site.project

    @property
    def subsidiary(self):
        return self.activity_record.site.project.subsidiary

    @property
    def company(self):
        return self.activity_record.site.project.subsidiary.company

    @property
    def reporting_period(self):
        return self.activity_record.reporting_period

    @property
    def file_extension(self):
        import os
        return os.path.splitext(self.original_filename)[1].lower()

    @property
    def is_previewable(self):
        return self.file_extension in [".pdf", ".jpg", ".jpeg", ".png"]

    @property
    def is_pdf(self):
        return self.file_extension == ".pdf"

    @property
    def is_image(self):
        return self.file_extension in [".jpg", ".jpeg", ".png"]

    @property
    def file_size_formatted(self):
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.2f} MB"

    @property
    def status_badge_class(self):
        return "badge-success" if self.status == EvidenceStatus.ACTIVE else "badge-secondary"


# -----------------------------------------------------------------------------
# PHASE 10: VALIDATION ENGINE & DATA QUALITY AUDIT
# -----------------------------------------------------------------------------

class ValidationRule(models.Model):
    """
    Controlled ESG Validation Rule Definition.

    Defines deterministic data quality, taxonomy, boundary, and evidence rules evaluated
    by the Validation Engine before records proceed through Submission, Review,
    Anomaly Detection, or GHG Scope 1/2/3 Calculation.
    """

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Stable unique rule identifier (e.g. STRUCT_REQ_QUANTITY, EVID_MANDATORY_CHECK).",
    )
    name = models.CharField(
        max_length=150,
        help_text="Human-readable rule name.",
    )
    description = models.TextField(
        blank=True,
        help_text="Operational description explaining what this rule checks and why.",
    )
    category = models.CharField(
        max_length=30,
        choices=ValidationCategory.choices,
        db_index=True,
        help_text="Functional validation layer classification.",
    )
    severity = models.CharField(
        max_length=20,
        choices=ValidationSeverity.choices,
        default=ValidationSeverity.ERROR,
        help_text="Severity of non-compliance (ERROR blocks progression; WARNING advises).",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this rule is active and evaluated during validation runs.",
    )
    is_blocking = models.BooleanField(
        default=True,
        help_text="If True, violations prevent the record from proceeding to submission or ready status.",
    )
    applicable_activity = models.ForeignKey(
        ActivityMaster,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validation_rules_set",
        help_text="Specific activity this rule applies to. If empty, rule applies across all activities.",
    )
    rule_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configured parameters (e.g. thresholds, required evidence types, min/max).",
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Rule revision version number for regulatory lineage and audit traceability.",
    )
    effective_from = models.DateField(
        null=True,
        blank=True,
        help_text="Effective start date from which this rule is enforced.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_validation_rules",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_validation_rules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Validation Rule"
        verbose_name_plural = "Validation Rules"
        ordering = ["category", "code"]
        indexes = [
            models.Index(fields=["category", "is_active"], name="idx_valrule_cat_act"),
            models.Index(fields=["code"], name="idx_valrule_code"),
        ]

    def __str__(self):
        return f"[{self.code}] {self.name} ({self.get_severity_display()})"

    @property
    def severity_badge_class(self):
        return {
            ValidationSeverity.ERROR: "badge-danger",
            ValidationSeverity.WARNING: "badge-warning",
            ValidationSeverity.INFO: "badge-info",
        }.get(self.severity, "badge-secondary")


class ValidationRun(models.Model):
    """
    Execution History Instance of a Validation Run for an Activity Record.

    Preserves complete immutable audit history across successive edits and revalidations.
    """

    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.CASCADE,
        related_name="validation_runs",
        help_text="Operational record evaluated during this run.",
    )
    run_number = models.PositiveIntegerField(
        default=1,
        help_text="Sequential iteration count of validation evaluations for this record.",
    )
    status = models.CharField(
        max_length=30,
        choices=ValidationStatus.choices,
        default=ValidationStatus.UNVALIDATED,
        db_index=True,
        help_text="Composite validation outcome of this run.",
    )
    total_rules_evaluated = models.PositiveIntegerField(
        default=0,
        help_text="Count of active rules executed in this run.",
    )
    error_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of blocking ERROR violations detected.",
    )
    warning_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of WARNING non-conformances detected.",
    )
    info_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of INFO informational items generated.",
    )
    summary_message = models.TextField(
        blank=True,
        help_text="Executive summary of the validation outcome.",
    )
    executed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executed_validation_runs",
        help_text="User who initiated this validation run (or System).",
    )
    executed_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when validation was executed.",
    )
    execution_duration_ms = models.PositiveIntegerField(
        default=0,
        help_text="Execution latency in milliseconds.",
    )
    rule_version_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot of rule codes and versions evaluated for regulatory lineage.",
    )

    class Meta:
        verbose_name = "Validation Run"
        verbose_name_plural = "Validation Runs"
        ordering = ["-executed_at", "-run_number"]
        indexes = [
            models.Index(fields=["activity_record", "-executed_at"], name="idx_valrun_rec_exec"),
            models.Index(fields=["status"], name="idx_valrun_status"),
        ]

    def __str__(self):
        return f"Run #{self.run_number} for Record #{self.activity_record_id}: {self.get_status_display()} ({self.executed_at.strftime('%Y-%m-%d %H:%M')})"

    @property
    def is_valid(self):
        return self.status in [ValidationStatus.VALID, ValidationStatus.WARNING]

    @property
    def has_errors(self):
        return self.error_count > 0

    @property
    def badge_class(self):
        return {
            ValidationStatus.VALID: "badge-success",
            ValidationStatus.WARNING: "badge-warning",
            ValidationStatus.INVALID: "badge-danger",
            ValidationStatus.UNVALIDATED: "badge-secondary",
        }.get(self.status, "badge-secondary")


class ValidationResult(models.Model):
    """
    Granular Rule Evaluation Result associated with a Validation Run.

    Contains field-level or record-level message, severity, context, and blocking status.
    """

    validation_run = models.ForeignKey(
        ValidationRun,
        on_delete=models.CASCADE,
        related_name="results",
        help_text="Parent validation run.",
    )
    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.CASCADE,
        related_name="validation_results",
        help_text="Target activity record.",
    )
    rule = models.ForeignKey(
        ValidationRule,
        on_delete=models.PROTECT,
        related_name="results",
        help_text="Governing validation rule that produced this outcome.",
    )
    severity = models.CharField(
        max_length=20,
        choices=ValidationSeverity.choices,
        help_text="Severity of this finding.",
    )
    is_blocking = models.BooleanField(
        default=False,
        help_text="Whether this finding blocks record progression.",
    )
    field_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Target form field name (e.g. quantity, unit, measurement_date, evidence) for UI highlighting.",
    )
    message = models.TextField(
        help_text="Clear, human-readable finding explanation for operational users.",
    )
    context_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Diagnostic context data (e.g. given value, allowed values, expected bounds).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Validation Result"
        verbose_name_plural = "Validation Results"
        ordering = ["severity", "id"]
        indexes = [
            models.Index(fields=["validation_run", "severity"], name="idx_valres_run_sev"),
            models.Index(fields=["activity_record", "created_at"], name="idx_valres_rec_created"),
        ]

    def __str__(self):
        field_str = f" [{self.field_name}]" if self.field_name else ""
        return f"{self.severity}{field_str}: {self.message}"

    @property
    def is_error(self):
        return self.severity == ValidationSeverity.ERROR

    @property
    def is_warning(self):
        return self.severity == ValidationSeverity.WARNING

    @property
    def is_info(self):
        return self.severity == ValidationSeverity.INFO

    @property
    def badge_class(self):
        return {
            ValidationSeverity.ERROR: "badge-danger",
            ValidationSeverity.WARNING: "badge-warning",
            ValidationSeverity.INFO: "badge-info",
        }.get(self.severity, "badge-secondary")



