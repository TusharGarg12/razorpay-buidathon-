import csv

def main():
    # Load the evaluation subset
    bank_records = []
    with open('backend/data/bank.csv', mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bank_records.append(row['txn_id'])
            
    # Load the ground truth
    ground_truth = {}
    with open('backend/data/ground_truth.csv', mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ground_truth[row['bank_txn_id']] = row['ledger_txn_id']
            
    # Load the evaluation records' A_allocation
    a_alloc = {}
    with open('BenchRec_cash_v1.0_eval.csv', mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['A_id'] in bank_records:
                a_alloc[row['A_id']] = row['A_allocation']
                
    # Load baseline submission predictions
    baseline_preds = {}
    with open('MatcherByChatGPT_submission.csv', mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            b_id = str(row['B_id'])
            alloc_str = row['targetAllocation']
            if alloc_str and alloc_str != 'None':
                try:
                    import ast
                    allocs = ast.literal_eval(alloc_str)
                    for alloc in allocs:
                        if alloc not in baseline_preds:
                            baseline_preds[alloc] = []
                        baseline_preds[alloc].append(b_id)
                except Exception:
                    pass
                
    # Score the baseline on our 1:1 subset
    tp = 0
    fp = 0
    fn = 0
    
    for a_id in bank_records:
        true_l_id = ground_truth.get(a_id)
        alloc = a_alloc.get(a_id)
        
        predicted_l_ids = baseline_preds.get(alloc, [])
        
        # In a strictly 1:1 subset, if the baseline predicted the correct B_id, it's a TP.
        if true_l_id in predicted_l_ids:
            tp += 1
            # If it predicted OTHER B_ids for this allocation, those are FPs (since we know it's a 1:1 case).
            fp += (len(predicted_l_ids) - 1)
        else:
            fn += 1
            # Any predictions it made are FPs
            fp += len(predicted_l_ids)
            
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    
    print("--- ChatGPT Baseline on 1:1 Subset ---")
    print(f"Total evaluated Bank records: {len(bank_records)}")
    print(f"TP: {tp}")
    print(f"FP: {fp}")
    print(f"FN: {fn}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    
if __name__ == '__main__':
    main()
