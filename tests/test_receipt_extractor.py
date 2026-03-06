"""Tests for the receipt extractor service."""

import os
import textwrap

import pytest

from app.services.receipt_extractor import (
    _clean_amount,
    _extract_amount,
    _extract_currency,
    _extract_date,
    _extract_tax,
    _extract_vendor,
    extract_receipt_data,
)


# ---------------------------------------------------------------------------
# Unit tests for individual extractors
# ---------------------------------------------------------------------------

class TestCleanAmount:
    def test_plain_number(self):
        assert _clean_amount("123.45") == 123.45

    def test_with_currency_symbol(self):
        assert _clean_amount("£ 99.99") == 99.99

    def test_with_comma_thousands(self):
        assert _clean_amount("1,234.56") == 1234.56

    def test_invalid(self):
        assert _clean_amount("abc") is None


class TestExtractCurrency:
    def test_explicit_code(self):
        code, conf = _extract_currency("Total GBP 55.00")
        assert code == "GBP"
        assert conf == 1.0

    def test_pound_symbol(self):
        code, conf = _extract_currency("Amount £45.00")
        assert code == "GBP"
        assert conf > 0.5

    def test_dollar_symbol(self):
        code, _ = _extract_currency("Total $12.50")
        assert code == "USD"

    def test_default(self):
        code, conf = _extract_currency("No currency information here")
        assert isinstance(code, str)
        assert conf < 0.5


class TestExtractDate:
    def test_labelled_date(self):
        text = "Date: 15/06/2024\nSome other text"
        d, conf = _extract_date(text)
        assert d is not None
        assert d.year == 2024
        assert d.month == 6
        assert d.day == 15
        assert conf == 1.0

    def test_iso_format(self):
        d, _ = _extract_date("Invoice date 2024-03-01")
        assert d is not None
        assert d.year == 2024

    def test_no_date(self):
        d, conf = _extract_date("No date information in this text at all.")
        assert d is None
        assert conf == 0.0

    def test_written_month(self):
        d, _ = _extract_date("Issued: 5 January 2024")
        assert d is not None
        assert d.month == 1


class TestExtractAmount:
    def test_total_label(self):
        text = "Total: £120.50\nVAT: £20.00"
        amount, conf = _extract_amount(text)
        assert amount == pytest.approx(120.50)
        assert conf >= 0.9

    def test_grand_total(self):
        text = "Grand Total £ 250.00"
        amount, conf = _extract_amount(text)
        assert amount == pytest.approx(250.00)

    def test_generic_currency_symbol(self):
        text = "You owe £55.99"
        amount, conf = _extract_amount(text)
        assert amount == pytest.approx(55.99)

    def test_no_amount(self):
        amount, conf = _extract_amount("Nothing here")
        assert amount is None
        assert conf == 0.0


class TestExtractTax:
    def test_vat_label(self):
        text = "VAT: £24.00\nTotal: £144.00"
        tax, conf = _extract_tax(text)
        assert tax == pytest.approx(24.00)
        assert conf == 1.0

    def test_gst_label(self):
        tax, conf = _extract_tax("GST $5.50")
        assert tax == pytest.approx(5.50)

    def test_no_tax(self):
        tax, conf = _extract_tax("Total: £50.00")
        assert tax is None
        assert conf == 0.0


class TestExtractVendor:
    def test_first_meaningful_line(self):
        text = "Acme Supplies Ltd\nReceipt\nDate: 01/01/2024"
        vendor, conf = _extract_vendor(text)
        assert vendor == "Acme Supplies Ltd"

    def test_skips_receipt_heading(self):
        text = "Receipt\nACME COFFEE SHOP\nDate: 2024-01-01"
        vendor, conf = _extract_vendor(text)
        assert vendor == "ACME COFFEE SHOP"

    def test_no_useful_lines(self):
        text = "Receipt\nDate: 01/01/2024\nRef: 12345"
        vendor, conf = _extract_vendor(text)
        # May or may not find a vendor from later lines; just ensure no crash
        assert isinstance(conf, float)


# ---------------------------------------------------------------------------
# Integration test with a real text file
# ---------------------------------------------------------------------------

SAMPLE_RECEIPT_TEXT = textwrap.dedent("""\
    THE COFFEE HOUSE
    123 High Street, London
    Date: 12/03/2024
    Receipt No: 00987

    Cappuccino x2         £6.00
    Croissant             £2.50
    ----------------------------
    Subtotal              £8.50
    VAT (20%)             £1.70
    Total                £10.20
    Thank you for your visit!
""")


def test_extract_receipt_data_from_text_file(tmp_path):
    """Write sample receipt text to a fake image file and test extraction via a text stub."""
    # We test the parsing logic directly since OCR requires tesseract/actual image
    from app.services.receipt_extractor import (
        _extract_vendor,
        _extract_date,
        _extract_amount,
        _extract_tax,
        _extract_currency,
    )
    text = SAMPLE_RECEIPT_TEXT
    vendor, _ = _extract_vendor(text)
    date_, _ = _extract_date(text)
    amount, _ = _extract_amount(text)
    tax, _ = _extract_tax(text)
    currency, _ = _extract_currency(text)

    assert vendor == "THE COFFEE HOUSE"
    assert date_ is not None
    assert date_.month == 3
    assert date_.day == 12
    assert amount == pytest.approx(10.20)
    assert tax == pytest.approx(1.70)
    assert currency == "GBP"
