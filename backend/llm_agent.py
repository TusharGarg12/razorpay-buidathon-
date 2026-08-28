import os
import json
import time
import random
import httpx
import jellyfish
from typing import Dict, Any, Tuple, List
from pydantic import BaseModel, Field
from normalizer import serialize_for_llm
import config

class LLMResponse(BaseModel):
    decision: str = Field(pattern="^(match|unresolved)$")
    ledger_id: str = Field(default=None)
    reason: str = Field(default="")
    confidence: float = Field(ge=0.0, le=1.0)

class OllamaAgent:
    def __init__(self, host="http://localhost:11434", model="qwen2.5:latest"):
        self.host = host
        self.model = model
        self.client = httpx.Client(timeout=30.0)
        
    def heuristic_fallback(self, bank_rec: Dict[str, Any], ledger_rec: Dict[str, Any]) -> Tuple[str, float, str]:
        # Fallback if API fails: confidence = 0.5*amt_score + 0.25*date_score + 0.25*desc_jw_score
        # Calculate amount score (1.0 if identical, decays otherwise)
        from normalizer import normalize_amount
        b_curr = bank_rec.get('currency', 'INR')
        l_curr = ledger_rec.get('currency', 'INR')
        b_amt = normalize_amount(bank_rec.get('amount', 0), b_curr, 'INR')
        l_amt = normalize_amount(ledger_rec.get('amount', 0), l_curr, 'INR')
        amt_diff = abs(b_amt - l_amt)
        # Apply absolute-difference floor of 4000.0 INR (approx $50 USD)
        if amt_diff > 4000.0:
            amt_score = 0.0
        else:
            # 0.01 tolerance is in INR units since amounts are normalized
            amt_score = 1.0 if amt_diff < 0.01 else max(0.0, 1.0 - (amt_diff / max(b_amt, 1.0)))
        
        # Calculate date score
        date_score = 1.0 if bank_rec.get("date") == ledger_rec.get("date") else 0.5
        
        # Calculate text score
        desc_jw_score = jellyfish.jaro_winkler_similarity(
            str(bank_rec.get("description", "")).lower(),
            str(ledger_rec.get("description", "")).lower()
        )
        
        confidence = (0.5 * amt_score) + (0.25 * date_score) + (0.25 * desc_jw_score)
        
        if confidence > 0.6:
            return ("match", confidence, "Fallback heuristic exceeded 0.6 threshold")
        else:
            return ("unresolved", confidence, "API_FALLBACK")

    def resolve(self, bank_rec: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Resolves ambiguity and returns a MatchResult dict."""
        
        # Guard against NO_CANDIDATE falling into LLM
        if not candidates:
            return {
                "decision": "unresolved",
                "reason": "NO_CANDIDATE",
                "confidence": 0.0,
                "ledger_id": None,
                "is_fallback": False,
                "llm_called": False
            }
            
        b_str = serialize_for_llm(bank_rec, is_bank=True)
        c_strs = []
        for i, c in enumerate(candidates):
            c_strs.append(f"Candidate {i} (ID: {c.get('txn_id')}): " + serialize_for_llm(c, is_bank=False))
            
        prompt = (
            f"You are a reconciliation assistant. Compare the bank record to the candidate ledger records.\n"
            f"Note: Allowable fee tolerance is {config.FEE_TOLERANCE*100}% and allowable date drift is {config.DATE_DRIFT} days.\n"
            "Return JSON matching this schema exactly:\n"
            '{"decision": "match"|"unresolved", "confidence": float, "reason": "string", "ledger_id": "string"}\n\n'
            f"Bank Record:\n{b_str}\n\n"
            "Candidates:\n" + "\n".join(c_strs)
        )
        
        max_retries = 3
        best_candidate = candidates[0]
        
        for attempt in range(max_retries):
            try:
                response = self.client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    }
                )
                response.raise_for_status()
                raw_text = response.json().get("response", "{}")
                
                # strip markdown code blocks if any
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:-3]
                elif raw_text.startswith("```"):
                    raw_text = raw_text[3:-3]
                    
                data = json.loads(raw_text.strip())
                
                # Explicit validation
                if "decision" not in data or "confidence" not in data:
                    raise ValueError("Malformed schema: missing required fields")
                
                if data["decision"] not in ["match", "unresolved"]:
                    raise ValueError("Malformed schema: invalid decision enum")
                    
                conf = float(data["confidence"])
                
                if data["decision"] == "match":
                    l_id = data.get("ledger_id")
                    if not any(c.get("txn_id") == l_id for c in candidates):
                        # Treat hallucinated ledger_id as a hard failure (unresolved)
                        data["decision"] = "unresolved"
                        data["ledger_id"] = None
                        data["reason"] = "HALLUCINATED_LEDGER_ID"
                    else:
                        data["ledger_id"] = l_id
                else:
                    data["ledger_id"] = None
                    
                data["is_fallback"] = False
                data["llm_called"] = True
                data["confidence"] = conf
                return data
                
            except httpx.ConnectError:
                # Transient error: backoff and retry
                if attempt < max_retries - 1:
                    time.sleep((2 ** attempt) + random.random())
                    continue
                else:
                    break
            except Exception as e:
                # Permanent error (JSON parse failed, malformed schema, etc)
                # We fallback immediately
                break
                
        # Heuristic Fallback
        decision, conf, reason = self.heuristic_fallback(bank_rec, best_candidate)
        return {
            "decision": decision,
            "reason": reason,
            "confidence": conf,
            "ledger_id": best_candidate.get("txn_id") if decision == "match" else None,
            "is_fallback": True,
            "llm_called": True
        }
