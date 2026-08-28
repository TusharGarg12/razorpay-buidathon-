import csv
import random
from datetime import datetime, timedelta
import os

random.seed(42)

def generate_data():
    bank_records = []
    ledger_records = []
    ground_truth = []
    
    start_date = datetime(2024, 1, 1)
    
    b_idx = 1
    l_idx = 1
    
    # 1. Exact Match (18)
    for _ in range(18):
        amt = round(random.uniform(10.0, 5000.0), 2)
        date = start_date + timedelta(days=random.randint(0, 30))
        d_str = date.strftime("%Y-%m-%d")
        
        bank_id = f"B{b_idx:03d}"
        ledger_id = f"L{l_idx:03d}"
        
        bank_records.append([bank_id, d_str, amt, f"Payment from Client {b_idx}", f"REF-{b_idx}", "INR"])
        ledger_records.append([ledger_id, d_str, amt, f"Invoice INV-{l_idx}", f"INV-{l_idx}", "INR"])
        ground_truth.append([bank_id, ledger_id, "exact", "Exact match"])
        
        b_idx += 1
        l_idx += 1
        
    # 2. Amount Fee (3) (Tier 2, ±2% fee)
    for _ in range(3):
        amt = round(random.uniform(100.0, 1000.0), 2)
        fee = round(amt * 0.015, 2)
        b_amt = amt - fee
        date = start_date + timedelta(days=random.randint(0, 30))
        d_str = date.strftime("%Y-%m-%d")
        
        bank_id = f"B{b_idx:03d}"
        ledger_id = f"L{l_idx:03d}"
        
        bank_records.append([bank_id, d_str, b_amt, f"Stripe Payout", f"STR-{b_idx}", "INR"])
        ledger_records.append([ledger_id, d_str, amt, f"Stripe Sale", f"INV-{l_idx}", "INR"])
        ground_truth.append([bank_id, ledger_id, "amount_fee", "Fee deducted"])
        
        b_idx += 1
        l_idx += 1

    # 3. Timing Delay (3) (Tier 2, ±3 days)
    for _ in range(3):
        amt = round(random.uniform(100.0, 1000.0), 2)
        date = start_date + timedelta(days=random.randint(0, 30))
        b_date = date + timedelta(days=random.choice([1, 2, 3]))
        
        bank_id = f"B{b_idx:03d}"
        ledger_id = f"L{l_idx:03d}"
        
        bank_records.append([bank_id, b_date.strftime("%Y-%m-%d"), amt, f"Wire Transfer", f"WT-{b_idx}", "INR"])
        ledger_records.append([ledger_id, date.strftime("%Y-%m-%d"), amt, f"Wire Expected", f"INV-{l_idx}", "INR"])
        ground_truth.append([bank_id, ledger_id, "timing_delay", "Settlement delay"])
        
        b_idx += 1
        l_idx += 1

    # 4. Batching (many-to-1 ledger to bank) (3 batches -> 3 bank rows, 9 ledger rows)
    # Wait, the prompt said 38 bank, 38 ledger rows total. Let's adjust counts.
    # So far: 18 + 3 + 3 = 24.
    for _ in range(1): # 1 batch of 3 ledgers to 1 bank
        amts = [round(random.uniform(50, 200), 2) for _ in range(3)]
        total = sum(amts)
        date = start_date + timedelta(days=random.randint(0, 30))
        d_str = date.strftime("%Y-%m-%d")
        
        bank_id = f"B{b_idx:03d}"
        bank_records.append([bank_id, d_str, total, f"Batch Deposit", f"BD-{b_idx}", "INR"])
        b_idx += 1
        
        for a in amts:
            ledger_id = f"L{l_idx:03d}"
            ledger_records.append([ledger_id, d_str, a, f"Sale part", f"INV-{l_idx}", "INR"])
            ground_truth.append([bank_id, ledger_id, "batching", "Many to 1"])
            l_idx += 1

    # 5. Name mismatch (3) (Tier 2, JW)
    for _ in range(3):
        amt = round(random.uniform(100.0, 1000.0), 2)
        date = start_date + timedelta(days=random.randint(0, 30))
        d_str = date.strftime("%Y-%m-%d")
        
        bank_id = f"B{b_idx:03d}"
        ledger_id = f"L{l_idx:03d}"
        
        bank_records.append([bank_id, d_str, amt, f"RAZORPAY SETTLEMENT", f"REF-{b_idx}", "INR"])
        ledger_records.append([ledger_id, d_str, amt, f"Razorpay Settlement", f"INV-{l_idx}", "INR"])
        ground_truth.append([bank_id, ledger_id, "name_mismatch", "Case/formatting"])
        
        b_idx += 1
        l_idx += 1

    # 6. FX (2) (Tier 2, amt diff)
    for _ in range(2):
        amt_usd = round(random.uniform(10.0, 50.0), 2)
        amt_inr = round(amt_usd * 83.0, 2)
        date = start_date + timedelta(days=random.randint(0, 30))
        d_str = date.strftime("%Y-%m-%d")
        
        bank_id = f"B{b_idx:03d}"
        ledger_id = f"L{l_idx:03d}"
        
        bank_records.append([bank_id, d_str, amt_inr, f"USD Conversion", f"FX-{b_idx}", "INR"])
        ledger_records.append([ledger_id, d_str, amt_inr, f"USD Invoice", f"INV-{l_idx}", "USD"])
        ground_truth.append([bank_id, ledger_id, "fx_conversion", "Currency match"])
        
        b_idx += 1
        l_idx += 1

    # 7. Partial (4) (1-to-many bank to ledger or vice versa)
    # Let's do 2 partials -> 1 ledger to 2 banks
    for _ in range(2):
        amts = [round(random.uniform(100, 300), 2) for _ in range(2)]
        total = sum(amts)
        date = start_date + timedelta(days=random.randint(0, 30))
        d_str = date.strftime("%Y-%m-%d")
        
        ledger_id = f"L{l_idx:03d}"
        ledger_records.append([ledger_id, d_str, total, f"Split Invoice", f"INV-{l_idx}", "INR"])
        l_idx += 1
        
        for a in amts:
            bank_id = f"B{b_idx:03d}"
            bank_records.append([bank_id, d_str, a, f"Partial Pay", f"PP-{b_idx}", "INR"])
            ground_truth.append([bank_id, ledger_id, "partial", "1 to many"])
            b_idx += 1

    # 8. Typo (2) (Tier 3)
    for _ in range(2):
        amt = round(random.uniform(100.0, 1000.0), 2)
        date = start_date + timedelta(days=random.randint(0, 30))
        d_str = date.strftime("%Y-%m-%d")
        
        bank_id = f"B{b_idx:03d}"
        ledger_id = f"L{l_idx:03d}"
        
        bank_records.append([bank_id, d_str, amt, f"Software Lic", f"REF-{b_idx}", "INR"])
        ledger_records.append([ledger_id, d_str, amt, f"Sftware License", f"INV-{l_idx}", "INR"])
        ground_truth.append([bank_id, ledger_id, "typo", "LLM spelling fix"])
        
        b_idx += 1
        l_idx += 1

    # 9. Duplicate (1) (Tier 4 Exception)
    # Create 2 ledger records for 1 bank
    amt = round(random.uniform(100.0, 500.0), 2)
    date = start_date + timedelta(days=random.randint(0, 30))
    d_str = date.strftime("%Y-%m-%d")
    
    bank_id = f"B{b_idx:03d}"
    ledger_id1 = f"L{l_idx:03d}"
    ledger_id2 = f"L{l_idx+1:03d}"
    
    bank_records.append([bank_id, d_str, amt, f"Recurring", f"REC-{b_idx}", "INR"])
    ledger_records.append([ledger_id1, d_str, amt, f"Sub Jan", f"INV-{l_idx}", "INR"])
    ledger_records.append([ledger_id2, d_str, amt, f"Sub Jan Duplicate", f"INV-{l_idx+1}", "INR"])
    
    ground_truth.append([bank_id, ledger_id1, "duplicate", "Should catch dup"])
    
    b_idx += 1
    l_idx += 2

    # 10. Missing (1) (Tier 4 Exception)
    bank_id = f"B{b_idx:03d}"
    bank_records.append([bank_id, "2024-02-01", 99.99, "Unlogged deposit", "UNL", "INR"])
    # No ledger counterpart, no ground truth pair.

    # Ensure output dir
    os.makedirs("data", exist_ok=True)
    
    with open("data/bank.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["txn_id", "date", "amount", "description", "reference", "currency"])
        writer.writerows(bank_records)
        
    with open("data/ledger.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["txn_id", "date", "amount", "description", "invoice_id", "currency"])
        writer.writerows(ledger_records)
        
    with open("data/ground_truth.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["bank_txn_id", "ledger_txn_id", "mismatch_type", "notes"])
        writer.writerows(ground_truth)

    print(f"Generated {len(bank_records)} bank records, {len(ledger_records)} ledger records, {len(ground_truth)} truth pairs.")

if __name__ == "__main__":
    generate_data()
