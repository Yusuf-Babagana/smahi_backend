"""Read-only diagnostic for the SQLite -> MySQL migration backup.

Investigates a `core_businessprofile.user_id` duplicate-entry error hit
during `loaddata` — since the backup was dumped with `--natural-foreign
--natural-primary`, every accounts.user object has NO 'pk' key at all
(identified purely by its natural key/email), and every FK to it
elsewhere is serialized as ["email"], not a plain id. Checks two
distinct possible causes:

1. Two BusinessProfile/ArtisanProfile fixture rows genuinely share the
   exact same user natural key (the same email) — a real one-user/
   two-profiles bug already present in SQLite.
2. Two *different* emails in accounts.user collide under MySQL's
   case-insensitive comparison (e.g. "User@x.com" vs "user@x.com") —
   SQLite's default comparison is case-sensitive, so both could exist
   there as distinct users, each fine on their own, but whichever one
   gets inserted second collides with the first once loaded into MySQL.

Prints findings only, with enough context per account (name, phone,
role, status, created_at) to tell a real duplicate registration apart
from two genuinely different people who happen to share an email up to
casing. Changes nothing.

Usage: python check_duplicate_profiles.py
Reads: data_backup.json
"""
import json
from collections import defaultdict

data = json.load(open('data_backup.json', encoding='utf-8'))


def user_key(fields_user):
    return tuple(fields_user) if isinstance(fields_user, list) else fields_user


def describe_user(o):
    f = o['fields']
    return (
        f"pk={o.get('pk', 'N/A (natural-key only)')}  email={f.get('email')!r}  "
        f"name={f.get('first_name')} {f.get('last_name')}  phone={f.get('phone_number')!r}  "
        f"role={f.get('role')}  account_status={f.get('account_status')}  "
        f"is_active={f.get('is_active')}  created_at={f.get('created_at')}"
    )


print("=== Case-insensitive duplicate emails among accounts.user ===")
email_groups = defaultdict(list)
for obj in data:
    if obj['model'] == 'accounts.user':
        email_groups[obj['fields']['email'].strip().lower()].append(obj)
email_dupes = {k: v for k, v in email_groups.items() if len(v) > 1}
print(f"{len(email_dupes)} duplicate email group(s)")
for key, objs in email_dupes.items():
    print(f"  group: {key}")
    for o in objs:
        print(f"    {describe_user(o)}")

for model in ('core.businessprofile', 'core.artisanprofile'):
    print(f"\n=== Duplicate {model} rows sharing the same user natural key ===")
    groups = defaultdict(list)
    for obj in data:
        if obj['model'] == model:
            groups[user_key(obj['fields']['user'])].append(obj)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"{len(dupes)} duplicate user(s)")
    for key, objs in dupes.items():
        print(f"  user={key}:")
        for o in objs:
            print(f"    pk={o.get('pk', 'N/A')}  {o['fields']}")
