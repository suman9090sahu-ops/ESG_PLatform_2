"""
Django Admin Configuration for MEIL ESG CONTROL TOWER.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.core.models import (
    AuthAuditLog,
    Company,
    CompanyAssignment,
    Project,
    ProjectAssignment,
    Role,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    User,
    UserRole,
    ReportingPeriod,
    ActivityCategory,
    UnitOfMeasure,
    ActivityMaster,
    ActivityRecord,
    Evidence,
    ValidationRule,
    ValidationRun,
    ValidationResult,
)


class UserRoleInline(admin.TabularInline):
    model = UserRole
    fk_name = "user"
    extra = 1
    fields = ("role", "is_primary", "assigned_at", "assigned_by")
    readonly_fields = ("assigned_at",)


class SiteAssignmentInline(admin.TabularInline):
    model = SiteAssignment
    extra = 1
    readonly_fields = ("assigned_at",)


class SubsidiaryAssignmentInline(admin.TabularInline):
    model = SubsidiaryAssignment
    extra = 1
    readonly_fields = ("assigned_at",)


class ProjectAssignmentInline(admin.TabularInline):
    model = ProjectAssignment
    extra = 1
    readonly_fields = ("assigned_at",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for unified User identity model."""

    list_display = (
        "username",
        "email",
        "employee_id",
        "first_name",
        "last_name",
        "get_primary_role_display",
        "is_active",
        "is_staff",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "roles")
    search_fields = ("username", "first_name", "last_name", "email", "employee_id")
    inlines = [UserRoleInline, SiteAssignmentInline, SubsidiaryAssignmentInline]

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Enterprise Identity",
            {
                "fields": (
                    "employee_id",
                    "phone_number",
                    "department",
                    "designation",
                )
            },
        ),
    )

    def get_primary_role_display(self, obj):
        return obj.get_primary_role() or "—"

    get_primary_role_display.short_description = "Primary Role"


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_primary", "assigned_at", "assigned_by")
    list_filter = ("role", "is_primary")
    search_fields = ("user__username", "role__name")


class SubsidiaryInline(admin.TabularInline):
    model = Subsidiary
    extra = 0
    fields = ("code", "name", "industry", "status", "is_active")
    show_change_link = True


class ProjectInline(admin.TabularInline):
    model = Project
    extra = 0
    fields = ("code", "name", "location", "status", "is_active")
    show_change_link = True


class SiteInline(admin.TabularInline):
    model = Site
    extra = 0
    fields = ("code", "name", "facility_type", "location", "status", "is_active")
    show_change_link = True


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country", "status", "is_active", "created_at")
    list_filter = ("status", "is_active", "country")
    search_fields = ("code", "name", "legal_name")
    inlines = [SubsidiaryInline]


@admin.register(Subsidiary)
class SubsidiaryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company", "industry", "country", "status", "is_active")
    list_filter = ("company", "status", "is_active", "industry")
    search_fields = ("code", "name", "legal_name", "short_name", "industry")
    inlines = [ProjectInline]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "subsidiary", "location", "start_date", "end_date", "status", "is_active")
    list_filter = ("subsidiary__company", "subsidiary", "status", "is_active")
    search_fields = ("code", "name", "location", "description")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    inlines = [SiteInline]
    fieldsets = (
        (
            "Project Identification",
            {
                "fields": ("code", "name", "subsidiary", "status"),
            },
        ),
        (
            "Operational Scope & Location",
            {
                "fields": ("location", "description"),
            },
        ),
        (
            "Timeline Boundaries",
            {
                "fields": ("start_date", "end_date"),
            },
        ),
        (
            "Audit & Governance Lineage",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at"),
            },
        ),
    )


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "project",
        "facility_type",
        "location",
        "operational_start_date",
        "operational_end_date",
        "status",
        "is_active",
    )
    list_filter = (
        "project__subsidiary__company",
        "project__subsidiary",
        "status",
        "is_active",
        "facility_type",
    )
    search_fields = ("code", "name", "location", "facility_type", "contact_person", "contact_email")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    fieldsets = (
        (
            "Facility Boundary Identification",
            {
                "fields": ("code", "name", "project", "facility_type", "status"),
            },
        ),
        (
            "Geographic Location & Coordinates",
            {
                "fields": ("location", "latitude", "longitude"),
            },
        ),
        (
            "Site Leadership & Correspondence",
            {
                "fields": ("contact_person", "contact_email"),
            },
        ),
        (
            "Operational Lifecycle Dates",
            {
                "fields": ("operational_start_date", "operational_end_date"),
            },
        ),
        (
            "ESG Boundary Description",
            {
                "fields": ("description",),
            },
        ),
        (
            "Audit & Lineage",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at"),
            },
        ),
    )


