import csv
import jellyfish

def load_data(path):
    data = {}
    with open(path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data[row['txn_id']] = row
    return data

def main():
    bank_data = load_data('backend/data/bank.csv')
    ledger_data = load_data('backend/data/ledger.csv')
    
    with open('backend/data/ground_truth.csv', mode='r', encoding='utf-8') as f:
        gt = list(csv.DictReader(f))
        
    print("Inspecting 5 true matches for description overlap:")
    count = 0
    for row in gt:
        b_id = row['bank_txn_id']
        l_id = row['ledger_txn_id']
        
        if b_id in bank_data and l_id in ledger_data:
            b_desc = str(bank_data[b_id].get('description', '')).lower()
            l_desc = str(ledger_data[l_id].get('description', '')).lower()
            
            jw_score = jellyfish.jaro_winkler_similarity(b_desc, l_desc)
            
            # Simple token overlap metric from compute_weights:
            b_words = set(b_desc.split())
            l_words = set(l_desc.split())
            tok_score = len(b_words & l_words) / max(len(b_words | l_words), 1)
            
            print(f"Match {count+1}:")
            print(f"  Bank Desc:   '{b_desc}'")
            print(f"  Ledger Desc: '{l_desc}'")
            print(f"  Jaro-Winkler Score: {jw_score:.4f}")
            print(f"  Token Overlap:      {tok_score:.4f}")
            print("-" * 40)
            
            count += 1
            if count >= 5:
                break

if __name__ == '__main__':
    main()
