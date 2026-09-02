"""
LLM Agent — Ollama/Qwen2.5 primary, Gemini 2.0 Flash fallback (rate-limit aware), heuristic last resort.

Priority chain:
  1. Ollama (qwen2.5:latest at localhost:11434)  — zero API cost, fast
  2. Gemini 2.0 Flash                            — only called if Ollama fails; 429 triggers a 60-s cooldown
  3. Heuristic fallback                          — always works, no network dependency
"""

import os
import json
import time
import random
import threading
import httpx
import jellyfish
from typing import Dict, Any, Tuple, List, Optional
from pydantic import BaseModel, Field
from normalizer import serialize_for_llm
import config

# ─── Gemini rate-limit cooldown (module-level, thread-safe) ───────────────────
_gemini_lock = threading.Lock()
_gemini_blocked_until: float = 0.0          # epoch seconds; 0 = not blocked
GEMINI_COOLDOWN_SECONDS = 60                 # back-off window after a 429


def _gemini_is_blocked() -> bool:
    with _gemini_lock:
        return time.time() < _gemini_blocked_until


def _gemini_block():
    with _gemini_lock:
        global _gemini_blocked_until
        _gemini_blocked_until = time.time() + GEMINI_COOLDOWN_SECONDS
        print(f"[LLMAgent] Gemini rate-limited — blocking for {GEMINI_COOLDOWN_SECONDS}s")


class LLMResponse(BaseModel):
    decision: str = Field(pattern="^(match|unresolved)$")
    ledger_id: Optional[str] = Field(default=None)
    reason: str = Field(default="")
    confidence: float = Field(ge=0.0, le=1.0)


