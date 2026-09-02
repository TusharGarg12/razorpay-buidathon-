import os
import sys
import csv
from dotenv import load_dotenv

# Ensure dotenv doesn't override existing environment vars that might be correctly set in CI/CD
load_dotenv(override=False)

# Add backend directory to sys.path so we can import its modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from models import ReconciliationStats, ExceptionRecord
from blocker import DeepBlocker
from reconciler import Reconciler
from scorer import PipelineScorer
from validators import validate_input_data

def load_data(path):
    data = []
    if os.path.exists(path):
        with open(path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    return data

# MOCK HTTPX TO SPEED UP OFFLINE TESTING (Uncomment if Ollama is not running)
# import httpx
# from unittest.mock import patch
# mock_post = patch('httpx.Client.post', side_effect=httpx.ConnectError("Offline mock"))
# mock_post.start()

def main():
    print("Loading data...")
    bank_data = load_data("backend/data/bank.csv")
    ledger_data = load_data("backend/data/ledger.csv")
    
    validate_input_data(bank_data, "Bank")
    validate_input_data(ledger_data, "Ledger")
    
    if not bank_data or not ledger_data:
        print("Data files missing. Please run data_generator.py first.")
        return
        
    print(f"Loaded {len(bank_data)} bank records and {len(ledger_data)} ledger records.")
    
    print("Fitting DeepBlocker...")
    blocker = DeepBlocker()
    blocker.fit(ledger_data)
    
    print("Initializing Reconciler...")
    reconciler = Reconciler()
    matched_pairs = []
    exceptions = []
    
    total = len(bank_data)
    llm_calls = 0
    fallback_calls = 0
    
    print("Running pipeline...")
    for i, b_rec in enumerate(bank_data):
        # Step 1: Blocking
        candidates = blocker.get_candidates(b_rec)
        
        # Step 2: Reconcile
        res = reconciler.reconcile_record(b_rec, candidates)
        
        if res.llm_called:
            llm_calls += 1
            if res.is_fallback:
                fallback_calls += 1
                
        if b_rec['txn_id'] == 'B022':
            print(f"B022 Candidates: {[(c['txn_id'], c.get('_sim_score', 0)) for c in candidates]}")
            
        if res.decision == "match":
            matched_pairs.append((b_rec['txn_id'], res.matched_ledger_id))
        else:
            exceptions.append({
                "bank_txn_id": b_rec['txn_id'],
                "reason_code": res.reason,
                "detail": "Failed in pipeline"
            })
            print(f"FAILED: {b_rec['txn_id']} -> Reason: {res.reason}")
            
    print(f"Finished pipeline. Matched: {len(matched_pairs)}, Exceptions: {len(exceptions)}")
    print(f"Tier 3 LLM calls: {llm_calls} ({(llm_calls/total)*100:.1f}% of total). Fallbacks: {fallback_calls}")
    
    print("Running Scorer...")
    scorer = PipelineScorer()
    stats = scorer.score(matched_pairs, exceptions, len(bank_data), len(ledger_data))
    
    print("========================================")
    print("RESULTS:")
    print(f"Total Bank Records: {stats.total_bank_records}")
    print(f"Total Ledger Records: {stats.total_ledger_records}")
    print(f"Matches: {stats.matches} (TP: {stats.tp}, FP: {stats.fp})")
    print(f"Exceptions: {stats.exceptions} (FN: {stats.fn})")
    print(f"Precision: {stats.precision:.4f}")
    print(f"Recall: {stats.recall:.4f}")
    print(f"F1 Score: {stats.f1_score:.4f}")
    print("========================================")

if __name__ == '__main__':
    main()
