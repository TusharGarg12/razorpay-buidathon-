import pandas as pd
import json

df = pd.read_csv('BenchRec_cash_v1.0_train.csv')

metrics = {
    'total_rows': len(df),
    'columns': df.columns.tolist(),
    'match_rules': df['matchRule'].value_counts(dropna=False).head(10).to_dict() if 'matchRule' in df.columns else {},
    'a_types': df['A_transactionType'].value_counts(dropna=False).head(5).to_dict() if 'A_transactionType' in df.columns else {},
    'b_types': df['B_transactionType'].value_counts(dropna=False).head(5).to_dict() if 'B_transactionType' in df.columns else {},
    'missing_values': {col: int(df[col].isna().sum()) for col in df.columns if df[col].isna().sum() > 0},
    'unique_match_ids': int(df['matchId'].nunique()) if 'matchId' in df.columns else 0
}

with open('scratch/metrics_output.json', 'w') as f:
    json.dump(metrics, f, indent=4)

print("Metrics saved to scratch/metrics_output.json")
