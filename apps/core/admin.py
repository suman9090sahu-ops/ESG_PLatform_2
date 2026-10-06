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
    list_display = ("code", "name", "subsidiary", "location", "status", "is_active")
    list_filter = ("subsidiary__company", "subsidiary", "status", "is_active")
    search_fields = ("code", "name", "location", "description")
    inlines = [SiteInline]


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "project", "facility_type", "location", "status", "is_active")
    list_filter = ("project__subsidiary__company", "project__subsidiary", "status", "is_active", "facility_type")
    search_fields = ("code", "name", "location", "facility_type", "contact_person", "contact_email")


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

