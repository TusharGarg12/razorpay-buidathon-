import io
import json
from fastapi.testclient import TestClient

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from main import app

client = TestClient(app)

def test_upload_both_or_neither():
    # Only bank file
    bank_csv = b"txn_id,amount\n1,100"
    response = client.post(
        "/reconcile/stream",
        files={"bank_file": ("bank.csv", io.BytesIO(bank_csv), "text/csv")}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "Both bank and ledger files are required"

def test_upload_bad_columns():
    bank_csv = b"id,amount\n1,100"
    ledger_csv = b"txn_id,amount\n1,100"
    
    response = client.post(
        "/reconcile/stream",
        files={
            "bank_file": ("bank.csv", io.BytesIO(bank_csv), "text/csv"),
            "ledger_file": ("ledger.csv", io.BytesIO(ledger_csv), "text/csv")
        }
    )
    assert response.status_code == 400
    assert "Invalid bank CSV format: missing txn_id" in response.json()["detail"]["message"]

def test_upload_happy_path():
    # Simple matching setup
    bank_csv = b"txn_id,amount,date,description,party\nb1,100.00,2023-01-01,Test,Test\nb2,200.00,2023-01-02,Test2,Test2\nb3,300.00,2023-01-03,Test3,Test3\n"
    ledger_csv = b"txn_id,amount,date,description,party\nl1,100.00,2023-01-01,Test,Test\nl2,200.00,2023-01-02,Test2,Test2\nl3,300.00,2023-01-03,Test3,Test3\n"
    
    response = client.post(
        "/reconcile/stream",
        files={
            "bank_file": ("bank.csv", io.BytesIO(bank_csv), "text/csv"),
            "ledger_file": ("ledger.csv", io.BytesIO(ledger_csv), "text/csv")
        }
    )
    assert response.status_code == 200
    
    print("RESPONSE:", response.text)
    
    lines = response.text.split("\n\n")
    complete_event = None
    for line in lines:
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("type") == "complete":
                    complete_event = data
            except json.JSONDecodeError:
                pass
                
    assert complete_event is not None
    assert complete_event["stats"]["total_bank_records"] == 3
    # Match rate is definitely not the hardcoded demo rate (since demo is 60 records)
    assert complete_event["stats"]["total_bank_records"] != 60

from unittest.mock import patch

def test_temp_dir_cleanup():
    bank_csv = b"txn_id,amount,date,description,party\nb1,100.00,2023-01-01,Test,Test\n"
    ledger_csv = b"txn_id,amount,date,description,party\nl1,100.00,2023-01-01,Test,Test\n"
    
    import tempfile
    real_temp_dir = tempfile.mkdtemp()
    
    with patch('main.tempfile.mkdtemp') as mock_mkdtemp:
        mock_mkdtemp.return_value = real_temp_dir
        
        response = client.post(
            "/reconcile/stream",
            files={
                "bank_file": ("bank.csv", io.BytesIO(bank_csv), "text/csv"),
                "ledger_file": ("ledger.csv", io.BytesIO(ledger_csv), "text/csv")
            }
        )
        if response.status_code != 200:
            print("ERROR RESPONSE:", response.text)
        assert response.status_code == 200
        
        # Read the entire stream to trigger completion
        list(response.iter_lines())
        
        # Verify it was deleted
        assert not os.path.exists(real_temp_dir)


# ── BenchRec single-file upload tests ─────────────────────────────────────────

BENCHREC_HEADER = (
    b"matchId,A_transactionType,A_id,A_amount,A_valueDate,A_currencyCode,"
    b"A_transactionReferences,B_transactionType,B_id,B_amount,B_valueDate,"
    b"B_currencyCode,B_transactionReferences\n"
)

def _benchrec_row(match_id, side, txn_id, amount, date, currency, desc):
    if side == "A":
        row = [match_id, "A", txn_id, amount, date, currency, desc, "", "", "", "", "", ""]
    else:
        row = [match_id, "", "", "", "", "", "", "B", txn_id, amount, date, currency, desc]
    return (",".join(row) + "\n").encode()


def test_single_file_benchrec_happy_path():
    """Single combined BenchRec file splits into bank + ledger and reconciles."""
    csv_bytes = (
        BENCHREC_HEADER
        + _benchrec_row("M1", "A", "A001", "100.00", "2024-01-01", "USD", "Payment one")
        + _benchrec_row("M1", "B", "B001", "100.00", "2024-01-01", "USD", "Payment one")
        + _benchrec_row("M2", "A", "A002", "200.00", "2024-01-02", "USD", "Wire two")
        + _benchrec_row("M2", "B", "B002", "200.00", "2024-01-02", "USD", "Wire two")
    )

    response = client.post(
        "/reconcile/stream",
        files={"combined_file": ("combined.csv", io.BytesIO(csv_bytes), "text/csv")}
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    lines = response.text.split("\n\n")
    complete_event = None
    for line in lines:
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("type") == "complete":
                    complete_event = data
            except json.JSONDecodeError:
                pass

    assert complete_event is not None, "No complete event in SSE stream"
    # 2 A-side rows → 2 bank records
    assert complete_event["stats"]["total_bank_records"] == 2
    # 2 B-side rows → 2 ledger records
    assert complete_event["stats"]["total_ledger_records"] == 2


def test_single_file_wrong_format_rejected():
    """A single-file upload that isn't BenchRec format should be rejected."""
    non_benchrec = b"txn_id,amount,date\nX1,100,2024-01-01\n"

    response = client.post(
        "/reconcile/stream",
        files={"combined_file": ("plain.csv", io.BytesIO(non_benchrec), "text/csv")}
    )
    assert response.status_code == 400
    msg = response.json()["detail"]["message"]
    assert "BenchRec format" in msg or "A_transactionType" in msg


def test_combined_and_pair_both_rejected():
    """Sending combined_file AND bank_file together should be rejected."""
    csv = b"txn_id,amount\n1,100\n"
    response = client.post(
        "/reconcile/stream",
        files={
            "combined_file": ("combined.csv", io.BytesIO(BENCHREC_HEADER), "text/csv"),
            "bank_file":     ("bank.csv",     io.BytesIO(csv),             "text/csv"),
        }
    )
    assert response.status_code == 400
    assert "either" in response.json()["detail"]["message"].lower() or \
           "both" in response.json()["detail"]["message"].lower()
