import pandas as pd
import json
import csv
import random
import os

def process_benchrec(split='eval', max_records=400):
    print(f"Processing {split} split...")
    
    # Load dataset
    file_path = f"BenchRec_cash_v1.0_{split}.csv"
    df = pd.read_csv(file_path, dtype=str)
    
    # Separate A (Bank) and B (Ledger) records
    df_A = df[df['A_id'].notna()]
    df_B = df[df['B_id'].notna()]
    
    # If eval, we need the solution file to get B's targetAllocation
    if split == 'eval':
        sol_df = pd.read_csv("BenchRec_cash_v1.0_solution.csv", dtype=str)
        # Create mapping of B_id to targetAllocation
        b_target_map = dict(zip(sol_df['B_id'], sol_df['targetAllocation']))
        # In the eval dataframe, the targetAllocation column is empty. 
        # But we don't necessarily need it in df_B, we just need to build ground truth.
        df_B['targetAllocation'] = df_B['B_id'].map(b_target_map)
        
        # A records have A_allocation which acts as the target group
    
    # We want to sample A records that are involved in STRICTLY 1-to-1 matches
    # Find targetAllocations that appear exactly once in B_records
    alloc_counts = df_B['targetAllocation'].value_counts()
    one_to_one_allocs = alloc_counts[alloc_counts == 1].index
    
    # Filter A records to only those whose A_allocation is in the 1-to-1 list
    valid_A = df_A[df_A['A_allocation'].isin(one_to_one_allocs)]
    
    # Sample 400 A records from the 1-to-1 set
    sampled_A = valid_A.sample(n=min(max_records, len(valid_A)), random_state=42)
    a_allocs = set(sampled_A['A_allocation'].dropna())
    
    # Sample B records: definitely include the ones that match A, plus some random ones
    matched_B = df_B[df_B['targetAllocation'].isin(a_allocs)]
    
    # If we need more to reach max_records, sample from the rest
    remaining_spots = max(0, max_records - len(matched_B))
    if remaining_spots > 0:
        unmatched_B = df_B[~df_B['B_id'].isin(matched_B['B_id'])]
        random_B = unmatched_B.sample(n=min(remaining_spots, len(unmatched_B)), random_state=42)
        sampled_B = pd.concat([matched_B, random_B])
    else:
        # If there are too many matches (e.g. many-to-one), we just take all matched for the eval
        sampled_B = matched_B
        
    print(f"Sampled {len(sampled_A)} A records and {len(sampled_B)} B records.")

    suffix = "" if split == 'eval' else "_train"

    # Write bank.csv (A records)
    bank_file = f"backend/data/bank{suffix}.csv"
    with open(bank_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['txn_id', 'date', 'amount', 'currency', 'description'])
        writer.writeheader()
        for _, row in sampled_A.iterrows():
            writer.writerow({
                'txn_id': row['A_id'],
                'date': str(row['A_valueDate']).split(' ')[0] if pd.notna(row['A_valueDate']) else '',
                'amount': row['A_amount'],
                'currency': row['A_currencyCode'],
                'description': row['A_transactionAttributes'] if pd.notna(row['A_transactionAttributes']) else ''
            })

    # Write ledger.csv (B records)
    ledger_file = f"backend/data/ledger{suffix}.csv"
    with open(ledger_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['txn_id', 'date', 'amount', 'currency', 'description'])
        writer.writeheader()
        for _, row in sampled_B.iterrows():
            writer.writerow({
                'txn_id': row['B_id'],
                'date': str(row['B_valueDate']).split(' ')[0] if pd.notna(row['B_valueDate']) else '',
                'amount': row['B_amount'],
                'currency': row['B_currencyCode'],
                'description': row['B_transactionAttributes'] if pd.notna(row['B_transactionAttributes']) else ''
            })

    # Write ground_truth.csv
    gt_file = f"backend/data/ground_truth{suffix}.csv"
    with open(gt_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['bank_txn_id', 'ledger_txn_id'])
        writer.writeheader()
        
        # Build A_id -> target map
        a_map = dict(zip(sampled_A['A_id'], sampled_A['A_allocation']))
        # Build B_id -> target map
        b_map = dict(zip(sampled_B['B_id'], sampled_B['targetAllocation']))
        
        # Reverse b_map (target -> B_id list)
        target_to_b = {}
        for b_id, alloc in b_map.items():
            if pd.notna(alloc):
                if alloc not in target_to_b:
                    target_to_b[alloc] = []
                target_to_b[alloc].append(b_id)
                
        # For simplicity in 1-to-1 scoring, we just output pairs
        for a_id, alloc in a_map.items():
            if pd.notna(alloc) and alloc in target_to_b:
                for b_id in target_to_b[alloc]:
                    writer.writerow({
                        'bank_txn_id': a_id,
                        'ledger_txn_id': b_id
                    })

if __name__ == "__main__":
    process_benchrec(split='eval', max_records=400)
    process_benchrec(split='train', max_records=400)
