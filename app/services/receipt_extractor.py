"""
Receipt data extraction service.

Extracts key fields from uploaded receipts (PDF, JPG, PNG) using OCR (pytesseract)
for images and pdfplumber for PDFs. Regex patterns identify vendor, date, amount,
tax, and currency from the raw text.
"""

import re
from datetime import date

from dateutil import parser as date_parser

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Currency symbols / codes
_CURRENCY_SYMBOLS = {
    "£": "GBP",
    "$": "USD",
    "€": "EUR",
    "¥": "JPY",
    "₹": "INR",
}
_CURRENCY_CODE_RE = re.compile(
    r"\b(GBP|USD|EUR|JPY|INR|CAD|AUD|CHF|NZD)\b", re.IGNORECASE
)
_CURRENCY_SYMBOL_RE = re.compile(r"[£$€¥₹]")

# Amount: optional currency prefix, digits, optional decimal.
# Uses \b word boundaries so "total" does not match within "subtotal".
_AMOUNT_RE = re.compile(
    r"\b(?:grand\s*total|total\s+due|total\s+amount|amount\s+due|total|amount|net|sum|due|charged)\b"
    r"[^\d£$€¥₹]*"
    r"([£$€¥₹]?\s*\d{1,6}(?:[,\s]\d{3})*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_GENERIC_AMOUNT_RE = re.compile(
    r"[£$€¥₹]\s*(\d{1,6}(?:[,\s]\d{3})*(?:\.\d{1,2})?)"
)

# Tax: VAT / GST / tax line – requires a currency symbol to avoid capturing percentages
_TAX_RE = re.compile(
    r"(?:vat|gst|tax|sales\s*tax|hst|pst)"
    r"(?:\s*\([^)]*\))?"  # skip optional parenthetical e.g. (20%)
    r"[^\d£$€¥₹]*"
    r"([£$€¥₹]\s*\d{1,6}(?:[,\s]\d{3})*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# Date patterns (broad)
_DATE_RE = re.compile(
    r"""
    (?:
        \d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}   # 01/02/2024 or 01-02-24
        |
        \d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}      # 2024/01/02
        |
        \d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}
        |
        (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Vendor: often on the first non-empty line of a receipt
_VENDOR_SKIP_RE = re.compile(
    r"^(?:receipt|invoice|tax\s*invoice|bill|statement|"
    r"vat\s*number|reg(?:istration)?\s*no|tel|fax|email|www\.|"
    r"date|time|order|transaction|ref|no\.?:|#|\d+).*$",
    re.IGNORECASE,
)


def _clean_amount(raw: str) -> float | None:
    """Strip currency symbols and commas, return float."""
    cleaned = re.sub(r"[£$€¥₹,\s]", "", raw)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_currency(text: str) -> tuple[str, float]:
    """Return (currency_code, confidence 0-1)."""
    # Explicit code wins
    code_match = _CURRENCY_CODE_RE.search(text)
    if code_match:
        return code_match.group(0).upper(), 1.0
    # Symbol
    sym_match = _CURRENCY_SYMBOL_RE.search(text)
    if sym_match:
        return _CURRENCY_SYMBOLS.get(sym_match.group(0), "USD"), 0.8
    return "GBP", 0.3  # default with low confidence


def _extract_date(text: str) -> tuple[date | None, float]:
    """Return (date, confidence)."""
    # Look for date-labelled lines first
    for line in text.splitlines():
        if re.search(r"\bdate\b", line, re.IGNORECASE):
            match = _DATE_RE.search(line)
            if match:
                try:
                    parsed = date_parser.parse(match.group(0), dayfirst=True)
                    return parsed.date(), 1.0
                except Exception:
                    pass
    # Fall back to first date found anywhere
    match = _DATE_RE.search(text)
    if match:
        try:
            parsed = date_parser.parse(match.group(0), dayfirst=True)
            return parsed.date(), 0.7
        except Exception:
            pass
    return None, 0.0


def _extract_amount(text: str) -> tuple[float | None, float]:
    """Return (amount, confidence)."""
    match = _AMOUNT_RE.search(text)
    if match:
        val = _clean_amount(match.group(1))
        if val is not None and val > 0:
            return val, 1.0
    # Generic: last currency-prefixed amount (often the total)
    all_amounts = _GENERIC_AMOUNT_RE.findall(text)
    if all_amounts:
        val = _clean_amount(all_amounts[-1])
        if val is not None and val > 0:
            return val, 0.6
    return None, 0.0


def _extract_tax(text: str) -> tuple[float | None, float]:
    match = _TAX_RE.search(text)
    if match:
        val = _clean_amount(match.group(1))
        if val is not None and val >= 0:
            return val, 1.0
    return None, 0.0


def _extract_vendor(text: str) -> tuple[str | None, float]:
    """Heuristic: return the first meaningful non-boilerplate line."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:8]:
        if not _VENDOR_SKIP_RE.match(line) and len(line) > 2:
            return line, 0.7
    return None, 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD = 0.6


def extract_text_from_file(filepath: str) -> str:
    """Extract raw text from a PDF or image file."""
    lower = filepath.lower()
    if lower.endswith(".pdf"):
        return _extract_text_pdf(filepath)
    return _extract_text_image(filepath)


def _extract_text_pdf(filepath: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            return "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
    except Exception as exc:
        return f"[PDF extraction error: {exc}]"


def _extract_text_image(filepath: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(filepath)
        return pytesseract.image_to_string(img)
    except Exception as exc:
        return f"[Image extraction error: {exc}]"


def extract_receipt_data(filepath: str) -> dict:
    """
    Extract structured expense data from a receipt file.

    Returns a dict with keys:
        vendor, transaction_date, amount, tax_amount, currency,
        raw_text, flags (list of field names that could not be extracted
        with high confidence)
    """
    raw_text = extract_text_from_file(filepath)

    vendor, vendor_conf = _extract_vendor(raw_text)
    transaction_date, date_conf = _extract_date(raw_text)
    amount, amount_conf = _extract_amount(raw_text)
    tax_amount, tax_conf = _extract_tax(raw_text)
    currency, currency_conf = _extract_currency(raw_text)

    flags = []
    if vendor_conf < CONFIDENCE_THRESHOLD:
        flags.append("vendor")
    if date_conf < CONFIDENCE_THRESHOLD:
        flags.append("transaction_date")
    if amount_conf < CONFIDENCE_THRESHOLD:
        flags.append("amount")

    return {
        "vendor": vendor,
        "transaction_date": transaction_date.isoformat() if transaction_date else None,
        "amount": amount,
        "tax_amount": tax_amount,
        "currency": currency,
        "raw_text": raw_text,
        "flags": flags,
        "confidence": {
            "vendor": vendor_conf,
            "transaction_date": date_conf,
            "amount": amount_conf,
            "tax_amount": tax_conf,
            "currency": currency_conf,
        },
    }
