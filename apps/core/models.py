"""
Core Models for MEIL ESG CONTROL TOWER.

Establishes:
1. Unified Custom User Model (AbstractUser)
2. Centralized RBAC Role Models (Role, UserRole)
3. Organizational Hierarchy Foundation (Company, Subsidiary, Project, Site)
4. Relational User Scope Assignments (SiteAssignment, SubsidiaryAssignment, ProjectAssignment, CompanyAssignment)
5. Audit-Ready Authentication and Authorization Event Logging (AuthAuditLog)
"""

from decimal import Decimal
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
        OCR_REQUESTED = "OCR_REQUESTED", "OCR Processing Requested"
        OCR_STARTED = "OCR_STARTED", "OCR Processing Started"
        OCR_COMPLETED = "OCR_COMPLETED", "OCR Processing Completed"
        OCR_FAILED = "OCR_FAILED", "OCR Processing Failed"
        OCR_RETRIED = "OCR_RETRIED", "OCR Processing Retried"
        SUBMISSION_CREATED = "SUBMISSION_CREATED", "Activity Record Submitted"
        SUBMISSION_WITHDRAWN = "SUBMISSION_WITHDRAWN", "Activity Record Submission Withdrawn"
        SUBMISSION_REVIEWED = "SUBMISSION_REVIEWED", "Submission Reviewed"
        SUBMISSION_VERIFIED = "SUBMISSION_VERIFIED", "Submission Verified"
        CORRECTION_REQUESTED = "CORRECTION_REQUESTED", "Correction Requested"
        EXPLANATION_RECORDED = "EXPLANATION_RECORDED", "Explanation Recorded"
        SUBMISSION_ESCALATED = "SUBMISSION_ESCALATED", "Submission Escalated"
        CORRECTION_STARTED = "CORRECTION_STARTED", "Correction Work Started"
        CORRECTION_UPDATED = "CORRECTION_UPDATED", "Activity Record Corrected"
        CORRECTION_RESOLVED = "CORRECTION_RESOLVED", "Correction Request Resolved"
        RESUBMISSION_CREATED = "RESUBMISSION_CREATED", "Activity Record Resubmitted"
        ANOMALY_DETECTED = "ANOMALY_DETECTED", "Anomaly Detected"
        ANOMALY_ACKNOWLEDGED = "ANOMALY_ACKNOWLEDGED", "Anomaly Acknowledged"
        ANOMALY_EXPLAINED = "ANOMALY_EXPLAINED", "Anomaly Explained"
        ANOMALY_DISMISSED = "ANOMALY_DISMISSED", "Anomaly Dismissed"
        ANOMALY_RESOLVED = "ANOMALY_RESOLVED", "Anomaly Resolved"
        ANOMALY_RULE_CREATED = "ANOMALY_RULE_CREATED", "Anomaly Rule Created"
        ANOMALY_RULE_UPDATED = "ANOMALY_RULE_UPDATED", "Anomaly Rule Updated"
        ANOMALY_DETECTION_RUN = "ANOMALY_DETECTION_RUN", "Anomaly Detection Run Executed"
        SUPPLIER_CREATED = "SUPPLIER_CREATED", "Supplier Created"
        SUPPLIER_UPDATED = "SUPPLIER_UPDATED", "Supplier Updated"
        SUPPLIER_ARCHIVED = "SUPPLIER_ARCHIVED", "Supplier Archived"
        PROCUREMENT_CREATED = "PROCUREMENT_CREATED", "Procurement Created"
        PROCUREMENT_UPDATED = "PROCUREMENT_UPDATED", "Procurement Updated"
        PROCUREMENT_DELETED = "PROCUREMENT_DELETED", "Procurement Deleted"
        PROCUREMENT_SUBMITTED = "PROCUREMENT_SUBMITTED", "Procurement Submitted"
        PROCUREMENT_REVIEWED = "PROCUREMENT_REVIEWED", "Procurement Reviewed"
        PROCUREMENT_VERIFIED = "PROCUREMENT_VERIFIED", "Procurement Verified"
        PROCUREMENT_REJECTED = "PROCUREMENT_REJECTED", "Procurement Rejected"
        PROCUREMENT_CORRECTED = "PROCUREMENT_CORRECTED", "Procurement Corrected"
        PROCUREMENT_RESUBMITTED = "PROCUREMENT_RESUBMITTED", "Procurement Resubmitted"
        PROCUREMENT_ANOMALY_DETECTED = "PROCUREMENT_ANOMALY_DETECTED", "Procurement Anomaly Detected"

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

    @property
    def requires_evidence(self):
        """Returns True if this activity requires supporting audit documentation."""
        rules = self.validation_rules or {}
        return (
            rules.get("evidence_required") is True
            or rules.get("evidence_mandatory") is True
            or self.code in ["FUEL-DIESEL-STAT", "ELEC-GRID", "WASTE-HAZARDOUS", "DIESEL_GENSET"]
        )


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

    @property
    def latest_submission(self):
        """Returns the active or most recent formal Submission for this record."""
        return self.submissions.filter(is_current=True).first() or self.submissions.order_by("-submitted_at").first()

    @property
    def submission_count(self):
        """Total number of submission cycles attempted for this record."""
        return self.submissions.count()

    @property
    def is_locked_for_review(self):
        """Returns True if record is under review or approved downstream."""
        return self.status in [RecordStatus.SUBMITTED, RecordStatus.VERIFIED, RecordStatus.APPROVED]


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
    elif instance and getattr(instance, "procurement_record_id", None):
        proc = instance.procurement_record
        site_code = re.sub(r"[^a-zA-Z0-9_\-]", "_", proc.site.code.lower()) if proc.site else "proc_corp"
        period_code = re.sub(r"[^a-zA-Z0-9_\-]", "_", proc.reporting_period.code.lower()) if proc.reporting_period else "period_gen"
        record_id = f"proc_{proc.id}"

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
    meter logs, lab certifications, procurement POs) directly to ActivityRecord operational telemetry
    or ProcurementRecord commercial purchasing transactions.
    """

    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="evidence_files",
        help_text="Operational activity record supported by this evidence document.",
    )
    procurement_record = models.ForeignKey(
        "ProcurementRecord",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="evidence_files",
        help_text="Procurement record supported by this evidence document.",
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
            models.Index(fields=["procurement_record", "status"], name="idx_evid_proc_status"),
            models.Index(fields=["evidence_type"], name="idx_evid_type"),
            models.Index(fields=["created_at"], name="idx_evid_created"),
            models.Index(fields=["file_hash"], name="idx_evid_hash"),
        ]

    def __str__(self):
        ref = f"Record #{self.activity_record_id}" if self.activity_record_id else f"Procurement #{self.procurement_record_id}"
        return f"{self.get_evidence_type_display()}: {self.original_filename} ({ref})"

    def clean(self):
        super().clean()
        if not self.activity_record_id and not self.procurement_record_id:
            from django.core.exceptions import ValidationError
            raise ValidationError("Evidence document must be linked to either an ActivityRecord or a ProcurementRecord.")

    @property
    def is_active(self):
        return self.status == EvidenceStatus.ACTIVE

    @property
    def is_retired(self):
        return self.status == EvidenceStatus.RETIRED

    @property
    def site(self):
        if self.activity_record:
            return self.activity_record.site
        if self.procurement_record:
            return self.procurement_record.site
        return None

    @property
    def project(self):
        if self.activity_record:
            return self.activity_record.site.project
        if self.procurement_record:
            return self.procurement_record.project
        return None

    @property
    def subsidiary(self):
        if self.activity_record:
            return self.activity_record.site.project.subsidiary
        if self.procurement_record and self.procurement_record.project:
            return self.procurement_record.project.subsidiary
        return None

    @property
    def company(self):
        if self.activity_record:
            return self.activity_record.site.project.subsidiary.company
        if self.procurement_record:
            return self.procurement_record.company
        return None

    @property
    def reporting_period(self):
        if self.activity_record:
            return self.activity_record.reporting_period
        if self.procurement_record:
            return self.procurement_record.reporting_period
        return None

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

    @property
    def is_ocr_supported(self):
        """Returns True if the file format is supported by the OCR / document extraction pipeline."""
        return self.file_extension in [".pdf", ".jpg", ".jpeg", ".png"]

    @property
    def latest_ocr_run(self):
        """Returns the most recent or active OCRRun instance associated with this evidence."""
        return self.ocr_runs.filter(is_latest=True).first() or self.ocr_runs.order_by("-created_at").first()

    @property
    def has_ocr_run(self):
        """Returns True if at least one OCR execution has been attempted."""
        return self.ocr_runs.exists()

    @property
    def ocr_status(self):
        """Returns the status string of the latest OCR run or 'NOT_PROCESSED'."""
        latest = self.latest_ocr_run
        return latest.status if latest else "NOT_PROCESSED"

    @property
    def ocr_badge_class(self):
        """Bootstrap badge class corresponding to the OCR processing lifecycle state."""
        mapping = {
            "COMPLETED": "badge-success",
            "PROCESSING": "badge-info",
            "PENDING": "badge-warning",
            "FAILED": "badge-danger",
            "CANCELLED": "badge-secondary",
            "NOT_PROCESSED": "badge-light text-muted border",
        }
        return mapping.get(self.ocr_status, "badge-secondary")


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


# -----------------------------------------------------------------------------
# PHASE 11: OCR ENGINE & DOCUMENT-DATA EXTRACTION
# -----------------------------------------------------------------------------

class OCRStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class OCRRun(models.Model):
    """
    Immutable Execution Run for Evidence Optical Character Recognition & Text Extraction.

    Preserves multi-run historical versioning per Evidence document.
    Enforces that OCR output represents unverified extraction data rather than authoritative truth.
    """

    evidence = models.ForeignKey(
        Evidence,
        on_delete=models.CASCADE,
        related_name="ocr_runs",
        help_text="Supporting evidence document analyzed by this OCR execution.",
    )
    run_number = models.PositiveIntegerField(
        default=1,
        help_text="Sequential run counter for this specific evidence document.",
    )
    status = models.CharField(
        max_length=20,
        choices=OCRStatus.choices,
        default=OCRStatus.PENDING,
        db_index=True,
        help_text="Current lifecycle state of the OCR execution.",
    )
    engine = models.CharField(
        max_length=100,
        default="pypdf-text-extractor",
        help_text="Name of the underlying OCR / extraction engine (e.g. pypdf, tesseract, mock).",
    )
    engine_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Version identifier of the engine at time of execution.",
    )
    language = models.CharField(
        max_length=20,
        default="eng",
        help_text="Target extraction language (ISO 639-2).",
    )
    page_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of document pages processed.",
    )
    extracted_text = models.TextField(
        blank=True,
        help_text="Full aggregate raw text extracted from the document.",
    )
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Overall document text extraction confidence percentage (0.00 to 100.00).",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Descriptive failure summary if extraction fails.",
    )
    execution_duration_ms = models.PositiveIntegerField(
        default=0,
        help_text="Total execution time in milliseconds.",
    )
    page_data = models.JSONField(
        default=list,
        blank=True,
        help_text="Granular page-by-page breakdown containing text and confidence.",
    )
    raw_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw provider response, comparison telemetry, and diagnostic markers.",
    )
    is_latest = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if this is the active/latest OCR run for the parent evidence document.",
    )
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_ocr_runs",
        help_text="User who initiated or retried this OCR execution.",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when OCR extraction processing started.",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when OCR extraction processing finished.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "OCR Processing Run"
        verbose_name_plural = "OCR Processing Runs"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["evidence", "run_number"],
                name="uniq_ocr_run_evidence_number",
            ),
        ]
        indexes = [
            models.Index(fields=["evidence", "status"], name="idx_ocr_run_evid_status"),
            models.Index(fields=["evidence", "is_latest"], name="idx_ocr_run_evid_latest"),
            models.Index(fields=["created_at"], name="idx_ocr_run_created"),
        ]

    def __str__(self):
        return f"OCR Run #{self.run_number} for Evidence #{self.evidence_id} ({self.status})"

    @property
    def is_completed(self):
        return self.status == OCRStatus.COMPLETED

    @property
    def is_failed(self):
        return self.status == OCRStatus.FAILED

    @property
    def is_processing(self):
        return self.status == OCRStatus.PROCESSING

    @property
    def badge_class(self):
        mapping = {
            OCRStatus.COMPLETED: "badge-success",
            OCRStatus.PROCESSING: "badge-info",
            OCRStatus.PENDING: "badge-warning",
            OCRStatus.FAILED: "badge-danger",
            OCRStatus.CANCELLED: "badge-secondary",
        }
        return mapping.get(self.status, "badge-secondary")

    @property
    def fields_count(self):
        return self.fields.count()

    @property
    def comparison_summary(self):
        """Returns structured comparison between this OCR run and the parent Activity Record."""
        return self.raw_metadata.get("comparison", {})


class OCRField(models.Model):
    """
    Structured Field Entity extracted from OCR document text.

    Distinguishes between raw extracted text and normalized operational values
    without mutating the underlying ActivityRecord operational data.
    """

    ocr_run = models.ForeignKey(
        OCRRun,
        on_delete=models.CASCADE,
        related_name="fields",
        help_text="Parent OCR execution run that yielded this extracted field.",
    )
    field_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Standardized field key (e.g. invoice_number, quantity, billing_period, total_amount).",
    )
    raw_value = models.CharField(
        max_length=255,
        help_text="Exact un-normalized text sequence extracted from the document.",
    )
    normalized_value = models.CharField(
        max_length=255,
        blank=True,
        help_text="Cleaned, standardized, or machine-usable representation (e.g. 1250.50, 2026-03-31).",
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        help_text="Unit of measure associated with the value (e.g. kWh, Liters, MT, INR).",
    )
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Extraction confidence score percentage (0.00 to 100.00).",
    )
    page_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Page number where this entity was located (1-indexed).",
    )
    bounding_box = models.JSONField(
        default=dict,
        blank=True,
        help_text="Spatial layout coordinates if provided by the OCR engine.",
    )
    extraction_method = models.CharField(
        max_length=50,
        default="PATTERN_MATCH",
        help_text="Heuristic or model used to extract this field (e.g. REGEX, KEY_VALUE, LLM).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "OCR Extracted Field"
        verbose_name_plural = "OCR Extracted Fields"
        ordering = ["field_name", "page_number"]
        indexes = [
            models.Index(fields=["ocr_run", "field_name"], name="idx_ocr_field_run_name"),
        ]

    def __str__(self):
        return f"{self.field_name}: '{self.raw_value}' (Run #{self.ocr_run_id})"


# -----------------------------------------------------------------------------
# PHASE 12: ACTIVITY SUBMISSION & GOVERNANCE WORKFLOW
# -----------------------------------------------------------------------------

class SubmissionStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted for Review"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
    VERIFIED = "VERIFIED", "Verified"
    CORRECTION_REQUESTED = "CORRECTION_REQUESTED", "Correction Requested"
    EXPLAINED = "EXPLAINED", "Explained"
    ESCALATED = "ESCALATED", "Escalated"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Revision Requested"


class Submission(models.Model):
    """
    Authoritative ESG Activity Submission Entity for MEIL ESG CONTROL TOWER.

    Represents the formal handover of validated operational activity data from the
    Site Manager operational layer into the downstream Subsidiary Manager review workflow.
    Preserves:
    - Relational link to parent ActivityRecord and sequential submission counter.
    - Submitter user identity and authoritative submission timestamp.
    - Organizational boundary (Site, Project, Subsidiary, Company) and Reporting Period.
    - Snapshot of authoritative ValidationRun executed prior to submission.
    - Submitter operational commentary and structured telemetry snapshot.
    - Controlled lifecycle state (SUBMITTED -> UNDER_REVIEW -> APPROVED / REJECTED / WITHDRAWN).
    """

    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.PROTECT,
        related_name="submissions",
        help_text="Operational activity record submitted for downstream review.",
    )
    submission_number = models.PositiveIntegerField(
        default=1,
        help_text="Sequential submission iteration counter for this specific activity record.",
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.PROTECT,
        related_name="submissions",
        help_text="Operational site where the submitted activity took place.",
    )
    reporting_period = models.ForeignKey(
        ReportingPeriod,
        on_delete=models.PROTECT,
        related_name="submissions",
        help_text="Governing reporting period temporal boundary.",
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_activities",
        help_text="Site Manager or authorized operator who executed this submission.",
    )
    submitted_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when formal submission occurred.",
    )
    status = models.CharField(
        max_length=30,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.SUBMITTED,
        db_index=True,
        help_text="Controlled lifecycle state of this submission.",
    )
    validation_run = models.ForeignKey(
        ValidationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
        help_text="Authoritative validation execution run evaluated at time of submission.",
    )
    validation_status = models.CharField(
        max_length=30,
        choices=ValidationStatus.choices,
        default=ValidationStatus.VALID,
        db_index=True,
        help_text="Validation status outcome captured at the time of submission.",
    )
    comments = models.TextField(
        blank=True,
        help_text="Submitter commentary, handover remarks, or operational context.",
    )
    snapshot_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Immutable operational telemetry snapshot at time of submission for audit lineage.",
    )
    parent_submission = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resubmissions",
        help_text="Prior submission instance this submission corrects or supersedes.",
    )
    is_current = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if this is the active/latest submission for the activity record.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Activity Submission"
        verbose_name_plural = "Activity Submissions"
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["activity_record", "submission_number"],
                name="uniq_sub_record_number",
            ),
        ]
        indexes = [
            models.Index(fields=["activity_record", "status"], name="idx_sub_rec_status"),
            models.Index(fields=["site", "status"], name="idx_sub_site_status"),
            models.Index(fields=["reporting_period", "status"], name="idx_sub_period_status"),
            models.Index(fields=["submitted_at"], name="idx_sub_submitted_at"),
            models.Index(fields=["is_current"], name="idx_sub_is_current"),
        ]

    def __str__(self):
        return f"Submission #{self.submission_number} for Record #{self.activity_record_id} ({self.status})"

    @property
    def is_submitted(self):
        return self.status == SubmissionStatus.SUBMITTED

    @property
    def is_resubmission(self):
        return self.submission_number > 1 or self.parent_submission_id is not None

    @property
    def latest_correction_request(self):
        return self.correction_requests.order_by("-created_at").first()

    @property
    def is_withdrawn(self):
        return self.status == SubmissionStatus.WITHDRAWN

    @property
    def is_verified(self):
        return self.status in [SubmissionStatus.VERIFIED, SubmissionStatus.APPROVED]

    @property
    def is_correction_requested(self):
        return self.status in [SubmissionStatus.CORRECTION_REQUESTED, SubmissionStatus.REJECTED]

    @property
    def is_explained(self):
        return self.status == SubmissionStatus.EXPLAINED

    @property
    def is_escalated(self):
        return self.status == SubmissionStatus.ESCALATED

    @property
    def is_reviewable(self):
        return self.status in [
            SubmissionStatus.SUBMITTED,
            SubmissionStatus.UNDER_REVIEW,
            SubmissionStatus.EXPLAINED,
        ]

    @property
    def badge_class(self):
        mapping = {
            SubmissionStatus.SUBMITTED: "badge-primary",
            SubmissionStatus.UNDER_REVIEW: "badge-info",
            SubmissionStatus.WITHDRAWN: "badge-secondary",
            SubmissionStatus.VERIFIED: "badge-success",
            SubmissionStatus.CORRECTION_REQUESTED: "badge-warning",
            SubmissionStatus.EXPLAINED: "badge-info",
            SubmissionStatus.ESCALATED: "badge-danger",
            SubmissionStatus.APPROVED: "badge-success",
            SubmissionStatus.REJECTED: "badge-danger",
        }
        return mapping.get(self.status, "badge-secondary")

    @property
    def project(self):
        return self.site.project

    @property
    def subsidiary(self):
        return self.site.project.subsidiary

    @property
    def company(self):
        return self.site.project.subsidiary.company

    @property
    def activity(self):
        return self.activity_record.activity

    @property
    def quantity(self):
        return self.activity_record.quantity

    @property
    def unit(self):
        return self.activity_record.unit

    @property
    def measurement_date(self):
        return self.activity_record.measurement_date

    @property
    def evidence_files_count(self):
        return self.activity_record.evidence_count

    @property
    def latest_review(self):
        return self.reviews.order_by("-created_at").first()

    @property
    def review_count(self):
        return self.reviews.count()


# -----------------------------------------------------------------------------
# PHASE 13: SUBSIDIARY MANAGER REVIEW & GOVERNANCE WORKFLOW
# -----------------------------------------------------------------------------

class ReviewAction(models.TextChoices):
    VERIFY = "VERIFY", "Verify"
    REQUEST_CORRECTION = "REQUEST_CORRECTION", "Request Correction"
    EXPLAIN = "EXPLAIN", "Explain"
    ESCALATE = "ESCALATE", "Escalate"


class SubmissionReview(models.Model):
    """
    Authoritative Governance Review Decision & Audit Trail Entity for MEIL ESG CONTROL TOWER.

    Represents an immutable, historically preserved review decision executed by a Subsidiary Manager
    or authorized ESG governance reviewer on a submitted ActivityRecord / Submission.
    Preserves:
    - Relational binding to parent Submission.
    - Reviewer identity and authoritative timestamp.
    - Review decision action (VERIFY, REQUEST_CORRECTION, EXPLAIN, ESCALATE).
    - Status lifecycle delta (previous_status -> new_status).
    - Reviewer comments, contextual justification, or explanation.
    - Specific correction requirements for Site Manager if correction requested.
    - Target escalation authority if escalated.
    - Metadata snapshot for audit traceability.
    """

    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="reviews",
        help_text="Activity submission subjected to this review decision.",
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submission_reviews",
        help_text="Subsidiary Manager or authorized reviewer who executed this decision.",
    )
    action = models.CharField(
        max_length=30,
        choices=ReviewAction.choices,
        db_index=True,
        help_text="Authoritative review decision action taken.",
    )
    previous_status = models.CharField(
        max_length=30,
        choices=SubmissionStatus.choices,
        help_text="Submission status prior to this review action.",
    )
    new_status = models.CharField(
        max_length=30,
        choices=SubmissionStatus.choices,
        help_text="Submission status resulting from this review action.",
    )
    comments = models.TextField(
        blank=True,
        help_text="Reviewer comments, rationale, or contextual explanation.",
    )
    required_correction = models.TextField(
        blank=True,
        help_text="Specific correction or revision instructions required from site manager.",
    )
    escalated_to_role = models.CharField(
        max_length=50,
        blank=True,
        default=Role.Code.ESG_MANAGER,
        help_text="Target role or governance authority for escalation.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Contextual telemetry and state snapshot at time of review.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when review decision was recorded.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Submission Review Decision"
        verbose_name_plural = "Submission Review Decisions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["submission", "action"], name="idx_rev_sub_action"),
            models.Index(fields=["reviewer", "action"], name="idx_rev_user_action"),
            models.Index(fields=["created_at"], name="idx_rev_created_at"),
        ]

    def __str__(self):
        reviewer_name = self.reviewer.username if self.reviewer else "System"
        return f"{self.action} on Submission #{self.submission_id} by {reviewer_name} ({self.created_at:%Y-%m-%d %H:%M})"

    @property
    def badge_class(self):
        mapping = {
            ReviewAction.VERIFY: "badge-success",
            ReviewAction.REQUEST_CORRECTION: "badge-warning",
            ReviewAction.EXPLAIN: "badge-info",
            ReviewAction.ESCALATE: "badge-danger",
        }
        return mapping.get(self.action, "badge-secondary")


# -----------------------------------------------------------------------------
# PHASE 14: CORRECTIONS, EXPLANATIONS & RESUBMISSION WORKFLOW
# -----------------------------------------------------------------------------

class CorrectionStatus(models.TextChoices):
    OPEN = "OPEN", "Correction Requested"
    IN_PROGRESS = "IN_PROGRESS", "In Correction"
    READY_FOR_RESUBMISSION = "READY_FOR_RESUBMISSION", "Ready for Resubmission"
    RESOLVED = "RESOLVED", "Resolved / Resubmitted"
    CANCELLED = "CANCELLED", "Cancelled"


class CorrectionAffectedArea(models.TextChoices):
    ACTIVITY_DATA = "ACTIVITY_DATA", "Activity Data"
    EVIDENCE = "EVIDENCE", "Evidence"
    BOTH = "BOTH", "Activity Data & Evidence"
    OTHER = "OTHER", "Other"


class CorrectionRequest(models.Model):
    """
    Formal Correction Request Entity for MEIL ESG CONTROL TOWER.

    Represents a specific, auditable request generated when a Subsidiary Manager
    returns a submitted ActivityRecord to the Site Manager for correction.
    Preserves:
    - Binding to original Submission and Governance Review decision.
    - Reviewer identity and authoritative timestamp.
    - Mandatory reason and actionable correction instructions.
    - Affected operational scope (Activity Data, Evidence, Both, Other).
    - Status lifecycle progression (OPEN -> IN_PROGRESS -> READY_FOR_RESUBMISSION -> RESOLVED).
    - Explanatory commentary from Site Manager upon resolving.
    - Binding to the resulting Resubmission and resolving user.
    """

    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="correction_requests",
        help_text="The submission for which correction was requested.",
    )
    review = models.ForeignKey(
        SubmissionReview,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="correction_requests",
        help_text="Review decision record that generated this correction request.",
    )
    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.CASCADE,
        related_name="correction_requests",
        help_text="Parent operational activity record subject to correction.",
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_corrections",
        help_text="Subsidiary Manager who requested this correction.",
    )
    reason = models.TextField(
        help_text="Authoritative reason why correction is required.",
    )
    required_correction = models.TextField(
        blank=True,
        help_text="Specific operational changes and revision instructions.",
    )
    affected_area = models.CharField(
        max_length=30,
        choices=CorrectionAffectedArea.choices,
        default=CorrectionAffectedArea.ACTIVITY_DATA,
        help_text="Operational scope of required correction.",
    )
    status = models.CharField(
        max_length=30,
        choices=CorrectionStatus.choices,
        default=CorrectionStatus.OPEN,
        db_index=True,
        help_text="Lifecycle status of this correction request.",
    )
    site_manager_notes = models.TextField(
        blank=True,
        help_text="Explanatory notes provided by Site Manager upon correcting.",
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_corrections",
        help_text="Site Manager who resolved and resubmitted this correction.",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when correction was resubmitted.",
    )
    resubmission = models.ForeignKey(
        Submission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="originating_correction_requests",
        help_text="New submission instance resulting from this correction.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Correction Request"
        verbose_name_plural = "Correction Requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["activity_record", "status"], name="idx_corr_rec_status"),
            models.Index(fields=["submission", "status"], name="idx_corr_sub_status"),
            models.Index(fields=["status", "created_at"], name="idx_corr_status_date"),
        ]

    def __str__(self):
        return f"Correction #{self.id} for Record #{self.activity_record_id} ({self.status})"

    @property
    def is_open(self):
        return self.status in [CorrectionStatus.OPEN, CorrectionStatus.IN_PROGRESS]

    @property
    def is_resolved(self):
        return self.status == CorrectionStatus.RESOLVED

    @property
    def badge_class(self):
        mapping = {
            CorrectionStatus.OPEN: "badge-warning",
            CorrectionStatus.IN_PROGRESS: "badge-info",
            CorrectionStatus.READY_FOR_RESUBMISSION: "badge-primary",
            CorrectionStatus.RESOLVED: "badge-success",
            CorrectionStatus.CANCELLED: "badge-secondary",
        }
        return mapping.get(self.status, "badge-secondary")


class ActivityRevision(models.Model):
    """
    Authoritative Activity Record Revision & Operational Audit Ledger Entity.

    Preserves the historical operational state of an ActivityRecord across
    correction and resubmission cycles without altering or destroying the original data.
    """

    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.CASCADE,
        related_name="revisions",
        help_text="Parent operational activity record.",
    )
    revision_number = models.PositiveIntegerField(
        default=1,
        help_text="Sequential revision index for this activity record.",
    )
    submission = models.ForeignKey(
        Submission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_revisions",
        help_text="Submission associated with this revision snapshot.",
    )
    correction_request = models.ForeignKey(
        CorrectionRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_revisions",
        help_text="Correction request that prompted this revision.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_revisions",
        help_text="User who authored this revision.",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Brief rationale or lifecycle event (e.g., INITIAL_SUBMISSION, CORRECTION_RESUBMISSION).",
    )
    comments = models.TextField(
        blank=True,
        help_text="Detailed explanatory notes or commentary.",
    )
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        help_text="Authoritative operational consumption quantity at this revision.",
    )
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        help_text="Unit of measure applied at this revision.",
    )
    measurement_date = models.DateField(
        help_text="Measurement date for this revision.",
    )
    notes = models.TextField(blank=True)
    evidence_reference = models.CharField(max_length=255, blank=True)
    validation_status = models.CharField(max_length=30, blank=True)
    changed_fields = models.JSONField(
        default=dict,
        blank=True,
        help_text="Field-by-field delta compared to previous revision.",
    )
    snapshot_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Complete operational and evidence state snapshot.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Activity Record Revision"
        verbose_name_plural = "Activity Record Revisions"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["activity_record", "revision_number"],
                name="uniq_rec_rev_number",
            ),
        ]
        indexes = [
            models.Index(fields=["activity_record", "revision_number"], name="idx_rev_rec_num"),
            models.Index(fields=["created_at"], name="idx_rev_created_at2"),
        ]

    def __str__(self):
        return f"Revision #{self.revision_number} for Record #{self.activity_record_id} ({self.created_at:%Y-%m-%d})"


# -----------------------------------------------------------------------------
# PHASE 15: ANOMALY DETECTION ENGINE
# -----------------------------------------------------------------------------

class AnomalySeverity(models.TextChoices):
    INFO = "INFO", "Information"
    LOW = "LOW", "Low Risk"
    MEDIUM = "MEDIUM", "Medium Risk"
    HIGH = "HIGH", "High Risk"
    CRITICAL = "CRITICAL", "Critical Risk"


class AnomalyStatus(models.TextChoices):
    OPEN = "OPEN", "Open / Pending Review"
    ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
    EXPLAINED = "EXPLAINED", "Explained"
    RESOLVED = "RESOLVED", "Resolved"
    DISMISSED = "DISMISSED", "Dismissed"


class AnomalyCategory(models.TextChoices):
    HISTORICAL_SPIKE = "HISTORICAL_SPIKE", "Historical Spike"
    HISTORICAL_DROP = "HISTORICAL_DROP", "Historical Drop"
    PERIOD_VARIANCE = "PERIOD_VARIANCE", "Period-over-Period Variance"
    THRESHOLD_BREACH = "THRESHOLD_BREACH", "Threshold Breach"
    DUPLICATE_SUSPECT = "DUPLICATE_SUSPECT", "Duplicate-Like Activity"
    INTENSITY_ANOMALY = "INTENSITY_ANOMALY", "Operational Intensity Anomaly"


class AnomalyRule(models.Model):
    """
    Deterministic Anomaly Detection Rule Definition.

    Configures deterministic baseline, variance, and threshold checks evaluated
    by the Anomaly Engine across operational ESG data records.
    Anomaly rules produce review signals and risk indicators, NEVER automatic rejections.
    """

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Stable unique rule identifier (e.g. HIST_SPIKE_100, PERIOD_VAR_50).",
    )
    name = models.CharField(
        max_length=150,
        help_text="Human-readable rule name.",
    )
    description = models.TextField(
        blank=True,
        help_text="Operational description explaining what pattern this rule flags.",
    )
    category = models.CharField(
        max_length=40,
        choices=AnomalyCategory.choices,
        db_index=True,
        help_text="Category of anomaly pattern detected.",
    )
    severity = models.CharField(
        max_length=20,
        choices=AnomalySeverity.choices,
        default=AnomalySeverity.MEDIUM,
        help_text="Default risk severity assigned to anomalies flagged by this rule.",
    )
    threshold_percentage = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Configured percentage variance threshold (e.g., 100.00 for +100% spike).",
    )
    rule_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configured parameters (e.g. min_baseline_count, min_val, max_val, tolerance).",
    )
    applicable_activity = models.ForeignKey(
        ActivityMaster,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anomaly_rules",
        help_text="Specific activity this rule applies to. If empty, rule evaluates across all activities.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this rule is currently evaluated during detection runs.",
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Monotonic rule version for regulatory lineage and audit traceability.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_anomaly_rules",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_anomaly_rules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Anomaly Rule"
        verbose_name_plural = "Anomaly Rules"
        ordering = ["category", "code"]

    def __str__(self):
        return f"{self.code} (v{self.version}) - {self.name} [{self.severity}]"

    @property
    def badge_class(self):
        return {
            AnomalySeverity.CRITICAL: "badge-danger",
            AnomalySeverity.HIGH: "badge-danger",
            AnomalySeverity.MEDIUM: "badge-warning",
            AnomalySeverity.LOW: "badge-info",
            AnomalySeverity.INFO: "badge-secondary",
        }.get(self.severity, "badge-secondary")


class AnomalyDetectionRun(models.Model):
    """
    Execution History Instance of an Anomaly Detection Evaluation Run.

    Tracks batch or single-record anomaly evaluations for governance transparency and performance telemetry.
    """

    class ScopeType(models.TextChoices):
        RECORD = "RECORD", "Single Activity Record"
        SUBMISSION = "SUBMISSION", "Submission"
        SITE = "SITE", "Operational Site Batch"
        PERIOD = "PERIOD", "Reporting Period Batch"
        ENTERPRISE = "ENTERPRISE", "Enterprise Batch"

    run_number = models.PositiveIntegerField(
        default=1,
        help_text="Sequential iteration count of anomaly runs.",
    )
    scope_type = models.CharField(
        max_length=30,
        choices=ScopeType.choices,
        default=ScopeType.RECORD,
        db_index=True,
    )
    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="anomaly_runs",
    )
    submission = models.ForeignKey(
        Submission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anomaly_runs",
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anomaly_runs",
    )
    reporting_period = models.ForeignKey(
        ReportingPeriod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anomaly_runs",
    )
    records_evaluated = models.PositiveIntegerField(default=0)
    anomalies_detected = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=30, default="COMPLETED", db_index=True)
    summary_message = models.TextField(blank=True)
    execution_duration_ms = models.PositiveIntegerField(default=0)
    executed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executed_anomaly_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Anomaly Detection Run"
        verbose_name_plural = "Anomaly Detection Runs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"AnomalyRun #{self.id} ({self.scope_type}): {self.anomalies_detected} flagged / {self.records_evaluated} evaluated"


class AnomalyRecord(models.Model):
    """
    Authoritative ESG Anomaly Result Entity.

    Identifies an unusual, suspicious, or unexpected operational pattern in an ActivityRecord.
    Preserves:
    - Target ActivityRecord and governing Submission (if submitted).
    - Governing rule, code, and version at time of detection.
    - Risk severity and controlled lifecycle status.
    - Observed value, baseline value, difference, and variance percentage.
    - Explainable human-readable justification.
    - Review lifecycle commentary, reviewer identity, and timestamp.
    """

    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.CASCADE,
        related_name="anomalies",
        help_text="Target operational activity record flagged.",
    )
    submission = models.ForeignKey(
        Submission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anomalies",
        help_text="Governing formal submission instance associated with this anomaly.",
    )
    detection_run = models.ForeignKey(
        AnomalyDetectionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anomalies",
        help_text="Detection run that generated this anomaly finding.",
    )
    rule = models.ForeignKey(
        AnomalyRule,
        on_delete=models.PROTECT,
        related_name="detected_anomalies",
        help_text="Governing anomaly rule.",
    )
    rule_code = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Rule code snapshot for regulatory lineage.",
    )
    rule_version = models.PositiveIntegerField(
        default=1,
        help_text="Rule version snapshot.",
    )
    severity = models.CharField(
        max_length=20,
        choices=AnomalySeverity.choices,
        default=AnomalySeverity.MEDIUM,
        db_index=True,
        help_text="Risk severity of this anomaly finding.",
    )
    status = models.CharField(
        max_length=30,
        choices=AnomalyStatus.choices,
        default=AnomalyStatus.OPEN,
        db_index=True,
        help_text="Controlled lifecycle review status.",
    )
    observed_value = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        help_text="Actual measured consumption quantity recorded.",
    )
    baseline_value = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Calculated historical baseline or expected comparator value.",
    )
    deviation_value = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Absolute difference (observed - baseline).",
    )
    deviation_percentage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage variance relative to baseline.",
    )
    explanation = models.TextField(
        help_text="Deterministic explanation why this record was flagged as anomalous.",
    )
    context_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Operational metadata, historical sample size, duplicate record IDs, etc.",
    )
    review_comment = models.TextField(
        blank=True,
        help_text="Reviewer remarks, justification, operational context, or resolution explanation.",
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_anomalies",
        help_text="User who conducted review action (acknowledged, explained, resolved, dismissed).",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when review action was executed.",
    )
    resolution_action = models.CharField(
        max_length=30,
        blank=True,
        help_text="Specific review action taken (e.g. ACKNOWLEDGED, EXPLAINED, RESOLVED, DISMISSED).",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this anomaly is the active unresolved finding for this record and rule.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ESG Anomaly Record"
        verbose_name_plural = "ESG Anomaly Records"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["activity_record", "status"], name="idx_anom_rec_status"),
            models.Index(fields=["submission", "status"], name="idx_anom_sub_status"),
            models.Index(fields=["status", "severity"], name="idx_anom_status_sev"),
            models.Index(fields=["rule_code", "status"], name="idx_anom_rule_status"),
        ]

    def __str__(self):
        return f"Anomaly #{self.id} [{self.severity}] on Record #{self.activity_record_id} ({self.rule_code}): {self.status}"

    @property
    def is_open(self):
        return self.status in [AnomalyStatus.OPEN, AnomalyStatus.ACKNOWLEDGED]

    @property
    def is_resolved_or_dismissed(self):
        return self.status in [AnomalyStatus.RESOLVED, AnomalyStatus.DISMISSED]

    @property
    def badge_class(self):
        return {
            AnomalyStatus.OPEN: "badge-danger",
            AnomalyStatus.ACKNOWLEDGED: "badge-warning",
            AnomalyStatus.EXPLAINED: "badge-info",
            AnomalyStatus.RESOLVED: "badge-success",
            AnomalyStatus.DISMISSED: "badge-secondary",
        }.get(self.status, "badge-secondary")

    @property
    def severity_badge_class(self):
        return {
            AnomalySeverity.CRITICAL: "badge-danger",
            AnomalySeverity.HIGH: "badge-danger",
            AnomalySeverity.MEDIUM: "badge-warning",
            AnomalySeverity.LOW: "badge-info",
            AnomalySeverity.INFO: "badge-secondary",
        }.get(self.severity, "badge-secondary")

    @property
    def site(self):
        return self.activity_record.site

    @property
    def activity(self):
        return self.activity_record.activity

    @property
    def reporting_period(self):
        return self.activity_record.reporting_period


# -----------------------------------------------------------------------------
# PHASE 16: SUPPLIER & PROCUREMENT MANAGEMENT
# -----------------------------------------------------------------------------

class SupplierType(models.TextChoices):
    GOODS = "GOODS", "Goods & Materials Supplier"
    SERVICES = "SERVICES", "Services & Contractor"
    MANUFACTURER = "MANUFACTURER", "Manufacturer / OEM"
    DISTRIBUTOR = "DISTRIBUTOR", "Distributor / Dealer"
    FUEL_SUPPLIER = "FUEL_SUPPLIER", "Fuel & Energy Supplier"
    UTILITY_PROVIDER = "UTILITY_PROVIDER", "Utility Provider (Power / Water / Gas)"
    TRANSPORTER = "TRANSPORTER", "Transporter / Logistics Provider"
    WASTE_OPERATOR = "WASTE_OPERATOR", "Waste Management Operator"
    CONSULTANT = "CONSULTANT", "Technical / Professional Consultant"
    OTHER = "OTHER", "Other Vendor / Supplier"


class SupplierStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    BLOCKED = "BLOCKED", "Blocked"
    ARCHIVED = "ARCHIVED", "Archived"


class Supplier(models.Model):
    """
    Centralized Supplier / Vendor Master for MEIL ESG CONTROL TOWER.
    Maintains authoritative master records of all commercial vendors, contractors,
    and service providers contributing to procurement transactions and Scope 3 footprint.
    """
    supplier_code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique stable internal identifier for the supplier (e.g. SUP-001).",
    )
    name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Primary trade name or common business name of supplier.",
    )
    legal_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Registered legal corporate entity name.",
    )
    supplier_type = models.CharField(
        max_length=50,
        choices=SupplierType.choices,
        default=SupplierType.GOODS,
        db_index=True,
        help_text="Primary classification of goods or services provided.",
    )
    status = models.CharField(
        max_length=20,
        choices=SupplierStatus.choices,
        default=SupplierStatus.ACTIVE,
        db_index=True,
        help_text="Lifecycle state of this supplier master record.",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="suppliers",
        help_text="Parent Enterprise or Company entity. If null, supplier is Enterprise-wide.",
    )
    contact_person = models.CharField(
        max_length=150,
        blank=True,
        help_text="Primary representative or account manager.",
    )
    contact_email = models.EmailField(
        blank=True,
        help_text="Official business correspondence email.",
    )
    contact_phone = models.CharField(
        max_length=32,
        blank=True,
        help_text="Official business contact phone.",
    )
    tax_identifier = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Tax identification number (e.g. GSTIN, PAN, VAT, TIN).",
    )
    address = models.TextField(
        blank=True,
        help_text="Registered office address or facility location.",
    )
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="India", blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    environmental_certifications = models.CharField(
        max_length=255,
        blank=True,
        help_text="Environmental/sustainability accreditations (e.g. ISO 14001, ISO 50001, LEED, GreenPro).",
    )
    has_esg_declaration = models.BooleanField(
        default=False,
        help_text="Whether supplier has signed an ESG / Supplier Code of Conduct declaration.",
    )
    esg_notes = models.TextField(
        blank=True,
        help_text="Sustainability notes, renewable power share, or Scope 3 decarbonization commitments.",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_suppliers",
        help_text="User who registered this supplier master record.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status", "name"], name="idx_supp_status_name"),
            models.Index(fields=["company", "status"], name="idx_supp_co_status"),
        ]

    def __str__(self):
        return f"{self.name} ({self.supplier_code})"

    @property
    def is_active(self):
        return self.status == SupplierStatus.ACTIVE

    @property
    def procurements_count(self):
        return self.procurements.count()

    @property
    def active_procurements_count(self):
        return self.procurements.exclude(status="CANCELLED").count()

    def archive(self, actor=None):
        """Soft-archives supplier to protect historical procurement integrity."""
        self.status = SupplierStatus.ARCHIVED
        self.save(update_fields=["status", "updated_at"])


class ProcurementCategory(models.TextChoices):
    RAW_MATERIAL = "RAW_MATERIAL", "Raw Material"
    CONSTRUCTION_MATERIAL = "CONSTRUCTION_MATERIAL", "Construction Material (Cement, Steel, Aggregate, Sand)"
    FUEL = "FUEL", "Fuel (Diesel, Petrol, Biofuel, Natural Gas)"
    ELECTRICITY = "ELECTRICITY", "Purchased Electricity / Grid Energy"
    EQUIPMENT = "EQUIPMENT", "Capital Equipment & Machinery"
    CONSUMABLE = "CONSUMABLE", "Operating Consumables & Spares"
    SERVICES = "SERVICES", "Contracted Services & Civil Works"
    TRANSPORT_SERVICE = "TRANSPORT_SERVICE", "Transport & Freight Logistics"
    WASTE_SERVICE = "WASTE_SERVICE", "Waste Collection & Disposal Services"
    TRAVEL = "TRAVEL", "Business Travel & Lodging"
    OTHER = "OTHER", "Other Purchased Goods & Services"


class ProcurementStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    VERIFIED = "VERIFIED", "Verified / Approved"
    CORRECTION_REQUESTED = "CORRECTION_REQUESTED", "Correction Requested"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


class ProcurementRecord(models.Model):
    """
    Commercial Procurement & Purchasing Transaction Record.
    Captures commercial purchasing transactions distinct from operational ESG Activity Records.
    """
    procurement_number = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Unique institutional transaction reference (e.g. PROC-2026-POL-0001).",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="procurements",
        help_text="Vendor or commercial provider.",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="procurements",
        help_text="Operating company or enterprise division executing the purchase.",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="procurements",
        help_text="Infrastructure project boundary. Optional for enterprise purchases.",
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="procurements",
        help_text="Operational site boundary receiving the goods/services.",
    )
    reporting_period = models.ForeignKey(
        ReportingPeriod,
        on_delete=models.PROTECT,
        related_name="procurements",
        help_text="Governing reporting period temporal boundary.",
    )
    purchase_date = models.DateField(
        db_index=True,
        help_text="Official transaction or delivery date.",
    )
    category = models.CharField(
        max_length=50,
        choices=ProcurementCategory.choices,
        default=ProcurementCategory.RAW_MATERIAL,
        db_index=True,
        help_text="Procurement classification category.",
    )
    purchase_order_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Purchase Order (PO) number or commercial agreement code.",
    )
    invoice_reference = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Commercial / Tax Invoice Number provided by supplier.",
    )
    invoice_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date printed on the supplier invoice.",
    )
    total_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Gross commercial transaction value.",
    )
    currency = models.CharField(
        max_length=10,
        default="INR",
        choices=[
            ("INR", "INR - Indian Rupee"),
            ("USD", "USD - US Dollar"),
            ("EUR", "EUR - Euro"),
            ("GBP", "GBP - British Pound"),
        ],
        help_text="Monetary currency code.",
    )
    description = models.TextField(
        blank=True,
        help_text="Procurement scope, commercial terms, or transaction remarks.",
    )
    status = models.CharField(
        max_length=30,
        choices=ProcurementStatus.choices,
        default=ProcurementStatus.DRAFT,
        db_index=True,
        help_text="Controlled workflow lifecycle state.",
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="Locks record from Site Manager modification once submitted or verified.",
    )
    validation_status = models.CharField(
        max_length=30,
        choices=ValidationStatus.choices,
        default=ValidationStatus.UNVALIDATED,
        db_index=True,
        help_text="Automated deterministic validation evaluation status.",
    )
    has_anomalies = models.BooleanField(
        default=False,
        help_text="Whether anomaly detection flagged potential duplicates, spikes, or variances.",
    )
    activity_record = models.ForeignKey(
        ActivityRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procurement_sources",
        help_text="Linked ESG operational activity record, if derived.",
    )
    review_comments = models.TextField(
        blank=True,
        help_text="Review comments or rejection reasoning.",
    )
    correction_notes = models.TextField(
        blank=True,
        help_text="Correction explanations upon resubmission.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_procurements",
        help_text="User who initiated this procurement record.",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_procurements",
        help_text="User who last updated this procurement record.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Procurement Record"
        verbose_name_plural = "Procurement Records"
        ordering = ["-purchase_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(total_amount__gte=0),
                name="check_procurement_amt_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="idx_proc_co_status"),
            models.Index(fields=["site", "status"], name="idx_proc_site_status"),
            models.Index(fields=["supplier", "status"], name="idx_proc_supp_status"),
            models.Index(fields=["reporting_period", "status"], name="idx_proc_period_status"),
            models.Index(fields=["invoice_reference"], name="idx_proc_inv_ref"),
        ]

    def __str__(self):
        return f"{self.procurement_number} - {self.supplier.name} ({self.total_amount} {self.currency})"

    @property
    def items_count(self):
        return self.items.count()

    @property
    def items_total_amount(self):
        return sum(item.total_amount for item in self.items.all())

    @property
    def evidence_count(self):
        return self.evidence_files.filter(status=EvidenceStatus.ACTIVE).count()

    @property
    def has_evidence(self):
        return self.evidence_count > 0

    @property
    def is_editable(self):
        return self.status in [ProcurementStatus.DRAFT, ProcurementStatus.CORRECTION_REQUESTED] and not self.is_locked

    @property
    def status_badge_class(self):
        return {
            ProcurementStatus.DRAFT: "badge-secondary",
            ProcurementStatus.SUBMITTED: "badge-primary",
            ProcurementStatus.UNDER_REVIEW: "badge-info",
            ProcurementStatus.VERIFIED: "badge-success",
            ProcurementStatus.CORRECTION_REQUESTED: "badge-warning",
            ProcurementStatus.REJECTED: "badge-danger",
            ProcurementStatus.CANCELLED: "badge-dark",
        }.get(self.status, "badge-secondary")

    @property
    def validation_badge_class(self):
        return {
            ValidationStatus.VALID: "badge-success",
            ValidationStatus.WARNING: "badge-warning",
            ValidationStatus.INVALID: "badge-danger",
            ValidationStatus.UNVALIDATED: "badge-secondary",
        }.get(self.validation_status, "badge-secondary")


class ProcurementItem(models.Model):
    """
    Individual line item in a procurement transaction.
    """
    procurement = models.ForeignKey(
        ProcurementRecord,
        on_delete=models.CASCADE,
        related_name="items",
        help_text="Parent procurement transaction.",
    )
    line_number = models.PositiveIntegerField(
        default=1,
        help_text="Sequential line number within the procurement transaction.",
    )
    item_name = models.CharField(
        max_length=255,
        help_text="Material, goods, or service line description (e.g. TMT Steel Bars 16mm).",
    )
    category = models.CharField(
        max_length=50,
        choices=ProcurementCategory.choices,
        default=ProcurementCategory.RAW_MATERIAL,
        help_text="Category for this specific item.",
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        help_text="Purchased physical quantity (must be > 0).",
    )
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Standardized unit of measure from Activity Master taxonomy.",
    )
    unit_custom = models.CharField(
        max_length=50,
        blank=True,
        help_text="Custom or commercial unit string if not in UnitOfMeasure master.",
    )
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Unit price / commercial rate.",
    )
    total_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Line item commercial value.",
    )
    activity_master = models.ForeignKey(
        ActivityMaster,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="procurement_items",
        help_text="Linked ActivityMaster catalog entity for ESG relevance.",
    )
    scope3_category = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ("CAT_01", "Scope 3.1: Purchased Goods and Services"),
            ("CAT_02", "Scope 3.2: Capital Goods"),
            ("CAT_03", "Scope 3.3: Fuel- and Energy-Related Activities"),
            ("CAT_04", "Scope 3.4: Upstream Transportation and Distribution"),
            ("CAT_05", "Scope 3.5: Waste Generated in Operations"),
            ("CAT_06", "Scope 3.6: Business Travel"),
            ("CAT_07", "Scope 3.7: Employee Commuting"),
            ("CAT_08", "Scope 3.8: Upstream Leased Assets"),
            ("OTHER", "Other / Not Classified"),
        ],
        help_text="Future Scope 3 GHG Protocol integration category.",
    )
    notes = models.TextField(blank=True, help_text="Item technical notes or specifications.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Procurement Line Item"
        verbose_name_plural = "Procurement Line Items"
        ordering = ["procurement", "line_number"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name="check_proc_item_qty_positive",
            ),
            models.CheckConstraint(
                check=models.Q(total_amount__gte=0),
                name="check_proc_item_amt_non_neg",
            ),
            models.UniqueConstraint(
                fields=["procurement", "line_number"],
                name="unique_proc_item_line_no",
            ),
        ]

    def __str__(self):
        unit_str = self.unit.symbol if self.unit else self.unit_custom
        return f"Line {self.line_number}: {self.item_name} ({self.quantity} {unit_str}) - {self.total_amount}"



