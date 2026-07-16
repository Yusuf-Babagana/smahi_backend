# S-MAHII — Business Rules Specification

> **Canonical specification for what the application is SUPPOSED to do.**
> Companion to `KNOWLEDGE_BASE.md` (how it's built) and `DEPENDENCY_MAP.md` (how it's wired).
> Produced by the Business Rules Audit, 2026-07-15. Every "current behavior" statement below was verified against the live code on that date.
>
> **How to read the markers:**
> - ✅ **ENFORCED** — the rule exists and code enforces it. Breaking it is a bug.
> - ⚠️ **IMPLICIT** — the code *behaves* this way, but nothing enforces it as a rule; the behavior is an accident of implementation, not a decision.
> - ❓ **OPEN DECISION** — a product question nobody has answered. Numbered `D1…D24` for easy reference. **The product owner decides these; developers must not resolve them ad hoc.**
>
> **Maintenance rule:** any PR that changes a behavior described here must update this file in the same commit. When an OPEN DECISION is answered, record the answer here (with date) and move it to the enforced rules once implemented.

---

## 1. User Lifecycle

### Current behavior (verified)

| Rule | Status |
|---|---|
| One account per email (`User.email` unique, email is the login identifier) | ✅ |
| Roles: `client` (default), `artisan`, `agent`, `state_coordinator`, `admin` — exactly one role per user | ✅ (single CharField) |
| Role is chosen at registration and is **not editable** via the API afterwards (`UserUpdateSerializer` excludes it; role changes require Django admin) | ✅ |
| One user = at most one `ArtisanProfile` (DB-level OneToOne) — **a user can never own multiple artisan profiles** | ✅ |
| Registering with `role='artisan'` auto-creates a pending `ArtisanProfile` | ✅ |
| `state_coordinator` exists as a choice but has **no behavior, permissions, or UI anywhere** | ⚠️ |
| `is_active=False` blocks login **and** invalidates existing JWTs on their next request (SimpleJWT checks `is_active`) | ✅ |
| `email_verified` (added 2026-07-15): set `True` only by confirming an emailed OTP (Brevo). Separate from the artisan `is_verified` badge. OTP: 6 digits, hashed at rest, 10-min expiry, 5 attempts, 60s resend cooldown. Auto-sent at registration (best-effort) | ✅ |
| `email_verified` currently **gates nothing** — unverified-email users can do everything | ⚠️ (see D26) |
| Password reset (added 2026-07-15): public two-step flow — emailed OTP (`password-reset/request/`), then `email+code+new_password` (`.../confirm/`). Enumeration-safe: unknown emails get identical responses. Same OTP limits as email verification | ✅ |
| A password reset does **not** invalidate existing JWT sessions (token blacklist is off) — a stolen 7-day access / 30-day refresh token survives the password change | ⚠️ |
| `account_status` (active/inactive/suspended) is stored but **read by nothing** — "suspending" a user via this field does nothing | ⚠️ |
| A deactivated artisan (`is_active=False`) **still appears in public search** and can still be booked/messaged (nothing filters `user__is_active`) | ⚠️ |

### Open decisions

- **D1 — Suspension semantics.** What should suspending a user actually do? Proposed dimensions: block login, hide from search, freeze active bookings, block chat, notify counterparties. And is `account_status` the mechanism, or should it be removed in favor of `is_active`?
- **D2 — What happens to an artisan's ACTIVE bookings when they are suspended/deactivated?** Today: nothing — bookings stay in whatever status they had; the client has no signal. Options: auto-cancel with reason, freeze, or manual ops process.
- **D3 — `state_coordinator`:** define its purpose (verification oversight per state? agent management?) or delete the role.
- **D4 — Can a user hold two roles** (e.g., an artisan who also books other artisans as a client)? Current code: role is single, but nothing stops an artisan from *creating bookings as a client* (booking creation is not role-gated — see §2). Decide whether that's a feature or a bug.

---

## 2. Booking Lifecycle

> **Reworked 2026-07-16** (product-owner sign-off): D5, D8, D9, D10, and D11 are RESOLVED and implemented. Pricing is negotiated and paid **outside the app** — the platform never handles client→artisan money. (Separately, artisans owe a one-time ₦2,500 platform service fee at registration; Paystack integration pending — see §7.)

### Current behavior (verified, implemented 2026-07-16)

