from typing import List, Dict, Any

def validate_input_data(records: List[Dict[str, Any]], record_type: str = "Bank"):
    """
    Validates input data for structural integrity before reconciliation.
    """
    if not records:
        raise ValueError(f"{record_type} records file is empty.")
        
    seen_ids = set()
    for rec in records:
        tid = rec.get("txn_id")
        if not tid:
            raise ValueError(f"{record_type} record missing txn_id: {rec}")
            
        if tid in seen_ids:
            raise ValueError(f"Duplicate {record_type} txn_id found: {tid}")
        seen_ids.add(tid)
