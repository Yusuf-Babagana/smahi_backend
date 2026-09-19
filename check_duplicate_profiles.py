"""Read-only diagnostic for the SQLite -> MySQL migration backup.

Investigates a `core_businessprofile.user_id` duplicate-entry error hit
during `loaddata` — since the backup was dumped with `--natural-foreign
--natural-primary`, every accounts.user object has NO 'pk' key at all
(identified purely by its natural key/email), and every FK to it
elsewhere is serialized as ["email"], not a plain id. Checks:

1. Two *different* emails in accounts.user that collide under MySQL's
   case-insensitive comparison (e.g. "User@x.com" vs "user@x.com") —
   SQLite's default comparison is case-sensitive, so both exist there as
   distinct users; MySQL won't allow both.
2. For each such pair, whether EITHER account has its own
   BusinessProfile/ArtisanProfile, plus how many Bookings/
   RegistrationPayments they're tied to — needed before deciding which
   account in a pair to keep, since merging two accounts that BOTH have
   their own BusinessProfile/ArtisanProfile would immediately recreate
   the exact OneToOne conflict this is investigating.

Prints findings only. Changes nothing.

Usage: python check_duplicate_profiles.py
Reads: data_backup.json
"""
import json
from collections import defaultdict

data = json.load(open('data_backup.json', encoding='utf-8'))


def describe_user(o):
    f = o['fields']
    return (
        f"email={f.get('email')!r}  name={f.get('first_name')} {f.get('last_name')}  "
        f"phone={f.get('phone_number')!r}  role={f.get('role')}  "
        f"account_status={f.get('account_status')}  is_active={f.get('is_active')}  "
        f"created_at={f.get('created_at')}"
    )


# Index every model that references a user by natural key, keyed by that
# natural key's email string, for the cross-reference lookups below.
business_by_email = {}
artisan_by_email = {}
bookings_as_client = defaultdict(int)
bookings_as_artisan = defaultdict(int)
payments_by_email = defaultdict(int)

for obj in data:
    f = obj['fields']
    if obj['model'] == 'core.businessprofile':
        business_by_email[f['user'][0]] = f
    elif obj['model'] == 'core.artisanprofile':
        artisan_by_email[f['user'][0]] = f
    elif obj['model'] == 'core.booking':
        bookings_as_client[f['client'][0]] += 1
        bookings_as_artisan[f['artisan'][0]] += 1
    elif obj['model'] == 'core.registrationpayment':
        payments_by_email[f['user'][0]] += 1


def cross_reference(email):
    parts = []
    if email in business_by_email:
        bp = business_by_email[email]
        parts.append(f"BusinessProfile(name={bp.get('business_name')!r}, status={bp.get('verification_status')})")
    if email in artisan_by_email:
        ap = artisan_by_email[email]
        parts.append(f"ArtisanProfile(category={ap.get('category')})")
    if bookings_as_client[email]:
        parts.append(f"{bookings_as_client[email]} booking(s) as client")
    if bookings_as_artisan[email]:
        parts.append(f"{bookings_as_artisan[email]} booking(s) as artisan")
    if payments_by_email[email]:
        parts.append(f"{payments_by_email[email]} registration payment(s)")
    return '; '.join(parts) if parts else '(no linked records)'


print("=== Case-insensitive duplicate emails among accounts.user ===")
email_groups = defaultdict(list)
for obj in data:
    if obj['model'] == 'accounts.user':
        email_groups[obj['fields']['email'].strip().lower()].append(obj)
email_dupes = {k: v for k, v in email_groups.items() if len(v) > 1}
print(f"{len(email_dupes)} duplicate email group(s)\n")
for key, objs in email_dupes.items():
    print(f"group: {key}")
    for o in objs:
        email = o['fields']['email']
        print(f"    {describe_user(o)}")
        print(f"      -> {cross_reference(email)}")
    print()
