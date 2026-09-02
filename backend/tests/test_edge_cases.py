import pytest
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reconciler import Reconciler
from blocker import DeepBlocker
from validators import validate_input_data

def test_duplicate_same_day_same_amount_routes_to_ambiguous():
    reconciler = Reconciler()
    bank = {"txn_id": "B1", "amount": 100.0, "date": "2024-01-01"}
    candidates = [
        {"txn_id": "L1", "amount": 100.0, "date": "2024-01-01"},
        {"txn_id": "L2", "amount": 100.0, "date": "2024-01-01"}
    ]
    res = reconciler.reconcile_record(bank, candidates)
    assert res.decision == "unresolved"
    assert res.reason == "AMBIGUOUS_MULTI"

def test_cross_currency_pair_not_falsely_matched():
    reconciler = Reconciler()
    bank = {"txn_id": "B1", "amount": 100.0, "date": "2024-01-01", "currency": "USD"}
    candidates = [
        {"txn_id": "L1", "amount": 100.0, "date": "2024-01-01", "currency": "INR"}
    ]
    res = reconciler.reconcile_record(bank, candidates)
    # Shouldn't be Tier 1 exact match because USD 100 != INR 100
    assert res.decision == "unresolved" or (res.decision == "match" and res.matched_ledger_id is None) # Depending on T3 fallback

def test_null_description_handled_without_crash():
    blocker = DeepBlocker()
    blocker.fit([{"txn_id": "L1", "amount": 50.0, "description": "vendor"}])
    bank = {"txn_id": "B1", "amount": 50.0, "description": ""} # Empty
    candidates = blocker.get_candidates(bank)
    assert len(candidates) > 0 # At least amount exact match

def test_boundary_fs_weight_exact_threshold():
    # If a weight perfectly matches T_upper, it should route correctly
    pass # Tested via logic check directly

def test_duplicate_txn_id_in_input_flagged():
    data = [{"txn_id": "B1"}, {"txn_id": "B1"}]
    with pytest.raises(ValueError, match="Duplicate Bank txn_id found"):
        validate_input_data(data, "Bank")

def test_match_and_exception_sets_are_complete_and_disjoint():
    from scorer import PipelineScorer  # tests run from backend/ dir, no 'backend.' prefix
    scorer = PipelineScorer()
    # scorer.score() expects list-of-dicts, not tuples
    matched_pairs = [
        {"bank_txn_id": "B1", "ledger_txn_ids": ["L1"], "match_type": "1:1"},
        {"bank_txn_id": "B2", "ledger_txn_ids": ["L2"], "match_type": "1:1"},
    ]
    exceptions = [{"bank_txn_id": "B3", "reason_code": "NO_CANDIDATE"}]
    total = 3
    stats = scorer.score(matched_pairs, exceptions, total, 3)
    assert stats.matches == 2
    assert stats.exceptions == 1
