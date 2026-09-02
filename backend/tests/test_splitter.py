"""Tests for the BenchRec splitter module."""

import os
import sys
import tempfile
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from splitter import is_benchrec_format, split_benchrec_bytes, split_benchrec_file


# ── is_benchrec_format ────────────────────────────────────────────────────────

def test_detects_benchrec_header():
    header = "matchId,matchDate,A_transactionType,A_id,A_amount,B_transactionType,B_id,B_amount\n"
    assert is_benchrec_format(header) is True


def test_rejects_standard_header():
    header = "txn_id,amount,date,description\n"
    assert is_benchrec_format(header) is False


def test_rejects_empty_header():
    assert is_benchrec_format("") is False


# ── split_benchrec_bytes ──────────────────────────────────────────────────────

def _make_benchrec_csv(*rows):
    """Helper to build BenchRec CSV bytes from row tuples."""
    header = "matchId,A_transactionType,A_id,A_amount,A_valueDate,A_currencyCode,A_transactionReferences,B_transactionType,B_id,B_amount,B_valueDate,B_currencyCode,B_transactionReferences\n"
    lines = [header]
    for row in rows:
        lines.append(",".join(str(c) for c in row) + "\n")
    return "".join(lines).encode("utf-8")


def test_splits_a_and_b_sides():
    csv_bytes = _make_benchrec_csv(
        # A-side row
        ("M1", "A", "A001", "100.00", "2024-01-01", "USD", "Payment ref 1", "", "", "", "", "", ""),
        # B-side row
        ("M1", "", "", "", "", "", "", "B", "B001", "100.00", "2024-01-01", "USD", "Payment ref 1"),
        # Another A-side
        ("M2", "A", "A002", "200.00", "2024-01-02", "INR", "Wire transfer", "", "", "", "", "", ""),
    )
    bank, ledger = split_benchrec_bytes(csv_bytes)

    assert len(bank) == 2
    assert len(ledger) == 1

    # Check column mapping for A-side
    assert bank[0]["txn_id"] == "A001"
    assert bank[0]["amount"] == "100.00"
    assert bank[0]["date"] == "2024-01-01"
    assert bank[0]["currency"] == "USD"
    assert bank[0]["description"] == "Payment ref 1"

    # Check column mapping for B-side
    assert ledger[0]["txn_id"] == "B001"
    assert ledger[0]["amount"] == "100.00"
    assert ledger[0]["currency"] == "USD"


def test_skips_rows_with_empty_ids():
    csv_bytes = _make_benchrec_csv(
        # A-side with empty ID — should be skipped
        ("M1", "A", "", "100.00", "2024-01-01", "USD", "desc", "", "", "", "", "", ""),
        # B-side with valid ID
        ("M1", "", "", "", "", "", "", "B", "B001", "100.00", "2024-01-01", "USD", "desc"),
    )
    bank, ledger = split_benchrec_bytes(csv_bytes)

    assert len(bank) == 0
    assert len(ledger) == 1


def test_empty_file_returns_empty_lists():
    csv_bytes = "matchId,A_transactionType,A_id,A_amount,A_valueDate,A_currencyCode,A_transactionReferences,B_transactionType,B_id,B_amount,B_valueDate,B_currencyCode,B_transactionReferences\n".encode("utf-8")
    bank, ledger = split_benchrec_bytes(csv_bytes)
    assert len(bank) == 0
    assert len(ledger) == 0


def test_handles_bom_encoding():
    """Ensure UTF-8 BOM doesn't break column detection."""
    bom = b'\xef\xbb\xbf'
    csv_bytes = bom + _make_benchrec_csv(
        ("M1", "A", "A001", "50.00", "2024-06-15", "EUR", "BOM test", "", "", "", "", "", ""),
    )
    bank, ledger = split_benchrec_bytes(csv_bytes)
    assert len(bank) == 1
    assert bank[0]["txn_id"] == "A001"


# ── split_benchrec_file ──────────────────────────────────────────────────────

def test_split_from_file():
    csv_bytes = _make_benchrec_csv(
        ("M1", "A", "A001", "100.00", "2024-01-01", "USD", "ref1", "", "", "", "", "", ""),
        ("M1", "", "", "", "", "", "", "B", "B001", "100.00", "2024-01-01", "USD", "ref1"),
    )
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
        f.write(csv_bytes)
        f.flush()
        path = f.name

    try:
        bank, ledger = split_benchrec_file(path)
        assert len(bank) == 1
        assert len(ledger) == 1
        assert bank[0]["txn_id"] == "A001"
        assert ledger[0]["txn_id"] == "B001"
    finally:
        os.unlink(path)
