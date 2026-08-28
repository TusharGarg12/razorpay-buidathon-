import os
import sys
import pytest

# Ensure backend is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_agent import OllamaAgent

def test_fallback_large_abs_diff():
    """
    Regression test for the $10M/$40M bug.
    When absolute difference is very large (e.g. 30M INR), but percentage-wise 
    might seem small in a different formulation, the abs-diff floor of 4000 
    must hard-cap the amount score to 0.0.
    """
    agent = OllamaAgent()
    
    bank_rec = {
        'amount': 40000000.0,
        'currency': 'INR',
        'date': '2023-10-01',
        'description': 'Transfer to Account'
    }
    ledger_rec = {
        'amount': 10000000.0,
        'currency': 'INR',
        'date': '2023-10-01',
        'description': 'Transfer to Account'
    }
    
    # Even with identical dates (0.25) and descriptions (0.25), 
    # the amt_score should be 0.0 due to > 4000 diff.
    # Total confidence = 0.5*0 + 0.25*1 + 0.25*1 = 0.5
    # Threshold is 0.6, so it must be unresolved.
    decision, conf, reason = agent.heuristic_fallback(bank_rec, ledger_rec)
    
    assert decision == "unresolved", f"Expected unresolved, got {decision}"
    assert conf == 0.5, f"Expected exactly 0.5 confidence due to 0 amount score, got {conf}"

def test_fallback_date_proximity_affects_score():
    """
    Verifies that date proximity actually affects the composite score,
    so the date dimension isn't silently ignored.
    """
    agent = OllamaAgent()
    
    bank_rec = {
        'amount': 1000.0,
        'currency': 'INR',
        'date': '2023-10-01',
        'description': 'Payment from client'
    }
    
    # Case A: Identical date
    ledger_rec_same_date = {
        'amount': 1000.0,
        'currency': 'INR',
        'date': '2023-10-01',
        'description': 'Payment from client'
    }
    
    dec_same, conf_same, _ = agent.heuristic_fallback(bank_rec, ledger_rec_same_date)
    assert conf_same == 1.0, f"Expected 1.0 for perfect match, got {conf_same}"
    
    # Case B: Different date
    ledger_rec_diff_date = {
        'amount': 1000.0,
        'currency': 'INR',
        'date': '2023-10-15',
        'description': 'Payment from client'
    }
    
    dec_diff, conf_diff, _ = agent.heuristic_fallback(bank_rec, ledger_rec_diff_date)
    
    # The date score drops to 0.5, so 0.25 * 0.5 = 0.125 contribution instead of 0.25.
    # Total = 0.5(1.0) + 0.25(0.5) + 0.25(1.0) = 0.5 + 0.125 + 0.25 = 0.875
    assert conf_diff < conf_same, "Different date did not lower the score"
    assert conf_diff == 0.875, f"Expected exactly 0.875, got {conf_diff}"
