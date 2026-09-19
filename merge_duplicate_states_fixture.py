"""One-off fixup for the SQLite -> MySQL migration's `dumpdata` backup.

SQLite's default text comparison is byte-exact, but MySQL's default
collation folds case, accents, and — as it turns out — language-specific
things like German "ß" (which MySQL's collation treats as equal to "ss",
something no generic Unicode normalization reproduces) — so a worldwide
reference dataset (states, then cities/LGAs) that happened to have near-
duplicate rows in SQLite (found so far: "Dhaka" vs "Dhaka ", "Urumqi" vs
"Ürümqi", "Haßbergen" vs presumably "Hassbergen") satisfied SQLite's
unique constraints fine but trips `loaddata`'s IntegrityError against
MySQL. Rather than keep guessing at Unicode folding rules and fixing one
new language's quirk at a time, this asks MySQL itself what it considers
a duplicate: it loads every candidate name into a TEMPORARY table (never
touching the real locations_state/locations_lga tables) using that
column's *actual* collation (read from MySQL, not assumed), then lets
MySQL's own GROUP BY tell us which rows it would treat as colliding —
authoritative, not a guess.

For each such group it keeps the row whose name has no leading/trailing
whitespace (falling back to a deterministic shortest-name/lowest-pk
choice when that's ambiguous, with a printed NOTE so it can be
reviewed), re-points every FK/M2M reference at the kept row, and drops
the duplicate(s). Requires a working DATABASE_URL pointing at the target
MySQL database (only ever SELECTs/uses a session-local TEMPORARY table —
never writes to a real table). The JSON backup itself is read-only input;
output goes to a separate file.

Usage: python merge_duplicate_states_fixture.py
Reads:  data_backup.json
Writes: data_backup_step1_locations.json (input to merge_duplicate_users.py next)
"""
import json
import os
from collections import defaultdict

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smahi_backend.settings')
django.setup()

from django.db import connection  # noqa: E402

INPUT = 'data_backup.json'
OUTPUT = 'data_backup_step1_locations.json'


def get_collation(table, column):
    with connection.cursor() as cur:
        cur.execute(f"SHOW FULL COLUMNS FROM {table} WHERE Field = %s", [column])
        row = cur.fetchone()
        if row is None:
            raise SystemExit(f"Column {table}.{column} not found — is DATABASE_URL pointing at the right database?")
        return row[2]  # the 'Collation' column


def find_duplicate_pk_groups(rows, collation):
    """rows: [(pk, name, group_key_value), ...]. Returns a list of pk-lists,
    one per group MySQL's own collation considers colliding on (name,
    group_key_value). Uses a TEMPORARY table (session-local, auto-dropped,
    never touches a real table) so MySQL's actual comparison rules decide
    equality instead of a guessed Python approximation."""
    with connection.cursor() as cur:
        cur.execute("DROP TEMPORARY TABLE IF EXISTS _dedupe_scratch")
        cur.execute(f"""
            CREATE TEMPORARY TABLE _dedupe_scratch (
                pk INT PRIMARY KEY,
                name VARCHAR(255) COLLATE {collation},
                group_key INT
            )
        """)
        cur.executemany(
            "INSERT INTO _dedupe_scratch (pk, name, group_key) VALUES (%s, %s, %s)",
            rows,
        )
        cur.execute("""
            SELECT GROUP_CONCAT(pk) FROM _dedupe_scratch
            GROUP BY name, group_key HAVING COUNT(*) > 1
        """)
        result = [list(map(int, row[0].split(','))) for row in cur.fetchall()]
        cur.execute("DROP TEMPORARY TABLE _dedupe_scratch")
    return result


def pick_canonical(objs):
    """The whitespace-clean row wins. If that's ambiguous (0 or 2+ clean
    candidates), fall back to a deterministic (shortest name, then lowest
    pk) choice and flag it so the choice can be reviewed."""
    clean = [o for o in objs if o['fields']['name'] == o['fields']['name'].strip()]
    if len(clean) == 1:
        return clean[0]
    chosen = min(objs, key=lambda o: (len(o['fields']['name']), o['pk']))
    names = [(o['pk'], repr(o['fields']['name'])) for o in objs]
    print(f"  NOTE: ambiguous group (not a plain whitespace dupe): {names} -> keeping pk {chosen['pk']}")
    return chosen


def merge_duplicates(data, model_label, table, name_column, group_column, key_fields, fk_models, m2m_model_fields):
    """Merges duplicate rows of `model_label`, where "duplicate" is
    determined by MySQL's actual collation for `table`.`name_column`
    (queried live, not assumed). fk_models: model labels with a plain FK
    field (named after model_label's own name, e.g. 'state'/'lga')
    pointing at this model. m2m_model_fields: {model_label: field_name}
    for M2M fields pointing at this model."""
    field_name = model_label.split('.')[-1]  # 'locations.state' -> 'state'
    name_field, group_field = key_fields

    objs_by_pk = {}
    rows_for_mysql = []
    for obj in data:
        if obj['model'] == model_label:
            objs_by_pk[obj['pk']] = obj
            rows_for_mysql.append((obj['pk'], obj['fields'][name_field], obj['fields'][group_field]))

    collation = get_collation(table, name_column)
    print(f"{table}.{name_column} collation: {collation}")
    pk_groups = find_duplicate_pk_groups(rows_for_mysql, collation)

    remap = {}
    drop_pks = set()
    for pks in pk_groups:
        objs = [objs_by_pk[pk] for pk in pks]
        canon_pk = pick_canonical(objs)['pk']
        for pk in pks:
            if pk != canon_pk:
                remap[pk] = canon_pk
                drop_pks.add(pk)

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
    data, 'locations.state', 'locations_state', 'name', 'country_id', ('name', 'country'),
    fk_models={'accounts.user', 'core.booking', 'core.activitylog', 'locations.lga'},
    m2m_model_fields={'core.artisanprofile': 'service_states'},
)
data = merge_duplicates(
    data, 'locations.lga', 'locations_lga', 'name', 'state_id', ('name', 'state'),
    fk_models={'accounts.user', 'core.booking', 'core.activitylog'},
    m2m_model_fields={'core.artisanprofile': 'service_lgas'},
)

print(f"Total objects: {before} -> {len(data)} (dropped {before - len(data)})")

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(data, f)

print(f"Wrote {OUTPUT}")
