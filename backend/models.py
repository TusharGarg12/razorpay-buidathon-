from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal

class BankRecord(BaseModel):
    txn_id: str
    date: str
    amount: float
    description: str
    reference: str
    currency: str = "INR"

class LedgerRecord(BaseModel):
    txn_id: str
    date: str
    amount: float
    description: str
    invoice_id: str
    currency: str = "INR"

class MatchResult(BaseModel):
    decision: Literal["match", "unresolved"]
    matched_ledger_id: Optional[str] = None
    reason: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    is_fallback: bool = False
    llm_called: bool = False
    
class ExceptionRecord(BaseModel):
    bank_txn_id: str
    reason_code: str
    detail: str

class PipelineProgress(BaseModel):
    step: str
    label: str

class ReconciliationStats(BaseModel):
    total_bank_records: int
    total_ledger_records: int
    matches: int
    exceptions: int
    tp: int = Field(default=0)
    fp: int = Field(default=0)
    fn: int = Field(default=0)
    precision: float
    recall: float
    f1_score: float
