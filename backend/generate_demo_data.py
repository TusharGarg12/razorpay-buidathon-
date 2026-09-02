import csv
import os

bank_records = [
    # ─── STRENGTHS: Tier 1 (Exact Match) ───
    ["B001", "2024-03-01", 1200.00, "AWS Cloud Services", "REF-001", "USD"],
    
    # ─── STRENGTHS: Tier 2 (Fuzzy / Smart Rules) ───
    # 1. Fee deduction (Bank amount is less than Ledger due to payment gateway fee)
    ["B002", "2024-03-02", 485.00, "STRIPE TRANSFER", "STR-002", "USD"],
    # 2. Timing Slip (Funds take a few days to settle)
    ["B003", "2024-03-05", 3500.00, "WIRE INBOUND", "WT-003", "USD"],
    # 3. N:1 Batching (One lump sum in bank, multiple small ledger entries)
    ["B004", "2024-03-06", 150.00, "POS SETTLEMENT BATCH", "POS-004", "USD"],
    # 4. 1:N Split Payment (Client paid in two installments, one invoice)
    ["B005", "2024-03-07", 200.00, "CLIENT A PART 1", "PAY-005A", "USD"],
    ["B006", "2024-03-08", 300.00, "CLIENT A PART 2", "PAY-005B", "USD"],
    
    # ─── STRENGTHS: Tier 3 (LLM Semantic Understanding) ───
    # 1. Semantic leap ("UBER EATS" = "Team Lunch")
    ["B007", "2024-03-10", 45.00, "UBER *EATS PENDING", "UB-007", "USD"],
    # 2. Extreme Abbreviations ("GGL G-SUITE" = "Google Workspace")
    ["B008", "2024-03-11", 9200.00, "GGL* G-SUITE", "GG-008", "USD"],

    # ─── EXCEPTIONS: Normal Pipeline Rejections ───
    # Missing Ledger Entry (Bank fee that wasn't recorded in accounting)
    ["B009", "2024-03-12", 15.00, "MONTHLY MAINTENANCE FEE", "FEE-009", "USD"],

    # ─── WEAKNESSES: Edge Cases that Break the Engine ───
    # 1. Extreme Ambiguity (Two identical amounts on same day for similar generalized items)
    ["B010", "2024-03-15", 150.00, "AMZN Mktp US", "AMZ-010", "USD"],
    # 2. Jaro-Winkler Trap (Names are lexically similar but semantically entirely different)
    ["B011", "2024-03-16", 85.00, "Applebees", "APP-011", "USD"],
]

ledger_records = [
    # Tier 1
    ["L001", "2024-03-01", 1200.00, "AWS Cloud Services", "INV-001", "USD"],
    
    # Tier 2
    ["L002", "2024-03-02", 500.00, "Stripe Payments", "INV-002", "USD"],
    ["L003", "2024-03-01", 3500.00, "Expected Wire", "INV-003", "USD"],
    ["L004A", "2024-03-06", 100.00, "Coffee Sales", "INV-004A", "USD"],
    ["L004B", "2024-03-06", 50.00, "Pastry Sales", "INV-004B", "USD"],
    ["L005", "2024-03-07", 500.00, "Client A Full Invoice", "INV-005", "USD"],
    
    # Tier 3
    ["L007", "2024-03-10", 45.00, "Team Lunch", "INV-007", "USD"],
    ["L008", "2024-03-11", 9200.00, "Google Workspace Sub", "INV-008", "USD"],
    
    # Weaknesses
    ["L010A", "2024-03-15", 150.00, "Office Supplies", "INV-010A", "USD"],
    ["L010B", "2024-03-15", 150.00, "Keyboard Replacement", "INV-010B", "USD"],
    ["L011", "2024-03-16", 85.00, "Apple Inc", "INV-011", "USD"],
]

import random
from datetime import timedelta, datetime

# Pad to at least 60 records (add 50 exact matches)
start_date = datetime(2024, 3, 20)
for i in range(12, 65):
    amt = round(random.uniform(50.0, 500.0), 2)
    date = start_date + timedelta(days=random.randint(0, 30))
    d_str = date.strftime("%Y-%m-%d")
    
    bank_id = f"B{i:03d}"
    ledger_id = f"L{i:03d}"
    
    bank_records.append([bank_id, d_str, amt, f"Client {i} Payment", f"REF-{i:03d}", "USD"])
    ledger_records.append([ledger_id, d_str, amt, f"Invoice INV-{i:03d}", f"INV-{i:03d}", "USD"])

def write_csv(filename, headers, records):
    filepath = os.path.join(os.path.dirname(__file__), "..", "data", filename)
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(records)

if __name__ == "__main__":
    write_csv("bank.csv", ["txn_id", "date", "amount", "description", "reference", "currency"], bank_records)
    write_csv("ledger.csv", ["id", "date", "amount", "description", "reference", "currency"], ledger_records)
    print("Demo data generated successfully in data/ directory!")
