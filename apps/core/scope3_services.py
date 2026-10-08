"""
Scope 3 Value Chain Emissions Engine for MEIL ESG CONTROL TOWER.

Fulfills Phase 23 Requirements:
- Complete GHG Protocol Corporate Value Chain (Scope 3) 15-category architecture:
    Upstream (Categories 1 - 8):
      1. Purchased Goods and Services
      2. Capital Goods
      3. Fuel- and Energy-Related Activities
      4. Upstream Transportation and Distribution
      5. Waste Generated in Operations
      6. Business Travel
      7. Employee Commuting
      8. Upstream Leased Assets
    Downstream (Categories 9 - 15):
      9. Downstream Transportation and Distribution
      10. Processing of Sold Products
      11. Use of Sold Products
      12. End-of-Life Treatment of Sold Products
      13. Downstream Leased Assets
      14. Franchises
      15. Investments
- Deterministic automatic scope classification from activity taxonomy and rules
- Scope 3 category binding on ActivityMaster, EmissionFactor, and CalculationResult
- Explicit configuration & data-required states (zero fabricated data)
- Full consolidation and 6-tier traceability integration
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.db import models
from django.utils import timezone

from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    CalculationResult,
    CalculationStatus,
    EmissionFactor,
    EmissionFactorStatus,
    PeriodStatus,
    RecordStatus,
    ReportingPeriod,
    Scope3CalculationMethod,
    Scope3Category,
    Scope3Direction,
    ScopeClassification,
    Site,
    Subsidiary,
)
from apps.core.period_services import get_accessible_reporting_periods
from apps.core.scope_services import (
    get_accessible_sites,
    get_accessible_subsidiaries,
)

logger = logging.getLogger("apps.core")

# -----------------------------------------------------------------------------
# 1. AUTHORITATIVE 15 GHG PROTOCOL SCOPE 3 CATEGORIES
# -----------------------------------------------------------------------------

SCOPE_3_CATEGORIES_DATA: List[Dict[str, Any]] = [
    {
        "category_number": 1,
        "code": "SCOPE3_CAT_01",
        "name": "Purchased Goods and Services",
        "direction": Scope3Direction.UPSTREAM,
        "description": (
            "Extraction, production, and transportation of goods and services purchased "
            "or acquired by the reporting company in the reporting year, not otherwise "
            "included in Categories 2 - 8 (e.g. structural steel, cement, lubricants, "
            "consulting services, civil subcontracting)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.SUPPLIER_SPECIFIC,
            Scope3CalculationMethod.HYBRID,
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.SPEND_BASED,
        ],
    },
    {
        "category_number": 2,
        "code": "SCOPE3_CAT_02",
        "name": "Capital Goods",
        "direction": Scope3Direction.UPSTREAM,
        "description": (
            "Extraction, production, and transportation of capital goods purchased "
            "or acquired by the reporting company in the reporting year (e.g. heavy cranes, "
            "batching plants, transformers, fleet vehicles, industrial machinery)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.SUPPLIER_SPECIFIC,
            Scope3CalculationMethod.HYBRID,
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.SPEND_BASED,
        ],
    },
    {
        "category_number": 3,
        "code": "SCOPE3_CAT_03",
        "name": "Fuel- and Energy-Related Activities",
        "direction": Scope3Direction.UPSTREAM,
        "description": (
            "Extraction, production, and transportation of fuels and energy purchased or "
            "acquired by the reporting company in the reporting year, not already accounted "
            "for in Scope 1 or Scope 2 (e.g. Well-to-Tank / WTT upstream fuel extraction "
            "and Transmission & Distribution electricity grid losses)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.SUPPLIER_SPECIFIC,
        ],
    },
    {
        "category_number": 4,
        "code": "SCOPE3_CAT_04",
        "name": "Upstream Transportation and Distribution",
        "direction": Scope3Direction.UPSTREAM,
        "description": (
            "Transportation and distribution of products purchased by the reporting company "
            "in the reporting year between Tier 1 suppliers and its own operations in vehicles "
            "not owned or operated by the reporting company (e.g. commercial road freight, "
            "rail freight, marine shipments)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.DISTANCE_BASED,
            Scope3CalculationMethod.FUEL_BASED,
            Scope3CalculationMethod.SPEND_BASED,
        ],
    },
    {
        "category_number": 5,
        "code": "SCOPE3_CAT_05",
        "name": "Waste Generated in Operations",
        "direction": Scope3Direction.UPSTREAM,
        "description": (
            "Disposal and treatment of waste generated in the reporting company's operations "
            "in the reporting year in facilities not owned or controlled by the reporting company "
            "(e.g. hazardous industrial chemical waste incineration, municipal landfill, "
            "recycled construction scrap)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.WASTE_TYPE_SPECIFIC,
            Scope3CalculationMethod.AVERAGE_DATA,
        ],
    },
    {
        "category_number": 6,
        "code": "SCOPE3_CAT_06",
        "name": "Business Travel",
        "direction": Scope3Direction.UPSTREAM,
        "description": (
            "Transportation of employees for business-related activities in the reporting year "
            "(in vehicles not owned or operated by the reporting company, e.g. commercial "
            "airline flights, passenger rail, hired taxis, hotel lodging)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.DISTANCE_BASED,
            Scope3CalculationMethod.SPEND_BASED,
            Scope3CalculationMethod.FUEL_BASED,
        ],
    },
    {
        "category_number": 7,
        "code": "SCOPE3_CAT_07",
        "name": "Employee Commuting",
        "direction": Scope3Direction.UPSTREAM,
        "description": (
            "Transportation of employees between their homes and their worksites in the "
            "reporting year (in vehicles not owned or operated by the reporting company, "
            "e.g. public buses, personal two-wheelers, passenger trains, carpools)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.DISTANCE_BASED,
        ],
    },
    {
        "category_number": 8,
        "code": "SCOPE3_CAT_08",
        "name": "Upstream Leased Assets",
        "direction": Scope3Direction.UPSTREAM,
        "description": (
            "Operation of assets leased by the reporting company (lessee) in the reporting year "
            "and not included in Scope 1 and Scope 2 (e.g. leased regional corporate offices, "
            "leased warehouses, off-site rented equipment)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.SPEND_BASED,
        ],
    },
    {
        "category_number": 9,
        "code": "SCOPE3_CAT_09",
        "name": "Downstream Transportation and Distribution",
        "direction": Scope3Direction.DOWNSTREAM,
        "description": (
            "Transportation and distribution of products sold by the reporting company in the "
            "reporting year between the reporting company's operations and the end consumer "
            "(if not paid for by the reporting company)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.DISTANCE_BASED,
            Scope3CalculationMethod.FUEL_BASED,
            Scope3CalculationMethod.SPEND_BASED,
        ],
    },
    {
        "category_number": 10,
        "code": "SCOPE3_CAT_10",
        "name": "Processing of Sold Products",
        "direction": Scope3Direction.DOWNSTREAM,
        "description": (
            "Processing of intermediate products sold in the reporting year by downstream "
            "manufacturers (e.g. secondary refinement or fabrication of semi-finished components)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.SUPPLIER_SPECIFIC,
        ],
    },
    {
        "category_number": 11,
        "code": "SCOPE3_CAT_11",
        "name": "Use of Sold Products",
        "direction": Scope3Direction.DOWNSTREAM,
        "description": (
            "End use of goods and services sold by the reporting company in the reporting year "
            "(direct use-phase emissions such as fuel consumption of manufactured gensets, "
            "or indirect use-phase emissions of electrical appliances)."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.HYBRID,
        ],
    },
    {
        "category_number": 12,
        "code": "SCOPE3_CAT_12",
        "name": "End-of-Life Treatment of Sold Products",
        "direction": Scope3Direction.DOWNSTREAM,
        "description": (
            "Waste disposal and treatment of products sold by the reporting company at the "
            "end of their life cycle."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.WASTE_TYPE_SPECIFIC,
            Scope3CalculationMethod.AVERAGE_DATA,
        ],
    },
    {
        "category_number": 13,
        "code": "SCOPE3_CAT_13",
        "name": "Downstream Leased Assets",
        "direction": Scope3Direction.DOWNSTREAM,
        "description": (
            "Operation of assets owned by the reporting company (lessor) and leased to "
            "other entities in the reporting year."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.SPEND_BASED,
        ],
    },
    {
        "category_number": 14,
        "code": "SCOPE3_CAT_14",
        "name": "Franchises",
        "direction": Scope3Direction.DOWNSTREAM,
        "description": (
            "Operation of franchises in the reporting year, not included in Scope 1 and Scope 2."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.SUPPLIER_SPECIFIC,
        ],
    },
    {
        "category_number": 15,
        "code": "SCOPE3_CAT_15",
        "name": "Investments",
        "direction": Scope3Direction.DOWNSTREAM,
        "description": (
            "Operation of investments (including project finance, equity investments, and debt "
            "investments) in the reporting year, per GHG Protocol Scope 3 Category 15 and "
            "PCAF Financed Emissions standards."
        ),
        "applicable_methods": [
            Scope3CalculationMethod.SPEND_BASED,
            Scope3CalculationMethod.AVERAGE_DATA,
            Scope3CalculationMethod.SUPPLIER_SPECIFIC,
        ],
    },
]


def seed_scope3_categories() -> Dict[int, Scope3Category]:
    """
    Ensures all 15 official GHG Protocol Scope 3 categories exist in the database.
    Also binds existing Scope 3 ActivityMaster catalog items to their authoritative category.
    Returns a dictionary mapping category_number -> Scope3Category instance.
    """
    category_map: Dict[int, Scope3Category] = {}
    for data in SCOPE_3_CATEGORIES_DATA:
        methods_list = [m.value if hasattr(m, "value") else str(m) for m in data["applicable_methods"]]
        cat, created = Scope3Category.objects.get_or_create(
            category_number=data["category_number"],
            defaults={
                "code": data["code"],
                "name": data["name"],
                "direction": data["direction"],
                "description": data["description"],
                "applicable_methods": methods_list,
                "is_active": True,
            },
        )
        if not created:
            # Update fields to match current definitions if needed
            cat.code = data["code"]
            cat.name = data["name"]
            cat.direction = data["direction"]
            cat.description = data["description"]
            cat.applicable_methods = methods_list
            cat.save()
        category_map[data["category_number"]] = cat

    # Automatically link existing standard Scope 3 activities to categories
    cat_4 = category_map.get(4)
    cat_5 = category_map.get(5)
    cat_6 = category_map.get(6)
    cat_1 = category_map.get(1)

    # 1. Transport -> Category 4
    if cat_4:
        ActivityMaster.objects.filter(
            models.Q(code="TRANSPORT-COMMERCIAL-FREIGHT") | models.Q(category__code="TRANSPORT")
        ).update(
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=cat_4,
            calculation_method=Scope3CalculationMethod.DISTANCE_BASED,
        )

    # 2. Waste -> Category 5
    if cat_5:
        ActivityMaster.objects.filter(
            models.Q(code__in=["WASTE-HAZARDOUS", "WASTE-NON-HAZARDOUS"]) | models.Q(category__code="WASTE")
        ).update(
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=cat_5,
            calculation_method=Scope3CalculationMethod.WASTE_TYPE_SPECIFIC,
        )

    # 3. Business Travel -> Category 6
    if cat_6:
        ActivityMaster.objects.filter(
            models.Q(code="TRAVEL-AIR-DOMESTIC") | models.Q(category__code="TRAVEL")
        ).update(
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=cat_6,
            calculation_method=Scope3CalculationMethod.DISTANCE_BASED,
        )

    # 4. Purchased materials / goods -> Category 1
    if cat_1:
        ActivityMaster.objects.filter(
            code__in=["PURCHASED-GOODS-STEEL", "PURCHASED-GOODS-CEMENT", "PURCHASED-GOODS"]
        ).update(
            scope_classification=ScopeClassification.SCOPE_3,
            scope3_category=cat_1,
            calculation_method=Scope3CalculationMethod.AVERAGE_DATA,
        )

    return category_map


# -----------------------------------------------------------------------------
# 2. DETERMINISTIC AUTOMATIC SCOPE CLASSIFICATION SERVICE
# -----------------------------------------------------------------------------

def classify_activity_scope(
    category_code: str = "",
    activity_code: str = "",
    activity_name: str = "",
    is_company_owned: bool = True,
) -> Dict[str, Any]:
    """
    Determines Scope (Scope 1, Scope 2, Scope 3, Non-GHG) and Scope 3 Category
    from activity taxonomy, equipment ownership, and regulatory boundary rules.
    
    Prevents Site Managers from having to manually guess Scope.
    
    Rules:
    - Company-owned diesel/petrol combustion -> Scope 1
    - Purchased grid electricity / captive renewable -> Scope 2
    - Water withdrawal / physical resources -> Non-GHG
    - Purchased goods & raw materials -> Scope 3 (Cat 1)
    - Capital equipment & machinery -> Scope 3 (Cat 2)
    - Upstream freight transport -> Scope 3 (Cat 4)
    - Waste generated in operations -> Scope 3 (Cat 5)
    - Business travel -> Scope 3 (Cat 6)
    - Employee commuting -> Scope 3 (Cat 7)
    - Downstream distribution -> Scope 3 (Cat 9)
    - Investments -> Scope 3 (Cat 15)
    """
    cat_upper = (category_code or "").strip().upper()
    act_code_upper = (activity_code or "").strip().upper()
    act_name_upper = (activity_name or "").strip().upper()

    # Rule 1: Water Resources -> Non-GHG physical resource
    if cat_upper == "WATER" or act_code_upper.startswith("WATER-"):
        return {
            "scope": ScopeClassification.NON_GHG,
            "scope3_category_number": None,
            "calculation_method": Scope3CalculationMethod.NOT_APPLICABLE,
            "reason": "Water resource extraction & consumption (SEBI BRSR P6 physical volumetric ledger)",
        }

    # Rule 2: Purchased / Grid Electricity -> Scope 2
    if (
        cat_upper in ["ENERGY", "ELEC-P23", "POWER"]
        or act_code_upper.startswith("ELEC-")
        or "GRID" in act_code_upper
        or "SOLAR" in act_code_upper
    ):
        return {
            "scope": ScopeClassification.SCOPE_2,
            "scope3_category_number": None,
            "calculation_method": Scope3CalculationMethod.NOT_APPLICABLE,
            "reason": "Indirect emissions from purchased electricity / captive renewable generation (Scope 2)",
        }

    # Rule 3: Company-owned Fuel Combustion -> Scope 1
    if (
        cat_upper in ["FUEL", "DEMO-FUEL", "CAT-FUEL-LIVE", "LIVE-ENERGY"]
        or act_code_upper.startswith("FUEL-")
        or "GENSET" in act_code_upper
        or "DIESEL-STAT" in act_code_upper
        or "PETROL-MOB" in act_code_upper
    ):
        return {
            "scope": ScopeClassification.SCOPE_1,
            "scope3_category_number": None,
            "calculation_method": Scope3CalculationMethod.NOT_APPLICABLE,
            "reason": "Direct emissions from company-owned stationary or mobile fuel combustion (Scope 1)",
        }

    # Rule 4: Waste Management -> Scope 3 Category 5
    if cat_upper == "WASTE" or act_code_upper.startswith("WASTE-") or "WASTE" in act_name_upper:
        return {
            "scope": ScopeClassification.SCOPE_3,
            "scope3_category_number": 5,
            "calculation_method": Scope3CalculationMethod.WASTE_TYPE_SPECIFIC,
            "reason": "Scope 3 Category 5: Waste Generated in Operations",
        }

    # Rule 5: Transport & Logistics -> Scope 3 Category 4 (Upstream) or Category 9 (Downstream)
    if cat_upper in ["TRANSPORT", "LOGISTICS"] or "TRANSPORT" in act_code_upper or "FREIGHT" in act_code_upper:
        if "DOWNSTREAM" in act_code_upper or "DOWNSTREAM" in act_name_upper:
            return {
                "scope": ScopeClassification.SCOPE_3,
                "scope3_category_number": 9,
                "calculation_method": Scope3CalculationMethod.DISTANCE_BASED,
                "reason": "Scope 3 Category 9: Downstream Transportation and Distribution",
            }
        return {
            "scope": ScopeClassification.SCOPE_3,
            "scope3_category_number": 4,
            "calculation_method": Scope3CalculationMethod.DISTANCE_BASED,
            "reason": "Scope 3 Category 4: Upstream Transportation and Distribution",
        }

    # Rule 6: Business Travel -> Scope 3 Category 6
    if cat_upper == "TRAVEL" or act_code_upper.startswith("TRAVEL-") or "TRAVEL" in act_name_upper:
        return {
            "scope": ScopeClassification.SCOPE_3,
            "scope3_category_number": 6,
            "calculation_method": Scope3CalculationMethod.DISTANCE_BASED,
            "reason": "Scope 3 Category 6: Business Travel",
        }

    # Rule 7: Employee Commuting -> Scope 3 Category 7
    if "COMMUT" in act_code_upper or "COMMUT" in act_name_upper:
        return {
            "scope": ScopeClassification.SCOPE_3,
            "scope3_category_number": 7,
            "calculation_method": Scope3CalculationMethod.AVERAGE_DATA,
            "reason": "Scope 3 Category 7: Employee Commuting",
        }

    # Rule 8: Capital Goods / Machinery -> Scope 3 Category 2
    if "CAPITAL" in act_code_upper or "EQUIPMENT" in act_code_upper or "MACHINERY" in act_name_upper:
        return {
            "scope": ScopeClassification.SCOPE_3,
            "scope3_category_number": 2,
            "calculation_method": Scope3CalculationMethod.SPEND_BASED,
            "reason": "Scope 3 Category 2: Capital Goods",
        }

    # Rule 9: Purchased Goods / Raw Materials / Steel / Cement -> Scope 3 Category 1
    if (
        cat_upper in ["LIVE-CAT-MAT", "MATERIAL", "PROCUREMENT", "RAW_MATERIAL"]
        or "STEEL" in act_code_upper
        or "CEMENT" in act_code_upper
        or "PURCHASED" in act_code_upper
    ):
        return {
            "scope": ScopeClassification.SCOPE_3,
            "scope3_category_number": 1,
            "calculation_method": Scope3CalculationMethod.AVERAGE_DATA,
            "reason": "Scope 3 Category 1: Purchased Goods and Services",
        }

    # Rule 10: Investments -> Scope 3 Category 15
    if "INVEST" in act_code_upper or "INVEST" in act_name_upper or "FINANCE" in act_name_upper:
        return {
            "scope": ScopeClassification.SCOPE_3,
            "scope3_category_number": 15,
            "calculation_method": Scope3CalculationMethod.SPEND_BASED,
            "reason": "Scope 3 Category 15: Investments",
        }

    # Fallback default: Scope 1
    return {
        "scope": ScopeClassification.SCOPE_1,
        "scope3_category_number": None,
        "calculation_method": Scope3CalculationMethod.NOT_APPLICABLE,
        "reason": "Default operational direct activity classification (Scope 1)",
    }


# -----------------------------------------------------------------------------
# 3. SCOPE 3 INVENTORY & CONSOLIDATION SUMMARY SERVICE
# -----------------------------------------------------------------------------

def get_scope3_inventory_summary(
    user,
    period_id: Optional[int] = None,
    subsidiary_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Computes corporate Scope 3 GHG inventory breakdown across all 15 official categories.
    
    Guarantees:
    - Clear distinction between Upstream (Categories 1 - 8) and Downstream (Categories 9 - 15)
    - Exact reconciliation with live CalculationResult ledger and verified ActivityRecords
    - Zero fabricated numbers: categories without source data explicitly expose 'DATA_REQUIRED'
    - Categories with activity data but missing emission factors expose 'REQUIRES_CONFIGURATION'
    - Full multi-tenant and role-based queryset scoping
    """
    # Ensure categories are seeded in the database
    categories_qs = Scope3Category.objects.all().order_by("category_number")
    if categories_qs.count() < 15:
        seed_scope3_categories()
        categories_qs = Scope3Category.objects.all().order_by("category_number")

    # 1. Resolve Accessible Temporal Boundary
    accessible_periods = get_accessible_reporting_periods(user).order_by("-start_date")
    current_period = None
    if period_id:
        current_period = accessible_periods.filter(pk=period_id).first()
    if not current_period:
        today = timezone.localdate()
        current_period = (
            accessible_periods.filter(code="FY2025-26").first()
            or accessible_periods.filter(start_date__lte=today, end_date__gte=today, status=PeriodStatus.OPEN).first()
            or accessible_periods.filter(status=PeriodStatus.OPEN).order_by("start_date").first()
            or accessible_periods.first()
        )

    # 2. Resolve Accessible Subsidiaries & Sites
    accessible_subs = get_accessible_subsidiaries(user).select_related("company").order_by("name")
    if subsidiary_id:
        target_subs = accessible_subs.filter(pk=subsidiary_id)
    else:
        target_subs = accessible_subs

    accessible_sites = get_accessible_sites(user).filter(project__subsidiary__in=target_subs)

    # 3. Query Scoped Verified Activity Records for Scope 3
    records_qs = ActivityRecord.objects.filter(
        site__in=accessible_sites,
        activity__scope_classification=ScopeClassification.SCOPE_3,
        status__in=[RecordStatus.VERIFIED, RecordStatus.APPROVED],
    ).select_related(
        "site",
        "site__project",
        "site__project__subsidiary",
        "reporting_period",
        "activity",
        "activity__scope3_category",
        "unit",
    ).prefetch_related(
        "calculation_results",
    )

    if current_period:
        records_qs = records_qs.filter(reporting_period=current_period)

    # Map verified records by Scope 3 category number
    records_by_cat: Dict[int, List[ActivityRecord]] = {i: [] for i in range(1, 16)}
    for rec in records_qs:
        cat_num = None
        if rec.activity and rec.activity.scope3_category:
            cat_num = rec.activity.scope3_category.category_number
        elif rec.activity:
            # Fallback deduction based on classification service
            classification = classify_activity_scope(
                category_code=rec.activity.category.code if rec.activity.category else "",
                activity_code=rec.activity.code,
                activity_name=rec.activity.name,
            )
            cat_num = classification.get("scope3_category_number")

        if cat_num and 1 <= cat_num <= 15:
            records_by_cat[cat_num].append(rec)

    # 4. Aggregate Each Category
    total_upstream_tco2e = Decimal("0.0000")
    total_downstream_tco2e = Decimal("0.0000")
    active_categories_count = 0
    requires_config_count = 0
    data_required_count = 0

    all_categories_summary: List[Dict[str, Any]] = []
    upstream_summary: List[Dict[str, Any]] = []
    downstream_summary: List[Dict[str, Any]] = []

    for cat_obj in categories_qs:
        cat_num = cat_obj.category_number
        cat_records = records_by_cat.get(cat_num, [])

        cat_emissions = Decimal("0.0000")
        has_config_required = False
        has_calculated = False

        record_details: List[Dict[str, Any]] = []
        for rec in cat_records:
            latest_calc = rec.calculation_results.filter(is_latest=True).first()
            if not latest_calc:
                # Trigger on-the-fly calculate if missing
                from apps.core.calculation_services import calculate_activity_record
                latest_calc = calculate_activity_record(rec)

            calc_val = latest_calc.calculated_value if latest_calc else Decimal("0.0000")
            calc_status = latest_calc.status if latest_calc else CalculationStatus.NOT_CALCULATED

            if calc_status == CalculationStatus.CALCULATED:
                cat_emissions += calc_val
                has_calculated = True
            elif calc_status == CalculationStatus.REQUIRES_CONFIGURATION:
                has_config_required = True

            record_details.append({
                "record": rec,
                "id": rec.id,
                "activity_name": rec.activity.name,
                "activity_code": rec.activity.code,
                "site": rec.site,
                "measurement_date": rec.measurement_date,
                "quantity": rec.quantity,
                "unit": rec.unit.symbol if rec.unit else "",
                "calculated_tco2e": calc_val,
                "calculation_status": calc_status,
                "calculation_id": latest_calc.id if latest_calc else None,
                "methodology": latest_calc.formula_repr if latest_calc else "",
            })

        # Determine Category Status
        if has_calculated and cat_records:
            status_code = "DATA_RECORDED"
            status_display = "Data Recorded & Verified"
            status_badge = "badge-success"
            active_categories_count += 1
        elif has_config_required and cat_records:
            status_code = "REQUIRES_CONFIGURATION"
            status_display = "Requires Factor Configuration"
            status_badge = "badge-warning"
            requires_config_count += 1
        else:
            status_code = "DATA_REQUIRED"
            status_display = "Data Required (No Records)"
            status_badge = "badge-secondary"
            data_required_count += 1

        cat_emissions = round(cat_emissions, 4)

        if cat_obj.direction == Scope3Direction.UPSTREAM:
            total_upstream_tco2e += cat_emissions
        else:
            total_downstream_tco2e += cat_emissions

        # Activities registered for this category
        registered_activities = ActivityMaster.objects.filter(
            models.Q(scope3_category=cat_obj) | models.Q(scope_classification=ScopeClassification.SCOPE_3)
        ).filter(
            status="ACTIVE"
        )
        if cat_num == 4:
            registered_activities = registered_activities.filter(models.Q(scope3_category=cat_obj) | models.Q(category__code="TRANSPORT"))
        elif cat_num == 5:
            registered_activities = registered_activities.filter(models.Q(scope3_category=cat_obj) | models.Q(category__code="WASTE"))
        elif cat_num == 6:
            registered_activities = registered_activities.filter(models.Q(scope3_category=cat_obj) | models.Q(category__code="TRAVEL"))
        else:
            registered_activities = registered_activities.filter(scope3_category=cat_obj)

        category_item = {
            "category": cat_obj,
            "category_number": cat_num,
            "code": cat_obj.code,
            "name": cat_obj.name,
            "direction": cat_obj.direction,
            "direction_display": cat_obj.get_direction_display(),
            "direction_badge": cat_obj.direction_badge_class,
            "description": cat_obj.description,
            "applicable_methods": cat_obj.applicable_methods or [],
            "status": status_code,
            "status_display": status_display,
            "status_badge": status_badge,
            "emissions_tco2e": cat_emissions,
            "record_count": len(cat_records),
            "records": record_details,
            "activities_count": registered_activities.count(),
            "activities": list(registered_activities[:5]),
        }

        all_categories_summary.append(category_item)
        if cat_obj.direction == Scope3Direction.UPSTREAM:
            upstream_summary.append(category_item)
        else:
            downstream_summary.append(category_item)

    total_scope3_tco2e = round(total_upstream_tco2e + total_downstream_tco2e, 4)

    # Compute percentage share for each category
    for item in all_categories_summary:
        if total_scope3_tco2e > Decimal("0.0000"):
            item["pct_of_scope3"] = round((item["emissions_tco2e"] / total_scope3_tco2e) * Decimal("100.0"), 1)
        else:
            item["pct_of_scope3"] = Decimal("0.0")

    return {
        "current_period": current_period,
        "accessible_periods": accessible_periods,
        "accessible_subsidiaries": accessible_subs,
        "selected_subsidiary_id": subsidiary_id,
        "total_scope3_tco2e": total_scope3_tco2e,
        "total_upstream_tco2e": round(total_upstream_tco2e, 4),
        "total_downstream_tco2e": round(total_downstream_tco2e, 4),
        "active_categories_count": active_categories_count,
        "requires_config_count": requires_config_count,
        "data_required_count": data_required_count,
        "categories_count": 15,
        "all_categories": all_categories_summary,
        "upstream_categories": upstream_summary,
        "downstream_categories": downstream_summary,
    }


