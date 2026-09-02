import pytest
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from reconciler import Reconciler

def test_fee_deduction_routes_to_tier3():
    reconciler = Reconciler()
    # Amount within FEE_TOLERANCE (1.5% < 2%) but date 4 days apart (> DATE_DRIFT=3).
    # With BenchRec weights: amt_agree(7.61) + date_disagree(-5.83) + desc(0.0) = 1.78
    # T_lower(-2.0) < 1.78 < T_upper(10.0)  →  clerical zone  →  LLM called
    bank   = {"txn_id": "B1", "amount": 98.50,  "date": "2024-01-05", "description": "Stripe Payout"}
    ledger = {"txn_id": "L1", "amount": 100.00, "date": "2024-01-01", "description": "Invoice 1234"}

    res = reconciler.reconcile_record(bank, [ledger])
    assert res.decision in ["match", "unresolved"]
    assert res.llm_called == True, "Fee deduction with date drift should route to LLM (clerical zone)"

def test_typo_handled_by_jaro_winkler():
    reconciler = Reconciler()
    bank   = {"txn_id": "B2", "amount": 500.00, "date": "2024-01-01", "description": "Razorpay Settlement"}
    ledger = {"txn_id": "L2", "amount": 500.00, "date": "2024-01-01", "description": "RAZORPAY SETTLEMENT"}

    # Exact amount, exact date, exact desc (case insensitive) → Tier 1 exact match
    res = reconciler.reconcile_record(bank, [ledger])
    assert res.decision == "match"
    assert res.matched_ledger_id == "L2"
    assert res.llm_called == False, "Exact match should not route to LLM"

def test_timing_delay_routes_to_tier3():
    reconciler = Reconciler()
    # Amount exact, date 4 days apart (> DATE_DRIFT=3).
    # With BenchRec weights: amt_agree(7.61) + date_disagree(-5.83) + desc(0.0) = 1.78
    # T_lower(-2.0) < 1.78 < T_upper(10.0)  →  clerical zone  →  LLM called
    bank   = {"txn_id": "B3", "amount": 328.71, "date": "2024-01-05", "description": "Wire Transfer"}
    ledger = {"txn_id": "L3", "amount": 328.71, "date": "2024-01-01", "description": "Wire Expected"}

    res = reconciler.reconcile_record(bank, [ledger])
    assert res.llm_called == True, "4-day timing delay should fall in clerical zone and route to LLM"