@admin.register(SiteAssignment)
class SiteAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "site", "assigned_at")
    search_fields = ("user__username", "site__name", "site__code")


@admin.register(SubsidiaryAssignment)
class SubsidiaryAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "subsidiary", "assigned_at")
    search_fields = ("user__username", "subsidiary__name", "subsidiary__code")


@admin.register(ProjectAssignment)
class ProjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "project", "assigned_at")
    search_fields = ("user__username", "project__name")


@admin.register(CompanyAssignment)
class CompanyAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "assigned_at")
    search_fields = ("user__username", "company__name")


@admin.register(AuthAuditLog)
class AuthAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "event_type",
        "user",
        "username_attempted",
        "ip_address",
        "resource_accessed",
        "success",
    )
    list_filter = ("event_type", "success", "created_at")
    search_fields = ("username_attempted", "user__username", "resource_accessed", "details", "ip_address")
    readonly_fields = (
        "created_at",
        "user",
        "username_attempted",
        "event_type",
        "ip_address",
        "user_agent",
        "resource_accessed",
        "details",
        "success",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReportingPeriod)
class ReportingPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "fiscal_year",
        "company",
        "subsidiary",
        "start_date",
        "end_date",
        "status",
        "created_at",
    )
    list_filter = ("status", "company", "fiscal_year")
    search_fields = ("code", "name", "fiscal_year", "company__name", "description")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    fieldsets = (
        (
            "Period Identification",
            {
                "fields": ("code", "name", "fiscal_year", "status"),
            },
        ),
        (
            "Temporal Boundary",
            {
                "fields": ("start_date", "end_date"),
            },
        ),
        (
            "Organizational Scope",
            {
                "fields": ("company", "subsidiary"),
            },
        ),
        (
            "Operational Notes",
            {
                "fields": ("description",),
            },
        ),
        (
            "Audit Metadata",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at"),
            },
        ),
    )


@admin.register(ActivityCategory)
class ActivityCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "display_order", "status", "is_active", "created_at")
    list_filter = ("status", "is_active")
    search_fields = ("code", "name", "description")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "dimension", "status", "is_active", "created_at")
    list_filter = ("status", "dimension", "is_active")
    search_fields = ("code", "name", "symbol", "description")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")


@admin.register(ActivityMaster)
class ActivityMasterAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "activity_type",
        "scope_classification",
        "base_unit",
        "collection_frequency",
        "status",
        "is_active",
        "created_at",
    )
    list_filter = ("status", "scope_classification", "category", "collection_frequency")
    search_fields = ("code", "name", "activity_type", "description", "evidence_requirement_hint")
    filter_horizontal = ("allowed_units",)
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    fieldsets = (
        (
            "Activity Definition",
            {
                "fields": ("code", "name", "category", "activity_type", "status"),
            },
        ),
        (
            "Measurement & Unit Validation",
            {
                "fields": ("base_unit", "allowed_units"),
            },
        ),
        (
            "ESG & GHG Regulatory Classification",
            {
                "fields": ("scope_classification", "collection_frequency", "evidence_requirement_hint"),
            },
        ),
        (
            "Operational Guidance & Applicability",
            {
                "fields": ("description", "applicability_notes"),
            },
        ),
        (
            "Advanced Integration Hooks (JSON Metadata)",
            {
                "fields": ("validation_rules", "calculation_metadata"),
                "classes": ("collapse",),
            },
        ),
        (
            "Audit Metadata",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at"),
            },
        ),
    )


@admin.register(ActivityRecord)
class ActivityRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "activity",
        "site",
        "reporting_period",
        "measurement_date",
        "quantity",
        "unit",
        "status",
        "validation_status",
        "created_by",
        "created_at",
    )
    list_filter = (
        "status",
        "validation_status",
        "reporting_period",
        "activity__category",
        "site__project__subsidiary__company",
    )
    search_fields = (
        "activity__name",
        "activity__code",
        "site__name",
        "site__code",
        "notes",
        "evidence_reference",
    )
    readonly_fields = ("created_at", "updated_at", "last_validated_at")
    date_hierarchy = "measurement_date"
    raw_id_fields = ("site", "reporting_period", "activity", "unit", "created_by", "updated_by")
    fieldsets = (
        (
            "Operational Binding",
            {
                "fields": ("site", "reporting_period", "activity", "status", "validation_status", "last_validated_at"),
            },
        ),
        (
            "Telemetry & Measurement",
            {
                "fields": ("measurement_date", "quantity", "unit"),
            },
        ),
        (
            "Evidence & Notes",
            {
                "fields": ("evidence_reference", "notes"),
            },
        ),
        (
            "Audit Lineage",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at"),
            },
        ),
    )


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0
    fields = ("original_filename", "evidence_type", "file_size", "status", "created_at")
    readonly_fields = ("original_filename", "evidence_type", "file_size", "status", "created_at")
    can_delete = False
    show_change_link = True


