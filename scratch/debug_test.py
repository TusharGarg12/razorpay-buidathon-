import io
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

BENCHREC_HEADER = (
    b"matchId,A_transactionType,A_id,A_amount,A_valueDate,A_currencyCode,"
    b"A_transactionReferences,B_transactionType,B_id,B_amount,B_valueDate,"
    b"B_currencyCode,B_transactionReferences\n"
)

def _benchrec_row(match_id, side, txn_id, amount, date, currency, desc):
    if side == "A":
        return f"{match_id},A,{txn_id},{amount},{date},{currency},{desc},,,,,,\n".encode()
    else:
        return f"{match_id},,,,,,,,B,{txn_id},{amount},{date},{currency},{desc}\n".encode()

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

print(response.status_code)
print(response.text)
