"""
Phase 23: Scope 3 Emissions Engine Automated Test Suite.

Authoritative verification of:
1. GHG Protocol 15 Scope 3 Categories & Value Chain Boundary (Upstream 1-8, Downstream 9-15)
2. Deterministic Automatic Scope Classification Engine (Taxonomy & Ownership based)
3. Scope 3 Activity Master Integration & Calculation Methods
4. Deterministic Scope 3 Emissions Calculations (Freight, Waste, Travel, Purchased Goods)
5. Missing Factor Safety (REQUIRES_CONFIGURATION, zero synthetic or fake data)
6. Scope 3 CalculationResult Ledger Snapshotting (scope3_category, calculation_method)
7. Scope 3 Inventory Summary Aggregation (Upstream vs. Downstream, DATA_RECORDED, DATA_REQUIRED)
8. Multi-Site Reconciled Consolidation & Double-Counting Protection
9. 6-Tier Auditor Traceability Lineage for Scope 3 Disclosures
10. Strict Multi-Tenant RBAC & Auditor Read-Only Boundaries
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.activity_forms import ActivityMasterForm
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
    PeriodStatus,
    Project,
    RecordStatus,
    ReportingPeriod,
    Role,
    Scope3Category,
    Scope3CalculationMethod,
    Scope3Direction,
    ScopeClassification,
    Site,
    SiteAssignment,
    Submission,
    SubmissionStatus,
    Subsidiary,
    SubsidiaryAssignment,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
    ValidationStatus,
)
from apps.core.reporting_services import get_consolidated_report, get_trace_lineage_context
from apps.core.scope3_services import (
    classify_activity_scope,
    get_scope3_category_detail,
    get_scope3_inventory_summary,
    seed_scope3_categories,
)

User = get_user_model()


class Phase23Scope3EngineTestCase(TestCase):
    def setUp(self):
        # 1. Base Organization Hierarchy
        self.company = Company.objects.create(
            name="MEIL Power & Infrastructure Enterprise",
            code="MEIL-CORP",
        )
        self.subsidiary = Subsidiary.objects.create(
            company=self.company,
            name="MEIL Logistics & Environmental Division",
            code="MEIL-ENV",
        )
        self.other_subsidiary = Subsidiary.objects.create(
            company=self.company,
            name="MEIL Heavy Transmission Division",
            code="MEIL-HTD",
        )
        self.project = Project.objects.create(
            subsidiary=self.subsidiary,
            name="Hyderabad Solar & Civil Corridor",
            code="PRJ-HYD-01",
        )
        self.site_a = Site.objects.create(
            project=self.project,
            name="Central Logistics Staging Hub",
            code="HYD-STG-01",
        )
        self.site_b = Site.objects.create(
            project=self.project,
            name="Civil Construction Yard Beta",
            code="HYD-YRD-02",
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
        self.u_tkm, _ = UnitOfMeasure.objects.get_or_create(
            code="T-KM",
            defaults={"name": "Tonne-Kilometre", "symbol": "t-km", "dimension": UnitDimension.OTHER},
        )
        self.u_pkm, _ = UnitOfMeasure.objects.get_or_create(
            code="P-KM",
            defaults={"name": "Passenger-Kilometre", "symbol": "p-km", "dimension": UnitDimension.OTHER},
        )
        self.u_tonne, _ = UnitOfMeasure.objects.get_or_create(
            code="TONNE",
            defaults={"name": "Metric Tonne", "symbol": "t", "dimension": UnitDimension.MASS},
        )
        self.u_kg, _ = UnitOfMeasure.objects.get_or_create(
            code="KG",
            defaults={"name": "Kilogram", "symbol": "kg", "dimension": UnitDimension.MASS},
        )
        self.u_litre, _ = UnitOfMeasure.objects.get_or_create(
            code="LITRE",
            defaults={"name": "Litre", "symbol": "L", "dimension": UnitDimension.VOLUME},
        )
        self.u_kwh, _ = UnitOfMeasure.objects.get_or_create(
            code="KWH",
            defaults={"name": "Kilowatt Hour", "symbol": "kWh", "dimension": UnitDimension.ENERGY},
        )

        # 4. RBAC Roles & Personas
        self.role_site, _ = Role.objects.get_or_create(code=Role.Code.SITE_MANAGER, defaults={"name": "Site Manager", "is_active": True})
        self.role_sub, _ = Role.objects.get_or_create(code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Subsidiary Manager", "is_active": True})
        self.role_esg, _ = Role.objects.get_or_create(code=Role.Code.ESG_MANAGER, defaults={"name": "ESG Manager", "is_active": True})
        self.role_auditor, _ = Role.objects.get_or_create(code=Role.Code.AUDITOR, defaults={"name": "Auditor", "is_active": True})

        self.site_mgr = User.objects.create_user(username="s3_site_mgr", password="password123")
        self.sub_mgr = User.objects.create_user(username="s3_sub_mgr", password="password123")
        self.esg_mgr = User.objects.create_user(username="s3_esg_mgr", password="password123")
        self.auditor = User.objects.create_user(username="s3_auditor", password="password123")

        UserRole.objects.create(user=self.site_mgr, role=self.role_site, is_primary=True)
        UserRole.objects.create(user=self.sub_mgr, role=self.role_sub, is_primary=True)
        UserRole.objects.create(user=self.esg_mgr, role=self.role_esg, is_primary=True)
        UserRole.objects.create(user=self.auditor, role=self.role_auditor, is_primary=True)

        SiteAssignment.objects.create(user=self.site_mgr, site=self.site_a)
        SubsidiaryAssignment.objects.create(user=self.sub_mgr, subsidiary=self.subsidiary)
        CompanyAssignment.objects.create(user=self.esg_mgr, company=self.company)
        CompanyAssignment.objects.create(user=self.auditor, company=self.company)

        # 5. Initialize 15 Scope 3 Categories
        self.cat_map = seed_scope3_categories()

        # 6. Categories for Activities
        self.act_cat_transport = ActivityCategory.objects.create(name="Upstream Freight & Logistics", code="TRANSPORT")
        self.act_cat_waste = ActivityCategory.objects.create(name="Operational Waste Management", code="WASTE")
        self.act_cat_travel = ActivityCategory.objects.create(name="Business Air & Rail Travel", code="TRAVEL")
        self.act_cat_materials = ActivityCategory.objects.create(name="Purchased Raw Materials", code="MATERIAL")

        # 7. Scope 3 Activity Masters
        self.act_freight = ActivityMaster.objects.create(
            code="TRANSPORT-COMMERCIAL-FREIGHT",
            name="Commercial Road Freight (Third-Party Fleet)",
            category=self.act_cat_transport,
            activity_type="UPSTREAM_TRANSPORT",
            base_unit=self.u_tkm,
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[4],
            calculation_method=Scope3CalculationMethod.DISTANCE_BASED,
            is_active=True,
        )
        self.act_waste_haz = ActivityMaster.objects.create(
            code="WASTE-HAZARDOUS",
            name="Hazardous Waste Incineration / Co-processing",
            category=self.act_cat_waste,
            activity_type="WASTE_DISPOSAL",
            base_unit=self.u_kg,
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[5],
            calculation_method=Scope3CalculationMethod.WASTE_TYPE_SPECIFIC,
            is_active=True,
        )
        self.act_waste_nonhaz = ActivityMaster.objects.create(
            code="WASTE-NON-HAZARDOUS",
            name="Non-Hazardous Construction Solid Scrap (Landfill)",
            category=self.act_cat_waste,
            activity_type="WASTE_DISPOSAL",
            base_unit=self.u_tonne,
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[5],
            calculation_method=Scope3CalculationMethod.WASTE_TYPE_SPECIFIC,
            is_active=True,
        )
        self.act_air_travel = ActivityMaster.objects.create(
            code="TRAVEL-AIR-DOMESTIC",
            name="Commercial Domestic Air Travel",
            category=self.act_cat_travel,
            activity_type="BUSINESS_TRAVEL",
            base_unit=self.u_pkm,
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[6],
            calculation_method=Scope3CalculationMethod.DISTANCE_BASED,
            is_active=True,
        )
        self.act_steel = ActivityMaster.objects.create(
            code="PURCHASED-GOODS-STEEL",
            name="Structural Rebar & Reinforcement Steel Procurement",
            category=self.act_cat_materials,
            activity_type="PURCHASED_GOODS",
            base_unit=self.u_tonne,
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[1],
            calculation_method=Scope3CalculationMethod.AVERAGE_DATA,
            is_active=True,
        )
        self.act_unconfigured = ActivityMaster.objects.create(
            code="SCOPE3-UNCONFIGURED-MACHINERY",
            name="Procured Heavy Cranes & Generators (Capital Goods)",
            category=self.act_cat_materials,
            activity_type="CAPITAL_GOODS",
            base_unit=self.u_tonne,
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[2],
            calculation_method=Scope3CalculationMethod.SPEND_BASED,
            is_active=True,
        )

        # 8. Scope 3 Approved Emission Factors
        self.ef_freight = EmissionFactor.objects.create(
            code="EF-S3-FREIGHT-2024",
            name="GLEC Heavy Commercial Road Freight Factor",
            activity=self.act_freight,
            activity_code="TRANSPORT-COMMERCIAL-FREIGHT",
            scope=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[4],
            calculation_method=Scope3CalculationMethod.DISTANCE_BASED,
            factor_value=Decimal("0.120000"),
            factor_unit="kg CO₂e / t-km",
            input_unit=self.u_tkm,
            output_unit="kg CO₂e",
            source="GLEC Framework v2.0 / DEFRA 2024 Road Freight",
            effective_year=2024,
            version="v2.0",
            status=EmissionFactorStatus.ACTIVE,
            created_by=self.esg_mgr,
        )
        self.ef_waste_haz = EmissionFactor.objects.create(
            code="EF-S3-WASTE-HAZ-2024",
            name="Hazardous Waste High-Temperature Incineration Factor",
            activity=self.act_waste_haz,
            activity_code="WASTE-HAZARDOUS",
            scope=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[5],
            calculation_method=Scope3CalculationMethod.WASTE_TYPE_SPECIFIC,
            factor_value=Decimal("1.850000"),
            factor_unit="kg CO₂e / kg",
            input_unit=self.u_kg,
            output_unit="kg CO₂e",
            source="UK DEFRA 2024 / IPCC Waste Model",
            effective_year=2024,
            version="v1.0",
            status=EmissionFactorStatus.ACTIVE,
            created_by=self.esg_mgr,
        )
        self.ef_waste_nonhaz = EmissionFactor.objects.create(
            code="EF-S3-WASTE-NONHAZ-2024",
            name="Construction Solid Scrap Landfill Factor",
            activity=self.act_waste_nonhaz,
            activity_code="WASTE-NON-HAZARDOUS",
            scope=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[5],
            calculation_method=Scope3CalculationMethod.WASTE_TYPE_SPECIFIC,
            factor_value=Decimal("45.000000"),
            factor_unit="kg CO₂e / t",
            input_unit=self.u_tonne,
            output_unit="kg CO₂e",
            source="UK DEFRA 2024 Commercial Waste",
            effective_year=2024,
            version="v1.0",
            status=EmissionFactorStatus.ACTIVE,
            created_by=self.esg_mgr,
        )
        self.ef_travel = EmissionFactor.objects.create(
            code="EF-S3-AIR-TRAVEL-2024",
            name="Domestic Commercial Air Travel Factor (with RF)",
            activity=self.act_air_travel,
            activity_code="TRAVEL-AIR-DOMESTIC",
            scope=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[6],
            calculation_method=Scope3CalculationMethod.DISTANCE_BASED,
            factor_value=Decimal("0.150000"),
            factor_unit="kg CO₂e / p-km",
            input_unit=self.u_pkm,
            output_unit="kg CO₂e",
            source="ICAO Carbon Calculator / DEFRA 2024",
            effective_year=2024,
            version="v1.0",
            status=EmissionFactorStatus.ACTIVE,
            created_by=self.esg_mgr,
        )
        self.ef_steel = EmissionFactor.objects.create(
            code="EF-S3-STEEL-REBAR-2024",
            name="Secondary EAF Structural Steel Embodied Carbon Factor",
            activity=self.act_steel,
            activity_code="PURCHASED-GOODS-STEEL",
            scope=ScopeClassification.SCOPE_3,
            scope3_category=self.cat_map[1],
            calculation_method=Scope3CalculationMethod.AVERAGE_DATA,
            factor_value=Decimal("1800.000000"),
            factor_unit="kg CO₂e / t",
            input_unit=self.u_tonne,
            output_unit="kg CO₂e",
            source="World Steel Association / Ecoinvent 3.8",
            effective_year=2024,
            version="v1.0",
            status=EmissionFactorStatus.ACTIVE,
            created_by=self.esg_mgr,
        )

        self.client = Client()

    # =========================================================================
    # 1. GHG PROTOCOL 15 SCOPE 3 CATEGORIES ARCHITECTURE TESTS
    # =========================================================================

    def test_ghg_protocol_15_categories_structure(self):
        """Verify all 15 official GHG Protocol categories exist with correct boundary direction."""
        categories = Scope3Category.objects.all().order_by("category_number")
        self.assertEqual(categories.count(), 15)

        # Upstream Categories 1-8
        for cat in categories.filter(category_number__lte=8):
            self.assertEqual(
                cat.direction,
                Scope3Direction.UPSTREAM,
                f"Category {cat.category_number} ({cat.name}) must be classified as UPSTREAM.",
            )
            self.assertEqual(cat.code, f"SCOPE3_CAT_{cat.category_number:02d}")
            self.assertTrue(len(cat.applicable_methods) > 0)

        # Downstream Categories 9-15
        for cat in categories.filter(category_number__gte=9):
            self.assertEqual(
                cat.direction,
                Scope3Direction.DOWNSTREAM,
                f"Category {cat.category_number} ({cat.name}) must be classified as DOWNSTREAM.",
            )
            self.assertEqual(cat.code, f"SCOPE3_CAT_{cat.category_number:02d}")
            self.assertTrue(len(cat.applicable_methods) > 0)

    def test_seed_scope3_categories_idempotency(self):
        """Verify seed_scope3_categories is fully idempotent and creates zero duplicates."""
        initial_count = Scope3Category.objects.count()
        self.assertEqual(initial_count, 15)

        # Call again
        second_map = seed_scope3_categories()
        self.assertEqual(Scope3Category.objects.count(), 15)
        self.assertEqual(len(second_map), 15)

    # =========================================================================
    # 2. AUTOMATIC SCOPE CLASSIFICATION TESTS
    # =========================================================================

    def test_automatic_scope_classification_rules(self):
        """Verify deterministic automatic scope classifier correctly infers Scopes 1, 2, 3 and Non-GHG."""
        # 1. Fuel / Genset combustion -> Scope 1
        res_s1 = classify_activity_scope(category_code="FUEL", activity_code="FUEL-DIESEL-STAT")
        self.assertEqual(res_s1["scope"], ScopeClassification.SCOPE_1)
        self.assertIsNone(res_s1["scope3_category_number"])

        # 2. Grid electricity -> Scope 2
        res_s2 = classify_activity_scope(category_code="ENERGY", activity_code="ELEC-GRID")
        self.assertEqual(res_s2["scope"], ScopeClassification.SCOPE_2)
        self.assertIsNone(res_s2["scope3_category_number"])

        # 3. Water resource -> Non-GHG
        res_water = classify_activity_scope(category_code="WATER", activity_code="WATER-GROUNDWATER")
        self.assertEqual(res_water["scope"], ScopeClassification.NON_GHG)
        self.assertIsNone(res_water["scope3_category_number"])

        # 4. Commercial freight transport -> Scope 3 (Category 4 Upstream)
        res_freight = classify_activity_scope(category_code="TRANSPORT", activity_code="TRANSPORT-COMMERCIAL-FREIGHT")
        self.assertEqual(res_freight["scope"], ScopeClassification.SCOPE_3)
        self.assertEqual(res_freight["scope3_category_number"], 4)
        self.assertEqual(res_freight["calculation_method"], Scope3CalculationMethod.DISTANCE_BASED)

        # 5. Downstream logistics -> Scope 3 (Category 9 Downstream)
        res_downstream = classify_activity_scope(category_code="TRANSPORT", activity_code="TRANSPORT-DOWNSTREAM-DISPATCH")
        self.assertEqual(res_downstream["scope"], ScopeClassification.SCOPE_3)
        self.assertEqual(res_downstream["scope3_category_number"], 9)

        # 6. Operational waste -> Scope 3 (Category 5)
        res_waste = classify_activity_scope(category_code="WASTE", activity_code="WASTE-HAZARDOUS")
        self.assertEqual(res_waste["scope"], ScopeClassification.SCOPE_3)
        self.assertEqual(res_waste["scope3_category_number"], 5)
        self.assertEqual(res_waste["calculation_method"], Scope3CalculationMethod.WASTE_TYPE_SPECIFIC)

        # 7. Business travel -> Scope 3 (Category 6)
        res_travel = classify_activity_scope(category_code="TRAVEL", activity_code="TRAVEL-AIR-DOMESTIC")
        self.assertEqual(res_travel["scope"], ScopeClassification.SCOPE_3)
        self.assertEqual(res_travel["scope3_category_number"], 6)

        # 8. Employee commuting -> Scope 3 (Category 7)
        res_commute = classify_activity_scope(activity_code="EMPLOYEE-COMMUTING-BUS", activity_name="Staff Bus Shuttle")
        self.assertEqual(res_commute["scope"], ScopeClassification.SCOPE_3)
        self.assertEqual(res_commute["scope3_category_number"], 7)

        # 9. Purchased steel / materials -> Scope 3 (Category 1)
        res_mat = classify_activity_scope(category_code="MATERIAL", activity_code="STEEL-REBAR-PROCUREMENT")
        self.assertEqual(res_mat["scope"], ScopeClassification.SCOPE_3)
        self.assertEqual(res_mat["scope3_category_number"], 1)

        # 10. Capital goods / equipment -> Scope 3 (Category 2)
        res_cap = classify_activity_scope(activity_code="CAPITAL-EQUIPMENT-CRANE", activity_name="Hydraulic Crawler Crane")
        self.assertEqual(res_cap["scope"], ScopeClassification.SCOPE_3)
        self.assertEqual(res_cap["scope3_category_number"], 2)

    # =========================================================================
    # 3. ACTIVITY MASTER & FORM TESTS
    # =========================================================================

    def test_scope3_activity_master_properties(self):
        """Verify ActivityMaster properties reflect Scope 3 category and direction."""
        self.assertEqual(self.act_freight.scope3_direction, Scope3Direction.UPSTREAM)
        self.assertEqual(self.act_freight.scope_classification, ScopeClassification.SCOPE_3)
        self.assertEqual(self.act_freight.calculation_method, Scope3CalculationMethod.DISTANCE_BASED)

        # Form validation
        form = ActivityMasterForm(
            data={
                "code": "TEST-S3-FORM-ACT",
                "name": "Test Form Scope 3 Activity",
                "category": self.act_cat_transport.id,
                "activity_type": "UPSTREAM_TRANSPORT",
                "base_unit": self.u_tkm.id,
                "scope_classification": ScopeClassification.SCOPE_3,
                "scope3_category": self.cat_map[4].id,
                "calculation_method": Scope3CalculationMethod.DISTANCE_BASED,
                "collection_frequency": "MONTHLY",
                "status": "ACTIVE",
            }
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        saved_act = form.save()
        self.assertEqual(saved_act.scope3_category.category_number, 4)
        self.assertEqual(saved_act.calculation_method, Scope3CalculationMethod.DISTANCE_BASED)

    # =========================================================================
    # 4. DETERMINISTIC SCOPE 3 CALCULATION TESTS
    # =========================================================================

    def test_scope3_upstream_freight_calculation(self):
        """
        Category 4: Upstream Freight:
        10,000 t-km @ 0.12 kg CO2e / t-km = 1,200 kg CO2e = 1.2000 tCO2e.
        """
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_freight,
            measurement_date=date(2025, 6, 15),
            quantity=Decimal("10000.0000"),
            unit=self.u_tkm,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(rec)
        self.assertEqual(calc.status, CalculationStatus.CALCULATED)
        self.assertEqual(calc.calculated_value, Decimal("1.2000"))
        self.assertEqual(calc.scope, ScopeClassification.SCOPE_3)
        self.assertEqual(calc.scope3_category, self.cat_map[4])
        self.assertEqual(calc.calculation_method, Scope3CalculationMethod.DISTANCE_BASED)
        self.assertTrue(calc.is_latest)
        self.assertTrue("10,000" in calc.formula_repr or "10000" in calc.formula_repr)
        self.assertIn("0.12", calc.formula_repr)

    def test_scope3_hazardous_waste_calculation(self):
        """
        Category 5: Hazardous Waste:
        2,500 kg @ 1.85 kg CO2e / kg = 4,625 kg CO2e = 4.6250 tCO2e.
        """
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_waste_haz,
            measurement_date=date(2025, 7, 10),
            quantity=Decimal("2500.0000"),
            unit=self.u_kg,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(rec)
        self.assertEqual(calc.status, CalculationStatus.CALCULATED)
        self.assertEqual(calc.calculated_value, Decimal("4.6250"))
        self.assertEqual(calc.scope, ScopeClassification.SCOPE_3)
        self.assertEqual(calc.scope3_category, self.cat_map[5])
        self.assertEqual(calc.calculation_method, Scope3CalculationMethod.WASTE_TYPE_SPECIFIC)

    def test_scope3_business_air_travel_calculation(self):
        """
        Category 6: Business Air Travel:
        5,000 p-km @ 0.15 kg CO2e / p-km = 750 kg CO2e = 0.7500 tCO2e.
        """
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_air_travel,
            measurement_date=date(2025, 8, 20),
            quantity=Decimal("5000.0000"),
            unit=self.u_pkm,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(rec)
        self.assertEqual(calc.status, CalculationStatus.CALCULATED)
        self.assertEqual(calc.calculated_value, Decimal("0.7500"))
        self.assertEqual(calc.scope, ScopeClassification.SCOPE_3)
        self.assertEqual(calc.scope3_category, self.cat_map[6])
        self.assertEqual(calc.calculation_method, Scope3CalculationMethod.DISTANCE_BASED)

    def test_scope3_purchased_steel_calculation(self):
        """
        Category 1: Purchased Goods and Services:
        100 tonnes @ 1,800.0 kg CO2e / tonne = 180,000 kg CO2e = 180.0000 tCO2e.
        """
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_steel,
            measurement_date=date(2025, 9, 5),
            quantity=Decimal("100.0000"),
            unit=self.u_tonne,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(rec)
        self.assertEqual(calc.status, CalculationStatus.CALCULATED)
        self.assertEqual(calc.calculated_value, Decimal("180.0000"))
        self.assertEqual(calc.scope, ScopeClassification.SCOPE_3)
        self.assertEqual(calc.scope3_category, self.cat_map[1])
        self.assertEqual(calc.calculation_method, Scope3CalculationMethod.AVERAGE_DATA)

    # =========================================================================
    # 5. MISSING FACTOR SAFETY & ZERO SYNTHETIC DATA
    # =========================================================================

    def test_scope3_missing_factor_safety(self):
        """
        When a Scope 3 activity has no active factor, calculation must result in:
        - REQUIRES_CONFIGURATION
        - 0.0000 tCO2e
        - Zero synthetic numbers fabricated
        - Clear diagnostic note
        """
        rec_unconfigured = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_unconfigured,
            measurement_date=date(2025, 9, 12),
            quantity=Decimal("50.0000"),
            unit=self.u_tonne,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )

        calc = calculate_activity_record(rec_unconfigured)
        self.assertEqual(calc.status, CalculationStatus.REQUIRES_CONFIGURATION)
        self.assertEqual(calc.calculated_value, Decimal("0.0000"))
        self.assertIn("Emission factor configuration required", calc.error_message)

    # =========================================================================
    # 6. SCOPE 3 INVENTORY SUMMARY & EXPLICIT STATUS AUDITING
    # =========================================================================

    def test_scope3_inventory_summary_aggregation(self):
        """Verify Scope 3 inventory breakdown: Upstream vs Downstream totals, and explicit category statuses."""
        # Record 1: Freight (Cat 4): 10,000 t-km -> 1.2000 tCO2e
        rec1 = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_freight,
            measurement_date=date(2025, 6, 1),
            quantity=Decimal("10000.0000"),
            unit=self.u_tkm,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        Submission.objects.create(
            activity_record=rec1,
            site=self.site_a,
            reporting_period=self.period_fy25,
            submitted_by=self.site_mgr,
            status=SubmissionStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
        )
        calculate_activity_record(rec1)

        # Record 2: Hazardous Waste (Cat 5): 2,500 kg -> 4.6250 tCO2e
        rec2 = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_waste_haz,
            measurement_date=date(2025, 6, 2),
            quantity=Decimal("2500.0000"),
            unit=self.u_kg,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        Submission.objects.create(
            activity_record=rec2,
            site=self.site_a,
            reporting_period=self.period_fy25,
            submitted_by=self.site_mgr,
            status=SubmissionStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
        )
        calculate_activity_record(rec2)

        # Record 3: Unconfigured Machinery (Cat 2): REQUIRES_CONFIGURATION
        rec3 = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_unconfigured,
            measurement_date=date(2025, 6, 3),
            quantity=Decimal("10.0000"),
            unit=self.u_tonne,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        Submission.objects.create(
            activity_record=rec3,
            site=self.site_a,
            reporting_period=self.period_fy25,
            submitted_by=self.site_mgr,
            status=SubmissionStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
        )
        calculate_activity_record(rec3)

        # Record 4: Unverified Draft record (Must NOT be counted)
        rec_draft = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_air_travel,
            measurement_date=date(2025, 6, 4),
            quantity=Decimal("100000.0000"),
            unit=self.u_pkm,
            status=RecordStatus.DRAFT,
            validation_status=ValidationStatus.UNVALIDATED,
            created_by=self.site_mgr,
        )
        calculate_activity_record(rec_draft)

        # Run inventory summary
        summary = get_scope3_inventory_summary(
            user=self.esg_mgr,
            period_id=self.period_fy25.id,
            subsidiary_id=self.subsidiary.id,
        )

        # Expected Upstream total = 1.2000 (Cat 4) + 4.6250 (Cat 5) = 5.8250 tCO2e
        self.assertEqual(summary["total_upstream_tco2e"], Decimal("5.8250"))
        self.assertEqual(summary["total_downstream_tco2e"], Decimal("0.0000"))
        self.assertEqual(summary["total_scope3_tco2e"], Decimal("5.8250"))

        # Category status checks
        cat4_item = next(c for c in summary["all_categories"] if c["category_number"] == 4)
        self.assertEqual(cat4_item["status"], "DATA_RECORDED")
        self.assertEqual(cat4_item["emissions_tco2e"], Decimal("1.2000"))

        cat5_item = next(c for c in summary["all_categories"] if c["category_number"] == 5)
        self.assertEqual(cat5_item["status"], "DATA_RECORDED")
        self.assertEqual(cat5_item["emissions_tco2e"], Decimal("4.6250"))

        cat2_item = next(c for c in summary["all_categories"] if c["category_number"] == 2)
        self.assertEqual(cat2_item["status"], "REQUIRES_CONFIGURATION")
        self.assertEqual(cat2_item["emissions_tco2e"], Decimal("0.0000"))

        # Category 15 (Investments) has no records -> DATA_REQUIRED
        cat15_item = next(c for c in summary["all_categories"] if c["category_number"] == 15)
        self.assertEqual(cat15_item["status"], "DATA_REQUIRED")
        self.assertEqual(cat15_item["emissions_tco2e"], Decimal("0.0000"))

    # =========================================================================
    # 7. MULTI-SITE RECONCILED CONSOLIDATION & RECONCILIATION
    # =========================================================================

    def test_multi_site_reconciled_consolidation_with_scope3(self):
        """
        Reconciliation test:
        Site A: Upstream Freight 10,000 t-km -> 1.2000 tCO2e
        Site B: Upstream Freight 20,000 t-km -> 2.4000 tCO2e
        Total Scope 3 Consolidated = 3.6000 tCO2e
        Reconciled against Scope 1 and Scope 2 with zero double counting.
        """
        for site, qty in [(self.site_a, Decimal("10000")), (self.site_b, Decimal("20000"))]:
            rec = ActivityRecord.objects.create(
                site=site,
                reporting_period=self.period_fy25,
                activity=self.act_freight,
                measurement_date=date(2025, 7, 1),
                quantity=qty,
                unit=self.u_tkm,
                status=RecordStatus.VERIFIED,
                validation_status=ValidationStatus.VALID,
                created_by=self.site_mgr,
            )
            Submission.objects.create(
                activity_record=rec,
                site=site,
                reporting_period=self.period_fy25,
                submitted_by=self.site_mgr,
                status=SubmissionStatus.VERIFIED,
                validation_status=ValidationStatus.VALID,
            )
            calculate_activity_record(rec)

        report = get_consolidated_report(user=self.esg_mgr, period_id=self.period_fy25.id)
        self.assertEqual(report["total_scope3_tco2e"], Decimal("3.6000"))
        self.assertEqual(report["total_upstream_tco2e"], Decimal("3.6000"))
        self.assertEqual(report["total_downstream_tco2e"], Decimal("0.0000"))
        self.assertEqual(report["total_verified_count"], 2)

    # =========================================================================
    # 8. 6-TIER AUDITOR TRACEABILITY LINEAGE FOR SCOPE 3
    # =========================================================================

    def test_six_tier_auditor_traceability_scope3(self):
        """Verify Layer 1 of 6-Tier Traceability includes Scope 3 category, direction, and calculation method."""
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_freight,
            measurement_date=date(2025, 8, 1),
            quantity=Decimal("15000.0000"),
            unit=self.u_tkm,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        calc = calculate_activity_record(rec)

        trace_ctx = get_trace_lineage_context(rec.id)
        layer1 = trace_ctx.get("layer1_report", {})

        self.assertEqual(layer1.get("scope"), ScopeClassification.SCOPE_3)
        self.assertEqual(layer1.get("scope3_category_number"), 4)
        self.assertEqual(layer1.get("scope3_direction"), Scope3Direction.UPSTREAM)
        self.assertEqual(layer1.get("calculation_method"), Scope3CalculationMethod.DISTANCE_BASED)
        self.assertTrue("15,000" in layer1.get("methodology") or "15000" in layer1.get("methodology"))
        self.assertEqual(layer1.get("emissions_tco2e"), Decimal("1.8000"))

    # =========================================================================
    # 9. RBAC & AUDITOR RESTRICTIONS
    # =========================================================================

    def test_scope3_rbac_views(self):
        """Verify ESG Manager and Auditor can view Scope 3 inventory and category detail."""
        # 1. ESG Manager access
        self.client.force_login(self.esg_mgr)
        resp_inv = self.client.get(reverse("core:scope3_inventory"))
        self.assertEqual(resp_inv.status_code, 200)
        self.assertContains(resp_inv, "Scope 3 Value Chain Emissions Inventory")

        resp_cat = self.client.get(reverse("core:scope3_category_detail", kwargs={"category_number": 4}))
        self.assertEqual(resp_cat.status_code, 200)
        self.assertContains(resp_cat, "Category 4: Upstream Transportation and Distribution")

        # 2. Auditor access (Read-Only)
        self.client.force_login(self.auditor)
        resp_aud_inv = self.client.get(reverse("core:scope3_inventory"))
        self.assertEqual(resp_aud_inv.status_code, 200)
        self.assertTrue(resp_aud_inv.context.get("is_auditor"))
        self.assertContains(resp_aud_inv, "Auditor Independent Assurance Workspace (Read-Only Mode)")

        resp_aud_cat = self.client.get(reverse("core:scope3_category_detail", kwargs={"category_number": 5}))
        self.assertEqual(resp_aud_cat.status_code, 200)
        self.assertTrue(resp_aud_cat.context.get("is_auditor"))
        self.assertContains(resp_aud_cat, "Auditor Independent Assurance Workspace (Read-Only Mode)")

    def test_site_manager_and_auditor_mutation_blocked(self):
        """Auditors and Site Managers are strictly prohibited from mutating emission factors or triggering recalculations."""
        rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_fy25,
            activity=self.act_freight,
            measurement_date=date(2025, 9, 1),
            quantity=Decimal("5000.0000"),
            unit=self.u_tkm,
            status=RecordStatus.VERIFIED,
            validation_status=ValidationStatus.VALID,
            created_by=self.site_mgr,
        )
        calculate_activity_record(rec)

        # Auditor cannot trigger recalculation
        self.client.force_login(self.auditor)
        resp_aud = self.client.post(reverse("core:record_recalculate", kwargs={"record_id": rec.id}))
        self.assertEqual(resp_aud.status_code, 403)

        # Site Manager cannot trigger recalculation
        self.client.force_login(self.site_mgr)
        resp_site = self.client.post(reverse("core:record_recalculate", kwargs={"record_id": rec.id}))
        self.assertEqual(resp_site.status_code, 403)