class LLMAgent:
    """
    Unified LLM agent.  Tries Ollama first, then Gemini (with rate-limit guard),
    then heuristic fallback.
    """

    def __init__(
        self,
        ollama_host: str = None,
        ollama_model: str = "qwen2.5:latest",
    ):
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.ollama_model = ollama_model
        self.client = httpx.Client(timeout=120.0)

        # Gemini client — only created if API key is present
        self._gemini_client = None
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=api_key)
            except Exception as e:
                print(f"[LLMAgent] Gemini init failed: {e}")

    # ─── Heuristic fallback ────────────────────────────────────────────────────
    def heuristic_fallback(
        self,
        bank_rec: Dict[str, Any],
        ledger_rec: Dict[str, Any],
    ) -> Tuple[str, float, str]:
        """
        confidence = 0.5*amt_score + 0.25*date_score + 0.25*desc_jw_score
        threshold  = 0.6
        """
        from normalizer import normalize_amount

        b_curr = bank_rec.get("currency", "INR")
        l_curr = ledger_rec.get("currency", "INR")
        b_amt = normalize_amount(bank_rec.get("amount", 0), b_curr, "INR")
        l_amt = normalize_amount(ledger_rec.get("amount", 0), l_curr, "INR")
        amt_diff = abs(b_amt - l_amt)

        if amt_diff > 4000.0:
            amt_score = 0.0
        else:
            amt_score = (
                1.0
                if amt_diff < 0.01
                else max(0.0, 1.0 - (amt_diff / max(b_amt, 1.0)))
            )

        date_score = 1.0 if bank_rec.get("date") == ledger_rec.get("date") else 0.5

        desc_jw_score = jellyfish.jaro_winkler_similarity(
            str(bank_rec.get("description", "")).lower(),
            str(ledger_rec.get("description", "")).lower(),
        )

        confidence = (0.5 * amt_score) + (0.25 * date_score) + (0.25 * desc_jw_score)

        if confidence > 0.6:
            return ("match", confidence, "Fallback heuristic exceeded 0.6 threshold")
        return ("unresolved", confidence, "API_FALLBACK")

    # ─── Build shared prompt ───────────────────────────────────────────────────
    def _build_prompt(self, bank_rec: Dict[str, Any], candidates: List[Dict[str, Any]]) -> str:
        b_str = serialize_for_llm(bank_rec, is_bank=True)
        c_strs = [
            f"Candidate {i} (ID: {c.get('txn_id')}): " + serialize_for_llm(c, is_bank=False)
            for i, c in enumerate(candidates)
        ]
        return (
            f"You are a financial reconciliation assistant.\n"
            f"Fee tolerance: {config.FEE_TOLERANCE * 100}% | Date drift: {config.DATE_DRIFT} days.\n"
            "Return ONLY valid JSON matching this schema (no markdown, no explanation):\n"
            '{"decision": "match"|"unresolved", "confidence": 0.0-1.0, '
            '"reason": "string", "ledger_id": "string or null"}\n\n'
            f"Bank Record:\n{b_str}\n\n"
            "Candidates:\n" + "\n".join(c_strs)
        )

    # ─── Parse raw LLM text → dict ─────────────────────────────────────────────
    def _parse_response(self, raw: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)

        if "decision" not in data or "confidence" not in data:
            raise ValueError("Missing required fields in LLM response")
        if data["decision"] not in ("match", "unresolved"):
            raise ValueError(f"Invalid decision: {data['decision']}")

        # Validate ledger_id is real
        if data["decision"] == "match":
            l_id = data.get("ledger_id")
            if not any(c.get("txn_id") == l_id for c in candidates):
                data["decision"] = "unresolved"
                data["ledger_id"] = None
                data["reason"] = "HALLUCINATED_LEDGER_ID"

        return data

    # ─── Ollama call ───────────────────────────────────────────────────────────
    def _call_ollama(self, prompt: str) -> str:
        resp = self.client.post(
            f"{self.ollama_host}/api/generate",
            json={
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
            headers={"ngrok-skip-browser-warning": "1"}
        )
        resp.raise_for_status()
        return resp.json().get("response", "{}")

    # ─── Gemini call ──────────────────────────────────────────────────────────
    def _call_gemini(self, prompt: str) -> str:
        if not self._gemini_client:
            raise RuntimeError("Gemini client not initialised")
        if _gemini_is_blocked():
            raise RuntimeError("Gemini is in rate-limit cooldown")

        try:
            response = self._gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
            )
            return response.text
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "resource_exhausted" in err_str or "rate" in err_str:
                _gemini_block()
            raise

    # ─── Main resolve entry point ─────────────────────────────────────────────
    def resolve(
        self,
        bank_rec: Dict[str, Any],
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Returns a dict with keys: decision, ledger_id, reason, confidence,
        is_fallback, llm_called, llm_source
        """
        if not candidates:
            return {
                "decision": "unresolved",
                "reason": "NO_CANDIDATE",
                "confidence": 0.0,
                "ledger_id": None,
                "is_fallback": False,
                "llm_called": False,
                "llm_source": "none",
            }

        prompt = self._build_prompt(bank_rec, candidates)
        best_candidate = candidates[0]
        max_retries = 3

        # ── 1. Try Ollama ──────────────────────────────────────────────────────
        for attempt in range(max_retries):
            try:
                raw = self._call_ollama(prompt)
                data = self._parse_response(raw, candidates)

                # Heuristic backstop against LLM overconfidence
                if data["decision"] == "match":
                    candidate = next(
                        (c for c in candidates if c.get("txn_id") == data.get("ledger_id")),
                        best_candidate,
                    )
                    backstop_dec, _, _ = self.heuristic_fallback(bank_rec, candidate)
                    if backstop_dec == "unresolved":
                        data["decision"] = "unresolved"
                        data["ledger_id"] = None
                        data["reason"] = "HEURISTIC_BACKSTOP_REJECTED"

                data["is_fallback"] = False
                data["llm_called"] = True
                data["llm_source"] = "ollama"
                return data

            except httpx.ConnectError:
                if attempt < max_retries - 1:
                    time.sleep((2 ** attempt) + random.random())
                    continue
                print("[LLMAgent] Ollama unreachable — trying Gemini fallback")
                break
            except Exception as e:
                print(f"[LLMAgent] Ollama error (attempt {attempt+1}): {e}")
                break  # Permanent error → skip to Gemini

        # ── 2. Try Gemini (if not rate-limited) ────────────────────────────────
        if self._gemini_client and not _gemini_is_blocked():
            try:
                raw = self._call_gemini(prompt)
                data = self._parse_response(raw, candidates)

                if data["decision"] == "match":
                    candidate = next(
                        (c for c in candidates if c.get("txn_id") == data.get("ledger_id")),
                        best_candidate,
                    )
                    backstop_dec, _, _ = self.heuristic_fallback(bank_rec, candidate)
                    if backstop_dec == "unresolved":
                        data["decision"] = "unresolved"
                        data["ledger_id"] = None
                        data["reason"] = "HEURISTIC_BACKSTOP_REJECTED"

                data["is_fallback"] = False
                data["llm_called"] = True
                data["llm_source"] = "gemini"
                return data

            except Exception as e:
                print(f"[LLMAgent] Gemini fallback failed: {e}")

        # ── 3. Heuristic last resort ───────────────────────────────────────────
        decision, conf, reason = self.heuristic_fallback(bank_rec, best_candidate)
        return {
            "decision": decision,
            "reason": reason,
            "confidence": conf,
            "ledger_id": best_candidate.get("txn_id") if decision == "match" else None,
            "is_fallback": True,
            "llm_called": True,
            "llm_source": "heuristic",
        }


# Backward-compat alias (reconciler.py imports OllamaAgent)
OllamaAgent = LLMAgent
