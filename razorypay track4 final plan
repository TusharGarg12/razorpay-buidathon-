# AI Finance Controller — Final Implementation Plan v2 (Track 04)
> **Razorpay Buildathon 2026 | Track 04 — "Run the books and the cash position"**
> **Updated with 3 new research sources**

---

## Decisions Locked ✅

| Question | Decision |
|----------|----------|
| LLM | **Gemini API** (real calls) + graceful fallback to smart heuristics on failure/rate-limit |
| Stack | **React + Vite** frontend + **Python FastAPI** backend |
| Deployment | **Vercel** (frontend) + **Railway/Render** (backend) |

---

## Complete Research Backbone (All 7 Sources)

| Source | Key Contribution to Our Build |
|--------|-------------------------------|
| `AI_Finance_Controller_Reconciliation.pdf` | 4-tier pipeline blueprint, 9 mismatch types, judging criteria |
| `Achieving_Automated_Reconciliation.pdf` | ±$0.01 rounding tolerance, ±3-day date window, NLP entity resolution 98.7%, error rate drop 2.8%→0.4% |
| `8-2-54-893.pdf` (IJFME 2025) | Multi-source ingestion, anomaly detection, real-time dashboards, OCR+NLP pipeline |
| `3183713.3196926.pdf` (SIGMOD'18) | DL entity matching beats rule-based by 6–32% F1 on dirty/textual data → justifies fuzzy+LLM tier |
| **`2004.00584v3.pdf` — Ditto (PVLDB'21)** | **Jaro-Winkler + TF-IDF summarization for LLM prompts; domain-knowledge span-typing; achieves 96.5% F1 on 789K company records** |
| **`p2459-thirumuruganathan.pdf` — DeepBlocker (PVLDB'21)** | **Embedding-based candidate blocking before matching — reduces pairs to evaluate from O(n²) to O(n); Autoencoder+cosine best on structured+dirty data** |
| **`WinklerReclink080315D.doc` — Winkler (2008)** | **Fellegi-Sunter probabilistic matching weights (m/u-probabilities); Jaro-Winkler string comparator (best for financial typo correction); EM algorithm for unsupervised parameter learning** |

---

## What the New Papers Change (Concrete Upgrades)

### From Ditto (`2004.00584v3.pdf`)
1. **String serialization for LLM** — serialize pairs as `[COL] date [VAL] 2024-01-15 [COL] amount [VAL] 1195.00 [SEP] [COL] date [VAL] 2024-01-14 [COL] amount [VAL] 1200.00` for Gemini context → structured, not raw text
2. **Domain knowledge injection** — tag amount spans `[AMT]1195[/AMT]` and date spans `[DATE]2024-01-15[/DATE]` so Gemini focuses on the right fields
3. **TF-IDF summarization** — when description field is long, summarize to top-N tokens before sending to LLM (avoids noise, fits token limit)
4. **Span normalization** — normalize amounts (drop commas, round to 2dp: "1,200.00" → "1200.00"), normalize dates (ISO format) before any comparison

### From DeepBlocker (`p2459-thirumuruganathan.pdf`)
5. **Blocking pre-filter** — before Tier 1, embed all bank+ledger records using SIF (weighted word averaging on description field), compute cosine similarity, only consider top-K candidates per bank record → reduces O(n²) comparisons to O(n·K) where K≪n. Best for performance at scale.

### From Winkler (`WinklerReclink080315D.doc`)
6. **Jaro-Winkler string comparator** — replace simple `RapidFuzz token_sort_ratio` in Tier 2 with **Jaro-Winkler** (proven best for financial typographical errors, outperforms Bigram and Edit Distance per Winkler Table 14.5)
7. **Fellegi-Sunter matching weights** — compute composite log-likelihood weight per candidate pair:
   - `weight = log(m_amount/u_amount) + log(m_date/u_date) + log(m_desc/u_desc)`
   - Where `m_prob` = probability of agreement given true match, `u_prob` = probability of random agreement
   - Set Tier 2 match threshold at weight > 0 (log-odds > 0 = more likely match than non-match)
8. **3-zone decision rule** — Fellegi-Sunter's `T_upper / clerical_zone / T_lower`:
   - Weight > T_upper → automatic match (Tier 2 confirmed)
   - T_lower < Weight < T_upper → send to LLM (Tier 3)
   - Weight < T_lower → automatic exception (Tier 4)

---

## Architecture (Updated)

```
┌────────────────────────────────────────────────────────────────┐
│                     Vercel — React + Vite                       │
│  Upload → Live Progress → Stats → Match Table → Exceptions      │
│  + Settlement Q&A Chat Panel                                    │
└──────────────────────────┬─────────────────────────────────────┘
                           │ HTTPS REST + SSE
┌──────────────────────────▼─────────────────────────────────────┐
│                  Railway — FastAPI Python                       │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  BLOCKING PRE-FILTER (NEW — from DeepBlocker)           │  │
│  │  SIF embeddings → cosine similarity → top-K candidates  │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                  │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │  SPAN NORMALIZATION (NEW — from Ditto)                   │  │
│  │  amounts→2dp, dates→ISO, names→lowercase stripped        │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                  │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │  TIER 1 — Exact Match                                    │  │
│  │  amount==amount AND date==date (or txn_id)               │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │ unresolved                       │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │  TIER 2 — Jaro-Winkler + Fellegi-Sunter weights (NEW)   │  │
│  │  • Jaro-Winkler on descriptions                         │  │
│  │  • Amount tolerance ±2%                                  │  │
│  │  • Date window ±3 days                                   │  │
│  │  • Many-to-1 / 1-to-many grouping                       │  │
│  │  • FS weight > T_upper → confirmed match                 │  │
│  │  • T_lower < weight < T_upper → pass to Tier 3          │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │ ambiguous zone                   │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │  TIER 3 — Gemini LLM (Ditto-style serialization)        │  │
│  │  • TF-IDF summarize long descriptions                    │  │
│  │  • Inject span tags [AMT], [DATE], [DESC]                │  │
│  │  • Serialize pair: [COL]...[VAL]...[SEP][COL]...[VAL]   │  │
│  │  • Structured output: {decision, reason, confidence}     │  │
│  │  • Fallback: heuristic score > 0.6 threshold             │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │ unresolved                       │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │  TIER 4 — Exception Log                                  │  │
│  │  Reason codes: NO_CANDIDATE, AMBIGUOUS_MULTI,            │  │
│  │  LIKELY_DUPLICATE, MISSING_RECORD,                       │  │
│  │  LOW_CONFIDENCE_LLM, API_FALLBACK                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## CSV Schemas (Locked)

### Bank / Gateway Feed (`bank.csv`)
```
txn_id, date, amount, description, reference, currency
B001, 2024-01-15, 1195.00, "RAZORPAY SETTLEMENT", "RZP-A1B2", INR
```

### Internal Ledger (`ledger.csv`)
```
txn_id, date, amount, description, invoice_id, currency
L001, 2024-01-14, 1200.00, "Invoice #INV-101 - Software License", "INV-101", INR
```

### Ground Truth (`ground_truth.csv`) — hidden answer key
```
bank_txn_id, ledger_txn_id, mismatch_type, notes
B001, L001, amount_fee, "Razorpay 0.4% fee deducted"
```

---

## 9 Mismatch Types → All Handled

| # | Type | Category | Resolution Tier | Algorithm Used |
|---|------|----------|-----------------|----------------|
| 1 | Fee deduction | Amount | **Tier 2** | ±2% tolerance + FS weight |
| 2 | T+1/T+2 delay | Timing | **Tier 2** | ±3 day window + FS weight |
| 3 | Batch aggregation | Structure | **Tier 2** | Many-to-1 group sum |
| 4 | Missing record | Missing | **Tier 4** | NO_CANDIDATE exception |
| 5 | Duplicate entry | Structure | **Tier 2** | Duplicate detection flag |
| 6 | Name mismatch | Data Quality | **Tier 2** | **Jaro-Winkler** ≥ 0.85 |
| 7 | FX conversion | Amount | **Tier 2** | ±2% tolerance |
| 8 | Partial payments | Structure | **Tier 2** | 1-to-many group sum |
| 9 | Human typos | Data Quality | **Tier 3** | **Ditto-style LLM** with span tags |

---

## Scoring Engine

```python
TP = correctly matched pairs (matches ground truth mapping)
FP = wrong matches (matched to wrong ledger record)
FN = missed matches (should have matched, didn't)

Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 * P * R / (P + R)
Match Rate = TP / total_bank_records
```

**Target:** Match Rate ≥ 88%, F1 ≥ 0.90, 100% of exceptions have reason codes

---

## Frontend UI Screens

### Screen 1 — Landing / Upload
- Hero: "AI Finance Controller" + animated subtitle
- Drag-drop zones: Bank CSV + Ledger CSV
- "Run Demo (60 records)" button → instant synthetic data
- Dark glassmorphism, premium typography (Inter font)

### Screen 2 — Live Processing (SSE Streaming)
- 5-step animated pipeline bar: **Blocking → Normalize → Tier1 → Tier2 → Tier3/4**
- Record counter ticking up live
- Log feed: "✓ Exact-matched B003 ↔ L007 | ⚡ Jaro-Winkler matched B011 ↔ L014 (0.93)"

### Screen 3 — Results Dashboard
- **Big 4 stats** (animated count-up): Match Rate | Precision | Recall | F1
- **Research badge**: "Jaro-Winkler + Fellegi-Sunter + Ditto-LLM pipeline"
- **Match Table**: filterable, color-coded by tier, confidence score shown
- **Exceptions Panel**: red badge, table with reason codes, export CSV button
- **Category Donut Chart**: Timing / Amount / Structure / Data Quality / Missing
- **Settlement Q&A Chat**: right sidebar, Gemini-powered

---

## Deployment Plan

### Frontend → Vercel
```bash
cd frontend && npm run build && vercel --prod
```
Env: `VITE_API_URL=https://your-backend.railway.app`

### Backend → Railway
```
Dockerfile: uvicorn main:app --host 0.0.0.0 --port $PORT
Env: GEMINI_API_KEY, ALLOWED_ORIGINS
```

---

## Complete File Structure

```
razorpay_track4/
├── backend/
│   ├── main.py              # FastAPI app, all routes + SSE
│   ├── data_generator.py    # 60+ synthetic records, 9 mismatch types, ground truth
│   ├── blocker.py           # DeepBlocker-inspired SIF embeddings + cosine pre-filter
│   ├── normalizer.py        # Ditto-inspired span normalization (amount, date, name)
│   ├── reconciler.py        # 4-tier engine: Exact → JaroWinkler+FS → LLM → Exception
│   ├── scorer.py            # Precision/Recall/F1 vs ground truth
│   ├── llm_agent.py         # Gemini API: Ditto serialization, span tags, fallback
│   ├── qa_agent.py          # Settlement Q&A via Gemini + reconciliation context
│   ├── models.py            # Pydantic schemas
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── UploadZone.jsx
│   │   │   ├── PipelineProgress.jsx   # 5-step animated bar
│   │   │   ├── StatsDashboard.jsx     # Animated counters
│   │   │   ├── MatchTable.jsx         # Color-coded, filterable
│   │   │   ├── ExceptionsPanel.jsx    # Prominent, reason codes
│   │   │   ├── CategoryChart.jsx      # Donut chart
│   │   │   └── QAChat.jsx             # Settlement Q&A chat
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
└── .env                     # GEMINI_API_KEY (you provide)
```

---

## Build Order (10 Phases)

| Phase | Task | Files |
|-------|------|-------|
| 1 | Synthetic data generator (60 records, 9 mismatch types, ground truth) | `data_generator.py` |
| 2 | Span normalizer (Ditto-style amount/date/name normalization) | `normalizer.py` |
| 3 | Blocking pre-filter (SIF embeddings + cosine, top-K candidates) | `blocker.py` |
| 4 | Tier 1 exact + Tier 2 Jaro-Winkler + Fellegi-Sunter weights | `reconciler.py` |
| 5 | Gemini Tier 3 LLM (Ditto serialization + span tags + fallback) | `llm_agent.py` |
| 6 | Exception logging + Scorer (P/R/F1) | `scorer.py` |
| 7 | FastAPI backend + SSE streaming | `main.py` |
| 8 | Settlement Q&A agent | `qa_agent.py` |
| 9 | React frontend — all components + premium dark UI | `frontend/src/` |
| 10 | Tests + Dockerfile + Vercel + Railway deploy | `backend/tests/`, `Dockerfile`, `vercel.json` |

---

## Verification Plan

### Automated Tests
```bash
pytest backend/tests/ -v
# All 9 mismatch types resolve to correct tier
# Match rate ≥ 88% on 60-record synthetic set  
# Exception list non-empty, all have reason codes
# Jaro-Winkler catches name variants (ABC Corp / ABC Co.)
# LLM fallback triggers correctly on mock API failure
# Fellegi-Sunter zone thresholds correctly route to Tier 3
```

### Manual Verification
- Full 60-record demo runs live (throughput check)
- Precision/recall on screen vs ground truth
- Exceptions panel prominent and complete
- Settlement Q&A answers 3+ question types
- Live URL works on Vercel + Railway

---

## Why This Will Win

| Judging Criterion | Our Approach | Research Backing |
|-------------------|-------------|------------------|
| **Throughput** | Blocking pre-filter keeps O(n·K), SSE streams live | DeepBlocker 2021 |
| **Measured Accuracy** | P/R/F1 vs ground truth, shown live on screen | All 4 original PDFs |
| **Honest Exceptions** | 6 reason codes, prominent panel, CSV export | AI_Finance_Controller PDF |
| **Matching Quality** | Jaro-Winkler > Edit Distance > Bigram for typos | Winkler 2008 Table 14.5 |
| **Dirty/Textual Data** | Ditto-style serialization, +29% F1 over SOTA | Ditto PVLDB 2021 |
| **Wow Factor** | Premium dark UI, live progress, Q&A chat | — |
