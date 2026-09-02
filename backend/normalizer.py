import re
from typing import Dict, Any

from datetime import datetime

# PRODUCTION NOTE: these FX rates are hardcoded mocks for demo purposes.
# In production, replace with a call to a live FX service (e.g. Open Exchange Rates,
# fixer.io, or your bank's FX API) to get accurate, up-to-date rates.
_FX_RATES_TO_INR = {"USD": 83.0, "EUR": 90.0, "GBP": 105.0, "INR": 1.0}

def normalize_amount(amount: float, from_curr: str = "INR", to_curr: str = "INR") -> float:
    amt = float(amount)
    if from_curr.upper() != to_curr.upper():
        rate_from = _FX_RATES_TO_INR.get(from_curr.upper(), 1.0)
        rate_to = _FX_RATES_TO_INR.get(to_curr.upper(), 1.0)
        amt = (amt * rate_from) / rate_to
    return round(amt, 2)

def normalize_date(date_str: str) -> str:
    # Explicitly enforce YYYY-MM-DD format
    d = date_str.strip()
    try:
        datetime.strptime(d, "%Y-%m-%d")
        return d
    except ValueError:
        raise ValueError(f"Ambiguous or unparseable date format: {d}. Expected YYYY-MM-DD.")

def normalize_description(desc: str) -> str:
    desc = desc.lower()
    # Strip legal suffixes only if they appear at the end of the string to avoid over-stripping
    # e.g., "corp networks" should keep "corp", but "abc corp" -> "abc"
    desc = re.sub(r'\b(inc|corp|co|llc|ltd)\b\.?$', '', desc)
    desc = re.sub(r'[^a-z0-9 ]', '', desc)
    return " ".join(desc.split())

def tfidf_summarize(desc: str, max_tokens: int = 20) -> str:
    """
    Return the top-N tokens from `desc` ranked by their TF-IDF score.
    Falls back to simple truncation when sklearn is unavailable or the
    corpus is too small to fit a vectorizer.
    """
    tokens = desc.split()
    if len(tokens) <= max_tokens:
        return desc  # nothing to trim

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np

        # Fit on the single document; gives IDF = 1 for all terms but still
        # provides useful TF weighting to surface high-frequency key tokens.
        vec = TfidfVectorizer(use_idf=False, norm="l1")
        tfidf_matrix = vec.fit_transform([desc])
        feature_names = vec.get_feature_names_out()
        scores = tfidf_matrix.toarray()[0]

        # Build token→max_score map (handles multi-word tokens gracefully)
        score_map = {feat: score for feat, score in zip(feature_names, scores)}

        # Sort original tokens by their TF-IDF score (descending)
        ranked = sorted(
            tokens,
            key=lambda t: score_map.get(t.lower(), 0.0),
            reverse=True,
        )
        # Take top-N, then restore original order for readability
        top_set = set(ranked[:max_tokens])
        return " ".join(t for t in tokens if t in top_set)
    except Exception:
        # Graceful fallback: simple head truncation
        return " ".join(tokens[:max_tokens])

def serialize_for_llm(record: Dict[str, Any], is_bank: bool) -> str:
    prefix = "Bank: " if is_bank else "Ledger: "
    date_val = str(record['date'])
    amt = float(record['amount'])
    amt_val = f"{amt:.2f}"
    desc_val = tfidf_summarize(str(record.get('description', '')))
    
    return f"{prefix}[CLS] [COL] date [VAL] [DATE]{date_val}[/DATE] [COL] amount [VAL] [AMT]{amt_val}[/AMT] [COL] desc [VAL] [DESC]{desc_val}[/DESC] [SEP]"
