import json
import os
import math
import jellyfish
from typing import List, Dict, Any

from models import MatchResult
from normalizer import normalize_amount, normalize_date
from llm_agent import OllamaAgent
import config

class Reconciler:
    def __init__(self):
        self.llm_agent = OllamaAgent()
        self.consumed_ledger_ids = set()
        
        # Load weights from config
        self.weights = {
            "amt": {"agree": 4.0, "disagree": -4.0},
            "date": {"agree": 4.0, "disagree": -3.0},
            "desc": {"agree": 6.0, "disagree": -3.0},
            "T_upper": 12.0,
            "T_lower": -3.0
        }
        try:
            with open(os.path.join(os.path.dirname(__file__), "weights_benchrec.json"), "r") as f:
                self.weights = json.load(f)
        except Exception:
            pass

    def _tier_1_exact(self, bank: Dict[str, Any], ledger: Dict[str, Any]) -> bool:
        b_curr = bank.get('currency', 'INR')
        l_curr = ledger.get('currency', 'INR')
        b_amt = normalize_amount(bank.get('amount', 0), b_curr, 'INR')
        l_amt = normalize_amount(ledger.get('amount', 0), l_curr, 'INR')
        
        # Exact match (allow 1 cent float precision diff - note: 0.01 is in INR since amounts are normalized)
        if abs(b_amt - l_amt) < 0.01:
            try:
                b_date = normalize_date(str(bank.get('date', '')))
                l_date = normalize_date(str(ledger.get('date', '')))
                if b_date == l_date:
                    return True
            except ValueError:
                return False
        return False

    def _tier_2_fs_weight(self, bank: Dict[str, Any], ledger: Dict[str, Any]) -> float:
        weight = 0.0
        
        # Null/missing guards
        if 'amount' not in bank or 'amount' not in ledger:
            weight += self.weights["amt"]["disagree"]
        else:
            b_curr = bank.get('currency', 'INR')
            l_curr = ledger.get('currency', 'INR')
            b_amt = normalize_amount(bank.get('amount', 0), b_curr, 'INR')
            l_amt = normalize_amount(ledger.get('amount', 0), l_curr, 'INR')
            
            # Sign matching (prevent +100 matching -100 silently)
            if (b_amt > 0 and l_amt < 0) or (b_amt < 0 and l_amt > 0):
                weight += self.weights["amt"]["disagree"]
            else:
                abs_diff = abs(abs(b_amt) - abs(l_amt))
                amt_diff_pct = abs_diff / max(abs(l_amt), 1.0)
                # Cap: fee tolerance AND max 4000 INR absolute difference (~$50 USD)
                if amt_diff_pct <= config.FEE_TOLERANCE and abs_diff <= 4000.0:
                    weight += self.weights["amt"]["agree"]
                else:
                    weight += self.weights["amt"]["disagree"]
            
        try:
            from datetime import datetime
            b_date = normalize_date(str(bank.get('date', '')))
            l_date = normalize_date(str(ledger.get('date', '')))
            b_dt = datetime.strptime(b_date, "%Y-%m-%d")
            l_dt = datetime.strptime(l_date, "%Y-%m-%d")
            if abs((b_dt - l_dt).days) <= config.DATE_DRIFT:
                weight += self.weights["date"]["agree"]
            else:
                weight += self.weights["date"]["disagree"]
        except ValueError:
            weight += self.weights["date"]["disagree"]
            
        b_desc = str(bank.get('description', '')).lower()
        l_desc = str(ledger.get('description', '')).lower()
        
        if not b_desc or not l_desc:
            weight += self.weights["desc"]["disagree"]
        else:
            jw_score = jellyfish.jaro_winkler_similarity(b_desc, l_desc)
            if jw_score >= 0.85:
                weight += self.weights["desc"]["agree"]
            else:
                weight += self.weights["desc"]["disagree"]
            
        return weight

    def reconcile_record(self, bank_record: Dict[str, Any], candidate_ledgers: list[Dict[str, Any]]) -> MatchResult:
        if not candidate_ledgers:
            return MatchResult(decision="unresolved", reason="NO_CANDIDATE", confidence=0.0)
            
        # Filter consumed candidates
        unconsumed_candidates = [c for c in candidate_ledgers if c.get('txn_id') not in self.consumed_ledger_ids]
        if not unconsumed_candidates:
            return MatchResult(decision="unresolved", reason="NO_UNCONSUMED_CANDIDATES", confidence=0.0)

        # Tier 1
        tier_1_matches = []
        for ledger in unconsumed_candidates:
            if self._tier_1_exact(bank_record, ledger):
                tier_1_matches.append(ledger)
                
        if len(tier_1_matches) == 1:
            matched_id = tier_1_matches[0].get('txn_id')
            self.consumed_ledger_ids.add(matched_id)
            return MatchResult(decision="match", matched_ledger_id=matched_id, confidence=1.0)
        elif len(tier_1_matches) > 1:
            return MatchResult(decision="unresolved", reason="AMBIGUOUS_MULTI", confidence=0.5)
                
        # Tier 2
        best_fs_weight = -999.0
        best_ledger = None
        
        for ledger in unconsumed_candidates:
            w = self._tier_2_fs_weight(bank_record, ledger)
            # Deterministic tie-break (first seen wins if tie, but can be improved)
            if w > best_fs_weight:
                best_fs_weight = w
                best_ledger = ledger
                
        if best_ledger:
            # Boundary inclusivity >=
            if best_fs_weight >= self.weights["T_upper"]:
                self.consumed_ledger_ids.add(best_ledger.get('txn_id'))
                return MatchResult(decision="match", matched_ledger_id=best_ledger.get('txn_id'), confidence=0.9)
            elif best_fs_weight >= self.weights["T_lower"]:
                # Tier 3 (LLM)
                llm_res = self.llm_agent.resolve(bank_record, [best_ledger])
                
                if llm_res.get("decision") == "match":
                    self.consumed_ledger_ids.add(llm_res.get("ledger_id"))
                    
                return MatchResult(
                    decision=llm_res.get("decision"),
                    matched_ledger_id=llm_res.get("ledger_id"),
                    reason=llm_res.get("reason"),
                    confidence=llm_res.get("confidence"),
                    is_fallback=llm_res.get("is_fallback", False),
                    llm_called=llm_res.get("llm_called", False)
                )
            else:
                # Tier 4
                return MatchResult(decision="unresolved", reason="FS_WEIGHT_LOW", confidence=0.1)
                
        return MatchResult(decision="unresolved", reason="NO_CANDIDATE", confidence=0.0)
