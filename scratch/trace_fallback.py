"""
Forensic trace of heuristic_fallback for the 9 rate-limited records.
Prints the exact confidence value, component breakdown, and threshold outcome.
"""
import os
import sys
import csv
import json
import jellyfish
from dotenv import load_dotenv

load_dotenv(override=False)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from normalizer import normalize_amount, normalize_date

FAILED_IDS = [
    '955428064662', '835464269726', '145845337112', '467223240451',
    '798674129063', '712771274873', '556313217993', '439318458113', '410557410280'
]

def load_data(path):
    data = {}
    with open(path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data[row['txn_id']] = row
    return data

def heuristic_trace(bank_rec, ledger_rec):
    """Exact replica of GeminiAgent.heuristic_fallback with detailed trace."""
    b_curr = bank_rec.get('currency', 'INR')
    l_curr = ledger_rec.get('currency', 'INR')
    b_amt = normalize_amount(bank_rec.get('amount', 0), b_curr, 'INR')
    l_amt = normalize_amount(ledger_rec.get('amount', 0), l_curr, 'INR')
    amt_diff = abs(b_amt - l_amt)
    amt_score = 1.0 if amt_diff < 0.01 else max(0.0, 1.0 - (amt_diff / max(b_amt, 1.0)))
    
    date_score = 1.0 if bank_rec.get("date") == ledger_rec.get("date") else 0.5
    
    desc_jw_score = jellyfish.jaro_winkler_similarity(
        str(bank_rec.get("description", "")).lower(),
        str(ledger_rec.get("description", "")).lower()
    )
    
    confidence = (0.5 * amt_score) + (0.25 * date_score) + (0.25 * desc_jw_score)
    
    return {
        'b_amt': b_amt, 'l_amt': l_amt,
        'amt_diff': amt_diff, 'amt_score': amt_score,
        'b_date': bank_rec.get("date"), 'l_date': ledger_rec.get("date"),
        'date_score': date_score,
        'desc_jw_score': desc_jw_score,
        'confidence': confidence,
        'decision': 'match' if confidence > 0.6 else 'unresolved',
        'threshold': 0.6
    }

def main():
    bank_data = load_data('backend/data/bank.csv')
    ledger_data = load_data('backend/data/ledger.csv')
    
    with open('backend/data/ground_truth.csv') as f:
        gt = {row['bank_txn_id']: row['ledger_txn_id'] for row in csv.DictReader(f)}
    
    print("=== HEURISTIC FALLBACK TRACE FOR FAILED RECORDS ===\n")
    
    for b_id in FAILED_IDS:
        if b_id not in bank_data:
            print(f"Bank record {b_id} not in eval set, skipping.")
            continue
        
        b_rec = bank_data[b_id]
        # Best candidate: the ground truth ledger (or first ledger if no GT)
        true_l_id = gt.get(b_id)
        if true_l_id and true_l_id in ledger_data:
            l_rec = ledger_data[true_l_id]
            match_type = "GT pair"
        else:
            l_rec = list(ledger_data.values())[0]
            match_type = "first ledger (no GT pair)"
        
        trace = heuristic_trace(b_rec, l_rec)
        
        print(f"Bank ID: {b_id} ({match_type})")
        print(f"  Amounts:   bank={trace['b_amt']:.2f}, ledger={trace['l_amt']:.2f}, diff={trace['amt_diff']:.2f}, amt_score={trace['amt_score']:.4f}")
        print(f"  Dates:     bank={trace['b_date']}, ledger={trace['l_date']}, date_score={trace['date_score']:.4f}")
        print(f"  Desc JW:   {trace['desc_jw_score']:.4f}")
        print(f"  Confidence = 0.5*{trace['amt_score']:.4f} + 0.25*{trace['date_score']:.4f} + 0.25*{trace['desc_jw_score']:.4f}")
        print(f"             = {0.5*trace['amt_score']:.4f} + {0.25*trace['date_score']:.4f} + {0.25*trace['desc_jw_score']:.4f}")
        print(f"             = {trace['confidence']:.4f}  (threshold={trace['threshold']})")
        print(f"  DECISION:  {trace['decision']}")
        print("-" * 60)

if __name__ == '__main__':
    main()
