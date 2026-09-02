"""
Reconciler — 4-tier pipeline supporting 1:1, 1:N, N:1, and N:M matching.

Pass order:
  Pass 1 — 1:1  : Exact (Tier 1) + Jaro-Winkler / Fellegi-Sunter (Tier 2) + LLM (Tier 3)
  Pass 2 — 1:N  : 1 bank  → subset of ledgers whose amounts sum to bank amount
  Pass 3 — N:1  : subset of banks → 1 ledger  (partial payments)
  Pass 4 — N:M  : group of banks ↔ group of ledgers (complex netting / batch)
  Exceptions    : all remaining unmatched bank records flagged with reason codes

The full 4-pass orchestration lives in main.py's event_stream().
This module exposes the matching primitives and the single-record
reconcile_record() entry point used by the streaming loop.
"""

import json
import os
import itertools
import jellyfish
from typing import List, Dict, Any, Optional, Set, Tuple

from models import MatchResult
from normalizer import normalize_amount, normalize_date
from llm_agent import OllamaAgent
import config

MAX_GROUP_SIZE = 5          # max records per side for group matching
GROUP_AMT_TOL = 0.03        # 3% tolerance when comparing group sums


class Reconciler:
    def __init__(self):
        self.llm_agent = OllamaAgent()

        # Sets of consumed IDs — prevents double-matching
        self.consumed_bank_ids: Set[str] = set()
        self.consumed_ledger_ids: Set[str] = set()

        # Load Fellegi-Sunter weights
        self.weights = {
            "amt":    {"agree": 4.0,  "disagree": -4.0},
            "date":   {"agree": 4.0,  "disagree": -3.0},
            "desc":   {"agree": 6.0,  "disagree": -3.0},
            "T_upper": 12.0,
            "T_lower": -3.0,
        }
        try:
            wf = os.path.join(os.path.dirname(__file__), "weights_benchrec.json")
            with open(wf, "r") as f:
                self.weights = json.load(f)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # Tier helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _tier_1_exact(self, bank: Dict, ledger: Dict) -> bool:
        b_curr = bank.get("currency", "INR")
        l_curr = ledger.get("currency", "INR")
        b_amt = normalize_amount(bank.get("amount", 0), b_curr, "INR")
        l_amt = normalize_amount(ledger.get("amount", 0), l_curr, "INR")

        if abs(b_amt - l_amt) < 0.01:
            try:
                b_date = normalize_date(str(bank.get("date", "")))
                l_date = normalize_date(str(ledger.get("date", "")))
                return b_date == l_date
            except ValueError:
                return False
        return False

    def _tier_2_fs_weight(self, bank: Dict, ledger: Dict) -> float:
        weight = 0.0

        # Amount component
        if "amount" not in bank or "amount" not in ledger:
            weight += self.weights["amt"]["disagree"]
        else:
            b_curr = bank.get("currency", "INR")
            l_curr = ledger.get("currency", "INR")
            b_amt = normalize_amount(bank.get("amount", 0), b_curr, "INR")
            l_amt = normalize_amount(ledger.get("amount", 0), l_curr, "INR")

            if (b_amt > 0 and l_amt < 0) or (b_amt < 0 and l_amt > 0):
                weight += self.weights["amt"]["disagree"]
            else:
                abs_diff = abs(abs(b_amt) - abs(l_amt))
                amt_diff_pct = abs_diff / max(abs(l_amt), 1.0)
                if amt_diff_pct <= config.FEE_TOLERANCE and abs_diff <= 4000.0:
                    weight += self.weights["amt"]["agree"]
                else:
                    weight += self.weights["amt"]["disagree"]

        # Date component
        try:
            from datetime import datetime
            b_date = normalize_date(str(bank.get("date", "")))
            l_date = normalize_date(str(ledger.get("date", "")))
            b_dt = datetime.strptime(b_date, "%Y-%m-%d")
            l_dt = datetime.strptime(l_date, "%Y-%m-%d")
            if abs((b_dt - l_dt).days) <= config.DATE_DRIFT:
                weight += self.weights["date"]["agree"]
            else:
                weight += self.weights["date"]["disagree"]
        except ValueError:
            weight += self.weights["date"]["disagree"]

        # Description component (Jaro-Winkler)
        b_desc = str(bank.get("description", "")).lower()
        l_desc = str(ledger.get("description", "")).lower()
        if not b_desc or not l_desc:
            weight += self.weights["desc"]["disagree"]
        else:
            jw = jellyfish.jaro_winkler_similarity(b_desc, l_desc)
            if jw >= 0.85:
                weight += self.weights["desc"]["agree"]
            else:
                weight += self.weights["desc"]["disagree"]

        return weight

    def _run_1v1(
        self,
        bank: Dict,
        candidates: List[Dict],
    ) -> Optional[MatchResult]:
        """
        Run Tier 1 → Tier 2 → Tier 3 for a single bank record against candidates.
        Returns MatchResult if resolved, None if unresolved.
        """
        unconsumed = [c for c in candidates if c.get("txn_id") not in self.consumed_ledger_ids]
        if not unconsumed:
            return None

        # Tier 1 — exact
        t1_hits = [l for l in unconsumed if self._tier_1_exact(bank, l)]
        if len(t1_hits) == 1:
            lid = t1_hits[0].get("txn_id")
            self.consumed_ledger_ids.add(lid)
            return MatchResult(
                decision="match",
                matched_ledger_id=lid,
                matched_ledger_ids=[lid],
                match_type="1:1",
                confidence=1.0,
            )
        if len(t1_hits) > 1:
            return MatchResult(
                decision="unresolved",
                reason="AMBIGUOUS_MULTI",
                match_type="1:1",
                confidence=0.5,
            )

        # Tier 2 — Fellegi-Sunter
        best_w = -999.0
        best_l = None
        for l in unconsumed:
            w = self._tier_2_fs_weight(bank, l)
            if w > best_w:
                best_w = w
                best_l = l

        if best_l is None:
            return None

        if best_w >= self.weights["T_upper"]:
            lid = best_l.get("txn_id")
            self.consumed_ledger_ids.add(lid)
            return MatchResult(
                decision="match",
                matched_ledger_id=lid,
                matched_ledger_ids=[lid],
                match_type="1:1",
                confidence=0.9,
            )

        if best_w >= self.weights["T_lower"]:
            # Tier 3 — LLM
            llm = self.llm_agent.resolve(bank, [best_l])
            if llm.get("decision") == "match":
                lid = llm.get("ledger_id")
                self.consumed_ledger_ids.add(lid)
                return MatchResult(
                    decision="match",
                    matched_ledger_id=lid,
                    matched_ledger_ids=[lid],
                    match_type="1:1",
                    reason=llm.get("reason"),
                    confidence=llm.get("confidence", 0.7),
                    is_fallback=llm.get("is_fallback", False),
                    llm_called=True,
                    llm_source=llm.get("llm_source"),
                )
            return MatchResult(
                decision="unresolved",
                reason=llm.get("reason", "LLM_UNRESOLVED"),
                match_type="1:1",
                confidence=llm.get("confidence", 0.0),
                llm_called=True,
                llm_source=llm.get("llm_source"),
            )

        # Tier 4
        return MatchResult(decision="unresolved", reason="FS_WEIGHT_LOW", match_type="1:1", confidence=0.1)

    # ══════════════════════════════════════════════════════════════════════════
    # Group matching helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _amounts_sum_match(self, target_amt: float, group_amts: List[float]) -> bool:
        """Check if sum(group_amts) ≈ target_amt within GROUP_AMT_TOL."""
        s = sum(group_amts)
        tol = max(abs(target_amt) * GROUP_AMT_TOL, 1.0)
        return abs(s - target_amt) <= tol

    def _date_window_ok(self, dates: List[str], window_days: int = None) -> bool:
        """All dates in the group are within window_days of each other."""
        from datetime import datetime
        w = window_days if window_days is not None else config.DATE_DRIFT * 2
        try:
            dts = [datetime.strptime(normalize_date(d), "%Y-%m-%d") for d in dates]
            span = (max(dts) - min(dts)).days
            return span <= w
        except Exception:
            return True  # don't reject on bad dates

    def _find_1_to_N(
        self,
        bank: Dict,
        ledger_pool: List[Dict],
    ) -> Optional[MatchResult]:
        """
        1 bank → multiple ledgers: find a subset of available ledgers
        whose amounts sum to bank amount (within tolerance).
        """
        b_curr = bank.get("currency", "INR")
        b_amt = normalize_amount(bank.get("amount", 0), b_curr, "INR")

        available = [
            l for l in ledger_pool
            if l.get("txn_id") not in self.consumed_ledger_ids
        ]

        for size in range(2, min(MAX_GROUP_SIZE + 1, len(available) + 1)):
            for combo in itertools.combinations(available, size):
                l_amts = [
                    normalize_amount(l.get("amount", 0), l.get("currency", "INR"), "INR")
                    for l in combo
                ]
                if self._amounts_sum_match(b_amt, l_amts):
                    # Check date window
                    all_dates = [str(l.get("date", "")) for l in combo] + [str(bank.get("date", ""))]
                    if not self._date_window_ok(all_dates):
                        continue
                    # Accept this group
                    ids = [l.get("txn_id") for l in combo]
                    for lid in ids:
                        self.consumed_ledger_ids.add(lid)
                    return MatchResult(
                        decision="match",
                        matched_ledger_id=ids[0],
                        matched_ledger_ids=ids,
                        match_type="1:N",
                        confidence=0.92,
                    )
        return None

    def _find_N_to_1(
        self,
        bank_pool: List[Dict],
        ledger: Dict,
    ) -> Optional[Tuple[List[str], MatchResult]]:
        """
        N banks → 1 ledger: find a subset of bank records whose amounts
        sum to the ledger amount. Returns (bank_ids, MatchResult) or None.
        """
        l_curr = ledger.get("currency", "INR")
        l_amt = normalize_amount(ledger.get("amount", 0), l_curr, "INR")
        lid = ledger.get("txn_id")

        if lid in self.consumed_ledger_ids:
            return None

        available_banks = [
            b for b in bank_pool
            if b.get("txn_id") not in self.consumed_bank_ids
        ]

        for size in range(2, min(MAX_GROUP_SIZE + 1, len(available_banks) + 1)):
            for combo in itertools.combinations(available_banks, size):
                b_amts = [
                    normalize_amount(b.get("amount", 0), b.get("currency", "INR"), "INR")
                    for b in combo
                ]
                if self._amounts_sum_match(l_amt, b_amts):
                    all_dates = [str(b.get("date", "")) for b in combo] + [str(ledger.get("date", ""))]
                    if not self._date_window_ok(all_dates):
                        continue
                    bank_ids = [b.get("txn_id") for b in combo]
                    self.consumed_ledger_ids.add(lid)
                    for bid in bank_ids:
                        self.consumed_bank_ids.add(bid)
                    result = MatchResult(
                        decision="match",
                        matched_ledger_id=lid,
                        matched_ledger_ids=[lid],
                        matched_bank_ids=bank_ids,
                        match_type="N:1",
                        confidence=0.92,
                    )
                    return (bank_ids, result)
        return None

    def _find_N_to_M(
        self,
        bank_pool: List[Dict],
        ledger_pool: List[Dict],
    ) -> List[Tuple[List[str], List[str], MatchResult]]:
        """
        N banks ↔ M ledgers: group matching where sums must be equal.
        Returns list of (bank_ids, ledger_ids, MatchResult).
        Only considers groups of size 2–MAX_GROUP_SIZE per side.
        """
        results = []

        avail_banks = [b for b in bank_pool if b.get("txn_id") not in self.consumed_bank_ids]
        avail_ledgers = [l for l in ledger_pool if l.get("txn_id") not in self.consumed_ledger_ids]

        if len(avail_banks) < 2 or len(avail_ledgers) < 2:
            return results

        for bs in range(2, min(MAX_GROUP_SIZE + 1, len(avail_banks) + 1)):
            for b_combo in itertools.combinations(avail_banks, bs):
                # Skip if any already consumed
                if any(b.get("txn_id") in self.consumed_bank_ids for b in b_combo):
                    continue

                b_sum = sum(
                    normalize_amount(b.get("amount", 0), b.get("currency", "INR"), "INR")
                    for b in b_combo
                )

                for ls in range(2, min(MAX_GROUP_SIZE + 1, len(avail_ledgers) + 1)):
                    for l_combo in itertools.combinations(avail_ledgers, ls):
                        if any(l.get("txn_id") in self.consumed_ledger_ids for l in l_combo):
                            continue

                        l_sum = sum(
                            normalize_amount(l.get("amount", 0), l.get("currency", "INR"), "INR")
                            for l in l_combo
                        )

                        if not self._amounts_sum_match(b_sum, [l_sum]):
                            continue

                        all_dates = (
                            [str(b.get("date", "")) for b in b_combo]
                            + [str(l.get("date", "")) for l in l_combo]
                        )
                        if not self._date_window_ok(all_dates):
                            continue

                        bank_ids = [b.get("txn_id") for b in b_combo]
                        ledger_ids = [l.get("txn_id") for l in l_combo]

                        for bid in bank_ids:
                            self.consumed_bank_ids.add(bid)
                        for lid in ledger_ids:
                            self.consumed_ledger_ids.add(lid)

                        mr = MatchResult(
                            decision="match",
                            matched_ledger_id=ledger_ids[0],
                            matched_ledger_ids=ledger_ids,
                            matched_bank_ids=bank_ids,
                            match_type="N:M",
                            confidence=0.88,
                        )
                        results.append((bank_ids, ledger_ids, mr))
                        # Don't break — let the loop consume all non-overlapping groups
        return results

    # ══════════════════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════════════════

    def reconcile_record(
        self,
        bank_record: Dict,
        candidate_ledgers: List[Dict],
    ) -> MatchResult:
        """
        Single-record 1:1 entry point used by the SSE streaming loop in main.py.

        The full 4-pass pipeline (1:1 → 1:N → N:1 → N:M) is orchestrated in
        main.py's event_stream(), which streams progress events to the UI.
        This method handles only one bank record against its pre-blocked candidate
        ledgers (Tier 1 → Tier 2 → Tier 3).
        """
        if not candidate_ledgers:
            return MatchResult(decision="unresolved", reason="NO_CANDIDATE", match_type="1:1", confidence=0.0)

        unconsumed = [c for c in candidate_ledgers if c.get("txn_id") not in self.consumed_ledger_ids]
        if not unconsumed:
            return MatchResult(decision="unresolved", reason="NO_UNCONSUMED_CANDIDATES", match_type="1:1", confidence=0.0)

        result = self._run_1v1(bank_record, unconsumed)
        if result is not None:
            return result

        return MatchResult(decision="unresolved", reason="NO_CANDIDATE", match_type="1:1", confidence=0.0)
