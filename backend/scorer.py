import csv
from typing import List, Dict, Any
from models import ReconciliationStats

class PipelineScorer:
    def __init__(self, ground_truth_file: str = "backend/data/ground_truth.csv"):
        self.ground_truth = {}
        try:
            with open(ground_truth_file, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.ground_truth[row['bank_txn_id']] = row['ledger_txn_id']
        except Exception:
            pass

    def score(self, matched_pairs: List[tuple], exceptions: List[Dict[str, Any]], total_bank: int, total_ledger: int) -> ReconciliationStats:
        tp = 0
        fp = 0
        
        # 1. Invariant check: Match + Exception == Total
        if len(matched_pairs) + len(exceptions) != total_bank:
            print(f"WARNING: Pipeline invariant broken! Matches ({len(matched_pairs)}) + Exceptions ({len(exceptions)}) != Total Bank Records ({total_bank}).")
            
        for b_id, l_id in matched_pairs:
            if b_id in self.ground_truth:
                if self.ground_truth[b_id] == l_id:
                    tp += 1
                else:
                    fp += 1
            else:
                fp += 1
                
        # False negatives: present in ground truth, but not in our matched_pairs
        fn = len(self.ground_truth) - tp
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        # 2. Check uncategorized exceptions and patch them
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
            f1_score=f1
        )
