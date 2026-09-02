import csv
import os
from typing import List, Dict, Any
from models import ReconciliationStats

# Check multiple possible locations for ground truth
# 1. Local development (../data)
# 2. Docker container (/app/data)
_POSSIBLE_GTS = [
    os.path.join(os.path.dirname(__file__), "..", "data", "ground_truth.csv"),
    os.path.join(os.path.dirname(__file__), "data", "ground_truth.csv"),
]
_DEFAULT_GT = next((p for p in _POSSIBLE_GTS if os.path.exists(p)), _POSSIBLE_GTS[0])

class PipelineScorer:
    def __init__(self, ground_truth_file: str = _DEFAULT_GT):
        # ground_truth: bank_txn_id → list of valid ledger_txn_ids (supports 1:N / N:M)
        self.ground_truth: Dict[str, List[str]] = {}
        try:
            with open(ground_truth_file, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    bid = row['bank_txn_id']
                    lid = row['ledger_txn_id']
                    if bid not in self.ground_truth:
                        self.ground_truth[bid] = []
                    self.ground_truth[bid].append(lid)
        except Exception:
            pass

    def score(
        self,
        matched_pairs: List[Dict[str, Any]],
        exceptions: List[Dict[str, Any]],
        total_bank: int,
        total_ledger: int,
    ) -> ReconciliationStats:
        tp = 0
        fp = 0
        match_type_counts: Dict[str, int] = {}

        # Invariant check
        bank_ids_in_matches = {p['bank_txn_id'] for p in matched_pairs}
        bank_ids_in_exceptions = {e['bank_txn_id'] for e in exceptions}
        if len(bank_ids_in_matches | bank_ids_in_exceptions) != total_bank:
            print(
                f"WARNING: Pipeline invariant broken! "
                f"Matched ({len(bank_ids_in_matches)}) + Exceptions ({len(bank_ids_in_exceptions)}) "
                f"!= Total Bank Records ({total_bank})."
            )

        for pair in matched_pairs:
            bid = pair['bank_txn_id']
            # ledger_txn_ids is the new field; fall back to legacy matched_ledger_id
            matched_lids = pair.get('ledger_txn_ids') or [pair.get('matched_ledger_id')]
            matched_lids = [l for l in matched_lids if l]

            mt = pair.get('match_type', '1:1')
            match_type_counts[mt] = match_type_counts.get(mt, 0) + 1

            if bid in self.ground_truth:
                gt_lids = set(self.ground_truth[bid])
                # TP: at least one of our matched ledger IDs is in ground truth
                if any(lid in gt_lids for lid in matched_lids):
                    tp += 1
                else:
                    fp += 1
            else:
                fp += 1

        # FN: bank records in ground truth that we didn't match correctly
        matched_bank_ids = {p['bank_txn_id'] for p in matched_pairs if
                            any((lid in self.ground_truth.get(p['bank_txn_id'], [])) 
                                for lid in (p.get('ledger_txn_ids') or [p.get('matched_ledger_id')])
                                if lid)}
        fn = len(self.ground_truth) - len(matched_bank_ids & set(self.ground_truth.keys()))

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        # Patch uncategorized exceptions
        for exc in exceptions:
            if not exc.get("reason_code"):
                exc["reason_code"] = "UNKNOWN_EXCEPTION"

        return ReconciliationStats(
            total_bank_records=total_bank,
            total_ledger_records=total_ledger,
            matches=len(matched_pairs),
            exceptions=len(exceptions),
            tp=tp,
            fp=fp,
            fn=fn,
            precision=precision,
            recall=recall,
            f1_score=f1,
            match_type_counts=match_type_counts,
        )
