# Centralized Configuration for Reconciliation Rules

# MODEL EVALUATION NOTE:
# Ran Qwen vs Gemini side-by-side using model_eval.py on BenchRec clerical-zone records.
# Results showed Qwen confidence aligns reasonably well with Gemini (no systematic overconfidence).
# No threshold adjustment or penalty needed for Qwen relative to the 0.6 fallback threshold right now.

# Fee deduction tolerance (e.g. 0.02 = 2%).
# Note: Explicitly choosing 0.02 (2%) to resolve the prior 0.4-2% vs 0.4-2.5% drift discrepancy.
FEE_TOLERANCE = 0.02

# Maximum allowable date drift in days for a match to still be considered viable
# before incurring severe penalties or being rejected.
DATE_DRIFT = 3
