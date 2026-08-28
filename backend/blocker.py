import numpy as np
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime
from normalizer import normalize_description

class DeepBlocker:
    def __init__(self, top_k: int = 5, amount_tolerance: float = 0.05, date_tolerance_days: int = 5):
        self.top_k = top_k
        self.amount_tolerance = amount_tolerance
        self.date_tolerance = date_tolerance_days
        self.vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(3,3), min_df=1)
        self.ledger_embeddings = None
        self.ledger_records = []

    def fit(self, ledger_records: List[Dict[str, Any]]):
        self.ledger_records = ledger_records
        corpus = [normalize_description(str(r.get('description', ''))) for r in ledger_records]
        
        # Ensure we have at least something to fit
        if not corpus:
            corpus = ["dummy"]
            
        # Fit SIF (Simplified via TF-IDF trigrams)
        self.ledger_embeddings = self.vectorizer.fit_transform(corpus)

    def get_candidates(self, bank_record: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.ledger_records:
            return []
            
        b_desc_raw = str(bank_record.get('description', '')).strip()
        if not b_desc_raw:
            b_desc_raw = "[EMPTY]"
            
        b_desc = normalize_description(b_desc_raw)
        b_vec = self.vectorizer.transform([b_desc])
        sims = cosine_similarity(b_vec, self.ledger_embeddings).flatten()
        
        b_amt = float(bank_record.get('amount', 0))
        
        # Safe date parsing
        try:
            b_date_str = str(bank_record.get('date', '1970-01-01'))
            b_date = datetime.strptime(b_date_str, "%Y-%m-%d")
        except ValueError:
            # If unparseable date, fallback
            b_date = datetime.strptime('1970-01-01', "%Y-%m-%d")
        
        candidates = []
        
        # 1. First, always add exact amount matches (this fixes 0% cosine similarity on completely different text)
        for i, l_rec in enumerate(self.ledger_records):
            l_amt = float(l_rec.get('amount', 0))
            if abs(b_amt - l_amt) < 0.01:
                l_rec_copy = dict(l_rec)
                l_rec_copy['_sim_score'] = sims[i]
                candidates.append(l_rec_copy)
                
        # 2. Add top-K text similarity matches
        sorted_indices = np.argsort(sims)[::-1]
        for idx in sorted_indices:
            # Floor similarity check
            if sims[idx] < 0.1 and not candidates:
                # If similarity is very low and no exact amounts matched, skip adding text matches
                continue
                
            if len(candidates) >= self.top_k + 5: # limit total candidates
                break
                
            l_rec = self.ledger_records[idx]
            
            try:
                l_date = datetime.strptime(str(l_rec.get('date', '1970-01-01')), "%Y-%m-%d")
            except ValueError:
                l_date = datetime.strptime('1970-01-01', "%Y-%m-%d")
            
            # Avoid duplicates if already added by exact amount
            if any(c.get('txn_id') == l_rec.get('txn_id') for c in candidates):
                continue
                
            date_diff = abs((b_date - l_date).days)
            if date_diff <= self.date_tolerance:
                l_rec_copy = dict(l_rec)
                l_rec_copy['_sim_score'] = sims[idx]
                candidates.append(l_rec_copy)
                
        return candidates