def get_scope3_category_detail(
    user,
    category_number: int,
    period_id: Optional[int] = None,
    subsidiary_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Returns granular audit-ready details for a single Scope 3 Category (1 to 15).
    Includes category metadata, registered activities, configured factors, and verified records.
    """
    category = Scope3Category.objects.filter(category_number=category_number).first()
    if not category:
        seed_scope3_categories()
        category = Scope3Category.objects.filter(category_number=category_number).first()

    summary = get_scope3_inventory_summary(user, period_id=period_id, subsidiary_id=subsidiary_id)
    cat_item = next((c for c in summary["all_categories"] if c["category_number"] == category_number), None)

    # Configured Emission Factors for this category
    factors_qs = EmissionFactor.objects.filter(
        models.Q(scope3_category=category)
        | models.Q(scope=ScopeClassification.SCOPE_3, activity__scope3_category=category)
    ).select_related("activity", "input_unit")

    # Registered Activities
    activities_qs = ActivityMaster.objects.filter(
        models.Q(scope3_category=category)
        | models.Q(scope_classification=ScopeClassification.SCOPE_3)
    ).select_related("category", "base_unit")
    if category_number == 4:
        activities_qs = activities_qs.filter(models.Q(scope3_category=category) | models.Q(category__code="TRANSPORT"))
    elif category_number == 5:
        activities_qs = activities_qs.filter(models.Q(scope3_category=category) | models.Q(category__code="WASTE"))
    elif category_number == 6:
        activities_qs = activities_qs.filter(models.Q(scope3_category=category) | models.Q(category__code="TRAVEL"))
    else:
        activities_qs = activities_qs.filter(scope3_category=category)

    return {
        "category": category,
        "category_summary": cat_item,
        "current_period": summary["current_period"],
        "accessible_periods": summary["accessible_periods"],
        "accessible_subsidiaries": summary["accessible_subsidiaries"],
        "factors": factors_qs,
        "activities": activities_qs,
        "records": cat_item["records"] if cat_item else [],
    }