| Rule | Status |
|---|---|
| Booking creator is always the requesting user (`client` forced server-side) | ✅ |
| Only the booking's client and artisan can *see* it (role-scoped querysets) | ✅ |
| Only `role='client'` may create a booking (D9: `IsClient` on the create action) | ✅ |
| The `artisan` target must be `role='artisan'`, active, with an `ArtisanProfile`, and not the requester (D8). Verification is NOT required to be bookable — still open under D13 | ✅ |
| `scheduled_date` must be in the future (D10: past-dated bookings forbidden); create accepts either `scheduled_date` or mobile-style `date` + `time` (combined server-side, time defaults 09:00) | ✅ |
| `duration_hours` and `total_cost` are **optional** — price is agreed off-app after inspection, so it is unknown at request time | ✅ |
| Mobile field aliases: create accepts `description`→`service_description`, `location`→`address`; reads additionally return `description`, `location`, `date`, `time` alongside the canonical fields | ✅ |
| Only `status` and `cancellation_reason` are editable after creation | ✅ |
| Status changes follow the D5 transition table below; anything else → 400 | ✅ |
| `cancellation_reason` remains optional when cancelling (revisit if disputes emerge) | ✅ |
| `total_bookings` = **jobs completed** (D11): increments atomically (`F()`) on the transition to `completed`, not on creation | ✅ |
| DELETE on bookings is disabled (405) — a booking is a shared record; `cancelled` is the only way to end one | ✅ |
| Booking creation runs in a transaction (no orphan-booking 500s) | ✅ |

### State transitions — ✅ D5 RESOLVED (2026-07-16, artisan-only completion)

| From → To | Who | Notes |
|---|---|---|
| pending → confirmed | artisan | acceptance ("Accept" in the app) |
| pending → cancelled | either | artisan decline or client withdrawal |
| confirmed → in_progress | artisan | job started |
| confirmed → cancelled | either | |
| in_progress → completed | **artisan only** | unlocks review; increments `total_bookings` |
| in_progress → cancelled | ❌ nobody | dispute territory — deliberately not allowed (revisit with a dispute flow) |
| completed / cancelled | terminal | no transitions out (D6 confirmed: pending is entry-only) |

Enforced in `BookingUpdateSerializer.ALLOWED_TRANSITIONS`; counter side-effect in `BookingViewSet.perform_update`. Test coverage: `core/tests.py` (22 tests).

### Open decisions

