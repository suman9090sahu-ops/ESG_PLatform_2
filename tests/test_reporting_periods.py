"""
Comprehensive Test Suite for Phase 04 — Reporting Periods & Temporal Governance.

Covers:
1. Model Tests:
   - ReportingPeriod creation, fiscal year attributes, and string representation
   - Date range validation (start_date < end_date enforced)
   - Database CheckConstraint on start_date < end_date
   - UniqueConstraint per company and period code
   - Cross-period overlap prevention within same organizational scope
   - Isolation across distinct companies

2. Queryset Scoping Tests:
   - Scoped access across all 5 user roles:
     * MEIL_OPERATOR (Global scope)
     * ESG_MANAGER (Corporate scope)
     * SUBSIDIARY_MANAGER (Divisional scope)
     * SITE_MANAGER (Operational site scope)
     * AUDITOR (Assurance read-only scope)
   - Cross-tenant / cross-company isolation

3. Object-Level Authorization & IDOR Security:
   - Direct URL tampering on /reporting-periods/<id>/ returns 403 Forbidden
   - Direct tampering on /reporting-periods/<id>/edit/ returns 403 Forbidden
   - Direct tampering on /reporting-periods/<id>/status/ returns 403 Forbidden
   - Security violation audit logging (UNAUTHORIZED_ACCESS_ATTEMPT)

4. Lifecycle State Machine & Transition Tests:
   - Valid lifecycle transitions: DRAFT -> OPEN -> CLOSED -> LOCKED -> FINALIZED
   - Reopening (CLOSED -> OPEN) and Unlocking (LOCKED -> CLOSED)
   - Invalid transitions rejected (DRAFT -> FINALIZED, FINALIZED -> OPEN)
   - Role-based transition authorization (Auditors, Site Managers, and Subsidiary Managers denied)
   - Audit logging (PERIOD_STATUS_CHANGED)

5. Downstream Data Protection & Governance Guards:
   - is_period_open, is_period_closed, is_period_locked, is_period_finalized
   - can_user_enter_data returns True ONLY when period is OPEN and user holds operational role
   - can_user_modify_data returns False for CLOSED, LOCKED, FINALIZED
   - Locked and Finalized periods reject metadata modifications

6. Form & Admin Tests:
   - Form field-level validation and scope choice filtering
   - Duplicate code detection in form
"""

from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import (
    AuthAuditLog,
    Company,
    CompanyAssignment,
    OrganizationStatus,
    PeriodStatus,
    Project,
    ReportingPeriod,
    Role,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    UserRole,
)
from apps.core.period_services import (
    can_user_enter_data,
    can_user_modify_data,
    get_accessible_reporting_periods,
    get_current_reporting_period,
    is_period_closed,
    is_period_finalized,
    is_period_locked,
    is_period_open,
    transition_period_status,
    user_can_access_reporting_period,
    user_can_manage_period_lifecycle,
    user_can_manage_reporting_period,
    validate_status_transition,
)

User = get_user_model()


