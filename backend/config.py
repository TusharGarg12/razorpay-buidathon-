# Centralized Configuration for Reconciliation Rules

# MODEL EVALUATION NOTE:
# Ran Qwen vs Gemini side-by-side using model_eval.py on a sample of 10 BenchRec records.
# CAVEAT: These 10 rows were a general sample from the 1:1 subset, NOT specifically filtered for ambiguous/clerical-zone records. 
# Results showed Qwen confidence aligns reasonably well with Gemini (no systematic overconfidence), but this decision 
# rests largely on non-ambiguous cases.
# No threshold adjustment or penalty needed for Qwen relative to the 0.6 fallback threshold right now, but 
# recommend re-running on a larger, strictly ambiguous subset if overconfidence is observed in production.

# Fee deduction tolerance (e.g. 0.02 = 2%).
# Note: Explicitly choosing 0.02 (2%) to resolve the prior 0.4-2% vs 0.4-2.5% drift discrepancy.
FEE_TOLERANCE = 0.02

# Maximum allowable date drift in days for a match to still be considered viable
# before incurring severe penalties or being rejected.
DATE_DRIFT = 3
