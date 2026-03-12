"""Tests for the Form 4 XML parser."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.core.models import InsiderTransaction
from src.data.parsers.form4_parser import parse_form4

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "form4"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _filed_date() -> datetime:
    return datetime(2025, 1, 15, tzinfo=timezone.utc)


class TestParsePurchase:
    def test_purchase_basic_fields(self):
        xml = _load_fixture("purchase.xml")
        results = parse_form4(xml, "AAPL", _filed_date())

        assert len(results) == 1
        txn = results[0]
        assert isinstance(txn, InsiderTransaction)
        assert txn.symbol == "AAPL"
        assert txn.insider_name == "John Doe"
        assert txn.insider_title == "CEO"
        assert txn.transaction_type == "P"
        assert txn.shares == 10000.0
        assert txn.price_per_share == 150.25
        assert txn.shares_owned_after == 50000.0
        assert txn.is_direct is True


class TestParseSale:
    def test_sale_basic_fields(self):
        xml = _load_fixture("sale.xml")
        results = parse_form4(xml, "AAPL", _filed_date())

        assert len(results) == 1
        txn = results[0]
        assert txn.transaction_type == "S"
        assert txn.insider_name == "Jane Smith"
        assert txn.insider_title == "Director"
        assert txn.shares == 5000.0
        assert txn.price_per_share == 175.50
        assert txn.shares_owned_after == 25000.0


class TestParseOptionExercise:
    def test_option_exercise_basic_fields(self):
        xml = _load_fixture("option_exercise.xml")
        results = parse_form4(xml, "AAPL", _filed_date())

        assert len(results) == 1
        txn = results[0]
        assert txn.transaction_type == "M"
        assert txn.insider_name == "Bob Johnson"
        assert txn.insider_title == "CFO"
        assert txn.shares == 20000.0
        assert txn.price_per_share == 90.0
        assert txn.is_direct is False


class TestMalformedXml:
    def test_invalid_xml_returns_empty(self):
        results = parse_form4("<<<not xml>>>", "AAPL", _filed_date())
        assert results == []

    def test_empty_string_returns_empty(self):
        results = parse_form4("", "AAPL", _filed_date())
        assert results == []


class TestMultipleTransactions:
    def test_multiple_non_derivative_transactions(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Multi Trader</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>VP</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>100.00</value></transactionPricePerShare>
      </transactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>110.00</value></transactionPricePerShare>
      </transactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""
        results = parse_form4(xml, "TEST", _filed_date())

        assert len(results) == 2
        assert results[0].transaction_type == "P"
        assert results[0].shares == 1000.0
        assert results[1].transaction_type == "S"
        assert results[1].shares == 500.0
