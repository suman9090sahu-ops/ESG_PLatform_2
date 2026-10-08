"""
Unit Normalization and Conversion Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 24 Requirements:
- Centralized, deterministic unit validation and conversion engine
- Standard physical dimension preservation (VOLUME, ENERGY, MASS, DISTANCE)
- Strict prevention of cross-dimensional conversion (e.g. Volume to Mass without specific gravity)
- High-precision Decimal conversions ensuring exact reproducibility
- Comprehensive support for metric and imperial industrial telemetry
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple, Union

from apps.core.models import UnitDimension, UnitOfMeasure

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# EXCEPTIONS
# -----------------------------------------------------------------------------

class UnitConversionError(Exception):
    """Base exception for unit validation and normalization errors."""
    pass


class UnitDimensionMismatchError(UnitConversionError):
    """Raised when attempting to convert across incompatible physical dimensions."""
    pass


class UnsupportedUnitError(UnitConversionError):
    """Raised when an unmapped or invalid unit is supplied."""
    pass


# -----------------------------------------------------------------------------
# CANONICAL DIMENSION BASES & SCALE FACTORS
# -----------------------------------------------------------------------------
# Each supported unit specifies: (dimension, multiplier_to_canonical_base)
# Base Volume: Litre (L)
# Base Energy: Kilowatt Hour (kWh)
# Base Mass: Kilogram (kg)
# Base Distance: Kilometre (km)

UNIT_CONVERSION_SCALES: Dict[str, Tuple[str, Decimal]] = {
    # Volume (Canonical Base: Litre - L)
    "L": (UnitDimension.VOLUME, Decimal("1.0")),
    "LITRE": (UnitDimension.VOLUME, Decimal("1.0")),
    "LTR": (UnitDimension.VOLUME, Decimal("1.0")),
    "LTR-LIVE": (UnitDimension.VOLUME, Decimal("1.0")),
    "L-DEMO": (UnitDimension.VOLUME, Decimal("1.0")),
    "LITRES": (UnitDimension.VOLUME, Decimal("1.0")),
    "KL": (UnitDimension.VOLUME, Decimal("1000.0")),
    "KILOLITRE": (UnitDimension.VOLUME, Decimal("1000.0")),
    "KILOLITER": (UnitDimension.VOLUME, Decimal("1000.0")),
    "KL-LIVE": (UnitDimension.VOLUME, Decimal("1000.0")),
    "M3": (UnitDimension.VOLUME, Decimal("1000.0")),
    "M³": (UnitDimension.VOLUME, Decimal("1000.0")),
    "CUBIC METRE": (UnitDimension.VOLUME, Decimal("1000.0")),
    "GALLON": (UnitDimension.VOLUME, Decimal("3.785412")),

    # Energy (Canonical Base: Kilowatt Hour - kWh)
    "KWH": (UnitDimension.ENERGY, Decimal("1.0")),
    "KWH-P23": (UnitDimension.ENERGY, Decimal("1.0")),
    "KILOWATT HOUR": (UnitDimension.ENERGY, Decimal("1.0")),
    "MWH": (UnitDimension.ENERGY, Decimal("1000.0")),
    "MEGAWATT HOUR": (UnitDimension.ENERGY, Decimal("1000.0")),
    "GJ": (UnitDimension.ENERGY, Decimal("277.777778")),
    "MJ": (UnitDimension.ENERGY, Decimal("0.277778")),

    # Mass (Canonical Base: Kilogram - kg)
    "KG": (UnitDimension.MASS, Decimal("1.0")),
    "KILOGRAM": (UnitDimension.MASS, Decimal("1.0")),
    "TONNE": (UnitDimension.MASS, Decimal("1000.0")),
    "T": (UnitDimension.MASS, Decimal("1000.0")),
    "MT": (UnitDimension.MASS, Decimal("1000.0")),
    "METRIC TONNE": (UnitDimension.MASS, Decimal("1000.0")),
    "G": (UnitDimension.MASS, Decimal("0.001")),
    "GRAM": (UnitDimension.MASS, Decimal("0.001")),
    "LBS": (UnitDimension.MASS, Decimal("0.453592")),

    # Distance (Canonical Base: Kilometre - km)
    "KM": (UnitDimension.DISTANCE, Decimal("1.0")),
    "KILOMETRE": (UnitDimension.DISTANCE, Decimal("1.0")),
    "PASSENGER_KM": (UnitDimension.DISTANCE, Decimal("1.0")),
    "P-KM": (UnitDimension.DISTANCE, Decimal("1.0")),
    "PASSENGER-KILOMETRE": (UnitDimension.DISTANCE, Decimal("1.0")),
    "MILE": (UnitDimension.DISTANCE, Decimal("1.609344")),
}

CANONICAL_BASE_SYMBOLS: Dict[str, str] = {
    UnitDimension.VOLUME: "L",
    UnitDimension.ENERGY: "kWh",
    UnitDimension.MASS: "kg",
    UnitDimension.DISTANCE: "km",
}


def _clean_token(token: Optional[str]) -> str:
    if not token:
        return ""
    return str(token).strip().upper().replace("³", "3")


def get_unit_scale(unit: Union[UnitOfMeasure, str]) -> Tuple[str, Decimal]:
    """
    Resolves physical dimension and canonical scale multiplier for a UnitOfMeasure or unit string.
    Returns: (dimension, multiplier_to_base)
    """
    if isinstance(unit, UnitOfMeasure):
        code_token = _clean_token(unit.code)
        sym_token = _clean_token(unit.symbol)
        name_token = _clean_token(unit.name)

        # 1. Lookup by symbol, code, or name
        for token in [sym_token, code_token, name_token]:
            if token in UNIT_CONVERSION_SCALES:
                return UNIT_CONVERSION_SCALES[token]

        # 2. Fallback to model's declared dimension
        declared_dim = unit.dimension or UnitDimension.OTHER
        return (declared_dim, Decimal("1.0"))

    # String token lookup
    token = _clean_token(unit)
    if token in UNIT_CONVERSION_SCALES:
        return UNIT_CONVERSION_SCALES[token]

    raise UnsupportedUnitError(f"Unsupported or unrecognized measurement unit: '{unit}'")


def convert_quantity(
    quantity: Union[Decimal, float, int, str],
    from_unit: UnitOfMeasure,
    to_unit: UnitOfMeasure,
) -> Tuple[Decimal, Decimal]:
    """
    Converts a telemetry quantity from from_unit to to_unit.
    
    Returns:
        (converted_quantity, conversion_factor)
        
    Raises:
        UnitDimensionMismatchError: If units belong to different physical dimensions.
        UnitConversionError: If quantity is invalid or units cannot be evaluated.
    """
    if quantity is None:
        raise UnitConversionError("Quantity cannot be None.")

    try:
        qty = Decimal(str(quantity))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise UnitConversionError(f"Invalid numeric quantity: {quantity}") from exc

    if not from_unit or not to_unit:
        raise UnitConversionError("Both from_unit and to_unit must be provided.")

    # Identity check
    if getattr(from_unit, "pk", None) and getattr(to_unit, "pk", None) and from_unit.pk == to_unit.pk:
        return qty, Decimal("1.000000")

    from_sym = _clean_token(getattr(from_unit, "symbol", from_unit))
    to_sym = _clean_token(getattr(to_unit, "symbol", to_unit))
    from_code = _clean_token(getattr(from_unit, "code", from_unit))
    to_code = _clean_token(getattr(to_unit, "code", to_unit))

    if from_sym == to_sym and from_sym:
        return qty, Decimal("1.000000")
    if from_code == to_code and from_code:
        return qty, Decimal("1.000000")

    dim_from, scale_from = get_unit_scale(from_unit)
    dim_to, scale_to = get_unit_scale(to_unit)

    from_name = getattr(from_unit, "name", str(from_unit))
    to_name = getattr(to_unit, "name", str(to_unit))

    if dim_from != dim_to:
        raise UnitDimensionMismatchError(
            f"Incompatible unit conversion: Cannot convert '{from_name}' ({dim_from}) "
            f"to '{to_name}' ({dim_to}) across physical dimensions."
        )

    if scale_to == Decimal("0"):
        raise UnitConversionError(f"Target unit '{to_name}' has invalid zero conversion scale.")

    conv_factor = scale_from / scale_to
    converted = qty * conv_factor

    return converted, conv_factor


def normalize_to_dimension_base(
    quantity: Union[Decimal, float, int, str],
    unit: UnitOfMeasure,
) -> Tuple[Decimal, str, Decimal]:
    """
    Normalizes a quantity to the canonical base of its physical dimension.
    (e.g., kL -> L, MWh -> kWh, Tonne -> kg).
    
    Returns:
        (normalized_quantity, canonical_symbol, multiplier)
    """
    dim, scale = get_unit_scale(unit)
    canonical_symbol = CANONICAL_BASE_SYMBOLS.get(dim, unit.symbol)

    try:
        qty = Decimal(str(quantity))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise UnitConversionError(f"Invalid numeric quantity: {quantity}") from exc

    normalized = qty * scale
    return normalized, canonical_symbol, scale


def validate_unit_compatibility(
    unit: Optional[UnitOfMeasure],
    required_dimension_or_unit: Any,
) -> Tuple[bool, str]:
    """
    Validates whether an operational unit is compatible with a required dimension or target unit.
    Returns: (is_valid: bool, explanation: str)
    """
    if not unit:
        return False, "Operational unit of measure is missing."

    dim, _ = get_unit_scale(unit)

    if isinstance(required_dimension_or_unit, UnitOfMeasure):
        req_dim, _ = get_unit_scale(required_dimension_or_unit)
        if dim != req_dim:
            return (
                False,
                f"Entered unit '{unit.symbol}' ({dim}) is incompatible with target unit "
                f"'{required_dimension_or_unit.symbol}' ({req_dim}).",
            )
        return True, "Units are physically compatible."

    if isinstance(required_dimension_or_unit, str):
        req_token = required_dimension_or_unit.upper()
        if req_token in UnitDimension.values:
            if dim != req_token:
                return (
                    False,
                    f"Entered unit '{unit.symbol}' ({dim}) does not match expected dimension '{req_token}'.",
                )
            return True, "Dimension matches."

    return True, "Unit is valid."


class UnitConversionService:
    """Centralized facade service for physical unit validation and normalization."""

    @staticmethod
    def convert(
        quantity: Union[Decimal, float, int, str],
        from_unit: Any,
        to_unit: Any,
    ) -> Tuple[Decimal, Decimal]:
        return convert_quantity(quantity, from_unit, to_unit)

    @staticmethod
    def normalize_to_dimension_base(
        quantity: Union[Decimal, float, int, str],
        unit: Any,
    ) -> Tuple[Decimal, str, Decimal]:
        return normalize_to_dimension_base(quantity, unit)

    @staticmethod
    def get_scale(unit: Any) -> Tuple[str, Decimal]:
        return get_unit_scale(unit)

    @staticmethod
    def validate_compatibility(
        unit: Optional[UnitOfMeasure],
        required_dimension_or_unit: Any,
    ) -> Tuple[bool, str]:
        return validate_unit_compatibility(unit, required_dimension_or_unit)