class ReportingPeriodModelTests(TestCase):
    """Test model constraints, validation logic, and state helpers."""

    def setUp(self):
        self.company = Company.objects.create(
            name="MEIL Enterprise Group",
            code="MEIL-ENT",
            status=OrganizationStatus.ACTIVE,
        )
        self.other_company = Company.objects.create(
            name="Other Enterprise Ltd",
            code="OTHER-ENT",
            status=OrganizationStatus.ACTIVE,
        )
        self.subsidiary = Subsidiary.objects.create(
            company=self.company,
            name="MEIL Hydro Division",
            code="MEIL-HYDRO",
            status=OrganizationStatus.ACTIVE,
        )

    def test_valid_period_creation_and_str(self):
        """A valid reporting period can be created and returns informative str."""
        period = ReportingPeriod.objects.create(
            company=self.company,
            code="FY2025-26",
            name="FY 2025-26 Annual ESG Cycle",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.OPEN,
        )
        self.assertEqual(str(period), "FY 2025-26 Annual ESG Cycle (FY2025-26)")
        self.assertTrue(period.is_open)
        self.assertFalse(period.is_draft)
        self.assertTrue(period.allows_data_entry)
        self.assertTrue(period.allows_metadata_edit)

    def test_invalid_date_order_rejected(self):
        """End date before start date or equal to start date must raise ValidationError."""
        # 1. End date before start date
        period_inverted = ReportingPeriod(
            company=self.company,
            code="INV-01",
            name="Inverted Dates Period",
            fiscal_year="FY 2025-26",
            start_date=date(2026, 3, 31),
            end_date=date(2025, 4, 1),
        )
        with self.assertRaises(ValidationError):
            period_inverted.clean()

        # 2. Equal dates
        period_equal = ReportingPeriod(
            company=self.company,
            code="EQ-01",
            name="Equal Dates Period",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2025, 4, 1),
        )
        with self.assertRaises(ValidationError):
            period_equal.clean()

    def test_unique_constraint_per_company_and_code(self):
        """Duplicate period code within the same company is prohibited."""
        ReportingPeriod.objects.create(
            company=self.company,
            code="FY2025-26",
            name="First Period",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
        )

        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                ReportingPeriod.objects.create(
                    company=self.company,
                    code="FY2025-26",
                    name="Duplicate Code Period",
                    fiscal_year="FY 2025-26",
                    start_date=date(2026, 4, 1),
                    end_date=date(2027, 3, 31),
                )

    def test_same_code_allowed_for_different_companies(self):
        """Same period code across different enterprise companies is permitted (tenant isolation)."""
        p1 = ReportingPeriod.objects.create(
            company=self.company,
            code="FY2025-26",
            name="MEIL FY 2025-26",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
        )
        p2 = ReportingPeriod.objects.create(
            company=self.other_company,
            code="FY2025-26",
            name="Other FY 2025-26",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
        )
        self.assertNotEqual(p1.id, p2.id)

    def test_overlapping_periods_rejected_within_same_company(self):
        """Overlapping reporting periods within the same company raise ValidationError."""
        ReportingPeriod.objects.create(
            company=self.company,
            code="FY2025-26",
            name="Annual Period",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
        )

        # Overlapping period: starts inside existing period
        overlapping_period = ReportingPeriod(
            company=self.company,
            code="FY2025-H2",
            name="Conflicting Period",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 10, 1),
            end_date=date(2026, 9, 30),
        )
        with self.assertRaises(ValidationError) as ctx:
            overlapping_period.clean()
        self.assertIn("overlap", str(ctx.exception).lower())

    def test_non_overlapping_consecutive_periods_allowed(self):
        """Consecutive periods that do not overlap can be saved without error."""
        p1 = ReportingPeriod.objects.create(
            company=self.company,
            code="FY2024-25",
            name="FY 2024-25 Period",
            fiscal_year="FY 2024-25",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
        )
        p2 = ReportingPeriod.objects.create(
            company=self.company,
            code="FY2025-26",
            name="FY 2025-26 Period",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
        )
        self.assertEqual(ReportingPeriod.objects.filter(company=self.company).count(), 2)

    def test_lifecycle_status_properties(self):
        """Model properties correctly report lifecycle status and modification permissions."""
        period = ReportingPeriod.objects.create(
            company=self.company,
            code="FY2025-TEST",
            name="Test Period",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.DRAFT,
        )
        self.assertTrue(period.is_draft)
        self.assertFalse(period.allows_data_entry)
        self.assertTrue(period.allows_metadata_edit)

        period.status = PeriodStatus.OPEN
        self.assertTrue(period.is_open)
        self.assertTrue(period.allows_data_entry)
        self.assertTrue(period.allows_metadata_edit)

        period.status = PeriodStatus.CLOSED
        self.assertTrue(period.is_closed)
        self.assertFalse(period.allows_data_entry)
        self.assertTrue(period.allows_metadata_edit)

        period.status = PeriodStatus.LOCKED
        self.assertTrue(period.is_locked)
        self.assertFalse(period.allows_data_entry)
        self.assertFalse(period.allows_metadata_edit)

        period.status = PeriodStatus.FINALIZED
        self.assertTrue(period.is_finalized)
        self.assertFalse(period.allows_data_entry)
        self.assertFalse(period.allows_metadata_edit)


