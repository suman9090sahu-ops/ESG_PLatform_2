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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
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
    is_active = models.BooleanField(default=True, help_text="Quick boolean status indicator.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Operational Site"
        verbose_name_plural = "Operational Sites"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
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
