import csv
import math
import random
import os
import json
import numpy as np
import jellyfish

os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def compute_weights(bank_records, ledger_records, ground_truth):
    """Computes weights given a split of data using Laplace smoothing."""
    m_counts = {"amt_match": 0, "date_match": 0, "desc_match": 0, "total": 0}
    u_counts = {"amt_match": 0, "date_match": 0, "desc_match": 0, "total": 0}
    
    # Pre-index ledger for quick lookup
    l_dict = {l[0]: l for l in ledger_records}
    
    for b in bank_records:
        b_id, b_date, b_amt, b_desc = b[0], b[1], float(b[2]), str(b[3]).lower()
        true_l_id = ground_truth.get(b_id)
        
        # M-probabilities (matches)
        if true_l_id and true_l_id in l_dict:
            l = l_dict[true_l_id]
            l_date, l_amt, l_desc = l[1], float(l[2]), str(l[3]).lower()
            
            m_counts["total"] += 1
            abs_diff = abs(b_amt - l_amt)
            # 5% max AND max 4000 INR (~$50 USD) absolute difference
            if abs_diff / max(l_amt, 1.0) <= 0.05 and abs_diff <= 4000.0:
                m_counts["amt_match"] += 1
            if b_date == l_date:
                m_counts["date_match"] += 1
                
            # Use Jaro-Winkler at 0.85 threshold -- identical to reconciler.py _tier_2_fs_weight
            jw = jellyfish.jaro_winkler_similarity(b_desc, l_desc)
            if jw >= 0.85:
                m_counts["desc_match"] += 1
                
        # U-probabilities (non-matches)
        non_matches = [l_id for l_id in l_dict.keys() if l_id != true_l_id]
        if non_matches:
            random_l_id = random.choice(non_matches)
            l = l_dict[random_l_id]
            l_date, l_amt, l_desc = l[1], float(l[2]), str(l[3]).lower()
            
            u_counts["total"] += 1
            abs_diff = abs(b_amt - l_amt)
            if abs_diff / max(l_amt, 1.0) <= 0.05 and abs_diff <= 4000.0:
                u_counts["amt_match"] += 1
            if b_date == l_date:
                u_counts["date_match"] += 1
                
            # Use Jaro-Winkler at 0.85 threshold -- identical to reconciler.py _tier_2_fs_weight
            jw = jellyfish.jaro_winkler_similarity(b_desc, l_desc)
            if jw >= 0.85:
                u_counts["desc_match"] += 1

    weights = {}
    for feat in ["amt", "date", "desc"]:
        feat_key = f"{feat}_match"
        
        # Laplace Smoothing: (count + 1) / (total + 2)
        m_p = (m_counts[feat_key] + 1) / (m_counts["total"] + 2)
        u_p = (u_counts[feat_key] + 1) / (u_counts["total"] + 2)
        
        w_agree = math.log2(m_p / u_p)
        w_disagree = math.log2((1 - m_p) / (1 - u_p))
        
        # Clamp to Winkler plausible ranges (-10 to +10)
        w_agree = max(min(w_agree, 10.0), -10.0)
        w_disagree = max(min(w_disagree, 10.0), -10.0)
        
        weights[feat] = {"agree": round(w_agree, 2), "disagree": round(w_disagree, 2)}
        
    return weights

def run_cv():
    import sys
    bank_file = sys.argv[1] if len(sys.argv) > 1 else "backend/data/bank.csv"
    ledger_file = sys.argv[2] if len(sys.argv) > 2 else "backend/data/ledger.csv"
    gt_file = sys.argv[3] if len(sys.argv) > 3 else "backend/data/ground_truth.csv"
    out_file = sys.argv[4] if len(sys.argv) > 4 else "backend/weights.json"
    
    with open(bank_file, "r", encoding="utf-8") as f:
        bank_records = list(csv.reader(f))[1:]
    with open(ledger_file, "r", encoding="utf-8") as f:
        ledger_records = list(csv.reader(f))[1:]
    with open(gt_file, "r", encoding="utf-8") as f:
        ground_truth = {row[0]: row[1] for row in list(csv.reader(f))[1:]}

    # 5-fold CV
    random.seed(42)
    b_ids = [b[0] for b in bank_records]
    random.shuffle(b_ids)
    
    folds = np.array_split(b_ids, 5)
    all_weights = {"amt": {"agree": [], "disagree": []}, "date": {"agree": [], "disagree": []}, "desc": {"agree": [], "disagree": []}}
    
    for i in range(5):
        val_ids = set(folds[i])
        train_ids = set(b_ids) - val_ids
        
        train_bank = [b for b in bank_records if b[0] in train_ids]
        w = compute_weights(train_bank, ledger_records, ground_truth)
        
        for f in ["amt", "date", "desc"]:
            all_weights[f]["agree"].append(w[f]["agree"])
            all_weights[f]["disagree"].append(w[f]["disagree"])
            
    print("--- 5-Fold Cross Validation Variance ---")
    final_weights = {}
    for f in ["amt", "date", "desc"]:
        a_mean, a_std = np.mean(all_weights[f]["agree"]), np.std(all_weights[f]["agree"])
        d_mean, d_std = np.mean(all_weights[f]["disagree"]), np.std(all_weights[f]["disagree"])
        print(f"{f} agree: {a_mean:.2f} ± {a_std:.2f}")
        print(f"{f} disagree: {d_mean:.2f} ± {d_std:.2f}")
        
        final_weights[f] = {"agree": round(a_mean, 2), "disagree": round(d_mean, 2)}
        
    final_weights["T_upper"] = 10.0
    final_weights["T_lower"] = -2.0
    
    with open(out_file, "w") as f:
        json.dump(final_weights, f, indent=4)
        
    print(f"\nSaved weights to {out_file}")

if __name__ == "__main__":
    run_cv()
