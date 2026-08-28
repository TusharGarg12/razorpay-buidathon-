import pytest
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from reconciler import Reconciler

def test_fee_deduction_routes_to_tier3():
    reconciler = Reconciler()
    bank = {"txn_id": "B1", "amount": 98.50, "date": "2024-01-01", "description": "Stripe Payout"}
    ledger = {"txn_id": "L1", "amount": 100.00, "date": "2024-01-01", "description": "Invoice 1234"}
    
    # JW score is < 0.85 for Stripe Payout vs Invoice 1234
    # amt diff is 1.5% (<= 5%)
    # Date exact
    # Weight: +4.4 (amt) + 4.2 (date) - 3.2 (desc) = +5.4
    
    # This should be sent to Tier 3 (LLM) since 5.4 >= T_lower (-3.0) but < T_upper (12.0)
    
    res = reconciler.reconcile_record(bank, [ledger])
    assert res.decision in ["match", "unresolved"]
    assert res.llm_called == True, "Fee deduction should route to LLM"

def test_typo_handled_by_jaro_winkler():
    reconciler = Reconciler()
    bank = {"txn_id": "B2", "amount": 500.00, "date": "2024-01-01", "description": "Razorpay Settlement"}
    ledger = {"txn_id": "L2", "amount": 500.00, "date": "2024-01-01", "description": "RAZORPAY SETTLEMENT"}
    
    # Exact amount, exact date, exact desc (case insensitive)
    res = reconciler.reconcile_record(bank, [ledger])
    assert res.decision == "match"
    assert res.matched_ledger_id == "L2"
    assert res.llm_called == False, "Exact match should not route to LLM"

def test_timing_delay_routes_to_tier3():
    reconciler = Reconciler()
    bank = {"txn_id": "B3", "amount": 328.71, "date": "2024-01-04", "description": "Wire Transfer"}
    ledger = {"txn_id": "L3", "amount": 328.71, "date": "2024-01-01", "description": "Wire Expected"}
    
    # Amount exact (+4.4), date diff (-3.2), desc diff (-3.2) -> Weight: -2.0
    # To capture this, T_lower needs to be -3.0 or date penalty relaxed for close dates.
    # We will adjust T_lower in reconciler.py to capture this.
    res = reconciler.reconcile_record(bank, [ledger])
    assert res.llm_called == True, "Timing delay should route to LLM"
