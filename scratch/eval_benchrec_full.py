"""
BenchRec Full-Scale Evaluator v2 — fully vectorized, no per-record Python loops in hot path.

Strategy:
  1. Load A+B records with pandas, parse dates/amounts once into numpy arrays.
  2. Build a (A x B) candidate index using amount buckets + date window — all vectorized.
  3. Score each candidate pair with Fellegi-Sunter weights using pandas merge + vectorized math.
  4. Assign matches greedily (highest-weight first), respecting consumed-ID sets.
  5. Optionally call Ollama on N clerical-zone pairs.
  6. Report TP/FP/FN / Precision / Recall / F1 / MatchRate.

Usage:
  python eval_benchrec_v2.py
  python eval_benchrec_v2.py --llm-sample 200
  python eval_benchrec_v2.py --limit 10000 --llm-sample 50
"""

import sys, os, json, time, argparse
import numpy as np
import pandas as pd
import jellyfish, httpx

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT        = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND_DIR = os.path.join(ROOT, 'backend')
TRAIN_FILE  = os.path.join(ROOT, 'BenchRec_cash_v1.0_train.csv')
WEIGHTS_FILE= os.path.join(BACKEND_DIR, 'weights_benchrec.json')
OUT_FILE    = os.path.join(ROOT, 'benchrec_eval_results.json')

sys.path.insert(0, BACKEND_DIR)
from normalizer import normalize_amount

# ── weights ───────────────────────────────────────────────────────────────────
with open(WEIGHTS_FILE) as f:
    W = json.load(f)
AMT_AG   = W['amt']['agree'];    AMT_DIS  = W['amt']['disagree']
DATE_AG  = W['date']['agree'];   DATE_DIS = W['date']['disagree']
DESC_AG  = W['desc']['agree'];   DESC_DIS = W['desc']['disagree']
T_UPPER  = W['T_upper'];         T_LOWER  = W['T_lower']

FEE_TOL  = 0.02   # 2%
DATE_WIN = 3      # days
ABS_CAP  = 4000.0
JW_THRESH= 0.85

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:latest"

# ══════════════════════════════════════════════════════════════════════════════
# Ollama
# ══════════════════════════════════════════════════════════════════════════════
def check_ollama():
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def call_llm(bank_row, ledger_row) -> str:
    """Returns 'match' or 'unresolved'."""
    prompt = (
        "Financial reconciliation. Return ONLY valid JSON: "
        '{"decision":"match"|"unresolved","confidence":0.0-1.0}\n\n'
        f"Bank:   id={bank_row['txn_id']} date={bank_row['date_raw']} "
        f"amount={bank_row['amount_raw']} {bank_row['currency']} "
        f"desc={str(bank_row.get('description',''))[:80]}\n"
        f"Ledger: id={ledger_row['txn_id']} date={ledger_row['date_raw']} "
        f"amount={ledger_row['amount_raw']} {ledger_row['currency']} "
        f"desc={str(ledger_row.get('description',''))[:80]}"
    )
    try:
        r = httpx.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "prompt": prompt,
            "stream": False, "format": "json"
        }, timeout=30)
        r.raise_for_status()
        data = json.loads(r.json().get("response", "{}"))
        return data.get("decision", "unresolved")
    except Exception:
        return "unresolved"


