import re
from typing import Dict, Any

from datetime import datetime

def normalize_amount(amount: float, from_curr: str = "INR", to_curr: str = "INR") -> float:
    amt = float(amount)
    if from_curr.upper() != to_curr.upper():
        # Hardcoded mock FX rates for demo; in real prod, use an FX service
        rates = {"USD": 83.0, "EUR": 90.0, "GBP": 105.0, "INR": 1.0}
        rate_from = rates.get(from_curr.upper(), 1.0)
        rate_to = rates.get(to_curr.upper(), 1.0)
        # Convert to INR (base), then to target
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
    # Stub for TF-IDF summarization. For now, simple truncation.
    tokens = desc.split()
    return " ".join(tokens[:max_tokens])

def serialize_for_llm(record: Dict[str, Any], is_bank: bool) -> str:
    prefix = "Bank: " if is_bank else "Ledger: "
    date_val = str(record['date'])
    amt = float(record['amount'])
    amt_val = f"{amt:.2f}"
    desc_val = tfidf_summarize(str(record.get('description', '')))
    
    return f"{prefix}[CLS] [COL] date [VAL] [DATE]{date_val}[/DATE] [COL] amount [VAL] [AMT]{amt_val}[/AMT] [COL] desc [VAL] [DESC]{desc_val}[/DESC] [SEP]"
