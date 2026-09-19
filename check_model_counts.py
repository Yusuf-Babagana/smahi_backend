"""Read-only: lists every model label present in the migration backup and
how many objects of each. Used to confirm the exact shape of the real
dumpdata output (e.g. whether the accounts.Coordinator/Agent/BusinessOwner/
Client proxy models were serialized as their own separate fixture entries
alongside accounts.User) before writing anything that assumes a shape.

Usage: python check_model_counts.py
Reads: data_backup.json
"""
import json
from collections import Counter

data = json.load(open('data_backup.json', encoding='utf-8'))
counts = Counter(o['model'] for o in data)
for model in sorted(counts):
    print(f"{model}: {counts[model]}")
