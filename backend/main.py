from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
import csv
import os
from dotenv import load_dotenv
load_dotenv(override=False)

from models import ReconciliationStats, ExceptionRecord
from blocker import DeepBlocker
from reconciler import Reconciler
from scorer import PipelineScorer
from qa_agent import QAAgent
from validators import validate_input_data

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

qa = QAAgent()
last_stats = None

def load_data(path):
    data = []
    if os.path.exists(path):
        with open(path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    return data

@app.post("/reconcile/stream")
async def reconcile_stream():
    global last_stats
    
    async def event_stream():
        yield f"data: {json.dumps({'type': 'status', 'step': 'Initializing pipeline...' })}\n\n"
        await asyncio.sleep(0.5)
        
        bank_data = load_data("data/bank.csv")
        ledger_data = load_data("data/ledger.csv")
        
        if not bank_data or not ledger_data:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Data files missing' })}\n\n"
            return
            
        try:
            validate_input_data(bank_data, "Bank")
            validate_input_data(ledger_data, "Ledger")
        except ValueError as ve:
            yield f"data: {json.dumps({'type': 'error', 'message': str(ve)})}\n\n"
            return
            
        yield f"data: {json.dumps({'type': 'status', 'step': 'Blocking Pre-Filter (DeepBlocker)...' })}\n\n"
        await asyncio.sleep(0.5)
        
        blocker = DeepBlocker()
        blocker.fit(ledger_data)
        
        reconciler = Reconciler()
        matched_pairs = []
        exceptions = []
        
        total = len(bank_data)
        
        for i, b_rec in enumerate(bank_data):
            # Step 1: Blocking
            candidates = blocker.get_candidates(b_rec)
            
            # Step 2: Reconcile
            res = reconciler.reconcile_record(b_rec, candidates)
            
            if res.decision == "match":
                matched_pairs.append((b_rec['txn_id'], res.matched_ledger_id))
            else:
                exceptions.append({
                    "bank_txn_id": b_rec['txn_id'],
                    "reason_code": res.reason,
                    "detail": "Failed in pipeline"
                })
                
            # Stream progress
            yield f"data: {json.dumps({'type': 'progress', 'processed': i+1, 'total': total, 'matched': len(matched_pairs), 'exceptions': len(exceptions)})}\n\n"
            await asyncio.sleep(0.1) # Simulate processing time for demo UI
            
        # Score
        yield f"data: {json.dumps({'type': 'status', 'step': 'Scoring Engine...' })}\n\n"
        await asyncio.sleep(0.5)
        
        scorer = PipelineScorer()
        stats = scorer.score(matched_pairs, exceptions, total, len(ledger_data))
        last_stats = stats
        
        # Complete
        yield f"data: {json.dumps({'type': 'complete', 'stats': stats.model_dump()})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

class QARequest(BaseModel):
    query: str

@app.post("/api/qa")
async def ask_qa(req: QARequest):
    context = "No recent reconciliation run available."
    if last_stats:
        context = f"Total Bank: {last_stats.total_bank_records}, Total Ledger: {last_stats.total_ledger_records}. Matches: {last_stats.matches}. Exceptions: {last_stats.exceptions}. Precision: {last_stats.precision:.2f}, Recall: {last_stats.recall:.2f}, F1: {last_stats.f1_score:.2f}."
        
    answer = qa.ask(req.query, context)
    return {"answer": answer}
