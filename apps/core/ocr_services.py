"""
OCR & Document-Data Extraction Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 11 Requirements:
- Multi-provider abstraction (PyPDF text extractor, Tesseract image OCR, mock test provider).
- Pure-Python native extraction for text PDFs with page boundaries & character density confidence.
- Graceful error handling for missing Tesseract engine binaries without faking results.
- Versioned OCRRun executions preserving complete audit lineage per Evidence document.
- Extensible structured field extraction for ESG utility bills, fuel invoices, and challans.
- Raw vs. normalized value distinction.
- Deterministic comparison between extracted OCR fields and parent ActivityRecord telemetry.
- Zero-auto-correction principle: OCR output remains unverified operational telemetry.
- Strict object-level RBAC authorization & Insecure Direct Object Reference (IDOR) defense.
- Seamless audit logging integrated into AuthAuditLog.
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.auth_services import log_auth_event
from apps.core.evidence_services import user_can_access_evidence
from apps.core.models import (
    ActivityRecord,
    AuthAuditLog,
    Evidence,
    EvidenceStatus,
    OCRField,
    OCRRun,
    OCRStatus,
    Role,
    User,
)

logger = logging.getLogger("apps.core")

# Supported file extensions for document intelligence
SUPPORTED_OCR_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


class OCRError(Exception):
    """Base exception for OCR engine failures."""
    pass


class UnsupportedDocumentTypeError(OCRError):
    """Raised when an unsupported file type is submitted for OCR."""
    pass


class OCREngineUnavailableError(OCRError):
    """Raised when the required external engine binary (e.g. Tesseract) is missing."""
    pass


class DocumentReadError(OCRError):
    """Raised when a document cannot be opened or parsed."""
    pass


# -----------------------------------------------------------------------------
# 1. OCR PROVIDER ABSTRACTION & CONCRETE ENGINES
# -----------------------------------------------------------------------------

@dataclass
class OCRExtractionResult:
    """Standardized payload returned by any OCR / document extraction provider."""
    extracted_text: str
    page_count: int
    page_data: List[Dict[str, Any]] = field(default_factory=list)
    confidence: Optional[Decimal] = None
    engine: str = "pypdf-text-extractor"
    engine_version: str = "1.0.0"
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


class BaseOCRProvider:
    """Abstract base class for OCR and document text extraction providers."""

    name: str = "base-provider"
    version: str = "1.0.0"

    def can_process(self, file_extension: str) -> bool:
        raise NotImplementedError

    def extract(self, file_path: str, **kwargs) -> OCRExtractionResult:
        raise NotImplementedError


class PyPDFTextProvider(BaseOCRProvider):
    """
    Native PDF text extraction engine utilizing pypdf.
    Processes digital/text PDFs page-by-page, preserving page boundaries and
    computing deterministic confidence based on character extractability.
    """

    name = "pypdf-text-extractor"

    def __init__(self):
        try:
            import pypdf
            self.version = getattr(pypdf, "__version__", "5.0.0")
            self._available = True
        except ImportError:
            self.version = "unknown"
            self._available = False

    def can_process(self, file_extension: str) -> bool:
        return file_extension.lower() == ".pdf"

    def extract(self, file_path: str, **kwargs) -> OCRExtractionResult:
        if not self._available:
            raise OCREngineUnavailableError(
                "pypdf library is not installed in the application environment."
            )

        if not os.path.exists(file_path):
            raise DocumentReadError(f"Evidence file not found on disk: {file_path}")

        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            num_pages = len(reader.pages)
            if num_pages == 0:
                raise DocumentReadError("PDF document contains 0 pages.")

            full_text_parts = []
            page_data = []
            total_printable = 0
            total_chars = 0

            for page_idx, page in enumerate(reader.pages, start=1):
                try:
                    page_text = page.extract_text() or ""
                except Exception as pe:
                    logger.warning("Failed to extract text from page %s of %s: %s", page_idx, file_path, pe)
                    page_text = ""

                clean_page_text = page_text.strip()
                full_text_parts.append(clean_page_text)

                p_len = len(clean_page_text)
                p_printable = sum(1 for c in clean_page_text if c.isprintable() and not c.isspace())
                total_chars += p_len
                total_printable += p_printable

                p_conf = Decimal("95.00") if p_printable > 20 else (Decimal("50.00") if p_printable > 0 else Decimal("0.00"))
                page_data.append({
                    "page_number": page_idx,
                    "text": clean_page_text,
                    "character_count": p_len,
                    "confidence": float(p_conf),
                })

            aggregated_text = "\n\n--- Page Break ---\n\n".join(
                t for t in full_text_parts if t
            ).strip()

            if not aggregated_text or total_printable == 0:
                # Scanned or image-only PDF with no text layer
                tess_provider = TesseractOCRProvider()
                if tess_provider.is_available():
                    # Attempt Tesseract fallback
                    return tess_provider.extract(file_path, is_pdf=True, num_pages=num_pages)
                else:
                    raise OCRError(
                        "Scanned PDF contains no digital text layer. "
                        "Scanned image OCR requires Tesseract OCR engine, which is not available on this server."
                    )

            # Calculate confidence: for native digital text PDFs, confidence is high (95-99%)
            overall_confidence = Decimal("95.00") if total_printable > 50 else Decimal("75.00")

            return OCRExtractionResult(
                extracted_text=aggregated_text,
                page_count=num_pages,
                page_data=page_data,
                confidence=overall_confidence,
                engine=self.name,
                engine_version=self.version,
                raw_metadata={
                    "total_characters": total_chars,
                    "printable_characters": total_printable,
                    "is_digital_pdf": True,
                },
            )

        except OCRError:
            raise
        except Exception as exc:
            logger.exception("Error extracting text from PDF [%s]: %s", file_path, exc)
            raise DocumentReadError(f"Failed to read and parse PDF: {str(exc)}") from exc


class TesseractOCRProvider(BaseOCRProvider):
    """
    Image Optical Character Recognition provider utilizing Tesseract OCR.
    Handles scanned documents, invoices, JPG, and PNG images.
    Gracefully detects and reports missing engine binaries without crashing or fabricating results.
    """

    name = "tesseract-ocr"

    def __init__(self):
        self.cmd = getattr(settings, "OCR_TESSERACT_CMD", "")
        self.version = "unknown"
        self._check_availability()

    def _check_availability(self) -> bool:
        try:
            import pytesseract
            if self.cmd:
                pytesseract.pytesseract.tesseract_cmd = self.cmd
            # Check version
            self.version = str(pytesseract.get_tesseract_version())
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def is_available(self) -> bool:
        return self._check_availability()

    def can_process(self, file_extension: str) -> bool:
        return file_extension.lower() in [".jpg", ".jpeg", ".png", ".tiff", ".bmp"]

    def extract(self, file_path: str, is_pdf: bool = False, num_pages: int = 1, **kwargs) -> OCRExtractionResult:
        if not self._check_availability():
            raise OCREngineUnavailableError(
                "OCR engine binary (Tesseract) is not installed on this server host. "
                "Please install Tesseract-OCR and configure OCR_TESSERACT_CMD to enable scanned image text extraction."
            )

        if not os.path.exists(file_path):
            raise DocumentReadError(f"Image evidence file not found: {file_path}")

        try:
            import pytesseract
            from PIL import Image

            if is_pdf:
                raise OCRError(
                    "Direct PDF rasterization requires poppler / pdf2image utility which is not configured."
                )

            with Image.open(file_path) as img:
                # Extract text
                extracted_text = pytesseract.image_to_string(img, lang="eng").strip()

                # Extract confidence data
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                confidences = [
                    int(c) for c in data.get("conf", [])
                    if isinstance(c, (int, str)) and str(c).isdigit() and int(c) >= 0
                ]
                avg_conf = (
                    Decimal(str(round(sum(confidences) / len(confidences), 2)))
                    if confidences
                    else Decimal("50.00")
                )

                page_data = [{
                    "page_number": 1,
                    "text": extracted_text,
                    "confidence": float(avg_conf),
                }]

                return OCRExtractionResult(
                    extracted_text=extracted_text,
                    page_count=1,
                    page_data=page_data,
                    confidence=avg_conf,
                    engine=self.name,
                    engine_version=self.version,
                    raw_metadata={"words_detected": len(confidences)},
                )

        except (OCRError, OCREngineUnavailableError):
            raise
        except Exception as exc:
            logger.exception("Tesseract OCR extraction failed for [%s]: %s", file_path, exc)
            raise OCRError(f"Tesseract OCR processing failed: {str(exc)}") from exc


class MockOCRProvider(BaseOCRProvider):
    """
    Deterministic Mock OCR Provider for automated test suites and isolated testing.
    Produces deterministic text and entity fields without requiring disk files or external binaries.
    """

    name = "mock-ocr-engine"
    version = "1.0.0-test"

    def __init__(
        self,
        text: Optional[str] = None,
        confidence: Decimal = Decimal("94.50"),
        page_count: int = 1,
        should_fail: bool = False,
        error_message: str = "Simulated OCR Engine Failure",
    ):
        self.custom_text = text
        self.custom_confidence = confidence
        self.custom_page_count = page_count
        self.should_fail = should_fail
        self.error_message = error_message

    def can_process(self, file_extension: str) -> bool:
        return True

    def extract(self, file_path: str, **kwargs) -> OCRExtractionResult:
        if self.should_fail:
            raise OCRError(self.error_message)

        default_text = (
            "TAX INVOICE\n"
            "Supplier: Southern Power Distribution Company\n"
            "Consumer No: 04-982-38472\n"
            "Invoice No: INV-2026-98124\n"
            "Invoice Date: 15/04/2026\n"
            "Billing Period: 01/03/2026 to 31/03/2026\n"
            "Meter No: MTR-MEIL-901\n"
            "Units Consumed: 1,250.00 kWh\n"
            "Total Amount: INR 9,375.00\n"
        )
        text = self.custom_text if self.custom_text is not None else default_text
        return OCRExtractionResult(
            extracted_text=text,
            page_count=self.custom_page_count,
            page_data=[{"page_number": 1, "text": text, "confidence": float(self.custom_confidence)}],
            confidence=self.custom_confidence,
            engine=self.name,
            engine_version=self.version,
            raw_metadata={"mock": True},
        )


def get_ocr_provider(file_extension: str, provider_override: Optional[BaseOCRProvider] = None) -> BaseOCRProvider:
    """
    Factory function resolving the appropriate OCR provider for a given file format.
    """
    if provider_override is not None:
        return provider_override

    clean_ext = (file_extension or "").lower()
    if clean_ext == ".pdf":
        return PyPDFTextProvider()
    elif clean_ext in [".jpg", ".jpeg", ".png", ".tiff", ".bmp"]:
        return TesseractOCRProvider()
    else:
        raise UnsupportedDocumentTypeError(
            f"Unsupported document format '{clean_ext}' for OCR processing. "
            f"Supported formats are: {', '.join(sorted(SUPPORTED_OCR_EXTENSIONS))}."
        )


# -----------------------------------------------------------------------------
# 2. STRUCTURED ENTITY & FIELD EXTRACTION ENGINE
# -----------------------------------------------------------------------------

def extract_structured_fields(ocr_run: OCRRun, text: str) -> List[OCRField]:
    """
    Deterministic rule & pattern matching entity extractor.
    Extracts high-value ESG evidence fields (invoice number, billing period,
    quantity, unit, total amount, vendor, date) from extracted document text.

    Distinguishes raw matches from normalized machine-readable values.
    Saves instances directly to the database associated with ocr_run.
    """
    if not text:
        return []

    fields_created: List[OCRField] = []

    # 1. Invoice / Reference Number
    # Require explicit number indicator (No, #, Number, ID) or colon delimiter on same line
    inv_patterns = [
        r"(?:Invoice|Bill|Challan|Ref|Receipt)\s*(?:No|Number|#|ID|Code)[.:\s-]+\s*([A-Za-z0-9\-_/]{3,30})",
        r"(?:Inv\s*#)[.:\s-]*([A-Za-z0-9\-_/]{3,30})",
        r"(?:Invoice|Bill|Challan)[ \t]*[:][ \t]*([A-Za-z0-9\-_/]{3,30})",
    ]
    disallowed_inv_words = {"tax", "retail", "original", "duplicate", "commercial", "supplier", "vendor", "challan", "customer"}
    for pat in inv_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            raw_inv = match.group(1).strip()
            if raw_inv.lower() not in disallowed_inv_words:
                fields_created.append(
                    OCRField.objects.create(
                        ocr_run=ocr_run,
                        field_name="invoice_number",
                        raw_value=raw_inv,
                        normalized_value=raw_inv.upper(),
                        unit="",
                        confidence=Decimal("92.00"),
                        extraction_method="REGEX_PATTERN",
                    )
                )
                break

    # 2. Quantity & Unit
    # Check for number immediately followed by unit on the SAME line (using [ \t]* not \s*)
    qty_unit_pattern = (
        r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)[ \t]*"
        r"(kWh|kwh|liters|litres|kL|KL|MT|metric\s*tonnes|kg|gallons|cubic\s*meters|m3|GJ|MWh|units)"
    )
    qty_match = re.search(qty_unit_pattern, text, re.IGNORECASE)
    if qty_match:
        raw_qty = qty_match.group(1).strip()
        raw_unit = qty_match.group(2).strip()
        norm_qty = raw_qty.replace(",", "")
        fields_created.append(
            OCRField.objects.create(
                ocr_run=ocr_run,
                field_name="quantity",
                raw_value=f"{raw_qty} {raw_unit}",
                normalized_value=norm_qty,
                unit=raw_unit,
                confidence=Decimal("94.00"),
                extraction_method="REGEX_PATTERN",
            )
        )
    else:
        # Secondary fallback: "Units Consumed: 1250" or "Quantity: 1250"
        units_pattern = r"(?:Units\s*Consumed|Quantity|Net\s*Units|Consumption)[ \t]*[:.\-][ \t]*([0-9,]+(?:\.[0-9]+)?)"
        u_match = re.search(units_pattern, text, re.IGNORECASE)
        if u_match:
            raw_qty = u_match.group(1).strip()
            norm_qty = raw_qty.replace(",", "")
            fields_created.append(
                OCRField.objects.create(
                    ocr_run=ocr_run,
                    field_name="quantity",
                    raw_value=raw_qty,
                    normalized_value=norm_qty,
                    unit="",
                    confidence=Decimal("85.00"),
                    extraction_method="REGEX_PATTERN",
                )
            )

    # 3. Invoice / Measurement Date
    # Examples: 15/04/2026, 2026-04-15, 15-Apr-2026
    date_patterns = [
        r"(?:Invoice\s*Date|Bill\s*Date|Date)[:.\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"(?:Invoice\s*Date|Bill\s*Date|Date)[:.\s]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4})",
        r"(?:Invoice\s*Date|Bill\s*Date|Date)[:.\s]*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{4})",
    ]
    for pat in date_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            raw_date = match.group(1).strip()
            norm_date = _normalize_date_string(raw_date)
            fields_created.append(
                OCRField.objects.create(
                    ocr_run=ocr_run,
                    field_name="invoice_date",
                    raw_value=raw_date,
                    normalized_value=norm_date,
                    unit="",
                    confidence=Decimal("88.00"),
                    extraction_method="REGEX_PATTERN",
                )
            )
            break

    # 4. Billing Period
    period_pattern = r"(?:Billing\s*Period|Period)[:.\s]*([A-Za-z0-9\s/.,\-–to]+?(?=\n|$))"
    period_match = re.search(period_pattern, text, re.IGNORECASE)
    if period_match:
        raw_period = period_match.group(1).strip()
        if len(raw_period) >= 4 and len(raw_period) <= 60:
            fields_created.append(
                OCRField.objects.create(
                    ocr_run=ocr_run,
                    field_name="billing_period",
                    raw_value=raw_period,
                    normalized_value=raw_period,
                    unit="",
                    confidence=Decimal("82.00"),
                    extraction_method="REGEX_PATTERN",
                )
            )

    # 5. Total Financial Amount
    amount_pattern = r"(?:Total\s*(?:Amount|Due|Payable)?|Grand\s*Total)[:.\s]*(?:Rs\.?|INR|₹)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"
    amt_match = re.search(amount_pattern, text, re.IGNORECASE)
    if amt_match:
        raw_amt = amt_match.group(1).strip()
        norm_amt = raw_amt.replace(",", "")
        fields_created.append(
            OCRField.objects.create(
                ocr_run=ocr_run,
                field_name="total_amount",
                raw_value=raw_amt,
                normalized_value=norm_amt,
                unit="INR",
                confidence=Decimal("90.00"),
                extraction_method="REGEX_PATTERN",
            )
        )

    # 6. Supplier / Vendor Name
    vendor_pattern = r"(?:Supplier|Vendor|Billed\s*By|From)[:.\s]*([^\n\r]{3,80})"
    vendor_match = re.search(vendor_pattern, text, re.IGNORECASE)
    if vendor_match:
        raw_vendor = vendor_match.group(1).strip()
        fields_created.append(
            OCRField.objects.create(
                ocr_run=ocr_run,
                field_name="vendor_name",
                raw_value=raw_vendor,
                normalized_value=raw_vendor,
                unit="",
                confidence=Decimal("80.00"),
                extraction_method="REGEX_PATTERN",
            )
        )

    # 7. Meter / Consumer Number
    meter_pattern = r"(?:Consumer\s*No|Meter\s*(?:No|Number|ID)|CA\s*No)[:.\s]*([A-Za-z0-9\-_/]{4,30})"
    meter_match = re.search(meter_pattern, text, re.IGNORECASE)
    if meter_match:
        raw_meter = meter_match.group(1).strip()
        fields_created.append(
            OCRField.objects.create(
                ocr_run=ocr_run,
                field_name="meter_number",
                raw_value=raw_meter,
                normalized_value=raw_meter.upper(),
                unit="",
                confidence=Decimal("89.00"),
                extraction_method="REGEX_PATTERN",
            )
        )

    return fields_created


def _normalize_date_string(date_str: str) -> str:
    """Helper to convert common date formats into ISO YYYY-MM-DD."""
    clean = date_str.strip()
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
        return clean
    # DD/MM/YYYY or DD-MM-YYYY
    match_dmy = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", clean)
    if match_dmy:
        d, m, y = match_dmy.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return clean


# -----------------------------------------------------------------------------
# 3. OCR VS. ACTIVITY RECORD COMPARISON ENGINE
# -----------------------------------------------------------------------------

def compare_ocr_with_activity_record(ocr_run: OCRRun) -> Dict[str, Any]:
    """
    Compares extracted OCR entities against the parent Activity Record operational data.
    Provides automated telemetry for future validation, anomaly detection, and auditor review.

    Strictly complies with the Core Domain Principle:
    Does NOT overwrite or auto-correct the Activity Record operational data.
    """
    evidence = ocr_run.evidence
    record: ActivityRecord = evidence.activity_record

    fields_by_name = {f.field_name: f for f in ocr_run.fields.all()}

    comparison = {
        "evaluated": True,
        "activity_record_id": record.id,
        "evidence_id": evidence.id,
        "overall_status": "MATCH",
        "matches_count": 0,
        "mismatches_count": 0,
        "not_detected_count": 0,
        "items": {},
    }

    # 1. Compare Quantity
    qty_field = fields_by_name.get("quantity")
    if qty_field and qty_field.normalized_value:
        try:
            extracted_qty = float(qty_field.normalized_value)
            record_qty = float(record.quantity)
            delta = round(extracted_qty - record_qty, 3)
            delta_pct = round((delta / record_qty * 100), 2) if record_qty != 0 else 0.0

            if abs(delta) < 0.001:
                qty_status = "MATCH"
                comparison["matches_count"] += 1
            else:
                qty_status = "MISMATCH"
                comparison["mismatches_count"] += 1
                comparison["overall_status"] = "MISMATCH"

            comparison["items"]["quantity"] = {
                "label": "Operational Quantity",
                "status": qty_status,
                "record_value": record_qty,
                "extracted_value": extracted_qty,
                "unit": record.unit.symbol if record.unit else "",
                "delta": delta,
                "delta_pct": delta_pct,
            }
        except (ValueError, TypeError):
            comparison["items"]["quantity"] = {
                "label": "Operational Quantity",
                "status": "UNPARSEABLE",
                "record_value": float(record.quantity),
                "extracted_value": qty_field.raw_value,
            }
            comparison["not_detected_count"] += 1
    else:
        comparison["items"]["quantity"] = {
            "label": "Operational Quantity",
            "status": "NOT_DETECTED",
            "record_value": float(record.quantity),
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    # 2. Compare Unit
    if qty_field and qty_field.unit and record.unit:
        rec_unit = record.unit.symbol.strip().lower()
        ext_unit = qty_field.unit.strip().lower()

        # Simple unit symbol normalization mapping
        unit_equivalents = {
            "kwh": ["kwh", "units", "unit"],
            "l": ["l", "liter", "liters", "litres"],
            "kl": ["kl", "kiloliter", "kiloliters"],
            "mt": ["mt", "metric tonnes", "tonnes"],
        }
        is_unit_match = (
            rec_unit == ext_unit
            or ext_unit in unit_equivalents.get(rec_unit, [])
        )

        u_status = "MATCH" if is_unit_match else "MISMATCH"
        if is_unit_match:
            comparison["matches_count"] += 1
        else:
            comparison["mismatches_count"] += 1
            comparison["overall_status"] = "MISMATCH"

        comparison["items"]["unit"] = {
            "label": "Unit of Measure",
            "status": u_status,
            "record_value": record.unit.symbol,
            "extracted_value": qty_field.unit,
        }
    else:
        comparison["items"]["unit"] = {
            "label": "Unit of Measure",
            "status": "NOT_DETECTED",
            "record_value": record.unit.symbol if record.unit else "",
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    # 3. Compare Measurement Date
    date_field = fields_by_name.get("invoice_date")
    if date_field and date_field.normalized_value:
        rec_date_str = str(record.measurement_date)
        ext_date_str = date_field.normalized_value
        is_date_match = (rec_date_str == ext_date_str)

        d_status = "MATCH" if is_date_match else "MISMATCH"
        if is_date_match:
            comparison["matches_count"] += 1
        else:
            comparison["mismatches_count"] += 1

        comparison["items"]["date"] = {
            "label": "Measurement Date",
            "status": d_status,
            "record_value": rec_date_str,
            "extracted_value": ext_date_str,
        }
    else:
        comparison["items"]["date"] = {
            "label": "Measurement Date",
            "status": "NOT_DETECTED",
            "record_value": str(record.measurement_date),
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    # 4. Compare Invoice Reference Number
    inv_field = fields_by_name.get("invoice_number")
    record_ref = (record.evidence_reference or "").strip()
    if inv_field and record_ref:
        rec_clean = record_ref.upper()
        ext_clean = inv_field.normalized_value.upper()
        is_ref_match = (rec_clean in ext_clean or ext_clean in rec_clean)

        r_status = "MATCH" if is_ref_match else "MISMATCH"
        if is_ref_match:
            comparison["matches_count"] += 1
        else:
            comparison["mismatches_count"] += 1

        comparison["items"]["reference"] = {
            "label": "Document Reference",
            "status": r_status,
            "record_value": record_ref,
            "extracted_value": inv_field.raw_value,
        }
    elif inv_field:
        comparison["items"]["reference"] = {
            "label": "Document Reference",
            "status": "RECORD_UNSPECIFIED",
            "record_value": None,
            "extracted_value": inv_field.raw_value,
        }
        comparison["not_detected_count"] += 1
    else:
        comparison["items"]["reference"] = {
            "label": "Document Reference",
            "status": "NOT_DETECTED",
            "record_value": record_ref or None,
            "extracted_value": None,
        }
        comparison["not_detected_count"] += 1

    return comparison


# -----------------------------------------------------------------------------
# 4. RBAC & OBJECT-LEVEL AUTHORIZATION GUARDS
# -----------------------------------------------------------------------------

def user_can_view_ocr(user: User, evidence: Evidence) -> bool:
    """
    Evaluates whether the user is authorized to inspect OCR results for this Evidence.
    Inherits object-level scoping permissions from Evidence management.
    """
    return user_can_access_evidence(user, evidence)


def user_can_process_ocr(user: User, evidence: Evidence) -> bool:
    """
    Evaluates whether the user is authorized to initiate or retry OCR extraction.
    Strictly prohibits Auditor (read-only assurance role).
    Allows Site Manager, Subsidiary Manager, ESG Manager, Operator, and Superuser
    provided the evidence is accessible.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if not user_can_access_evidence(user, evidence):
        return False

    # Auditor is strictly READ-ONLY across all phases
    if user.has_role(Role.Code.AUDITOR) and not (
        user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)
    ):
        return False

    return True