- **D7 — Can an artisan "reject" a booking?** Still no `declined` status; artisan refusal uses `cancelled` (this is what the app's Decline button sends). Add a distinct status later if analytics need to separate refusals from withdrawals.
- ~~D5, D6, D8, D9, D10, D11~~ — resolved 2026-07-16 as described above.

---

## 3. Verification Lifecycle

### Current behavior (verified)

| Rule | Status |
|---|---|
| Verification request = 1–3 document images + optional info, submitted by the user for themselves | ✅ |
| **ANY authenticated user can submit a verification request** — clients and agents included (the artisan-only restriction exists only as a form hint, not enforcement) | ⚠️ |
| Agents see **all** pending requests — including, if they submitted one, **their own**; nothing prevents an agent approving their own request | ⚠️ |
| Approval sets BOTH `ArtisanProfile.verification_status='approved'` and `User.is_verified=True` (creating a profile if missing — even for a non-artisan) | ✅ (the dual-flag), ⚠️ (the profile-for-anyone side effect) |
| Rejection stores `rejection_reason`; the artisan may submit a new request | ✅ |
| **A rejected — or even APPROVED — request remains fully editable and deletable by its owner**: document images can be swapped after approval; the request underlying a live `is_verified` badge can be deleted | ⚠️ |
| Nothing ever un-sets `is_verified` — there is **no revocation path** (rejection after approval, fraud discovery, document expiry: all impossible without DB surgery) | ⚠️ |
| Multiple simultaneous pending requests by the same user are allowed | ⚠️ |
| **Verification gates nothing**: unverified and pending artisans appear in public search identically to approved ones and can be booked, reviewed, and messaged. The only effect is the badge fields the frontend displays | ⚠️ |

### Verification state transitions (current)

`pending → approved` (agent) ✅ · `pending → rejected` (agent) ✅ · `approved/rejected → (edited in place by owner)` ⚠️ · any own request → deleted by owner ⚠️ · `approved → revoked` **does not exist** ⚠️

### Open decisions

- **D12 — Who may submit?** Restrict to `role='artisan'`? (Strongly recommended; today's openness plus agent queue visibility = agents can self-verify.)
- **D13 — What does verification GATE?** The central product decision of this section. Options: (a) badge-only (current), (b) unverified artisans hidden from search, (c) discoverable but not bookable, (d) bookable with a warning. This decides what the verification program is *for*.
- **D14 — Conflict-of-interest rule:** may an agent process a request from someone they know / their own (if D12 ever allows)? Minimum: an agent must never process their own. Should approvals record location/territory (ties to D3)?
- **D15 — Editability by state:** proposed — `pending` requests editable by owner; `approved`/`rejected` requests frozen (immutable + undeletable) as audit records; resubmission after rejection = NEW request. Confirm?
- **D16 — Revocation:** should there be an `approved → revoked` path (agent- or admin-initiated)? What happens to the artisan's active bookings and search presence when revoked?
- **D17 — Document ownership & retention:** verification documents are government IDs on local disk. Who owns them, who may view them (today: the owner and any agent — and note `artisan_details` in the serializer means any agent listing pending requests receives the full user object), how long are they retained after approval/rejection/account deletion? (NDPA 2023 makes this a compliance question, not a preference.) Note: deleting a `VerificationRequest` row does **not** delete its image files from disk — orphan files accumulate.

---

## 4. Review Lifecycle

### Current behavior (verified)

| Rule | Status |
|---|---|
| One review per booking (DB-level OneToOne) | ✅ |
| Only the booking's client may create the review | ✅ (by ownership, not role) |
| Reviews allowed only for `status='completed'` bookings | ✅ (but see the guard's 500 bug, and note "completed" is self-declarable per §2) |
| Rating must be 1–5 | ✅ |
| **Reviews are immutable and undeletable via the API** (GET/POST only) — no editing after publication, no author deletion | ✅ |
| Reviews CAN be deleted via Django admin or by cascade (booking/user deletion) — and **the artisan's cached rating is NOT recomputed** on deletion (recompute runs only on `Review.save()`) | ⚠️ |
| A completed-then-reviewed booking can be moved back to `pending` by either party; the review survives, now attached to a "non-completed" booking | ⚠️ |
| Artisans cannot respond to reviews (no mechanism) | ⚠️ (absent, may be intentional) |

### Rating — source of truth ✅ (declared here as canon)

**The `Review` rows are the source of truth.** `ArtisanProfile.rating` and `total_reviews` are cached aggregates, recomputed from scratch by `update_rating()`. **Rule for all future code: any write path that creates, modifies, or deletes a Review — including admin actions, bulk operations, and cascades — must trigger a recompute.** A cached value that disagrees with the Review table is by definition wrong.

### Open decisions

- **D18 — Review editing/deletion policy:** confirm permanent immutability, or allow an edit window (e.g., 48h) / author deletion? Current behavior (immutable) is a defensible product stance — it just needs to be *chosen*.
- **D19 — Review disputes/moderation:** defamatory or fraudulent reviews — who can remove them (admin only?), and via what process? (Whatever the answer, it must respect the recompute rule above.)

---

## 5. Payment Lifecycle — DOES NOT EXIST

No payment code exists. `Booking.total_cost` is an unverified number typed by the client. Decisions required **before** any payment/wallet feature is designed (they shape the data model):

- **D20 — Payment model:** direct artisan payment (platform never touches money — records only), escrow (platform holds until completion), or wallet + escrow? Commission/fee structure?
- **D21 — Cancellation after payment:** refund rules per booking state (full before `confirmed`? partial after `in_progress`? who arbitrates?). *This is why the D5 transition table must be settled first — refund logic keys off booking states.*
- **D22 — Price source of truth:** does the artisan quote (offer/accept flow) replace the client-typed `total_cost`?

Until D20–D22 are answered, no code should treat `total_cost` as money.

---

## 6. Chat Lifecycle

### Current behavior (verified)

| Rule | Status |
|---|---|
| Chat is strictly 1-to-1; a conversation is found-or-created per user pair | ✅ |
| Only participants can read a conversation and its messages | ✅ |
| Users cannot message themselves | ✅ |
| **Any authenticated user may open a conversation with ANY user id** — no relationship (booking), role, or consent requirement; client↔client, anyone↔agent all possible | ⚠️ |
| Messages are plain text; no attachments, no editing, no deletion | ✅ (absent by design) |
| Read state: recipient marks a whole conversation read; per-message `is_read` | ✅ |
| No blocking, muting, reporting, or moderation of any kind; deactivating a user does not hide existing conversations | ⚠️ |

### Open decisions

- **D23 — Who may initiate chat with whom?** Options: anyone↔anyone (current), only client↔artisan, or only where a booking/inquiry relationship exists. Related: spam defense and a block/report mechanism — required before scale in an open marketplace.

---

## 7. Notification Rules — DO NOT EXIST

No email, SMS, or push infrastructure exists (verified: no email backend, no device-token model, no async layer). When notifications are built, this section must define: which events notify whom (booking created/status-changed, verification decided, new message, new review), on which channels, with what opt-out. Deferred until the feature is scheduled — but note the *dependency*: several decisions above (D1, D2, D16) have "notify the counterparty" as part of their answer.

---

## 8. Permission Matrix (as-implemented, verified 2026-07-15)

| Capability | Anon | Client | Artisan | Agent | State-coord | Admin (API) |
|---|---|---|---|---|---|---|
| Browse categories / locations / artisan search | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Register / login | ✅ | — | — | — | — | — |
| Edit own user profile | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| Own artisan-profile endpoint | — | — | ✅ (IsArtisan) | — | — | — |
| Submit verification request | — | ⚠️ yes (should be no?) | ✅ | ⚠️ **yes (incl. self-approval path)** | ⚠️ yes | ⚠️ yes |
| See verification requests | — | own ⚠️ | own ✅ | all pending ✅ | none | none |
| Edit/delete own verification request | — | ⚠️ any status | ⚠️ any status | ⚠️ any status | — | — |
| Approve/reject verification | — | — | — | ✅ (IsAgent) | — | — |
| Create booking | — | ✅ | ⚠️ yes | ⚠️ yes (then invisible to self) | ⚠️ yes | ⚠️ yes |
| See bookings | — | own-as-client ✅ | own-as-artisan ✅ | none | none | none |
| Set booking status | — | ⚠️ any | ⚠️ any | — | — | — |
| Create review (own completed booking) | — | ✅ | ✅ (as booking client) | ✅ (unreachable — can't see bookings) | — | — |
| Chat with any user | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| AI assistant | ⚠️ **✅ (open to the internet)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| Django admin panel | — | — | — | — | — | ✅ (is_staff) |

Cells marked ⚠️ are behaviors that exist but were almost certainly never decided. The matrix's intended shape is an open decision in aggregate: **D24 — sign off on the corrected matrix** (proposed corrections: verification submission = artisan-only; booking creation = client-only or client+artisan; AI = authenticated; agents barred from processing own requests).

---

## 9. State Transition Tables — Summary

| Entity | States | Rules today | Target |
|---|---|---|---|
| Booking | pending / confirmed / in_progress / completed / cancelled | **none** — any→any by either party ⚠️ | D5 table, pending sign-off |
| VerificationRequest | pending / approved / rejected | agent: pending→approved/rejected ✅; owner may edit/delete at any state ⚠️; no revocation ⚠️ | D15 + D16 |
| Review | (published) | immutable via API ✅; admin/cascade deletion skips recompute ⚠️ | D18 + recompute rule (§4) |
| User | active / is_active=False; `account_status` decorative | is_active enforced ✅; account_status ignored ⚠️ | D1 |

---

## 10. Data Ownership Rules

| Data | Owner | Who may read | Who may modify | Notes |
|---|---|---|---|---|
| User profile | the user | any authenticated user embedded in `_details` payloads (email, phone, GPS included) ⚠️ | the user | ⚠️ `UserSerializer` exposes email + phone_number to anyone who can see a booking/artisan/conversation containing that user — decide whether counterparties should see contact info *before* a confirmed booking (disintermediation risk: users bypassing the platform) |
| Artisan profile & rating | the artisan (fields), **the platform (rating/counters)** | public | artisan (fields); rating/counters are system-written only | Ratings are platform-owned trust data — never artisan-editable |
| Verification documents | the submitting user (subject), platform as custodian | owner + all agents ⚠️ | owner (any status ⚠️ — see D15) | Government IDs; NDPA-sensitive; see D17 |
| Bookings | shared: client + artisan | the two parties | the two parties (status only) | A booking is a *shared* record — one party must never be able to erase it unilaterally |
| Reviews | authored by client, **owned by the platform** | both parties (public display via rating) | nobody via API | Platform-owned trust data |
| Chat messages | sender authors; conversation is shared | participants only | nobody (no edit/delete) | |
| Media files | as per parent record | anyone with the URL (no signed URLs) ⚠️ | — | Files are **never deleted** when their DB records are — orphan files accumulate ⚠️ |

---

## 11. Deletion & Retention Policy

### Current behavior (verified — this is what the code does, not what anyone chose)

- **Deleting a User hard-CASCADEs**: their artisan profile, all verification requests, **all bookings on BOTH sides → those bookings' reviews**, and all their sent messages. Deleting one client silently deletes reviews and booking history belonging to *other people's* businesses — and the affected artisans' cached ratings are **not** recomputed (§4), so their displayed rating no longer matches their remaining reviews. ⚠️
- **Deleting a parent Category CASCADEs to all subcategories** (and nulls artisan profiles' category). One admin click can remove a whole taxonomy branch. ⚠️
- There is **no soft delete, no anonymization, no tombstones** anywhere, no account-deletion API, and no retention schedule for anything (verification documents included). Media files orphan on record deletion. ⚠️
- The only "backup" of the dev database is the git-tracked `db.sqlite3` — which is simultaneously the data-leak risk. ⚠️

### The rule this project needs (proposed, pending sign-off as part of D17 + below)

- **D25 — Deletion doctrine.** Proposed canon: **user-initiated account deletion = anonymize, never cascade.** Personal fields are scrubbed (NDPA erasure satisfied); bookings, reviews, and ratings survive as anonymized records because they are *shared/platform-owned* (§10). Hard deletion reserved for admin-verified special cases with a documented rating-recompute step. Verification documents: deleted on account deletion; retention period after rejection (e.g., 90 days?) to be set. Category deletion in admin: protected or two-step.

---

## Open Decisions Register (answer these; each unblocks implementation work)

| # | Decision | Blocks |
|---|---|---|
| D1 | Suspension semantics (`account_status`) | user mgmt hardening |
| D2 | Suspended artisan's active bookings | same |
| D3 | `state_coordinator` purpose or removal | role cleanup |
| D4 | Multi-role behavior (artisan-as-client) | booking rules |
| ~~D5~~ | ✅ RESOLVED 2026-07-16 — transition table implemented, artisan-only completion (§2) | — |
| ~~D6~~ | ✅ RESOLVED 2026-07-16 — pending is entry-only | — |
| D7 | `declined` status for artisan refusal? (currently maps to `cancelled`) | analytics nicety |
| ~~D8~~ | ✅ RESOLVED 2026-07-16 — bookable = active artisan with profile, no self-booking; verification NOT required (see D13) | — |
| ~~D9~~ | ✅ RESOLVED 2026-07-16 — booking creation is client-only | — |
| ~~D10~~ | ✅ RESOLVED 2026-07-16 — past-dated bookings forbidden | — |
| ~~D11~~ | ✅ RESOLVED 2026-07-16 — `total_bookings` = jobs completed | — |
| **D12** | **Verification submission = artisan-only?** | **agent self-approval hole** |
| **D13** | **What verification gates (search/booking/badge)** | **the point of the verification program** |
| D14 | Agent conflict-of-interest rule | verification hardening |
| D15 | Freeze processed verification requests? | same |
| D16 | Revocation path for `is_verified` | same |
| D17 | Verification document retention/access | NDPA compliance |
| D18 | Review immutability confirmed? | review policy |
| D19 | Review moderation process | same |
| D20–22 | Payment model / refunds / price source | all payment work |
| D23 | Chat initiation rules + blocking | chat hardening |
| D24 | Permission matrix sign-off | several fixes above |
| D25 | Deletion doctrine (anonymize vs cascade) | account deletion, NDPA |
| D26 | What should `email_verified` gate (booking? verification submission? nothing)? | email-verification follow-up |

**Fastest path:** with D5/D8/D9 done (2026-07-16), the remaining write-path integrity items are D12 and D13 (verification). The rest can be answered as their areas come up.

**Payments (context for D20–22, updated 2026-07-16):** client→artisan payment stays **outside the app** permanently by design. The only in-app money flow planned is the one-time **₦2,500 artisan registration service fee** (Paystack, not yet built).
