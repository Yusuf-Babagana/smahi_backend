"""One-off fixup for the SQLite -> MySQL migration's `dumpdata` backup.

SQLite's email uniqueness is case-sensitive; MySQL's default collation
isn't. check_duplicate_profiles.py found 12 real accounts.user pairs
differing only by email casing — some are the same real person registered
twice (likely the same phone-keyboard auto-capitalize issue already fixed
for temp passwords, this time hitting the registration screen's email
field), some are two different real people whose emails collide only
under MySQL's comparison.

Reads the actual plan (which real emails to merge/rename) from a LOCAL,
NOT-git-committed `user_merge_plan.json` — see that file's own comment for
its shape. This script is the reusable logic only; it contains no real
customer data itself.

For a merge (keep <- drop): drops the losing accounts.user object, then
re-points every reference to it elsewhere (bookings, profiles, payments,
activity log, chat, notifications, sponsor/referral relationships, device
tokens, OTPs, admin log entries, outstanding JWTs) at "keep" instead. If
the entry has "drop_profile": true, the DROPPED account's OWN
BusinessProfile/ArtisanProfile is dropped rather than remapped (the
keeper already has an equivalent one — remapping would recreate the exact
OneToOne conflict this is fixing).

For a rename (old -> new): both accounts are real, different people who
happen to collide only by casing. Neither is dropped — just change the
email value in place and rewrite references to match. The renamed person
needs to be told their login email changed.

Verifies at the end that no case-insensitive duplicate email remains.

Usage: python merge_duplicate_users.py
Reads:  data_backup.json, user_merge_plan.json
Writes: data_backup_fixed.json
"""
import json
from collections import defaultdict

INPUT = 'data_backup.json'
PLAN = 'user_merge_plan.json'
OUTPUT = 'data_backup_fixed.json'

# Every model referencing accounts.User via a plain FK, found via:
#   grep -rn "ForeignKey(User\|ForeignKey('self'\|ForeignKey(settings.AUTH_USER_MODEL" --include=*.py (excl. migrations)
# plus admin.LogEntry and token_blacklist.OutstandingToken (Django/SimpleJWT
# built-ins, not this codebase's own models, but both carry a `user` FK and
# were present in the dumpdata output).
FK_MODELS = {
    'accounts.user': ('sponsor_coordinator', 'sponsor_agent'),
    'chat.message': ('sender',),
    'core.artisanprofile': ('user', 'registered_by'),
    'core.businessprofile': ('user', 'registered_by'),
    'core.bookingphoto': ('uploaded_by',),
    'core.disputereport': ('reporter', 'resolved_by'),
    'core.booking': ('client', 'artisan'),
    'core.registrationpayment': ('user',),
    'core.activitylog': ('actor', 'target_user'),
    'core.favorite': ('client',),
    'notifications.devicetoken': ('user',),
    'notifications.notification': ('recipient',),
    'notifications.otpcode': ('user',),
    'admin.logentry': ('user',),
    'token_blacklist.outstandingtoken': ('user',),
}

# ManyToManyField(User, ...), found via:
#   grep -rn "ManyToManyField(User" --include=*.py (excl. migrations)
M2M_MODELS = {
    'chat.conversation': ('participants',),
}

PROFILE_MODELS = {'core.businessprofile', 'core.artisanprofile'}


def is_natural_key_of(value, email):
    return isinstance(value, list) and len(value) == 1 and value[0] == email


def rewrite_references(data, old_email, new_email):
    for obj in data:
        for field in FK_MODELS.get(obj['model'], ()):
            if is_natural_key_of(obj['fields'].get(field), old_email):
                obj['fields'][field] = [new_email]
        for field in M2M_MODELS.get(obj['model'], ()):
            values = obj['fields'].get(field) or []
            obj['fields'][field] = [[new_email] if v == [old_email] else v for v in values]


plan = json.load(open(PLAN, encoding='utf-8'))
renames = plan['renames']  # {old_email: new_email}
merges = plan['merges']    # [{"keep": email, "drop": email, "drop_profile": bool}, ...]

data = json.load(open(INPUT, encoding='utf-8'))

# --- Renames: change the email in place, then rewrite every reference to
# the old natural key so it still resolves.
for old_email, new_email in renames.items():
    found = False
    for obj in data:
        if obj['model'] == 'accounts.user' and obj['fields']['email'] == old_email:
            obj['fields']['email'] = new_email
            found = True
    if not found:
        raise SystemExit(f"RENAME source not found in data: {old_email!r}")
    rewrite_references(data, old_email, new_email)
    print(f"Renamed {old_email!r} -> {new_email!r}")

# --- Merges: drop the loser's own account (and its redundant profile, if
# flagged), then re-point every remaining reference at the keeper.
all_emails = {obj['fields']['email'] for obj in data if obj['model'] == 'accounts.user'}
missing = {m['drop'] for m in merges} - all_emails
if missing:
    raise SystemExit(f"MERGE 'drop' email(s) not found in data: {missing}")
missing = {m['keep'] for m in merges} - all_emails
if missing:
    raise SystemExit(f"MERGE 'keep' email(s) not found in data: {missing}")

drop_emails = {m['drop'] for m in merges}
drop_profile_for = {m['drop'] for m in merges if m.get('drop_profile')}

fixed = []
for obj in data:
    if obj['model'] == 'accounts.user' and obj['fields']['email'] in drop_emails:
        continue  # drop the duplicate account entirely
    if obj['model'] in PROFILE_MODELS:
        u = obj['fields'].get('user')
        if isinstance(u, list) and len(u) == 1 and u[0] in drop_profile_for:
            continue  # drop the superseded duplicate profile, don't remap it
    fixed.append(obj)
data = fixed

for m in merges:
    before = json.dumps(data)  # cheap way to count actual changes below
    rewrite_references(data, m['drop'], m['keep'])
    after = json.dumps(data)
    print(f"Merged {m['drop']!r} -> {m['keep']!r}" + (" (profile dropped)" if m.get('drop_profile') else ""))
    if before == after:
        print(f"  NOTE: no references to {m['drop']!r} were found to rewrite — is that expected?")

# --- Self-check: no case-insensitive duplicate email should remain.
email_groups = defaultdict(list)
for obj in data:
    if obj['model'] == 'accounts.user':
        email_groups[obj['fields']['email'].strip().lower()].append(obj['fields']['email'])
remaining_dupes = {k: v for k, v in email_groups.items() if len(v) > 1}
if remaining_dupes:
    raise SystemExit(f"Plan incomplete — duplicates remain: {remaining_dupes}")
print("\nVerified: no case-insensitive duplicate emails remain.")

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(data, f)
print(f"Wrote {OUTPUT}")

if renames:
    print("\nFOLLOW-UP NEEDED — these accounts got a new email to resolve a")
    print("collision with a different real person; let them know, or point")
    print("them to password reset once they try logging in with it:")
    for old_email, new_email in renames.items():
        print(f"  {old_email} -> {new_email}")
