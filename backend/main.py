from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncio
import json
import csv
import os
import io
import tempfile
import shutil
from dotenv import load_dotenv
load_dotenv(override=False)

from models import ReconciliationStats, ExceptionRecord
from blocker import DeepBlocker
from reconciler import Reconciler
from scorer import PipelineScorer
from qa_agent import QAAgent
from validators import validate_input_data
from splitter import is_benchrec_format, split_benchrec_bytes

app = FastAPI()

# Respect ALLOWED_ORIGINS env var; fall back to wildcard only for local dev.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
_allow_origins = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

qa = QAAgent()

# ── Thread-safe last-result cache ─────────────────────────────────────────────
# asyncio.Lock prevents concurrent reconciliation runs from corrupting the cache.
_result_lock = asyncio.Lock()
last_stats = None
last_matched_pairs = []
last_exceptions = []


def load_data(path):
    data = []
    if os.path.exists(path):
        with open(path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    return data


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.get("/health")
async def health():
    return {"status": "ok"}


async def validate_csv_upload(upload_file: UploadFile, file_label: str, allow_benchrec: bool = False):
    upload_file.file.seek(0, 2)
    if upload_file.file.tell() > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail={"type": "error", "message": f"{file_label} file exceeds 100MB limit"})
    await upload_file.seek(0)
    
    first_line = upload_file.file.readline().decode('utf-8-sig', errors='ignore')
    await upload_file.seek(0)
    cols = [c.lower().strip() for c in next(csv.reader(io.StringIO(first_line)), [])]
    
    # Accept either standard format (txn_id) or BenchRec format (A_transactionType + B_transactionType)
    is_standard = "txn_id" in cols
    is_benchrec = allow_benchrec and ("a_transactiontype" in cols and "b_transactiontype" in cols)
    
    if not is_standard and not is_benchrec:
        raise HTTPException(status_code=400, detail={"type": "error", "message": f"Invalid {file_label.lower()} CSV format: missing txn_id column (or A_transactionType/B_transactionType for BenchRec format)"})
    
    return "benchrec" if is_benchrec else "standard"

