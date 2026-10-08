"""
Phase 24: ESG Calculation, Emission Factors & Traceable Metric Engine Automated Test Suite.

Comprehensive tests verifying:
1. Centralized Unit Normalization (scale conversions, dimension protection, precision)
2. Emission Factor Selection & Versioning (activity mapping, scope, status filters)
3. Deterministic Scope 1 & Scope 2 Emissions Calculation Engine
4. Missing Factor Safety (REQUIRES_CONFIGURATION, zero fabricated numbers)
5. Multi-Site Reconciled Consolidation & Double-Counting Protection
6. Calculation Lineage & Auditor Traceability ("Trace This Number" integration)
7. Strict RBAC Enforcement (Auditor read-only, Site Manager mutation blocked, ESG Manager governance)
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.conversion_services import (
    UnitConversionService,
    UnitDimensionMismatchError,
    UnsupportedUnitError,
    convert_quantity,
)
from apps.core.calculation_services import (
    calculate_activity_record,
    recalculate_record,
    select_emission_factor,
)
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    CalculationResult,
    CalculationStatus,
    Company,
    CompanyAssignment,
    EmissionFactor,
    EmissionFactorStatus,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    PeriodStatus,
    Project,
    RecordStatus,
    ReportingPeriod,
    Role,
    ScopeClassification,
    Site,
    SiteAssignment,
    Submission,
    SubmissionReview,
    SubmissionStatus,
    Subsidiary,
    SubsidiaryAssignment,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
    ValidationStatus,
)
from apps.core.reporting_services import get_consolidated_report, get_trace_lineage_context

User = get_user_model()


class Phase24CalculationEngineTestCase(TestCase):
    def setUp(self):
        # 1. Base Organization Hierarchy
        self.company = Company.objects.create(
            name="MEIL Power & Infra Enterprise",
            code="MEIL-PIE",
        )
        self.subsidiary = Subsidiary.objects.create(
            company=self.company,
            name="MEIL Green Division",
            code="MEIL-GRN",
        )
        self.project = Project.objects.create(
            subsidiary=self.subsidiary,
            name="Anantapur Solar & Thermal Hub",
            code="PRJ-ATH-01",
        )
        self.site_a = Site.objects.create(
            project=self.project,
            name="Substation Alpha",
            code="ATH-STA",
        )
        self.site_b = Site.objects.create(
            project=self.project,
            name="Staging Yard Bravo",
            code="ATH-STB",
        )
        self.site_c = Site.objects.create(
            project=self.project,
            name="Fabrication Yard Charlie",
            code="ATH-STC",
        )

        # 2. Reporting Periods
        self.period_fy25 = ReportingPeriod.objects.create(
            company=self.company,
            name="Financial Year 2025-26",
            code="FY2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.OPEN,
        )
        self.period_fy24 = ReportingPeriod.objects.create(
            company=self.company,
            name="Financial Year 2024-25",
            code="FY2024-25",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            status=PeriodStatus.CLOSED,
        )

        # 3. Units of Measure
        self.u_litre, _ = UnitOfMeasure.objects.get_or_create(
            code="LITRE",
            defaults={"name": "Litre", "symbol": "L", "dimension": UnitDimension.VOLUME},
        )
        self.u_kl, _ = UnitOfMeasure.objects.get_or_create(
            code="KL",
            defaults={"name": "Kilolitre", "symbol": "kL", "dimension": UnitDimension.VOLUME},
        )
        self.u_kwh, _ = UnitOfMeasure.objects.get_or_create(
            code="KWH",
            defaults={"name": "Kilowatt Hour", "symbol": "kWh", "dimension": UnitDimension.ENERGY},
        )
        self.u_mwh, _ = UnitOfMeasure.objects.get_or_create(
            code="MWH",
            defaults={"name": "Megawatt Hour", "symbol": "MWh", "dimension": UnitDimension.ENERGY},
        )
        self.u_kg, _ = UnitOfMeasure.objects.get_or_create(
            code="KG",
            defaults={"name": "Kilogram", "symbol": "kg", "dimension": UnitDimension.MASS},
        )
        self.u_tonne, _ = UnitOfMeasure.objects.get_or_create(
            code="TONNE",
            defaults={"name": "Metric Tonne", "symbol": "t", "dimension": UnitDimension.MASS},
        )

        # 4. Roles & Users
        self.role_site, _ = Role.objects.get_or_create(code=Role.Code.SITE_MANAGER, defaults={"name": "Site Manager", "is_active": True})
        self.role_sub, _ = Role.objects.get_or_create(code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Subsidiary Manager", "is_active": True})
        self.role_esg, _ = Role.objects.get_or_create(code=Role.Code.ESG_MANAGER, defaults={"name": "ESG Manager", "is_active": True})
        self.role_auditor, _ = Role.objects.get_or_create(code=Role.Code.AUDITOR, defaults={"name": "Auditor", "is_active": True})

        self.site_mgr = User.objects.create_user(username="test_site_mgr", password="password123")
        self.sub_mgr = User.objects.create_user(username="test_sub_mgr", password="password123")
        self.esg_mgr = User.objects.create_user(username="test_esg_mgr", password="password123")
        self.auditor = User.objects.create_user(username="test_auditor", password="password123")

        UserRole.objects.create(user=self.site_mgr, role=self.role_site, is_primary=True)
        UserRole.objects.create(user=self.sub_mgr, role=self.role_sub, is_primary=True)
        UserRole.objects.create(user=self.esg_mgr, role=self.role_esg, is_primary=True)
        UserRole.objects.create(user=self.auditor, role=self.role_auditor, is_primary=True)

        SiteAssignment.objects.create(user=self.site_mgr, site=self.site_a)
        SubsidiaryAssignment.objects.create(user=self.sub_mgr, subsidiary=self.subsidiary)
        CompanyAssignment.objects.create(user=self.esg_mgr, company=self.company)
        CompanyAssignment.objects.create(user=self.auditor, company=self.company)

        # 5. Activity Masters & Emission Factors
        self.cat_stationary = ActivityCategory.objects.create(name="Stationary Fuel Combustion", code="CAT-STAT-FUEL")
        self.cat_mobile = ActivityCategory.objects.create(name="Mobile Combustion", code="CAT-MOB-FUEL")
        self.cat_electricity = ActivityCategory.objects.create(name="Purchased Electricity", code="CAT-ELEC")

        self.act_diesel_stat = ActivityMaster.objects.create(
            code="FUEL-DIESEL-STAT",
            name="Diesel (Stationary Generator / DG Set)",
            category=self.cat_stationary,
            activity_type="STATIONARY_COMBUSTION",
            base_unit=self.u_litre,
            scope_classification=ScopeClassification.SCOPE_1,
            is_active=True,
        )
        self.act_grid_elec = ActivityMaster.objects.create(
            code="ELEC-GRID",
            name="Grid Purchased Electricity",
            category=self.cat_electricity,
            activity_type="PURCHASED_ELECTRICITY",
            base_unit=self.u_kwh,
            scope_classification=ScopeClassification.SCOPE_2,
            is_active=True,
        )
        self.act_solar_elec = ActivityMaster.objects.create(
            code="ELEC-RENEWABLE-CAPTIVE",
            name="Captive Solar Power Generation",
            category=self.cat_electricity,
            activity_type="PURCHASED_ELECTRICITY",
            base_unit=self.u_kwh,
            scope_classification=ScopeClassification.SCOPE_2,
            is_active=True,
        )
        self.act_diesel_stat.allowed_units.add(self.u_litre, self.u_kl)
        self.act_grid_elec.allowed_units.add(self.u_kwh, self.u_mwh)
        self.act_solar_elec.allowed_units.add(self.u_kwh, self.u_mwh)

        self.ef_diesel = EmissionFactor.objects.create(
            code="EF-TEST-DIESEL-STAT-2024",
            name="IPCC 2006 Stationary Diesel Factor",
            activity=self.act_diesel_stat,
            activity_code="FUEL-DIESEL-STAT",
            scope=ScopeClassification.SCOPE_1,
            factor_value=Decimal("2.680000"),
            factor_unit="kg CO₂e / L",
            input_unit=self.u_litre,
            output_unit="kg CO₂e",
            source="IPCC 2006 Guidelines / India GHG Program",
            effective_year=2024,
            version="v1.0",
            status=EmissionFactorStatus.ACTIVE,
            created_by=self.esg_mgr,
        )
        self.ef_grid = EmissionFactor.objects.create(
            code="EF-TEST-GRID-CEA-V19",
            name="CEA Baseline Database v19 Grid Factor",
            activity=self.act_grid_elec,
            activity_code="ELEC-GRID",
            scope=ScopeClassification.SCOPE_2,
            factor_value=Decimal("0.820000"),
            factor_unit="kg CO₂e / kWh",
            input_unit=self.u_kwh,
            output_unit="kg CO₂e",
            source="Central Electricity Authority Baseline v19",
            effective_year=2024,
            version="v19.0",
            status=EmissionFactorStatus.ACTIVE,
            created_by=self.esg_mgr,
        )
        self.ef_solar = EmissionFactor.objects.create(
            code="EF-TEST-SOLAR-2024",
            name="Zero-emission Solar Factor",
            activity=self.act_solar_elec,
            activity_code="ELEC-RENEWABLE-CAPTIVE",
            scope=ScopeClassification.SCOPE_2,
            factor_value=Decimal("0.000000"),
            factor_unit="kg CO₂e / kWh",
            input_unit=self.u_kwh,
            output_unit="kg CO₂e",
            source="GHG Protocol Scope 2 Renewable Guidance",
            effective_year=2024,
            version="v1.0",
            status=EmissionFactorStatus.ACTIVE,
            created_by=self.esg_mgr,
        )

        self.client = Client()

    # =========================================================================
    # 1. UNIT NORMALIZATION TESTS
    # =========================================================================
    def test_unit_normalization_conversions(self):
        """Verify centralized unit conversions accurately convert volume, energy, and mass."""
        # Volume: 2.5 kL -> 2,500 L
        norm_kl, factor = convert_quantity(Decimal("2.5"), "KL", "LITRE")
        self.assertEqual(norm_kl, Decimal("2500.000000"))
        self.assertEqual(factor, Decimal("1000.0"))

        # Energy: 4.0 MWh -> 4,000 kWh
        norm_mwh, factor = convert_quantity(Decimal("4.0"), "MWH", "KWH")
        self.assertEqual(norm_mwh, Decimal("4000.000000"))
        self.assertEqual(factor, Decimal("1000.0"))

        # Mass: 1.5 tonne -> 1,500 kg
        norm_tonne, factor = convert_quantity(Decimal("1.5"), "TONNE", "KG")
        self.assertEqual(norm_tonne, Decimal("1500.000000"))
        self.assertEqual(factor, Decimal("1000.0"))

        # Same unit identity: 100 L -> 100 L
        norm_same, factor = convert_quantity(Decimal("100"), "LITRE", "LITRE")
        self.assertEqual(norm_same, Decimal("100.000000"))
        self.assertEqual(factor, Decimal("1.000000"))

    def test_unit_normalization_dimension_mismatch_rejection(self):
        """Cross-dimension conversion (e.g. Litre to Kilogram) must raise UnitDimensionMismatchError."""
        with self.assertRaises(UnitDimensionMismatchError):
            convert_quantity(Decimal("100"), "LITRE", "KG")

        with self.assertRaises(UnitDimensionMismatchError):
            convert_quantity(Decimal("50"), "KWH", "TONNE")

    def test_unit_normalization_unsupported_unit_rejection(self):
        """Unsupported or non-existent units must raise UnsupportedUnitError."""
        with self.assertRaises(UnsupportedUnitError):
            convert_quantity(Decimal("100"), "UNKNOWN_XYZ", "LITRE")

    # =========================================================================
    # 2. EMISSION FACTOR SELECTION TESTS
    # =========================================================================
    def test_emission_factor_selection_active_match(self):
        """Factor selector matches active factor by activity master, scope, and reporting year."""
        factor = select_emission_factor(self.act_diesel_stat, self.period_fy25)
        self.assertIsNotNone(factor)
        self.assertEqual(factor.code, "EF-TEST-DIESEL-STAT-2024")
        self.assertEqual(factor.factor_value, Decimal("2.680000"))

    def test_emission_factor_selection_ignores_archived(self):
        """Archived or inactive emission factors are strictly excluded from selection."""
        self.ef_diesel.status = EmissionFactorStatus.ARCHIVED
        self.ef_diesel.save()

        factor = select_emission_factor(self.act_diesel_stat, self.period_fy25)
        # Should not select the archived custom factor; will fallback or return None
        if factor:
            self.assertNotEqual(factor.id, self.ef_diesel.id)

    # =========================================================================
    # 3. DETERMINISTIC CALCULATION CORRECTNESS (SCOPE 1 & SCOPE 2)
    # =========================================================================
    def test_scope1_calculation_deterministic_math(self):
        """
        Demo Scenario 1:
        Input: 1,000 L of Diesel
        Factor: 2.680000 kg CO2e / L
        Expected Calculation: 1,000 * 2.68 / 1,000 = 2.6800 tCO2e
        """
        record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_diesel_stat,
            measurement_date=date(2025, 6, 15),
            quantity=Decimal("1000.0000"),
            unit=self.u_litre,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(record, user=self.esg_mgr, force_recalculate=True)

        self.assertEqual(calc.status, CalculationStatus.CALCULATED)
        self.assertEqual(calc.normalized_quantity, Decimal("1000.0000"))
        self.assertEqual(calc.normalized_unit, self.u_litre)
        self.assertEqual(calc.emission_factor, self.ef_diesel)
        self.assertEqual(calc.factor_value_applied, Decimal("2.680000"))
        self.assertEqual(calc.calculated_value, Decimal("2.6800"))
        self.assertEqual(calc.result_unit, "tCO₂e")
        self.assertIn("2.6800 kg CO", calc.formula_repr)

    def test_scope1_calculation_unit_conversion_input(self):
        """
        Input in kL: 2.0 kL of Diesel
        Normalized: 2,000 L
        Factor: 2.680000 kg CO2e / L
        Expected: 2,000 * 2.68 / 1,000 = 5.3600 tCO2e
        """
        record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_diesel_stat,
            measurement_date=date(2025, 7, 20),
            quantity=Decimal("2.0000"),
            unit=self.u_kl,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(record, user=self.esg_mgr, force_recalculate=True)

        self.assertEqual(calc.status, CalculationStatus.CALCULATED)
        self.assertEqual(calc.normalized_quantity, Decimal("2000.0000"))
        self.assertEqual(calc.calculated_value, Decimal("5.3600"))

    def test_scope2_calculation_grid_electricity(self):
        """
        Scope 2 Electricity Calculation:
        Input: 10,000 kWh Grid Electricity
        Factor: 0.820000 kg CO2e / kWh
        Expected: 10,000 * 0.82 / 1,000 = 8.2000 tCO2e
        """
        record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_grid_elec,
            measurement_date=date(2025, 8, 10),
            quantity=Decimal("10000.0000"),
            unit=self.u_kwh,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(record, user=self.esg_mgr, force_recalculate=True)

        self.assertEqual(calc.status, CalculationStatus.CALCULATED)
        self.assertEqual(calc.calculated_value, Decimal("8.2000"))
        self.assertEqual(calc.result_unit, "tCO₂e")

    def test_scope2_captive_solar_zero_emission(self):
        """Captive Solar renewable generation has 0.0000 emission factor -> 0.0000 tCO2e."""
        record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_solar_elec,
            measurement_date=date(2025, 8, 15),
            quantity=Decimal("25000.0000"),
            unit=self.u_kwh,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(record, user=self.esg_mgr, force_recalculate=True)

        self.assertEqual(calc.status, CalculationStatus.CALCULATED)
        self.assertEqual(calc.calculated_value, Decimal("0.0000"))

    def test_calculation_reproducibility(self):
        """Running calculation multiple times with same inputs produces identical deterministic results."""
        record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_diesel_stat,
            measurement_date=date(2025, 9, 1),
            quantity=Decimal("5000.0000"),
            unit=self.u_litre,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc_1 = calculate_activity_record(record, user=self.esg_mgr, force_recalculate=True)
        calc_2 = recalculate_record(record, user=self.esg_mgr)

        self.assertEqual(calc_1.calculated_value, calc_2.calculated_value)
        self.assertEqual(calc_1.formula_repr, calc_2.formula_repr)
        self.assertEqual(calc_2.calculated_value, Decimal("13.4000"))

    # =========================================================================
    # 4. MISSING FACTOR & SAFETY HANDLING
    # =========================================================================
    def test_missing_factor_requires_configuration_safe_state(self):
        """
        Demo Scenario 3:
        Activity without configured factor must enter REQUIRES_CONFIGURATION state.
        Calculated value must be exactly 0.0000, never fabricated or invented.
        """
        act_unconfigured = ActivityMaster.objects.create(
            code="ACT-TEST-FUGITIVE-SF6",
            name="SF6 High Voltage Gas",
            category=self.cat_stationary,
            activity_type="FUGITIVE_EMISSIONS",
            base_unit=self.u_kg,
            scope_classification=ScopeClassification.SCOPE_1,
            is_active=True,
        )

        record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=act_unconfigured,
            measurement_date=date(2025, 9, 15),
            quantity=Decimal("50.0000"),
            unit=self.u_kg,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(record, user=self.esg_mgr, force_recalculate=True)

        self.assertEqual(calc.status, CalculationStatus.REQUIRES_CONFIGURATION)
        self.assertEqual(calc.calculated_value, Decimal("0.0000"))
        self.assertIn("Emission factor configuration required", calc.error_message)

    def test_unverified_record_calculation_eligibility(self):
        """Unverified records (e.g. DRAFT or PENDING_CORRECTION) are not reporting-eligible."""
        record_draft = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_diesel_stat,
            measurement_date=date(2025, 9, 20),
            quantity=Decimal("1000.0000"),
            unit=self.u_litre,
            status=RecordStatus.DRAFT,
            validation_status=ValidationStatus.UNVALIDATED,
            created_by=self.site_mgr,
        )

        # Unverified records are strictly excluded from consolidated reporting totals
        report = get_consolidated_report(user=self.esg_mgr, period_id=self.period_fy25.id)
        self.assertEqual(report["total_scope1_tco2e"], Decimal("0.0000"))
        self.assertEqual(report["total_verified_count"], 0)

    # =========================================================================
    # 5. MULTI-SITE CONSOLIDATION & DOUBLE-COUNTING PROTECTION
    # =========================================================================
    def test_multi_site_reconciled_consolidation(self):
        """
        Demo Scenario 2: Multi-Site Consolidation:
        Site A: 1,000 L -> 2.6800 tCO2e
        Site B: 2,000 L -> 5.3600 tCO2e
        Site C: 3,000 L -> 8.0400 tCO2e
        Project Reconciled Total = 16.0800 tCO2e
        """
        for site, qty in [(self.site_a, Decimal("1000")), (self.site_b, Decimal("2000")), (self.site_c, Decimal("3000"))]:
            rec = ActivityRecord.objects.create(
                site=site,
                reporting_period=self.period_fy25,
                activity=self.act_diesel_stat,
                measurement_date=date(2025, 10, 1),
                quantity=qty,
                unit=self.u_litre,
                status=RecordStatus.VERIFIED,
                validation_status=ValidationStatus.VALID,
                created_by=self.site_mgr,
            )
            # Create verified submission for consolidation integration
            Submission.objects.create(
                activity_record=rec,
                site=site,
                reporting_period=self.period_fy25,
                submitted_by=self.site_mgr,
                status=SubmissionStatus.VERIFIED,
                validation_status=ValidationStatus.VALID,
                is_current=True,
            )
            calculate_activity_record(rec, user=self.esg_mgr, force_recalculate=True)

        report = get_consolidated_report(user=self.esg_mgr, period_id=self.period_fy25.id)

        self.assertEqual(report["total_scope1_tco2e"], Decimal("16.0800"))
        self.assertEqual(report["total_verified_count"], 3)

    def test_reporting_period_filtering(self):
        """Records from FY2024-25 are strictly isolated and not counted in FY2025-26."""
        # FY24 Record
        rec_fy24 = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy24,
            activity=self.act_diesel_stat,
            measurement_date=date(2024, 11, 1),
            quantity=Decimal("5000.0000"),
            unit=self.u_litre,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        Submission.objects.create(
            activity_record=rec_fy24,
            site=self.site_a,
            reporting_period=self.period_fy24,
            submitted_by=self.site_mgr,
            status=SubmissionStatus.VERIFIED,
            is_current=True,
        )
        calculate_activity_record(rec_fy24, user=self.esg_mgr, force_recalculate=True)

        # FY25 Consolidation must not include rec_fy24
        report_fy25 = get_consolidated_report(user=self.esg_mgr, period_id=self.period_fy25.id)
        self.assertEqual(report_fy25["total_scope1_tco2e"], Decimal("0.0000"))

        report_fy24 = get_consolidated_report(user=self.esg_mgr, period_id=self.period_fy24.id)
        self.assertEqual(report_fy24["total_scope1_tco2e"], Decimal("13.4000"))

    def test_double_counting_protection_superseded_submissions(self):
        """Superseded historical submissions (is_current=False) must not be counted twice."""
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_diesel_stat,
            measurement_date=date(2025, 11, 10),
            quantity=Decimal("1000.0000"),
            unit=self.u_litre,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        calculate_activity_record(rec, user=self.esg_mgr, force_recalculate=True)

        # Old submission superseded by resubmission
        Submission.objects.create(
            activity_record=rec,
            submission_number=1,
            site=self.site_a,
            reporting_period=self.period_fy25,
            submitted_by=self.site_mgr,
            status=SubmissionStatus.CORRECTION_REQUESTED,
            is_current=False,
        )
        # Current active verified submission
        Submission.objects.create(
            activity_record=rec,
            submission_number=2,
            site=self.site_a,
            reporting_period=self.period_fy25,
            submitted_by=self.site_mgr,
            status=SubmissionStatus.VERIFIED,
            is_current=True,
        )

        report = get_consolidated_report(user=self.esg_mgr, period_id=self.period_fy25.id)
        # Exactly 1 record should be counted, producing 2.6800, NOT double (5.3600)
        self.assertEqual(report["total_scope1_tco2e"], Decimal("2.6800"))
        self.assertEqual(report["total_verified_count"], 1)

    # =========================================================================
    # 6. LINEAGE & AUDITOR TRACEABILITY
    # =========================================================================
    def test_auditor_calculation_lineage_trace(self):
        """
        Demo Scenario 4: Auditor Trace Lineage:
        Auditor can trace from consolidated report -> submission -> record -> calculation result -> emission factor.
        """
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_diesel_stat,
            measurement_date=date(2025, 11, 20),
            quantity=Decimal("1000.0000"),
            unit=self.u_litre,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        sub = Submission.objects.create(
            activity_record=rec,
            site=self.site_a,
            reporting_period=self.period_fy25,
            submitted_by=self.site_mgr,
            status=SubmissionStatus.VERIFIED,
            is_current=True,
        )
        calc = calculate_activity_record(rec, user=self.esg_mgr, force_recalculate=True)

        lineage = get_trace_lineage_context(sub)

        self.assertIsNotNone(lineage["layer1_report"]["calculation_id"])
        self.assertEqual(lineage["layer1_report"]["calculation_id"], calc.id)
        self.assertEqual(lineage["layer1_report"]["emissions_tco2e"], Decimal("2.6800"))
        self.assertIn("IPCC 2006", lineage["layer1_report"]["factor_source"])

    # =========================================================================
    # 7. RBAC & PERMISSION BOUNDARIES
    # =========================================================================
    def test_rbac_auditor_and_site_manager_blocked_from_recalculation(self):
        """Auditor and Site Manager receive HTTP 403 Forbidden when attempting recalculation mutation."""
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_diesel_stat,
            measurement_date=date(2025, 12, 1),
            quantity=Decimal("1000.0000"),
            unit=self.u_litre,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        calc = calculate_activity_record(rec, user=self.esg_mgr, force_recalculate=True)
        url = reverse("core:record_recalculate", kwargs={"record_id": rec.id})

        # Auditor Blocked
        self.client.force_login(self.auditor)
        res_auditor = self.client.post(url)
        self.assertEqual(res_auditor.status_code, 403)

        # Site Manager Blocked
        self.client.force_login(self.site_mgr)
        res_site = self.client.post(url)
        self.assertEqual(res_site.status_code, 403)

        # ESG Manager Authorized
        self.client.force_login(self.esg_mgr)
        res_esg = self.client.post(url)
        self.assertEqual(res_esg.status_code, 302)  # Redirects to calculation detail

    def test_rbac_emission_factor_administration_boundaries(self):
        """Only ESG Manager or Admin can create/edit emission factors. Auditor and Site Manager get 403."""
        create_url = reverse("core:emission_factor_create")
        edit_url = reverse("core:emission_factor_edit", kwargs={"factor_id": self.ef_diesel.id})

        # Site Manager blocked
        self.client.force_login(self.site_mgr)
        res = self.client.get(create_url)
        self.assertEqual(res.status_code, 403)
        res = self.client.get(edit_url)
        self.assertEqual(res.status_code, 403)

        # Auditor blocked from mutating factor
        self.client.force_login(self.auditor)
        res = self.client.get(create_url)
        self.assertEqual(res.status_code, 403)
        res = self.client.get(edit_url)
        self.assertEqual(res.status_code, 403)

        # ESG Manager authorized to access factor management
        self.client.force_login(self.esg_mgr)
        res = self.client.get(create_url)
        self.assertEqual(res.status_code, 200)
        res = self.client.get(edit_url)
        self.assertEqual(res.status_code, 200)

    def test_auditor_read_only_access_to_calculation_desk_and_details(self):
        """Auditor can inspect calculation desk and calculation detail pages in read-only mode."""
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_diesel_stat,
            measurement_date=date(2025, 12, 5),
            quantity=Decimal("1000.0000"),
            unit=self.u_litre,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        calc = calculate_activity_record(rec, user=self.esg_mgr, force_recalculate=True)

        self.client.force_login(self.auditor)

        # Desk
        res_desk = self.client.get(reverse("core:calculation_desk"))
        self.assertEqual(res_desk.status_code, 200)

        # Detail
        res_detail = self.client.get(reverse("core:calculation_detail", kwargs={"calculation_id": calc.id}))
        self.assertEqual(res_detail.status_code, 200)

        # Factors catalog (Read-only view)
        res_factors = self.client.get(reverse("core:emission_factor_list"))
        self.assertEqual(res_factors.status_code, 200)
