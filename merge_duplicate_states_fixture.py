"""One-off fixup for the SQLite -> MySQL migration's `dumpdata` backup.

SQLite's default text comparison is case/accent/whitespace-sensitive, but
MySQL's default collation is none of those — so a worldwide reference
dataset (states, then cities/LGAs) that happened to have near-duplicate
rows in SQLite (found so far: Bangladesh states differing only by a
trailing space, e.g. "Dhaka" vs "Dhaka "; an LGA collision between
"Urumqi" and the correctly-accented "Ürümqi") satisfied SQLite's unique
constraints fine but trips `loaddata`'s IntegrityError against MySQL.
Rather than fix these one at a time as each new collision surfaces, this
merges every such duplicate for BOTH locations.State and locations.LGA in
one pass: for each colliding group (matched case/accent/whitespace-
insensitively, the same way MySQL's collation compares them) it keeps the
row whose name has no leading/trailing whitespace (falling back to a
deterministic shortest-name/lowest-pk choice for a non-whitespace
collision, with a printed NOTE so it can be reviewed), re-points every
FK/M2M reference at the kept row, and drops the duplicate(s). Pure JSON
in, JSON out — never touches a database, so the original backup is never
modified.

Usage: python merge_duplicate_states_fixture.py
Reads:  data_backup.json
Writes: data_backup_fixed.json
"""
import json
import unicodedata
from collections import defaultdict

INPUT = 'data_backup.json'
OUTPUT = 'data_backup_fixed.json'


def fold(name):
    """Matches MySQL's default collation, which is both case- AND
    accent-insensitive (its actual, real-world cause: the first fixed
    LGA collision was "Ürümqi" vs a plain-ASCII spelling of the same
    city — .lower() alone never groups those together, since Python
    doesn't fold accents). NFKD splits a letter from its combining
    accent mark(s); dropping non-ASCII bytes then strips the marks
    while leaving the base letter, e.g. "Ürümqi" -> "urumqi"."""
    decomposed = unicodedata.normalize('NFKD', name.strip())
    return decomposed.encode('ascii', 'ignore').decode('ascii').lower()


def pick_canonical(objs):
    """The whitespace-clean row wins. If that's ambiguous (0 or 2+ clean
    candidates — a non-whitespace collision, e.g. case/accents), fall back
    to a deterministic (shortest name, then lowest pk) choice and flag it
    so the choice can be reviewed rather than silently guessed."""
    clean = [o for o in objs if o['fields']['name'] == o['fields']['name'].strip()]
    if len(clean) == 1:
        return clean[0]
    chosen = min(objs, key=lambda o: (len(o['fields']['name']), o['pk']))
    names = [(o['pk'], repr(o['fields']['name'])) for o in objs]
    print(f"  NOTE: ambiguous group (not a plain whitespace dupe): {names} -> keeping pk {chosen['pk']}")
    return chosen


def merge_duplicates(data, model_label, key_fields, fk_models, m2m_model_fields):
    """Merges duplicate rows of `model_label` whose (key_fields, case/
    whitespace-normalized) collide. fk_models: model labels with a plain FK
    field (same name as key_fields[-1]'s owning field — here always the
    singular of model_label, e.g. 'state'/'lga') pointing at this model.
    m2m_model_fields: {model_label: field_name} for M2M fields pointing at
    this model."""
    field_name = model_label.split('.')[-1]  # 'locations.state' -> 'state'

    groups = defaultdict(list)
    for obj in data:
        if obj['model'] == model_label:
            key = tuple(
                fold(obj['fields'][f]) if f == 'name' else obj['fields'][f]
                for f in key_fields
            )
            groups[key].append(obj)

    remap = {}
    drop_pks = set()
    for key, objs in groups.items():
        if len(objs) <= 1:
            continue
        canon_pk = pick_canonical(objs)['pk']
        for o in objs:
            if o['pk'] != canon_pk:
                remap[o['pk']] = canon_pk
                drop_pks.add(o['pk'])

    print(f"Merging {len(remap)} duplicate {model_label} row(s): {remap}")

    fixed = []
    fk_rewritten = 0
    m2m_rewritten = 0
    for obj in data:
        if obj['model'] == model_label and obj['pk'] in drop_pks:
            continue  # drop the duplicate row entirely

        if obj['model'] in fk_models:
            v = obj['fields'].get(field_name)
            if v in remap:
                obj['fields'][field_name] = remap[v]
                fk_rewritten += 1

        m2m_field = m2m_model_fields.get(obj['model'])
        if m2m_field and obj['fields'].get(m2m_field):
            original = obj['fields'][m2m_field]
            remapped = [remap.get(pk, pk) for pk in original]
            deduped = list(dict.fromkeys(remapped))  # preserve order, drop dupes
            if deduped != original:
                obj['fields'][m2m_field] = deduped
                m2m_rewritten += 1

        fixed.append(obj)

    print(f"  Rewrote {fk_rewritten} FK reference(s) and {m2m_rewritten} M2M list(s).")
    return fixed


data = json.load(open(INPUT, encoding='utf-8'))
before = len(data)

# Every model referencing locations.State / locations.LGA, found via:
#   grep -rn "ForeignKey(State\|ManyToManyField(State" --include=*.py (excl. migrations)
#   grep -rn "ForeignKey(LGA\|ManyToManyField(LGA" --include=*.py (excl. migrations)
data = merge_duplicates(
    data, 'locations.state', ('name', 'country'),
    fk_models={'accounts.user', 'core.booking', 'core.activitylog', 'locations.lga'},
    m2m_model_fields={'core.artisanprofile': 'service_states'},
)
data = merge_duplicates(
    data, 'locations.lga', ('name', 'state'),
    fk_models={'accounts.user', 'core.booking', 'core.activitylog'},
    m2m_model_fields={'core.artisanprofile': 'service_lgas'},
)

print(f"Total objects: {before} -> {len(data)} (dropped {before - len(data)})")

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(data, f)

print(f"Wrote {OUTPUT}")