# -----------------------------------------------------------------------------
# 5. ORCHESTRATION & TRANSACTION-SAFE RUNNER
# -----------------------------------------------------------------------------

@transaction.atomic
def execute_ocr_run(
    evidence: Evidence,
    user: Optional[User] = None,
    request: Optional[Any] = None,
    provider_override: Optional[BaseOCRProvider] = None,
) -> OCRRun:
    """
    Executes an end-to-end OCR processing run for an Evidence document.

    Lifecycle:
    1. Validates user authorization (blocks IDOR and unauthorized roles).
    2. Enforces supported document format.
    3. Manages run numbering and sets is_latest=False on prior runs.
    4. Initializes new OCRRun in PROCESSING state.
    5. Dispatches to selected provider (e.g. PyPDFTextProvider or Tesseract).
    6. Extracts structured ESG fields and computes activity record comparison.
    7. Atomically transitions to COMPLETED or records descriptive FAILED state.
    8. Updates Evidence.ocr_metadata summary cache.
    9. Emits audit lineage event (OCR_STARTED, OCR_COMPLETED, or OCR_FAILED).
    """
    # 1. Authorize
    if not user_can_process_ocr(user, evidence):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Evidence:{evidence.id}/ocr/process",
            details="Unauthorized attempt to execute OCR document extraction.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to trigger OCR processing for this evidence.")

    # 2. Format validation
    ext = evidence.file_extension
    if ext not in SUPPORTED_OCR_EXTENSIONS:
        raise UnsupportedDocumentTypeError(
            f"Document format '{ext}' is not supported for OCR extraction. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_OCR_EXTENSIONS))}."
        )

    # 3. File existence check
    try:
        file_path = evidence.file.path
    except Exception:
        file_path = os.path.join(settings.MEDIA_ROOT, str(evidence.file))

    # 4. Run versioning
    existing_count = evidence.ocr_runs.count()
    run_number = existing_count + 1

    # Unset is_latest on historical runs
    evidence.ocr_runs.filter(is_latest=True).update(is_latest=False)

    # 5. Create new OCRRun
    start_time = time.time()
    ocr_run = OCRRun.objects.create(
        evidence=evidence,
        run_number=run_number,
        status=OCRStatus.PROCESSING,
        engine="initializing",
        is_latest=True,
        processed_by=user,
        started_at=timezone.now(),
    )

    log_auth_event(
        AuthAuditLog.EventType.OCR_STARTED,
        request=request,
        user=user,
        resource_accessed=f"Evidence:{evidence.id}/ocr/run/{ocr_run.id}",
        details=f"Started OCR processing run #{run_number} for evidence '{evidence.original_filename}'.",
        success=True,
    )

    # 6. Execute Provider
    try:
        provider = get_ocr_provider(ext, provider_override=provider_override)
        result: OCRExtractionResult = provider.extract(file_path)

        duration_ms = int((time.time() - start_time) * 1000)

        # Update run with extracted raw text
        ocr_run.status = OCRStatus.COMPLETED
        ocr_run.engine = result.engine
        ocr_run.engine_version = result.engine_version
        ocr_run.page_count = result.page_count
        ocr_run.extracted_text = result.extracted_text
        ocr_run.confidence = result.confidence
        ocr_run.page_data = result.page_data
        ocr_run.execution_duration_ms = duration_ms
        ocr_run.completed_at = timezone.now()

        # 7. Extract structured entities
        auto_extract = getattr(settings, "OCR_AUTO_EXTRACT_FIELDS", True)
        if auto_extract:
            extract_structured_fields(ocr_run, result.extracted_text)

        # 8. Compute telemetry comparison with Activity Record
        comparison = compare_ocr_with_activity_record(ocr_run)
        result.raw_metadata["comparison"] = comparison
        ocr_run.raw_metadata = result.raw_metadata
        ocr_run.save()

        # 9. Update evidence metadata cache
        evidence.ocr_metadata = {
            "latest_run_id": ocr_run.id,
            "run_number": ocr_run.run_number,
            "status": OCRStatus.COMPLETED,
            "engine": ocr_run.engine,
            "page_count": ocr_run.page_count,
            "confidence": float(ocr_run.confidence) if ocr_run.confidence else None,
            "fields_count": ocr_run.fields.count(),
            "comparison_status": comparison.get("overall_status", "UNKNOWN"),
            "completed_at": ocr_run.completed_at.isoformat() if ocr_run.completed_at else None,
        }
        evidence.save(update_fields=["ocr_metadata", "updated_at"])

        # 10. Audit event
        event_type = (
            AuthAuditLog.EventType.OCR_RETRIED
            if run_number > 1
            else AuthAuditLog.EventType.OCR_COMPLETED
        )
        log_auth_event(
            event_type,
            request=request,
            user=user,
            resource_accessed=f"Evidence:{evidence.id}/ocr/run/{ocr_run.id}",
            details=(
                f"Completed OCR run #{run_number} ({ocr_run.engine}) for '{evidence.original_filename}'. "
                f"Extracted {ocr_run.fields.count()} fields with {ocr_run.confidence or 0}% confidence in {duration_ms}ms."
            ),
            success=True,
        )

        logger.info(
            "OCR run #%s for Evidence %s completed successfully in %sms.",
            run_number,
            evidence.id,
            duration_ms,
        )
        return ocr_run

    except Exception as exc:
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = str(exc)

        ocr_run.status = OCRStatus.FAILED
        ocr_run.error_message = error_msg
        ocr_run.execution_duration_ms = duration_ms
        ocr_run.completed_at = timezone.now()
        ocr_run.save()

        evidence.ocr_metadata = {
            "latest_run_id": ocr_run.id,
            "run_number": ocr_run.run_number,
            "status": OCRStatus.FAILED,
            "error_message": error_msg,
            "failed_at": ocr_run.completed_at.isoformat() if ocr_run.completed_at else None,
        }
        evidence.save(update_fields=["ocr_metadata", "updated_at"])

        log_auth_event(
            AuthAuditLog.EventType.OCR_FAILED,
            request=request,
            user=user,
            resource_accessed=f"Evidence:{evidence.id}/ocr/run/{ocr_run.id}",
            details=f"OCR run #{run_number} failed for '{evidence.original_filename}': {error_msg}",
            success=False,
        )

        logger.warning(
            "OCR run #%s for Evidence %s failed: %s",
            run_number,
            evidence.id,
            error_msg,
        )
        return ocr_run