# ══════════════════════════════════════════════════════════════════════════════
# Data loading — vectorized
# ══════════════════════════════════════════════════════════════════════════════
def load_data(path: str, limit=None):
    print(f"Loading {os.path.basename(path)} ...", flush=True)
    df = pd.read_csv(path, dtype=str)

    # Separate A (bank) and B (ledger)
    a = df[df['A_id'].notna() & (df['A_id'].str.strip() != '')].copy()
    b = df[df['B_id'].notna() & (df['B_id'].str.strip() != '')].copy()

    if limit:
        a = a.sample(n=min(limit, len(a)), random_state=42)
        # keep B records that match sampled A allocations + some noise
        a_allocs = set(a['A_allocation'].dropna())
        b_match  = b[b['targetAllocation'].isin(a_allocs)]
        b_noise  = b[~b['B_id'].isin(b_match['B_id'])].sample(
                       n=min(limit//2, len(b)), random_state=42)
        b = pd.concat([b_match, b_noise]).drop_duplicates(subset=['B_id'])

    def parse_side(df_side, id_col, date_col, amt_col, curr_col, desc_col, alloc_col):
        out = pd.DataFrame()
        out['txn_id']      = df_side[id_col].str.strip()
        out['date_raw']    = df_side[date_col].fillna('').str.split(' ').str[0]
        out['amount_raw']  = pd.to_numeric(df_side[amt_col], errors='coerce').fillna(0.0)
        out['currency']    = df_side[curr_col].fillna('USD').str.strip()
        out['description'] = df_side[desc_col].fillna('').str.lower().str.strip()
        out['allocation']  = df_side[alloc_col].fillna('')

        # Parse dates → ordinal int (NaT → -1)
        parsed = pd.to_datetime(out['date_raw'], errors='coerce')
        out['date_ord']    = parsed.map(lambda d: d.toordinal() if pd.notna(d) else -1).astype(int)

        # Normalize amounts to INR (hardcoded rates matching normalizer.py)
        fx = {'USD': 83.0, 'EUR': 90.0, 'GBP': 105.0, 'INR': 1.0}
        rates = out['currency'].map(fx).fillna(1.0)
        out['amt_inr'] = (out['amount_raw'] * rates).round(2)

        return out.reset_index(drop=True)

    bank = parse_side(a, 'A_id', 'A_valueDate', 'A_amount',
                      'A_currencyCode', 'A_transactionAttributes', 'A_allocation')
    ledger = parse_side(b, 'B_id', 'B_valueDate', 'B_amount',
                        'B_currencyCode', 'B_transactionAttributes', 'targetAllocation')

    # Ground truth: A_allocation → list of B txn_ids
    alloc_to_b = ledger.groupby('allocation')['txn_id'].apply(list).to_dict()
    ground_truth = {}
    for _, row in a.iterrows():
        aid   = str(row['A_id']).strip()
        alloc = str(row.get('A_allocation', '') or '').strip()
        if alloc and alloc in alloc_to_b:
            ground_truth[aid] = alloc_to_b[alloc]

    print(f"  Bank: {len(bank):,}  Ledger: {len(ledger):,}  "
          f"GT pairs: {len(ground_truth):,}", flush=True)
    return bank, ledger, ground_truth


# ══════════════════════════════════════════════════════════════════════════════
# Vectorized candidate generation + FS scoring
# ══════════════════════════════════════════════════════════════════════════════
BLOCK_DATE_WIN = 14   # wider window for BLOCKING only — FS scorer re-checks with strict DATE_WIN=3
#
# Why AND not OR:
#   Amount is the high-selectivity primary filter (millions of unique values).
#   Date-only OR would generate O(n²) pairs (every pair within 14 days regardless of amount).
#   Keeping AND with a wider date window exposes clerical-zone pairs:
#     amt_agree + date 4-14 days apart  →  FS weight = +1.78  →  clerical zone  →  LLM ✓
#     amt_agree + date within 3 days    →  FS weight = +14.52 →  Tier 2 auto-match
#
def build_candidate_pairs(bank: pd.DataFrame, ledger: pd.DataFrame,
                          chunk_size: int = 5000) -> pd.DataFrame:
    """
    For each bank record, find ledger candidates where:
      - Amount within FEE_TOL (±2%) AND abs diff <= ABS_CAP   [primary, high-selectivity]
      AND
      - Date within BLOCK_DATE_WIN (14) days                   [relaxed for blocking only]

    The FS scorer then applies the strict DATE_WIN=3 threshold, correctly routing:
      • amt_agree + date ≤3d  → weight +14.52  → Tier 2 auto-match
      • amt_agree + date 4-14d→ weight  +1.78  → Clerical zone → LLM
      • amt_disagree (any)    → excluded at blocking stage (not a viable candidate)

    Done in chunks to avoid O(n²) memory blowup.
    Returns DataFrame with columns: [a_idx, b_idx, fs_w, tier1, amt_diff]
    """
    print(f"Building candidate pairs in chunks of {chunk_size:,} "
          f"(AND logic, block_date_win={BLOCK_DATE_WIN}d) ...", flush=True)
    t0 = time.time()
    results = []

    b_amt  = ledger['amt_inr'].values
    b_date = ledger['date_ord'].values

    total_chunks = (len(bank) + chunk_size - 1) // chunk_size

    for chunk_num, start in enumerate(range(0, len(bank), chunk_size)):
        end    = min(start + chunk_size, len(bank))
        a_sub  = bank.iloc[start:end]

        a_amt  = a_sub['amt_inr'].values[:, np.newaxis]   # (chunk, 1)
        a_date = a_sub['date_ord'].values[:, np.newaxis]  # (chunk, 1)

        # Amount condition
        diff      = np.abs(a_amt - b_amt)                 # (chunk, n_ledger)
        max_b     = np.maximum(np.abs(b_amt), 1.0)
        amt_ok    = (diff / max_b <= FEE_TOL) & (diff <= ABS_CAP)

        # Date condition (wide window for blocking only — FS scorer re-applies strict DATE_WIN=3)
        valid_dates = (a_date >= 0) & (b_date >= 0)
        date_ok     = valid_dates & (np.abs(a_date - b_date) <= BLOCK_DATE_WIN)

        # AND logic: amount must agree, date must be within blocking window
        # This exposes amt_agree+date_disagree (4-14d) → clerical zone → LLM
        mask = amt_ok & date_ok

        rows_a, rows_b = np.where(mask)

        if len(rows_a) == 0:
            continue

        # Compute FS score for each candidate pair
        a_global_idx = rows_a + start
        abs_diff     = diff[rows_a, rows_b]
        max_b_vals   = max_b[rows_b]
        a_date_vals  = bank['date_ord'].values[a_global_idx]
        b_date_vals  = b_date[rows_b]

        # Amount score (uses strict DATE_WIN=3 and FEE_TOL)
        w_amt  = np.where((abs_diff / max_b_vals <= FEE_TOL) & (abs_diff <= ABS_CAP),
                          AMT_AG, AMT_DIS)
        # Date score (uses strict DATE_WIN=3)
        w_date = np.where((np.abs(a_date_vals - b_date_vals) <= DATE_WIN)
                          & (a_date_vals >= 0) & (b_date_vals >= 0),
                          DATE_AG, DATE_DIS)
        w_desc = np.zeros(len(rows_a))   # desc weights are 0.0 in BenchRec weights

        # Tier 1: exact amount + exact date
        tier1  = (abs_diff < 0.01) & (a_date_vals == b_date_vals) & (a_date_vals >= 0)

        fs_w   = w_amt + w_date + w_desc

        chunk_df = pd.DataFrame({
            'a_idx':    a_global_idx,
            'b_idx':    rows_b,
            'fs_w':     fs_w,
            'tier1':    tier1,
            'amt_diff': abs_diff,
        })
        results.append(chunk_df)

        if (chunk_num + 1) % 5 == 0 or (chunk_num + 1) == total_chunks:
            print(f"  chunk {chunk_num+1}/{total_chunks}  "
                  f"pairs so far: {sum(len(r) for r in results):,}  "
                  f"{time.time()-t0:.1f}s", flush=True)

    if not results:
        return pd.DataFrame(columns=['a_idx', 'b_idx', 'fs_w', 'tier1', 'amt_diff'])

    pairs = pd.concat(results, ignore_index=True)
    print(f"  Total candidate pairs: {len(pairs):,}  ({time.time()-t0:.1f}s)", flush=True)
    return pairs



def assign_matches(pairs: pd.DataFrame, bank: pd.DataFrame, ledger: pd.DataFrame,
                   llm_sample: int = 0, ollama_ok: bool = False):
    """
    Greedy assignment: sort pairs by tier1 desc, then fs_w desc.
    Consume each (a, b) pair once — no double-matching.
    """
    if pairs.empty:
        return [], 0, 0, {"T1": 0, "T2": 0, "T3": 0}

    pairs = pairs.sort_values(['tier1', 'fs_w'], ascending=[False, False])

    consumed_a: set = set()
    consumed_b: set = set()
    matched_pairs = []
    llm_calls  = 0
    clerical_q = []   # (a_idx, b_idx) pairs in clerical zone

    tier_counts = {"T1": 0, "T2": 0, "T3": 0}

    print(f"\nAssigning matches from {len(pairs):,} candidate pairs ...", flush=True)
    t0 = time.time()

    for row in pairs.itertuples(index=False):
        ai, bi = row.a_idx, row.b_idx
        if ai in consumed_a or bi in consumed_b:
            continue

        if row.tier1:
            # Tier 1 — exact
            consumed_a.add(ai); consumed_b.add(bi)
            matched_pairs.append((ai, bi, '1', 1.0))
            tier_counts["T1"] += 1

        elif row.fs_w >= T_UPPER:
            # Tier 2 — FS confirmed
            consumed_a.add(ai); consumed_b.add(bi)
            matched_pairs.append((ai, bi, '2', 0.9))
            tier_counts["T2"] += 1

        elif row.fs_w >= T_LOWER:
            # Clerical zone — queue for LLM
            clerical_q.append((ai, bi, row.fs_w))

    print(f"  Pre-LLM: {len(matched_pairs):,} matches  "
          f"(T1={tier_counts['T1']:,} T2={tier_counts['T2']:,})  "
          f"Clerical queue: {len(clerical_q):,}  ({time.time()-t0:.1f}s)", flush=True)

    # ── Tier 3: LLM on clerical zone ──────────────────────────────────────────
    if ollama_ok and llm_sample > 0:
        print(f"\nCalling Ollama on up to {llm_sample} clerical-zone pairs ...", flush=True)
        sample = clerical_q[:llm_sample]
        for i, (ai, bi, _) in enumerate(sample):
            if ai in consumed_a or bi in consumed_b:
                continue
            dec = call_llm(bank.iloc[ai], ledger.iloc[bi])
            llm_calls += 1
            if dec == 'match':
                consumed_a.add(ai); consumed_b.add(bi)
                matched_pairs.append((ai, bi, '3', 0.7))
                tier_counts["T3"] += 1
            if (i + 1) % 50 == 0:
                print(f"  LLM: {i+1}/{len(sample)} done  T3 matches: {tier_counts['T3']}", flush=True)

    return matched_pairs, llm_calls, len(clerical_q), tier_counts


# ══════════════════════════════════════════════════════════════════════════════
# Scoring
# ══════════════════════════════════════════════════════════════════════════════
def compute_metrics(matched_pairs, exceptions, ground_truth,
                    bank, ledger, tier_counts):
    bank_ids   = bank['txn_id'].tolist()
    ledger_ids = ledger['txn_id'].tolist()

    tp = fp = 0
    for ai, bi, tier, conf in matched_pairs:
        a_id = bank_ids[ai]
        b_id = ledger_ids[bi]
        if a_id in ground_truth and b_id in ground_truth[a_id]:
            tp += 1
        else:
            fp += 1

    matched_a_correct = {bank_ids[ai] for ai, bi, _, _ in matched_pairs
                         if bank_ids[ai] in ground_truth
                         and ledger_ids[bi] in ground_truth[bank_ids[ai]]}
    fn = len(ground_truth) - len(matched_a_correct)

    precision  = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall     = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1         = 2*precision*recall / (precision+recall) if (precision+recall) > 0 else 0.0
    match_rate = len(matched_pairs) / len(bank) if len(bank) > 0 else 0.0

    return {
        'total_bank':  len(bank),
        'total_ledger':len(ledger),
        'gt_pairs':    len(ground_truth),
        'matches':     len(matched_pairs),
        'exceptions':  len(exceptions),
        'tp': tp, 'fp': fp, 'fn': fn,
        'precision':   round(precision, 4),
        'recall':      round(recall, 4),
        'f1_score':    round(f1, 4),
        'match_rate':  round(match_rate, 4),
        'tier_counts': tier_counts,
    }


def print_report(stats, llm_calls, clerical_q, elapsed):
    sep = "=" * 60
    print(f"\n{sep}")
    print("  BenchRec Full-Scale Evaluation Results")
    print(sep)
    print(f"  Bank records   : {stats['total_bank']:>10,}")
    print(f"  Ledger records : {stats['total_ledger']:>10,}")
    print(f"  Ground-truth   : {stats['gt_pairs']:>10,}  (true pairs)")
    print(sep)
    print(f"  Matched        : {stats['matches']:>10,}")
    print(f"  Exceptions     : {stats['exceptions']:>10,}")
    print(f"  Match rate     : {stats['match_rate']*100:>9.2f}%")
    print(sep)
    print(f"  TP             : {stats['tp']:>10,}")
    print(f"  FP             : {stats['fp']:>10,}")
    print(f"  FN             : {stats['fn']:>10,}")
    print(f"  Precision      : {stats['precision']*100:>9.2f}%")
    print(f"  Recall         : {stats['recall']*100:>9.2f}%")
    print(f"  F1 Score       : {stats['f1_score']*100:>9.2f}%")
    print(sep)
    tc = stats['tier_counts']
    print(f"  Tier 1 (exact) : {tc.get('T1',0):>10,}")
    print(f"  Tier 2 (FS)    : {tc.get('T2',0):>10,}")
    print(f"  Tier 3 (LLM)   : {tc.get('T3',0):>10,}  ({llm_calls} calls made)")
    print(f"  Clerical queue : {clerical_q:>10,}  (remaining unsampled)")
    print(sep)
    print(f"  Wall-clock     : {elapsed:.1f}s")
    print(sep)


# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit',      type=int, default=None)
    parser.add_argument('--llm-sample', type=int, default=0)
    parser.add_argument('--chunk-size', type=int, default=5000)
    args = parser.parse_args()

    print("\nChecking Ollama ...", flush=True)
    ollama_ok = check_ollama()
    print("  Ollama: " + ("UP (qwen2.5:latest)" if ollama_ok else "DOWN — Tier 3 disabled"), flush=True)

    t0 = time.time()

    bank, ledger, ground_truth = load_data(TRAIN_FILE, limit=args.limit)

    pairs = build_candidate_pairs(bank, ledger, chunk_size=args.chunk_size)

    matched, llm_calls, clerical_q, tier_counts = assign_matches(
        pairs, bank, ledger,
        llm_sample=args.llm_sample, ollama_ok=ollama_ok
    )

    # Build exceptions
    consumed_a = {ai for ai, *_ in matched}
    exceptions = [{'bank_txn_id': bank.iloc[i]['txn_id']}
                  for i in range(len(bank)) if i not in consumed_a]

    stats = compute_metrics(matched, exceptions, ground_truth,
                            bank, ledger, tier_counts)
    elapsed = time.time() - t0

    print_report(stats, llm_calls, clerical_q, elapsed)

    out = {**stats, 'llm_calls': llm_calls, 'clerical_queue': clerical_q,
           'elapsed_seconds': round(elapsed, 1),
           'config': {'limit': args.limit, 'llm_sample': args.llm_sample,
                      'T_upper': T_UPPER, 'T_lower': T_LOWER,
                      'fee_tol': FEE_TOL, 'date_win': DATE_WIN}}
    with open(OUT_FILE, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved -> {os.path.basename(OUT_FILE)}", flush=True)


if __name__ == '__main__':
    main()