@app.post("/reconcile/stream")
async def reconcile_stream(
    bank_file: Optional[UploadFile] = File(None),
    ledger_file: Optional[UploadFile] = File(None),
    combined_file: Optional[UploadFile] = File(None)
):
    # Three modes:
    # 1. combined_file only → BenchRec single-file split
    # 2. bank_file + ledger_file → standard two-file upload
    # 3. No files → demo data from data/bank.csv + data/ledger.csv
    
    has_combined = combined_file is not None
    has_pair = bank_file is not None or ledger_file is not None
    
    if has_combined and has_pair:
        raise HTTPException(status_code=400, detail={"type": "error", "message": "Upload either a single combined file OR separate bank/ledger files, not both"})
    
    if has_pair and (bool(bank_file) != bool(ledger_file)):
        raise HTTPException(status_code=400, detail={"type": "error", "message": "Both bank and ledger files are required"})
        
    temp_dir = None
    bank_path = "data/bank.csv"
    ledger_path = "data/ledger.csv"
    preloaded_bank = None
    preloaded_ledger = None
    
    if has_combined:
        # ── Single-file BenchRec path ──────────────────────────────────────────
        try:
            fmt = await validate_csv_upload(combined_file, "Combined", allow_benchrec=True)
            if fmt != "benchrec":
                raise HTTPException(status_code=400, detail={"type": "error", "message": "Single-file upload requires BenchRec format (A_transactionType/B_transactionType columns)"})
            
            content = await combined_file.read()
            preloaded_bank, preloaded_ledger = split_benchrec_bytes(content)
            
            if not preloaded_bank or not preloaded_ledger:
                raise HTTPException(status_code=400, detail={"type": "error", "message": "BenchRec file contains no A-side or B-side records"})
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail={"type": "error", "message": f"Error parsing combined file: {str(e)}"})
    elif bank_file and ledger_file:
        # ── Standard two-file path ─────────────────────────────────────────────
        try:
            await validate_csv_upload(bank_file, "Bank")
            await validate_csv_upload(ledger_file, "Ledger")
                
            temp_dir = tempfile.mkdtemp()
            bank_path = os.path.join(temp_dir, "bank.csv")
            ledger_path = os.path.join(temp_dir, "ledger.csv")
            
            with open(bank_path, "wb") as f:
                shutil.copyfileobj(bank_file.file, f)
            with open(ledger_path, "wb") as f:
                shutil.copyfileobj(ledger_file.file, f)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail={"type": "error", "message": f"Error parsing uploaded files: {str(e)}"})

    async def event_stream(b_path, l_path, t_dir, pre_bank=None, pre_ledger=None):
        try:
            global last_stats, last_matched_pairs, last_exceptions
    
            yield sse({"type": "status", "step": "Initializing pipeline…"})
            await asyncio.sleep(0.3)
    
            # ── Load data ──────────────────────────────────────────────────────────
            if pre_bank is not None and pre_ledger is not None:
                bank_data = pre_bank
                ledger_data = pre_ledger
            else:
                bank_data   = load_data(b_path)
                ledger_data = load_data(l_path)

            if not bank_data or not ledger_data:
                yield sse({"type": "error", "message": "Data files missing"})
                return

            try:
                validate_input_data(bank_data, "Bank")
                validate_input_data(ledger_data, "Ledger")
            except ValueError as ve:
                yield sse({"type": "error", "message": str(ve)})
                return

            yield sse({"type": "counts", "bank": len(bank_data), "ledger": len(ledger_data)})
            await asyncio.sleep(0.2)

            # ── Blocking ───────────────────────────────────────────────────────────
            yield sse({"type": "status", "step": "Blocking Pre-Filter (DeepBlocker)…"})
            await asyncio.sleep(0.3)
            blocker = DeepBlocker()
            blocker.fit(ledger_data)

            # ── Pass 1: 1:1 streaming ──────────────────────────────────────────────
            yield sse({"type": "status", "step": "Pass 1 — 1:1 matching (Tier 1 → 2 → 3)…"})
            await asyncio.sleep(0.2)

            reconciler = Reconciler()
            matched_pairs_raw = []
            exceptions_raw    = []
            unresolved_reasons = {}
            total = len(bank_data)

            for i, b_rec in enumerate(bank_data):
                candidates = blocker.get_candidates(b_rec)
                res = reconciler.reconcile_record(b_rec, candidates)

                bid = b_rec["txn_id"]

                if res.decision == "match":
                    reconciler.consumed_bank_ids.add(bid)
                    pair = {
                        "bank_txn_id":   bid,
                        "ledger_txn_ids": res.matched_ledger_ids or [res.matched_ledger_id],
                        "match_type":    res.match_type or "1:1",
                        "confidence":    res.confidence,
                        "llm_source":    res.llm_source,
                        "is_fallback":   res.is_fallback,
                        "tier": (
                            "3" if res.llm_called
                            else ("1" if res.confidence == 1.0 else "2")
                        ),
                    }
                    matched_pairs_raw.append(pair)
                    # Stream the individual match event for the UI
                    yield sse({
                        "type":    "record",
                        "bank_txn_id":   bid,
                        "ledger_txn_ids": pair["ledger_txn_ids"],
                        "match_type":    pair["match_type"],
                        "tier":          pair["tier"],
                        "confidence":    pair["confidence"],
                        "llm_source":    pair["llm_source"],
                        "reason":        res.reason,
                    })
                    # Don't add to exceptions yet — may still be resolved in group passes
                    unresolved_reasons[bid] = res.reason

                yield sse({
                    "type":       "progress",
                    "processed":  i + 1,
                    "total":      total,
                    "matched":    len(matched_pairs_raw),
                    "exceptions": 0,  # will be updated after group passes
                })
                await asyncio.sleep(0.05)

            # ── Pass 2: 1:N ────────────────────────────────────────────────────────
            yield sse({"type": "status", "step": "Pass 2 — 1:N group matching…"})
            await asyncio.sleep(0.2)

            unmatched_banks  = [b for b in bank_data if b["txn_id"] not in reconciler.consumed_bank_ids]
            avail_ledgers    = [l for l in ledger_data if l["txn_id"] not in reconciler.consumed_ledger_ids]

            for bank in unmatched_banks:
                bid = bank["txn_id"]
                if bid in reconciler.consumed_bank_ids:
                    continue
                res = reconciler._find_1_to_N(bank, avail_ledgers)
                if res and res.decision == "match":
                    reconciler.consumed_bank_ids.add(bid)
                    avail_ledgers = [l for l in avail_ledgers if l["txn_id"] not in reconciler.consumed_ledger_ids]
                    pair = {
                        "bank_txn_id":   bid,
                        "ledger_txn_ids": res.matched_ledger_ids,
                        "match_type":    "1:N",
                        "confidence":    res.confidence,
                        "llm_source":    None,
                        "is_fallback":   False,
                        "tier":          "2",
                    }
                    matched_pairs_raw.append(pair)
                    yield sse({"type": "record", **pair, "reason": None})
                await asyncio.sleep(0.02)

            # ── Pass 3: N:1 ────────────────────────────────────────────────────────
            yield sse({"type": "status", "step": "Pass 3 — N:1 group matching…"})
            await asyncio.sleep(0.2)

            unmatched_banks = [b for b in bank_data if b["txn_id"] not in reconciler.consumed_bank_ids]
            avail_ledgers   = [l for l in ledger_data if l["txn_id"] not in reconciler.consumed_ledger_ids]

            for ledger in avail_ledgers:
                r = reconciler._find_N_to_1(unmatched_banks, ledger)
                if r:
                    bank_ids, result = r
                    unmatched_banks = [b for b in unmatched_banks if b["txn_id"] not in reconciler.consumed_bank_ids]
                    for bid in bank_ids:
                        pair = {
                            "bank_txn_id":    bid,
                            "ledger_txn_ids": result.matched_ledger_ids,
                            "matched_bank_ids": result.matched_bank_ids,
                            "match_type":     "N:1",
                            "confidence":     result.confidence,
                            "llm_source":     None,
                            "is_fallback":    False,
                            "tier":           "2",
                        }
                        matched_pairs_raw.append(pair)
                        yield sse({"type": "record", **pair, "reason": None})
                await asyncio.sleep(0.02)

            # ── Pass 4: N:M ────────────────────────────────────────────────────────
            yield sse({"type": "status", "step": "Pass 4 — N:M group matching…"})
            await asyncio.sleep(0.2)

            unmatched_banks = [b for b in bank_data if b["txn_id"] not in reconciler.consumed_bank_ids]
            avail_ledgers   = [l for l in ledger_data if l["txn_id"] not in reconciler.consumed_ledger_ids]
            nm_results = reconciler._find_N_to_M(unmatched_banks, avail_ledgers)

            for bank_ids, ledger_ids, result in nm_results:
                for bid in bank_ids:
                    pair = {
                        "bank_txn_id":    bid,
                        "ledger_txn_ids": ledger_ids,
                        "matched_bank_ids": bank_ids,
                        "match_type":     "N:M",
                        "confidence":     result.confidence,
                        "llm_source":     None,
                        "is_fallback":    False,
                        "tier":           "2",
                    }
                    matched_pairs_raw.append(pair)
                    yield sse({"type": "record", **pair, "reason": None})
                await asyncio.sleep(0.02)

            # ── Exceptions for all remaining unmatched bank records ────────────────
            for bank in bank_data:
                bid = bank["txn_id"]
                if bid not in reconciler.consumed_bank_ids:
                    reason = unresolved_reasons.get(bid) or "NO_CANDIDATE"
                    if reason == "NO_CANDIDATE":
                        detail = "No matching ledger record found after all passes"
                    elif reason == "AMBIGUOUS_MULTI":
                        detail = "Multiple exact matches found, requiring human review"
                    elif reason == "LLM_UNRESOLVED":
                        detail = "AI reviewed but could not confidently match"
                    elif reason == "FS_WEIGHT_LOW":
                        detail = "Candidate similarity too low for AI review"
                    else:
                        detail = "Failed to match after AI reasoning"
                        
                    exceptions_raw.append({
                        "bank_txn_id": bid,
                        "reason_code": reason,
                        "detail": detail,
                    })

            # ── Score ──────────────────────────────────────────────────────────────
            yield sse({"type": "status", "step": "Scoring Engine…"})
            await asyncio.sleep(0.3)

            # Build the simple list-of-tuples expected by legacy scorer signature
            simple_pairs = [
                (p["bank_txn_id"], (p.get("ledger_txn_ids") or [None])[0])
                for p in matched_pairs_raw
            ]

            scorer = PipelineScorer()
            stats = scorer.score(matched_pairs_raw, exceptions_raw, total, len(ledger_data))

            # Acquire lock before writing shared state so concurrent runs don't
            # interleave results from two different reconciliation jobs.
            async with _result_lock:
                last_stats = stats
                last_matched_pairs = matched_pairs_raw
                last_exceptions = exceptions_raw

            yield sse({
                "type":    "complete",
                "stats":   stats.model_dump(),
                "matches": matched_pairs_raw,
                "exceptions": exceptions_raw,
            })
        finally:
            if t_dir and os.path.exists(t_dir):
                shutil.rmtree(t_dir, ignore_errors=True)

    return StreamingResponse(event_stream(bank_path, ledger_path, temp_dir, preloaded_bank, preloaded_ledger), media_type="text/event-stream")


@app.get("/last-result")
async def last_result():
    async with _result_lock:
        if not last_stats:
            return {"error": "No reconciliation run yet"}
        return {
            "stats":      last_stats.model_dump(),
            "matches":    last_matched_pairs,
            "exceptions": last_exceptions,
        }


class QARequest(BaseModel):
    query: str

@app.post("/api/qa")
async def ask_qa(req: QARequest):
    context = "No recent reconciliation run available."
    if last_stats:
        mt_counts = last_stats.match_type_counts or {}
        context = (
            f"Total Bank: {last_stats.total_bank_records}, "
            f"Total Ledger: {last_stats.total_ledger_records}. "
            f"Matches: {last_stats.matches}. Exceptions: {last_stats.exceptions}. "
            f"Match types — 1:1: {mt_counts.get('1:1',0)}, "
            f"1:N: {mt_counts.get('1:N',0)}, N:1: {mt_counts.get('N:1',0)}, "
            f"N:M: {mt_counts.get('N:M',0)}. "
            f"Precision: {last_stats.precision:.2f}, "
            f"Recall: {last_stats.recall:.2f}, F1: {last_stats.f1_score:.2f}."
        )
    answer = qa.ask(req.query, context)
    return {"answer": answer}