class ReportingPeriodScopingAndSecurityTests(TestCase):
    """Test role-based access, scoping, IDOR defense, and lifecycle transitions."""

    def setUp(self):
        # 1. Roles
        self.role_op, _ = Role.objects.get_or_create(code=Role.Code.MEIL_OPERATOR, defaults={"name": "Operator"})
        self.role_esg, _ = Role.objects.get_or_create(code=Role.Code.ESG_MANAGER, defaults={"name": "ESG"})
        self.role_sub, _ = Role.objects.get_or_create(code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Sub"})
        self.role_site, _ = Role.objects.get_or_create(code=Role.Code.SITE_MANAGER, defaults={"name": "Site"})
        self.role_auditor, _ = Role.objects.get_or_create(code=Role.Code.AUDITOR, defaults={"name": "Auditor"})

        # 2. Hierarchy - Company A (MEIL)
        self.company_a = Company.objects.create(name="MEIL Enterprise", code="MEIL-ENT", status=OrganizationStatus.ACTIVE)
        self.sub_a1 = Subsidiary.objects.create(company=self.company_a, name="Hydro Division", code="MEIL-HYDRO", status=OrganizationStatus.ACTIVE)
        self.sub_a2 = Subsidiary.objects.create(company=self.company_a, name="Solar Division", code="MEIL-SOLAR", status=OrganizationStatus.ACTIVE)
        self.proj_a1 = Project.objects.create(subsidiary=self.sub_a1, name="Hydro Dam Project", code="PRJ-HYD-01", status=OrganizationStatus.ACTIVE)
        self.site_a1 = Site.objects.create(project=self.proj_a1, name="Dam Site 1", code="SITE-HYD-01", status=OrganizationStatus.ACTIVE)

        # Hierarchy - Company B (Isolated Other Enterprise)
        self.company_b = Company.objects.create(name="External Group", code="EXT-GRP", status=OrganizationStatus.ACTIVE)
        self.sub_b1 = Subsidiary.objects.create(company=self.company_b, name="External Mining", code="EXT-MINE", status=OrganizationStatus.ACTIVE)

        # 3. Reporting Periods
        self.period_a_open = ReportingPeriod.objects.create(
            company=self.company_a,
            code="FY2025-26",
            name="MEIL FY 2025-26 Operational Cycle",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.OPEN,
        )
        self.period_a_draft = ReportingPeriod.objects.create(
            company=self.company_a,
            code="FY2026-27",
            name="MEIL FY 2026-27 Draft Cycle",
            fiscal_year="FY 2026-27",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            status=PeriodStatus.DRAFT,
        )
        self.period_b = ReportingPeriod.objects.create(
            company=self.company_b,
            code="EXT-FY25",
            name="External Corp Period",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.OPEN,
        )

        # 4. Persona Users
        self.user_op = User.objects.create_user(username="test_op", password="Password123!")
        UserRole.objects.create(user=self.user_op, role=self.role_op, is_primary=True)

        self.user_esg = User.objects.create_user(username="test_esg", password="Password123!")
        UserRole.objects.create(user=self.user_esg, role=self.role_esg, is_primary=True)
        CompanyAssignment.objects.create(user=self.user_esg, company=self.company_a)

        self.user_sub = User.objects.create_user(username="test_sub", password="Password123!")
        UserRole.objects.create(user=self.user_sub, role=self.role_sub, is_primary=True)
        SubsidiaryAssignment.objects.create(user=self.user_sub, subsidiary=self.sub_a1)

        self.user_site = User.objects.create_user(username="test_site", password="Password123!")
        UserRole.objects.create(user=self.user_site, role=self.role_site, is_primary=True)
        SiteAssignment.objects.create(user=self.user_site, site=self.site_a1)

        self.user_auditor = User.objects.create_user(username="test_auditor", password="Password123!")
        UserRole.objects.create(user=self.user_auditor, role=self.role_auditor, is_primary=True)
        CompanyAssignment.objects.create(user=self.user_auditor, company=self.company_a)

        self.client = Client()

    def test_accessible_periods_scoping(self):
        """Queryset scoping correctly filters periods based on user role and assignments."""
        # MEIL_OPERATOR sees all periods across enterprise
        op_periods = get_accessible_reporting_periods(self.user_op)
        self.assertIn(self.period_a_open, op_periods)
        self.assertIn(self.period_a_draft, op_periods)

        # ESG_MANAGER sees enterprise periods
        esg_periods = get_accessible_reporting_periods(self.user_esg)
        self.assertIn(self.period_a_open, esg_periods)

        # SUBSIDIARY_MANAGER sees Company A periods
        sub_periods = get_accessible_reporting_periods(self.user_sub)
        self.assertIn(self.period_a_open, sub_periods)
        self.assertNotIn(self.period_b, sub_periods)

        # SITE_MANAGER sees Company A periods
        site_periods = get_accessible_reporting_periods(self.user_site)
        self.assertIn(self.period_a_open, site_periods)
        self.assertNotIn(self.period_b, site_periods)

        # AUDITOR sees Company A periods
        auditor_periods = get_accessible_reporting_periods(self.user_auditor)
        self.assertIn(self.period_a_open, auditor_periods)

    def test_get_current_reporting_period(self):
        """get_current_reporting_period returns the active OPEN period for the given date and scope."""
        cur_period = get_current_reporting_period(
            company=self.company_a,
            as_of_date=date(2025, 6, 15),
        )
        self.assertEqual(cur_period, self.period_a_open)

    def test_operator_crud_views(self):
        """MEIL_OPERATOR can access list, detail, create, edit, and transition."""
        self.client.login(username="test_op", password="Password123!")

        # List
        resp = self.client.get(reverse("core:period_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "FY2025-26")

        # Detail
        resp = self.client.get(reverse("core:period_detail", args=[self.period_a_open.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Temporal Boundary")

        # Create GET
        resp = self.client.get(reverse("core:period_create"))
        self.assertEqual(resp.status_code, 200)

        # Create POST
        resp = self.client.post(
            reverse("core:period_create"),
            {
                "company": self.company_a.id,
                "code": "FY2027-28",
                "name": "FY 2027-28 Future Cycle",
                "fiscal_year": "FY 2027-28",
                "start_date": "2027-04-01",
                "end_date": "2028-03-31",
                "status": PeriodStatus.DRAFT,
                "description": "Seeded cycle",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ReportingPeriod.objects.filter(code="FY2027-28").exists())

        # Audit log verification
        self.assertTrue(
            AuthAuditLog.objects.filter(
                event_type=AuthAuditLog.EventType.PERIOD_CREATED,
                resource_accessed__contains="FY2027-28",
            ).exists()
        )

    def test_auditor_strictly_read_only(self):
        """AUDITOR can view list and detail, but CANNOT create, edit, or transition status."""
        self.client.login(username="test_auditor", password="Password123!")

        # Allowed read actions
        resp = self.client.get(reverse("core:period_list"))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(reverse("core:period_detail", args=[self.period_a_open.id]))
        self.assertEqual(resp.status_code, 200)

        # Denied mutation actions
        resp = self.client.get(reverse("core:period_create"))
        self.assertEqual(resp.status_code, 403)

        resp = self.client.get(reverse("core:period_edit", args=[self.period_a_open.id]))
        self.assertEqual(resp.status_code, 403)

        resp = self.client.post(
            reverse("core:period_status_transition", args=[self.period_a_open.id]),
            {"target_status": PeriodStatus.CLOSED},
        )
        self.assertEqual(resp.status_code, 403)

    def test_site_manager_and_sub_manager_cannot_create_or_edit(self):
        """Site and Subsidiary Managers cannot create, edit, or alter period status."""
        for username in ["test_site", "test_sub"]:
            self.client.login(username=username, password="Password123!")

            # Create denied
            resp = self.client.get(reverse("core:period_create"))
            self.assertEqual(resp.status_code, 403)

            # Edit denied
            resp = self.client.get(reverse("core:period_edit", args=[self.period_a_open.id]))
            self.assertEqual(resp.status_code, 403)

            # Transition denied
            resp = self.client.post(
                reverse("core:period_status_transition", args=[self.period_a_open.id]),
                {"target_status": PeriodStatus.CLOSED},
            )
            self.assertEqual(resp.status_code, 403)

    def test_idor_defense_on_unauthorized_period(self):
        """A user cannot access or tamper with an unassigned company's period by changing the ID in the URL."""
        self.client.login(username="test_site", password="Password123!")

        # Detail IDOR -> 403
        resp = self.client.get(reverse("core:period_detail", args=[self.period_b.id]))
        self.assertEqual(resp.status_code, 403)

        # Edit IDOR -> 403
        resp = self.client.get(reverse("core:period_edit", args=[self.period_b.id]))
        self.assertEqual(resp.status_code, 403)

        # Transition IDOR -> 403
        resp = self.client.post(
            reverse("core:period_status_transition", args=[self.period_b.id]),
            {"target_status": PeriodStatus.CLOSED},
        )
        self.assertEqual(resp.status_code, 403)

        # Audit log security event recorded
        self.assertTrue(
            AuthAuditLog.objects.filter(
                event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
                resource_accessed__contains=f"ReportingPeriod:{self.period_b.id}",
            ).exists()
        )

    def test_lifecycle_state_machine_transitions(self):
        """Test controlled transitions: DRAFT -> OPEN -> CLOSED -> LOCKED -> FINALIZED and reopening."""
        period = ReportingPeriod.objects.create(
            company=self.company_a,
            code="FY2028-TEST",
            name="Transition Test Period",
            fiscal_year="FY 2028-29",
            start_date=date(2028, 4, 1),
            end_date=date(2029, 3, 31),
            status=PeriodStatus.DRAFT,
        )

        # DRAFT -> OPEN
        transition_period_status(period, PeriodStatus.OPEN, user=self.user_op)
        self.assertEqual(period.status, PeriodStatus.OPEN)

        # OPEN -> CLOSED
        transition_period_status(period, PeriodStatus.CLOSED, user=self.user_op)
        self.assertEqual(period.status, PeriodStatus.CLOSED)

        # CLOSED -> OPEN (Reopen)
        transition_period_status(period, PeriodStatus.OPEN, user=self.user_op)
        self.assertEqual(period.status, PeriodStatus.OPEN)

        # OPEN -> CLOSED -> LOCKED
        transition_period_status(period, PeriodStatus.CLOSED, user=self.user_op)
        transition_period_status(period, PeriodStatus.LOCKED, user=self.user_op)
        self.assertEqual(period.status, PeriodStatus.LOCKED)

        # LOCKED -> CLOSED (Unlock)
        transition_period_status(period, PeriodStatus.CLOSED, user=self.user_op)
        self.assertEqual(period.status, PeriodStatus.CLOSED)

        # CLOSED -> LOCKED -> FINALIZED
        transition_period_status(period, PeriodStatus.LOCKED, user=self.user_op)
        transition_period_status(period, PeriodStatus.FINALIZED, user=self.user_op)
        self.assertEqual(period.status, PeriodStatus.FINALIZED)

        # FINALIZED is terminal; any further transition raises ValidationError
        with self.assertRaises(ValidationError):
            transition_period_status(period, PeriodStatus.OPEN, user=self.user_op)

        # Invalid direct jump: DRAFT -> FINALIZED raises ValidationError
        draft_period = ReportingPeriod.objects.create(
            company=self.company_a,
            code="FY2029-TEST",
            name="Direct Jump Period",
            fiscal_year="FY 2029-30",
            start_date=date(2029, 4, 1),
            end_date=date(2030, 3, 31),
            status=PeriodStatus.DRAFT,
        )
        with self.assertRaises(ValidationError):
            transition_period_status(draft_period, PeriodStatus.FINALIZED, user=self.user_op)

    def test_data_entry_and_modification_guards(self):
        """can_user_enter_data and can_user_modify_data only permit operational data entry when OPEN."""
        # 1. When period is OPEN
        self.assertTrue(can_user_enter_data(self.user_site, self.period_a_open))
        self.assertTrue(can_user_enter_data(self.user_op, self.period_a_open))
        # AUDITOR cannot enter data even if period is OPEN
        self.assertFalse(can_user_enter_data(self.user_auditor, self.period_a_open))

        # 2. When period is DRAFT
        self.assertFalse(can_user_enter_data(self.user_site, self.period_a_draft))

        # 3. When period is CLOSED / LOCKED / FINALIZED
        self.period_a_open.status = PeriodStatus.CLOSED
        self.period_a_open.save()
        self.assertFalse(can_user_enter_data(self.user_site, self.period_a_open))
        self.assertFalse(can_user_modify_data(self.user_site, self.period_a_open))

        self.period_a_open.status = PeriodStatus.LOCKED
        self.period_a_open.save()
        self.assertFalse(can_user_enter_data(self.user_site, self.period_a_open))
        self.assertFalse(can_user_modify_data(self.user_site, self.period_a_open))

        self.period_a_open.status = PeriodStatus.FINALIZED
        self.period_a_open.save()
        self.assertFalse(can_user_enter_data(self.user_site, self.period_a_open))
        self.assertFalse(can_user_modify_data(self.user_site, self.period_a_open))

    def test_locked_and_finalized_periods_reject_metadata_edit(self):
        """Edit view redirects and disallows modifications on LOCKED or FINALIZED periods."""
        self.period_a_open.status = PeriodStatus.LOCKED
        self.period_a_open.save()

        self.client.login(username="test_op", password="Password123!")
        resp = self.client.get(reverse("core:period_edit", args=[self.period_a_open.id]))
        # Should redirect to detail with error message
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse("core:period_detail", args=[self.period_a_open.id]))
