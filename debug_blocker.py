import sys
import csv

ledger_records = [
    {'txn_id': 'l1', 'amount': '100.00', 'date': '2023-01-01', 'desc': 'Test', 'party': 'Test'},
    {'txn_id': 'l2', 'amount': '200.00', 'date': '2023-01-02', 'desc': 'Test2', 'party': 'Test2'},
    {'txn_id': 'l3', 'amount': '300.00', 'date': '2023-01-03', 'desc': 'Test3', 'party': 'Test3'}
]

corpus = [
    " ".join(str(v) for k, v in r.items() if k != "txn_id" and v)
    for r in ledger_records
]
print("Corpus:", corpus)

from sklearn.feature_extraction.text import TfidfVectorizer

try:
    vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 3))
    vectorizer.fit_transform(corpus)
    print("Success")
except Exception as e:
    print(f"Error: {repr(e)}")