class ValidationRunInline(admin.TabularInline):
    model = ValidationRun
    extra = 0
    fields = ("run_number", "status", "error_count", "warning_count", "executed_by", "executed_at")
    readonly_fields = ("run_number", "status", "error_count", "warning_count", "executed_by", "executed_at")
    can_delete = False
    show_change_link = True


ActivityRecordAdmin.inlines = [EvidenceInline, ValidationRunInline]


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    """Admin configuration for Supporting Evidence documents."""

    list_display = (
        "id",
        "original_filename",
        "evidence_type",
        "activity_record",
        "file_size",
        "status",
        "uploaded_by",
        "created_at",
    )
    list_filter = (
        "status",
        "evidence_type",
        "created_at",
    )
    search_fields = (
        "original_filename",
        "description",
        "file_hash",
        "activity_record__activity__name",
        "activity_record__site__name",
    )
    readonly_fields = (
        "file_size",
        "file_type",
        "file_hash",
        "created_at",
        "updated_at",
        "retired_at",
        "retired_by",
    )
    date_hierarchy = "created_at"
    raw_id_fields = ("activity_record", "uploaded_by", "retired_by")
    fieldsets = (
        (
            "Document Identification",
            {
                "fields": ("activity_record", "evidence_type", "original_filename", "file", "status"),
            },
        ),
        (
            "Technical Metadata & Hash",
            {
                "fields": ("file_type", "file_size", "file_hash"),
            },
        ),
        (
            "Operational Notes & Retirement",
            {
                "fields": ("description", "retirement_reason", "retired_at", "retired_by"),
            },
        ),
        (
            "Pipeline Metadata Hooks",
            {
                "classes": ("collapse",),
                "fields": ("ocr_metadata", "validation_metadata"),
            },
        ),
        (
            "Audit Lineage",
            {
                "fields": ("uploaded_by", "created_at", "updated_at"),
            },
        ),
    )


class ValidationResultInline(admin.TabularInline):
    model = ValidationResult
    extra = 0
    fields = ("rule", "severity", "field_name", "is_blocking", "message")
    readonly_fields = ("rule", "severity", "field_name", "is_blocking", "message")
    can_delete = False
    show_change_link = True


@admin.register(ValidationRule)
class ValidationRuleAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "severity",
        "is_active",
        "is_blocking",
        "version",
        "applicable_activity",
        "updated_at",
    )
    list_filter = (
        "category",
        "severity",
        "is_active",
        "is_blocking",
    )
    search_fields = (
        "code",
        "name",
        "description",
    )
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Rule Specification",
            {
                "fields": ("code", "name", "category", "severity", "is_active", "is_blocking", "version"),
            },
        ),
        (
            "Domain Scope & Parameters",
            {
                "fields": ("applicable_activity", "rule_parameters", "description", "effective_from"),
            },
        ),
        (
            "Audit Lineage",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at"),
            },
        ),
    )


@admin.register(ValidationRun)
class ValidationRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "activity_record",
        "run_number",
        "status",
        "total_rules_evaluated",
        "error_count",
        "warning_count",
        "info_count",
        "executed_by",
        "executed_at",
    )
    list_filter = (
        "status",
        "executed_at",
    )
    search_fields = (
        "activity_record__activity__name",
        "activity_record__site__name",
        "summary_message",
    )
    readonly_fields = (
        "activity_record",
        "run_number",
        "status",
        "total_rules_evaluated",
        "error_count",
        "warning_count",
        "info_count",
        "summary_message",
        "executed_by",
        "executed_at",
        "execution_duration_ms",
        "rule_version_snapshot",
    )
    inlines = [ValidationResultInline]
    date_hierarchy = "executed_at"


@admin.register(ValidationResult)
class ValidationResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "validation_run",
        "activity_record",
        "rule",
        "severity",
        "field_name",
        "is_blocking",
        "created_at",
    )
    list_filter = (
        "severity",
        "is_blocking",
        "rule__category",
    )
    search_fields = (
        "rule__code",
        "rule__name",
        "message",
        "field_name",
    )
    readonly_fields = (
        "validation_run",
        "activity_record",
        "rule",
        "severity",
        "is_blocking",
        "field_name",
        "message",
        "context_data",
        "created_at",
    )



