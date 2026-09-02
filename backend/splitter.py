"""
BenchRec Single-File Splitter

Splits a combined BenchRec CSV (with interleaved A-side and B-side rows)
into separate bank and ledger record lists, mapping BenchRec columns to
the pipeline's expected schema (txn_id, amount, date, currency, description).
"""

import csv
import io
from typing import List, Dict, Any, Tuple, Optional


# BenchRec column → pipeline column mapping
_A_COLUMN_MAP = {
    "A_id": "txn_id",
    "A_amount": "amount",
    "A_valueDate": "date",
    "A_currencyCode": "currency",
    "A_transactionReferences": "description",
}

_B_COLUMN_MAP = {
    "B_id": "txn_id",
    "B_amount": "amount",
    "B_valueDate": "date",
    "B_currencyCode": "currency",
    "B_transactionReferences": "description",
}


def is_benchrec_format(header_line: str) -> bool:
    """
    Check whether a CSV header line matches the BenchRec combined format.
    Returns True if the header contains both A_transactionType and B_transactionType columns.
    """
    cols = [c.strip().lower() for c in next(csv.reader(io.StringIO(header_line)), [])]
    return "a_transactiontype" in cols and "b_transactiontype" in cols


def _map_row(row: Dict[str, str], column_map: Dict[str, str]) -> Dict[str, str]:
    """Map a BenchRec row to pipeline schema using the given column map."""
    mapped = {}
    for src, dst in column_map.items():
        mapped[dst] = row.get(src, "").strip()
    return mapped


def split_benchrec_file(file_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Read a BenchRec combined CSV and split into (bank_records, ledger_records).

    A-side rows (A_transactionType == 'A') become bank records.
    B-side rows (B_transactionType == 'B') become ledger records.

    Each record is mapped to the pipeline schema:
        txn_id, amount, date, currency, description

    Returns:
        Tuple of (bank_records, ledger_records) — each a list of dicts.
    """
    bank_records: List[Dict[str, Any]] = []
    ledger_records: List[Dict[str, Any]] = []

    with open(file_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            a_type = row.get("A_transactionType", "").strip()
            b_type = row.get("B_transactionType", "").strip()

            if a_type == "A":
                mapped = _map_row(row, _A_COLUMN_MAP)
                if mapped["txn_id"]:  # skip rows with empty IDs
                    bank_records.append(mapped)
            elif b_type == "B":
                mapped = _map_row(row, _B_COLUMN_MAP)
                if mapped["txn_id"]:
                    ledger_records.append(mapped)

    return bank_records, ledger_records


def split_benchrec_bytes(content: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Same as split_benchrec_file but accepts raw bytes (from an uploaded file).
    """
    bank_records: List[Dict[str, Any]] = []
    ledger_records: List[Dict[str, Any]] = []

    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        a_type = row.get("A_transactionType", "").strip()
        b_type = row.get("B_transactionType", "").strip()

        if a_type == "A":
            mapped = _map_row(row, _A_COLUMN_MAP)
            if mapped["txn_id"]:
                bank_records.append(mapped)
        elif b_type == "B":
            mapped = _map_row(row, _B_COLUMN_MAP)
            if mapped["txn_id"]:
                ledger_records.append(mapped)

    return bank_records, ledger_records
