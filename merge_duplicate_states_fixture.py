"""One-off fixup for the SQLite -> MySQL migration's `dumpdata` backup.

SQLite's default text comparison is case/whitespace-sensitive, so a handful
of Bangladesh states got saved twice with an identical name save for a
trailing space (e.g. "Dhaka" and "Dhaka ") — both satisfied SQLite's
(name, country) unique constraint. MySQL's default collation treats
trailing whitespace as insignificant for uniqueness, so `loaddata` fails
with a duplicate-entry IntegrityError partway through loading `locations.
state`. Run this once against the dumpdata backup before loading it into
MySQL: for each such pair it keeps the row whose name has no leading/
trailing whitespace, re-points every FK/M2M reference at that row instead,
and drops the duplicate. Does not touch the database — pure JSON in, JSON
out — so the original backup is never modified.

Usage: python merge_duplicate_states_fixture.py
Reads:  data_backup.json
Writes: data_backup_fixed.json
"""
import json
from collections import defaultdict

INPUT = 'data_backup.json'
OUTPUT = 'data_backup_fixed.json'

data = json.load(open(INPUT, encoding='utf-8'))

groups = defaultdict(list)
for obj in data:
    if obj['model'] == 'locations.state':
        key = (obj['fields']['name'].strip().lower(), obj['fields']['country'])
        groups[key].append(obj)

remap = {}
drop_pks = set()
for key, objs in groups.items():
    if len(objs) <= 1:
        continue
    canonical = [o for o in objs if o['fields']['name'] == o['fields']['name'].strip()]
    if len(canonical) != 1:
        raise SystemExit(f"Unexpected shape for group {key}: {[(o['pk'], o['fields']['name']) for o in objs]}")
    canon_pk = canonical[0]['pk']
    for o in objs:
        if o['pk'] != canon_pk:
            remap[o['pk']] = canon_pk
            drop_pks.add(o['pk'])

print(f"Merging {len(remap)} duplicate state(s): {remap}")

# Every model that references locations.State, found via:
#   grep -rn "ForeignKey(State\|ManyToManyField(State" --include=*.py (excl. migrations)
FK_MODELS = {'accounts.user', 'core.booking', 'core.activitylog', 'locations.lga'}
M2M_MODEL_FIELDS = {'core.artisanprofile': 'service_states'}

fixed = []
fk_rewritten = 0
m2m_rewritten = 0
for obj in data:
    if obj['model'] == 'locations.state' and obj['pk'] in drop_pks:
        continue  # drop the duplicate row entirely

    if obj['model'] in FK_MODELS:
        s = obj['fields'].get('state')
        if s in remap:
            obj['fields']['state'] = remap[s]
            fk_rewritten += 1

    m2m_field = M2M_MODEL_FIELDS.get(obj['model'])
    if m2m_field and obj['fields'].get(m2m_field):
        original = obj['fields'][m2m_field]
        remapped = [remap.get(pk, pk) for pk in original]
        deduped = list(dict.fromkeys(remapped))  # preserve order, drop dupes
        if deduped != original:
            obj['fields'][m2m_field] = deduped
            m2m_rewritten += 1

    fixed.append(obj)

print(f"Rewrote {fk_rewritten} FK reference(s) and {m2m_rewritten} M2M list(s).")
print(f"Total objects: {len(data)} -> {len(fixed)} (dropped {len(data) - len(fixed)})")

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(fixed, f)

print(f"Wrote {OUTPUT}")
