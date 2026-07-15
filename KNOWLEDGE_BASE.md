# S-MAHII Backend — Knowledge Base

> **Single source of truth for this project.**
> Last full audit: 2026-07-14 (every model, view, serializer, URL, permission, management command, and setting was read).
> If code and this document disagree, the code wins — then fix this document.

---

## 1. System Overview

**S-MAHII** is a Django REST API powering a Nigerian **service-directory mobile app** (React Native / Expo frontend). It connects **clients** who need services with **artisans** who provide them (plumbers, electricians, tailors, mechanics, caterers, …).

Core product loop:

```
Register → Browse/search artisans (category + location/GPS) → Book → Artisan completes job → Client reviews → Artisan rating updates
```

Supporting flows:
- **Artisan verification**: artisans upload ID documents; **agents** approve/reject them.
- **Chat**: 1-to-1 messaging between users (typically client ↔ artisan).
- **AI assistant**: OpenAI-backed helper (`gpt-4o-mini`) that answers "find me a service" questions.

The app is **bilingual-aware**: every service category has an English `name` and a Hausa `name_ha` (primary market is Northern Nigeria).

**Stack**

| Layer | Technology |
|---|---|
| Framework | Django 4.2, Django REST Framework 3.16 |
| Auth | `djangorestframework-simplejwt` (JWT Bearer tokens) |
| Database | SQLite (`db.sqlite3`) — `psycopg2-binary` installed but PostgreSQL is **not** configured |
| Filtering | `django-filter` + DRF SearchFilter/OrderingFilter |
| CORS | `django-cors-headers` (currently allow-all) |
| Config | `python-decouple` reading `.env` |
| Media | Local filesystem (`media/`), Pillow for ImageFields |
| AI | `openai` SDK → `gpt-4o-mini` |
| Deploy-ready extras | gunicorn, whitenoise (installed, **not wired into MIDDLEWARE**) |

**What does NOT exist** (do not go looking for it): no Celery / background tasks, no scheduled jobs, no signals, no custom middleware, no payment gateway, no logging config, no CI, no websockets (chat is HTTP polling). Tests exist only in `notifications/tests.py` (the OTP suite, added 2026-07-15); a service-layer pattern exists only in `notifications/services.py`.

---

## 2. Folder Structure

```
smahi_backend/
├── manage.py
├── requirements.txt              # ⚠ missing `openai` and `django-filter` (see §15)
├── .env / .env.example           # env config (python-decouple)
├── db.sqlite3                    # live dev database (tracked in git — see §16)
├── API_DOCUMENTATION.md          # endpoint reference (partially stale)
├── README.md
├── project_overview.txt / project_additional_codes.txt   # historical notes
├── seed_categories.py            # legacy standalone seed script (superseded)
├── countries.csv / states.csv / cities.csv / *_cache.json # seed_locations artifacts
│
├── smahi_backend/                # PROJECT CONFIG
│   ├── settings.py               # single settings file (no base/dev/prod split)
│   ├── urls.py                   # root URL routing
│   ├── wsgi.py / asgi.py
│
├── accounts/                     # APP: users & auth
│   ├── models.py                 # User (custom, email login) + UserManager
│   ├── serializers.py            # Registration / read / update serializers
│   ├── views.py                  # register, login, profile
│   ├── urls.py                   # /api/auth/*
│   ├── admin.py                  # UserAdmin
│
├── locations/                    # APP: geo reference data
│   ├── models.py                 # Country → State → LGA
│   ├── serializers.py            # full + "Lite" serializers
│   ├── views.py                  # public list/detail/search views
│   ├── urls.py                   # /api/locations/*
│   ├── admin.py
│   └── management/commands/seed_locations.py
│
├── core/                         # APP: business domain
│   ├── models.py                 # Category, ArtisanProfile, VerificationRequest, Booking, Review
│   ├── serializers.py            # per-model read/create/update serializers
│   ├── views.py                  # all core ViewSets + AIChatView + haversine helper
│   ├── urls.py                   # /api/* (router)
│   ├── permissions.py            # IsArtisan / IsClient / IsAgent / IsAdmin
│   ├── admin.py
│   └── management/commands/
│       ├── seed_data.py                    # sample categories + 4 test users
│       ├── seed_categories_hierarchy.py    # canonical 5-parent category taxonomy
│       └── cleanup_orphan_categories.py    # one-time migration of orphan/duplicate categories
│
└── chat/                         # APP: 1-to-1 messaging
    ├── models.py                 # Conversation, Message
    ├── serializers.py
    ├── views.py                  # ConversationViewSet, MessageViewSet
    ├── urls.py                   # /api/chat/*
    └── admin.py                  # empty (models not registered)
```

---

## 3. App Responsibilities

| App | Owns | Depends on |
|---|---|---|
| **locations** | Country/State/LGA reference data, public lookup endpoints, `seed_locations` | nothing |
| **accounts** | Custom `User` model (`AUTH_USER_MODEL`), registration, login, JWT issuance, own-profile endpoint | `locations` (FKs), `core` (creates `ArtisanProfile` at registration — see §15) |
| **core** | Categories, artisan profiles & search, verification workflow, bookings, reviews, role permissions, AI chat | `locations`, `accounts` |
| **chat** | Conversations & messages between any two users | `accounts` (User only) |
| **notifications** | OTP issuance/verification (`OTPCode` model, `services.py`) + Brevo transactional-email client (`brevo.py`). Added 2026-07-15 | `accounts` User via lazy `AUTH_USER_MODEL` FK only; **imported BY accounts** (views call `send_otp`/`verify_otp`) |

**Communication style:** direct ORM imports and foreign keys. No signals, no events. Side effects are inline (overridden `save()` methods, `perform_create` hooks).

---

## 4. Authentication Flow

**Mechanism:** JWT (SimpleJWT), `Authorization: Bearer <access>` header.
DRF defaults (settings.py): `JWTAuthentication` + `IsAuthenticated` globally; public endpoints opt out with `AllowAny`.

**Token policy** (`SIMPLE_JWT` in settings):
- Access token: **7 days** (unusually long — deliberate for mobile UX)
- Refresh token: **30 days**, `ROTATE_REFRESH_TOKENS=True`, blacklist **off**

**Registration** — `POST /api/auth/register/` (`accounts/views.py::register_view`, `AllowAny`):
1. `UserRegistrationSerializer` validates: password == password_confirm (min 8 chars), first/last name required, rejects literal "User User" placeholder names.
2. `User.objects.create_user(...)` (custom `UserManager`, email normalized, password hashed).
3. **If `role == 'artisan'`**: an `ArtisanProfile` is auto-created with `verification_status='pending'` and the optional `category_id` from the request. This is THE hook that guarantees every artisan has a profile.
4. Response: serialized user + `{refresh, access}` token pair (auto-login after registration).

**Login** — `POST /api/auth/login/` (`login_view`, `AllowAny`):
- Hand-rolled (does **not** use Django's `authenticate()` backends): fetch `User` by email → `check_password()` → check `is_active` → issue tokens.
- Unknown email and wrong password both return 401 `"Invalid credentials."` (no user enumeration). Disabled account → 403.
- ⚠ `account_status` (active/inactive/suspended) is **not checked** here — only `is_active`.

**Refresh** — `POST /api/auth/token/refresh/` → stock SimpleJWT `TokenRefreshView`.

**Profile** — `GET/PUT/PATCH /api/auth/profile/` → `ProfileView` (RetrieveUpdate on `request.user`; read uses `UserSerializer`, write uses narrower `UserUpdateSerializer` — role/email/is_verified are not editable).

---

## 5. Authorization Flow

Three layers, applied consistently:

1. **Endpoint gate — permission classes.** Global default `IsAuthenticated`; public endpoints use `AllowAny`; role-restricted actions add a role class from `core/permissions.py`:
   ```python
   class IsArtisan(BasePermission):
       def has_permission(self, request, view):
           return request.user and request.user.is_authenticated and request.user.role == 'artisan'
   ```
   (`IsClient`, `IsAgent`, `IsAdmin` are identical apart from the role string. `IsAdmin` and `IsClient` are currently **defined but unused** in views.)

2. **Row security — role-scoped `get_queryset()`.** This is the project's universal pattern. Users never receive rows that aren't theirs, because the queryset itself is filtered:
   - `BookingViewSet`: clients see `client=user`, artisans see `artisan=user`, everyone else `none()`.
   - `ReviewViewSet`: scoped through `booking__client` / `booking__artisan`.
   - `VerificationRequestViewSet`: artisans see own; agents see all `pending`; others `none()`.
   - `chat`: conversations via `request.user.conversations`, messages require `conversation__participants=request.user`.

   **There are no object-level `has_object_permission` checks anywhere — queryset scoping is the only row defense. Never replace a scoped `get_queryset()` with `Model.objects.all()`.**

3. **Write-shape control — per-action serializers.** Sensitive fields are `read_only` or absent from update serializers (e.g. `Booking.client` is forced to `request.user` in `perform_create`; `BookingUpdateSerializer` exposes only `status` + `cancellation_reason`).

**Known gaps (documented, not yet fixed):** booking status transitions are not validated (either party can set any status); `state_coordinator` role has no permissions or behavior; `account_status` is never enforced.

---

## 6. User Roles

`User.role` — a plain CharField with choices. **This one string drives all authorization.**

| Role | Who | Can do |
|---|---|---|
| `client` | Service consumer (default role) | Search artisans, create bookings, review completed bookings, chat |
| `artisan` | Service provider | Everything a user can, plus: own `ArtisanProfile` (`/api/artisan/profile/`), submit `VerificationRequest`s, see/manage bookings addressed to them |
| `agent` | Field verifier | See all **pending** verification requests; `POST /api/verification/{id}/process/` to approve/reject |
| `state_coordinator` | Reserved | **No behavior implemented anywhere** — exists only in `ROLE_CHOICES` |
| `admin` | Platform staff | No API-level special handling in views (the `IsAdmin` class exists but is unused); operates through Django admin (`is_staff`/`is_superuser`) |

Related flags on User:
- `is_verified` — set `True` when an agent approves a verification request.
- `account_status` — active/inactive/suspended; **currently decorative** (nothing reads it except superuser creation defaults).
- `is_active` — Django's flag; the only one login actually checks.

Test users (created by `python manage.py seed_data`): `admin@smahi.com/admin123`, `client@smahi.com/client123`, `artisan@smahi.com/artisan123`, `agent@smahi.com/agent123`.

---

## 7. Database Relationships

```
Country 1──* State 1──* LGA                       (locations; CASCADE down the chain)
   ▲            ▲          ▲
   │ SET_NULL   │          │   (all location FKs from other apps are SET_NULL)
User ───────────┴──────────┘   User.country / .state / .lga  (+ latitude/longitude decimals)
  │
  ├── 1──1 ArtisanProfile (CASCADE)  ── FK Category (SET_NULL)
  │         └── M2M service_countries/states/lgas   ⚠ schema-only, NOT used in search (§15)
  │
  ├── 1──* VerificationRequest (artisan, CASCADE; reviewed_by SET_NULL)
  │
  ├── 1──* Booking as client  (CASCADE) ─┐
  ├── 1──* Booking as artisan (CASCADE) ─┤── Booking 1──1 Review (CASCADE)
  │                                       └── FKs country/state/lga (SET_NULL)
  │
  ├── M2M Conversation.participants ── Conversation 1──* Message (CASCADE)
  └── 1──* Message as sender (CASCADE)

Category 1──* Category (self-FK `parent`, CASCADE)   # 5 parents, ~70 subcategories
Category 1──* ArtisanProfile (SET_NULL)
```

Key integrity facts:
- **Deleting a User cascades** to their ArtisanProfile, VerificationRequests, Bookings (both sides), Messages — and Bookings cascade to Reviews. Deleting a user destroys transaction history.
- **Deleting a parent Category cascades to its subcategories** (self-FK CASCADE) but only nulls artisan profiles (SET_NULL).
- `Review` is OneToOne with `Booking` → one review per booking, enforced at DB level.
- `unique_together`: `State(name, country)`, `LGA(name, state)`.
- **Denormalized fields** (never trust them blindly, know their updaters):
  - `ArtisanProfile.rating` / `total_reviews` — recomputed from scratch by `ArtisanProfile.update_rating()`, which is called from `Review.save()`. Self-healing on next review.
  - `ArtisanProfile.total_bookings` — naive `+= 1` in `BookingViewSet.perform_create` (non-atomic, never decremented on cancellation).

---

## 8. Business Workflows

### 8.1 Artisan onboarding & verification
```
Register (role=artisan, optional category_id)
  → ArtisanProfile auto-created (verification_status='pending')     [accounts/serializers.py]
  → Artisan completes profile: PUT /api/artisan/profile/            [core ArtisanProfileView]
  → Artisan uploads documents: POST /api/verification/  (1–3 images)
  → Agent lists pending: GET /api/verification/
  → Agent decides: POST /api/verification/{id}/process/ {status: approved|rejected, rejection_reason?}
       approved → ArtisanProfile.verification_status='approved' AND User.is_verified=True
       rejected → rejection_reason stored; artisan may re-submit
```
Note: `ArtisanProfileView.get_object` uses `get_or_create`, so an artisan without a profile (edge case) gets one on first access.

### 8.2 Discovery / search
`GET /api/artisans/` (public). Filter parameters, all optional and combinable:
- `category_id` — numeric ID; **a parent category automatically expands to itself + all subcategories**; a non-numeric value falls back to case-insensitive category-name match.
- `country_id` / `state_id` / `lga_id` — filter on the **artisan User's own location FKs** (NOT the `service_*` M2Ms — deliberate).
- `latitude` + `longitude` (or `use_saved=true` to use the authenticated user's stored coordinates) — triggers **in-Python Haversine distance ranking**: whole filtered queryset is loaded, each artisan gets a `.distance` (km), list sorts nearest-first, artisans without GPS sink to the bottom (`inf`), then optional `max_distance` (km) cutoff, then pagination. Invalid coordinates silently fall back to unsorted.
- The computed `distance` is exposed by `ArtisanProfileSerializer.get_distance` (rounded to 1 dp, `null` when absent).

### 8.3 Booking lifecycle
```
Client: POST /api/bookings/ {artisan, service_description, address, country/state/lga, scheduled_date, duration_hours, total_cost}
  → client forced to request.user; artisan_profile.total_bookings += 1
Status flow (convention, NOT enforced in code):
  pending → confirmed → in_progress → completed → cancelled(any point, with cancellation_reason)
Updates: PATCH /api/bookings/{id}/ — only {status, cancellation_reason} are writable.
```
⚠ There is no server-side state machine: both parties can set any status. Pricing is client-submitted; there is no payment integration.

### 8.4 Review & rating
```
Client: POST /api/reviews/ {booking, rating 1–5, comment}
Guards: booking must belong to the client, be status='completed', and not already reviewed (OneToOne).
Effect:  Review.save() → booking.artisan.artisan_profile.update_rating()
         → rating = avg(all reviews), total_reviews = count, saved.
```
Reviews are immutable via API (`http_method_names = ['get', 'post', 'head', 'options']`).

### 8.5 Chat
```
POST /api/chat/conversations/get_or_create/ {recipient_id}   → finds existing 1-to-1 thread or creates it
GET  /api/chat/messages/?conversation_id=N                    → messages (participant-only)
POST /api/chat/messages/ {conversation_id, text}              → send; Message.save() bumps conversation.updated_at
POST /api/chat/messages/mark_as_read/ {conversation_id}       → marks all OTHERS' messages read
```
Conversation list is ordered by `updated_at` (most recent activity first); `ConversationSerializer` computes `last_message` and `unread_count` per request.

### 8.6 AI assistant
`POST /api/ai/chat/ {text}` (**AllowAny**) → OpenAI `gpt-4o-mini`, fixed system prompt (S-MAHII assistant, Nigeria, 2–3 sentence answers), `max_tokens=150`, `temperature=0.7`. 400 if empty text, 503 if `OPENAI_API_KEY` unset, 500 (with exception string — known leak) on API failure. Stateless: no conversation history is sent or stored.

---

## 9. API Catalog

Base: `/api/`. 🔓 = `AllowAny`, 🔒 = JWT required, 🎭 = role-restricted. Pagination: PageNumber, 20/page, **except** endpoints marked "no pagination".

### Auth — `/api/auth/` (accounts)
| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `register/` | 🔓 | Creates user (+ArtisanProfile if artisan); returns user + tokens. Accepts `category_id`. Best-effort sends an email-verification OTP (never fails registration). |
| POST | `email/verify/request/` | 🔒 | (Re)sends OTP to own email. 429 inside 60s cooldown; 503 if Brevo down/unconfigured. |
| POST | `email/verify/confirm/` | 🔒 | `{code}` → sets `User.email_verified=True`; returns message + updated user. 400 on bad/expired code or >5 attempts. |
| POST | `password-reset/request/` | 🔓 | `{email}` → emails reset OTP. **Always 200 with identical body** (no enumeration); cooldown/provider errors swallowed. |
| POST | `password-reset/confirm/` | 🔓 | `{email, code, new_password}` → `set_password`. Unknown email answers exactly like a wrong code. No tokens returned. ⚠ Existing JWTs stay valid after reset (blacklist off). |
| POST | `login/` | 🔓 | Email + password → user + tokens |
| POST | `token/refresh/` | 🔓 | SimpleJWT refresh |
| GET/PUT/PATCH | `profile/` | 🔒 | Own profile; write via `UserUpdateSerializer` |

### Locations — `/api/locations/` (all 🔓, all no-pagination)
| Method | Path | Notes |
|---|---|---|
| GET | `countries/` | Lite serializer (id, name, emoji, phone_code) |
| GET | `countries/<pk>/` | Full nested (states → LGAs) — heavy |
| GET | `states/` `states/<country_id>/` `?country_id=` | Lite serializer |
| GET | `states/<pk>/` | ⚠ route shadowed: `states/<int>/` resolves to the country-filter list, not detail |
| GET | `lgas/` `lgas/<state_id>/` `?state_id=` | |
| GET | `search/?q=` | Combined countries(≤5)/states(≤10)/LGAs(≤10) |

### Core — `/api/` (DefaultRouter + 2 extra paths)
| Method | Path | Access | Notes |
|---|---|---|---|
| GET | `categories/` | 🔓 | Parents with nested subcategories; `?search=` → flat EN/HA name search. No pagination. |
| GET | `categories/all/` | 🔓 | Every category, flat |
| GET | `categories/<pk>/` | 🔓 | |
| GET | `artisans/` | 🔓 | Main search — see §8.2 for params |
| GET | `artisans/<pk>/` | 🔓 | |
| GET/PUT/PATCH | `artisan/profile/` | 🎭 artisan | Own profile, get_or_create |
| GET/POST/PUT/PATCH/DELETE | `verification/` | 🔒 (scoped) | Artisan: own; Agent: pending |
| POST | `verification/<pk>/process/` | 🎭 agent | Approve/reject; approval sets is_verified |
| GET/POST/PUT/PATCH/DELETE | `bookings/` | 🔒 (scoped) | Filterable by `status`, `artisan`, `client` |
| GET/POST | `reviews/` | 🔒 (scoped) | Create only for own completed bookings |
| POST | `ai/chat/` | 🔓 | OpenAI proxy |

### Chat — `/api/chat/`
| Method | Path | Access | Notes |
|---|---|---|---|
| GET/POST/… | `conversations/` | 🔒 (scoped) | Own conversations only |
| POST | `conversations/get_or_create/` | 🔒 | `{recipient_id}` |
| GET | `messages/?conversation_id=` | 🔒 (scoped) | Empty without the param |
| POST | `messages/` | 🔒 | `{conversation_id, text}` |
| POST | `messages/mark_as_read/` | 🔒 | `{conversation_id}` |

### Admin
`/admin/` — Django admin. Registered: User, Country/State/LGA, Category, ArtisanProfile (stats read-only), VerificationRequest, Booking, Review. Chat models are **not** registered.

---

## 10. Third-Party Integrations

| Integration | Where | Details |
|---|---|---|
| **OpenAI** | `core/views.py::AIChatView` | `gpt-4o-mini` chat completion; key from `OPENAI_API_KEY` env; synchronous call inside the request. The only *runtime* third-party dependency. |
| **dr5hn/countries-states-cities-database** (GitHub) | `locations/.../seed_locations.py` | Seed-time only: downloads countries/states/cities CSVs; Nigeria (36 states + FCT, 774 LGAs) is hardcoded for accuracy; rest of world imported with cities stored as LGAs. Root-level `.csv`/`*_cache.json` files are its cache artifacts. |
| **Payments** | — | **None.** `Booking.total_cost` is an unverified client-submitted number. |
| **Brevo** (transactional email) | `notifications/brevo.py` | OTP delivery via `requests` POST to `api.brevo.com/v3/smtp/email` (10s timeout, never raises). Key from `BREVO_API_KEY`; sender from `BREVO_SENDER_EMAIL`/`BREVO_SENDER_NAME`. Unset key → graceful failure (503 on request endpoint; registration unaffected). |
| **Email/SMS/Push (other)** | — | No Django email backend, no SMS, no push. |
| **Cloud storage** | — | None. Media is local disk. |

Environment variables (read via `python-decouple` `config()` in settings.py):
`SECRET_KEY` (insecure default!), `DEBUG` (default True), `CORS_ALLOW_ALL_ORIGINS`, `CORS_ALLOWED_ORIGINS`, `OPENAI_API_KEY`, `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME`. `.env` is gitignored; `.env.example` is the template (it also lists `ALLOWED_HOSTS`, which settings **never reads** — hosts are hardcoded `['*', ...]`).

---

## 11. Validation Rules

Validation lives in **serializers first**, occasionally duplicated in views. Model validators only fire through serializers (custom `save()` calls skip `full_clean()`).

| Object | Rule | Where |
|---|---|---|
| Registration | `password == password_confirm`, min 8 chars | `UserRegistrationSerializer.validate` |
| Registration | first_name/last_name required, non-blank | field declarations |
| Registration | Rejects first="User" AND last="User" (frontend placeholder guard) | `validate` |
| Registration | Django's 4 stock password validators configured in settings — ⚠ but `create_user` doesn't call `validate_password`, so only the serializer's `min_length=8` actually applies to API registration | settings vs. serializer |
| Booking | `scheduled_date` must be in the future | `BookingSerializer.validate_scheduled_date` — ⚠ defined on the *read* serializer; **creates go through `BookingCreateSerializer`, which has no date check** |
| Booking | `duration_hours ≥ 0.5`, `total_cost ≥ 0` | model validators (enforced via serializer) |
| Review | rating 1–5 | model validators + `ReviewSerializer.validate_rating` |
| Review | booking must be `completed`, owned by the client, not already reviewed | `ReviewViewSet.perform_create` (operative) + `ReviewSerializer.validate_booking` (dead — `booking` is read_only on the serializer) |
| Verification process | status ∈ {approved, rejected} | `VerificationProcessSerializer` |
| Chat | recipient_id required, not self | `ConversationViewSet.get_or_create` view checks |
| AI chat | non-empty `text` | view check |
| ArtisanProfile | rating 0–5 (model validators) | model |

Known validation holes (documented as-is): no uniqueness guard against two parallel pending VerificationRequests; no booking-status transition rules; `BookingCreateSerializer` misses the future-date check; `int(recipient_id)` in chat can raise uncaught ValueError.

---

## 12. Existing Coding Conventions

Follow these when extending the codebase — consistency beats personal preference:

1. **ViewSets + DefaultRouter** for resource CRUD; **generics** (RetrieveUpdateAPIView) for singleton "my profile" endpoints; **function-based views** only in auth.
2. **Per-action serializers** via `get_serializer_class()`: a full read serializer (with nested `_details`), plus narrow `XxxCreateSerializer` / `XxxUpdateSerializer` for writes, plus `XxxLiteSerializer` for dropdown lists.
3. **`_details` suffix convention**: clients send FK **ids** (`country: 1`), responses include both the id and a nested read-only object (`country_details: {...}`) via `source=`. Used everywhere — keep it.
4. **Row security via role-scoped `get_queryset()`** (see §5). Every new authenticated ViewSet must scope its queryset by `request.user` and role, defaulting to `Model.objects.none()`.
5. **Role permission classes** live in `core/permissions.py` — add new roles there, don't inline role checks in views (existing views do compare `user.role` inside `get_queryset`, which is accepted for scoping, not for gating).
6. **Query optimization**: `select_related` for FKs and `prefetch_related` for M2M/reverse on list endpoints (already done in bookings, artisans, locations).
7. **Ownership forced server-side**: `perform_create(serializer.save(client=request.user))` pattern — never trust an owner id from the payload.
8. **Reference/dropdown endpoints** are `AllowAny` + `pagination_class = None`.
9. **Seeding via management commands** (idempotent `get_or_create`), not standalone scripts (`seed_categories.py` at root is legacy).
10. **Bilingual data**: any user-facing taxonomy field gets a `_ha` Hausa twin (`name` / `name_ha`); `icon` holds an Ionicons name string for the mobile app.
11. Style: no type hints, no docstring standard, tutorial-style inline comments (emoji markers 🔥👇 mark historical fixes). Imports occasionally mid-file (`core/views.py`) — don't imitate that; top-of-file imports preferred for new code.
12. Timestamps: every model has `created_at = auto_now_add` / `updated_at = auto_now`; default ordering declared in `Meta` (usually `-created_at`).

---

## 13. Common Reusable Functions & Building Blocks

| Helper | Location | What it does / when to reuse |
|---|---|---|
| `calculate_haversine_distance(lat1, lon1, lat2, lon2)` | `core/views.py` (top) | Great-circle km between two GPS points. Reuse for ANY proximity feature (don't re-derive). |
| `IsArtisan / IsClient / IsAgent / IsAdmin` | `core/permissions.py` | Role gates. `IsClient`/`IsAdmin` currently unused but available. |
| `UserManager.create_user / create_superuser` | `accounts/models.py` | The only sanctioned way to create users (normalizes email, hashes password). |
| `ArtisanProfile.update_rating()` | `core/models.py` | Recomputes rating/total_reviews from all reviews. Call after anything that changes review data. |
| `UserSerializer` | `accounts/serializers.py` | Canonical user representation; embedded as `*_details` in core and chat serializers — changing its fields changes MANY payloads. |
| `CountrySerializer/StateSerializer/LGASerializer` (+ Lite variants) | `locations/serializers.py` | Reused across accounts and core for `_details` expansion. |
| `FlatCategorySerializer` / `SubcategorySerializer` | `core/serializers.py` | Flat vs. nested category views; both expose EN + HA names. |
| Get-or-create singletons | `ArtisanProfileView.get_object`, `ConversationViewSet.get_or_create` | Pattern for "ensure the resource exists" endpoints. |
| Management commands | `seed_locations`, `seed_categories_hierarchy`, `seed_data`, `cleanup_orphan_categories` | Environment bootstrap order: locations → categories hierarchy → sample data. |

---

## 14. Important Files (read these first when touching an area)

| File | Why it matters |
|---|---|
| `smahi_backend/settings.py` | All config; note the **duplicate ALLOWED_HOSTS / CORS blocks — the later definitions win** |
| `accounts/models.py` | `AUTH_USER_MODEL`; role choices; email login; GPS fields |
| `accounts/serializers.py` | Registration side effect: **creates ArtisanProfile** — the accounts→core coupling point |
| `core/models.py` | Whole business domain + `update_rating` denormalization |
| `core/views.py` | Largest file: search/distance logic, verification workflow, booking side effects, AI view, haversine helper |
| `core/serializers.py` | All read/write shapes + the `distance`/`profession_name` computed fields |
| `core/permissions.py` | The role-gate vocabulary |
| `smahi_backend/urls.py` + each app's `urls.py` | Routing map (core router is mounted at bare `/api/`) |
| `locations/management/commands/seed_locations.py` | Nigeria's canonical 774-LGA dataset (hardcoded) + world import |
| `core/management/commands/seed_categories_hierarchy.py` | The canonical category taxonomy (5 parents, EN/HA names, icons) |
| `API_DOCUMENTATION.md` | Frontend contract — **update it whenever an endpoint changes** (already drifts: register example lacks `category_id`; country `code` field doesn't exist) |
| `db.sqlite3` | The live dev DB, currently tracked in git |

---

## 15. Hidden Dependencies & Gotchas

Things that will bite you because nothing announces them:

1. ~~`requirements.txt` is incomplete~~ **FIXED 2026-07-15**: `openai==2.45.0` and `django-filter==25.2` added (both were also installed into `venv`, which is the working environment — the sibling `env` folder is stale). Still true: `django-environ` and `uuid` are listed but unused; `reportlab` is installed with no code using it yet.
2. **accounts → core import**: `accounts/serializers.py` imports `core.models.ArtisanProfile`. Registration is where artisan profiles are born. Renaming/moving `ArtisanProfile` breaks registration.
3. **`service_countries/states/lgas` M2Ms are decorative**: schema + serializers expose them, but artisan search filters on `user__country/state/lga`. Don't "fix" search to use the M2Ms without a product decision — the frontend relies on current behavior.
4. **Distance search is in-Python**: `ArtisanViewSet.list()` materializes the entire filtered queryset to compute Haversine distances. Works at current scale; any change must preserve the `artisan.distance` attribute contract with `ArtisanProfileSerializer.get_distance`.
5. **`Review.save()` and `Message.save()` have side effects** (rating recompute; conversation timestamp bump). `bulk_create`/`update()` bypass them silently.
6. **Rating side effect assumes profile exists**: `Review.save()` does `booking.artisan.artisan_profile` — an artisan User without a profile raises `RelatedObjectDoesNotExist`. Registration + `get_or_create` in views normally guarantee the profile; keep that guarantee.
7. **Serializer cross-imports**: `core/serializers.py` ← `accounts/serializers.py` ← `locations/serializers.py`, and `chat/serializers.py` ← accounts. A circular import is one careless import away; add new cross-app imports with care (models→serializers direction only).
8. **`ReviewViewSet.perform_create` latent `NameError`**: it raises `serializers.ValidationError` but `core/views.py` never imports `serializers`. The guard clauses work until the error path executes.
9. **`BookingSerializer.validate_scheduled_date` doesn't run on create** (creates use `BookingCreateSerializer`). Past-dated bookings are currently possible.
10. **URL shadowing in locations**: `states/<int:...>/` maps to the list-filtered-by-country view, so `StateDetailView`/`CountryDetailView`-style state detail is unreachable at `states/<pk>/`.
11. **`seed_data` location lookup is broken**: it queries `Country.objects.get(code='NG')` but the field is `iso2`; a bare `except` swallows it, so test users are seeded with `None` locations. Run order matters anyway: `seed_locations` → `seed_categories_hierarchy` → `seed_data`.
12. **`profession_name` fallback references a ghost field**: `ArtisanProfileSerializer.get_profession_name` checks `user.service_category`, which does not exist on User — harmless via `hasattr`, but don't assume the field is real.
13. **Frontend contract quirks**: unpaginated endpoints return bare arrays while paginated ones return `{count, next, previous, results}` — the mobile app expects exactly this split. `distance` is `null` unless GPS params were sent.
14. **Settings double-definitions**: `ALLOWED_HOSTS` and the CORS block each appear twice in settings.py; only the later ones apply. Editing the first block does nothing.
15. **JWT blacklist is off**: logout is purely client-side token deletion; a stolen refresh token stays valid up to 30 days.

---

## 16. Things Future Developers Must NEVER Break

1. **The custom User model contract**: `AUTH_USER_MODEL='accounts.User'`, email as `USERNAME_FIELD`, no `username` field. Never create users except through `UserManager.create_user`. Never add a migration that assumes `username` exists.
2. **Registration auto-creates the pending ArtisanProfile** for `role='artisan'`. Downstream code (rating updates, artisan search, profile endpoint) assumes every artisan has a profile.
3. **Queryset scoping = the security model.** Any new or modified authenticated ViewSet must filter by `request.user`/role in `get_queryset()` and default to `.none()`. Removing a filter leaks other users' bookings/reviews/messages.
4. **Ownership is set server-side** (`perform_create` forcing `client`/`sender`/`artisan` from `request.user`). Never make these fields writable from the payload.
5. **The review→rating chain**: `Review.save()` → `update_rating()`. Any alternate write path for reviews (bulk ops, admin actions, data fixes) must call `update_rating()` itself.
6. **One review per booking** (OneToOne) and **reviews only for completed bookings** — business invariants the mobile app and rating integrity depend on.
7. **Verification approval must update BOTH flags**: `ArtisanProfile.verification_status='approved'` **and** `User.is_verified=True` (two flags, two models — the frontend reads both).
8. **`Message.save()` bumps `Conversation.updated_at`** — the chat list ordering depends on it.
9. **Category parent-expansion in artisan search**: filtering by a parent `category_id` must keep including all its subcategories; the frontend's top-level category tiles rely on it.
10. **Public + unpaginated contracts**: `categories/`, `countries/`, `states/`, `lgas/` must stay `AllowAny` and unpaginated (registration screens fetch them before any token exists), and their bare-array response shape must not change.
11. **The `_details` response convention** (id in, nested object out). The mobile app parses these shapes everywhere.
12. **Token lifetimes are a product decision** (7-day access for mobile). Don't "harden" them casually — coordinate with the frontend's refresh logic.
13. **EN/HA bilingual category data**: never drop `name_ha` or seed new categories without Hausa names; `?search=` must keep matching both languages.
14. **Nigeria's hardcoded location dataset** in `seed_locations` (36 states + FCT, 774 LGAs) is the market-critical data — never replace it with the generic CSV import, which is less accurate for Nigeria.
15. **JWT + `AllowAny` opt-out pattern**: global default is `IsAuthenticated`; every public endpoint is explicit. Never flip the global default to `AllowAny`.

---

*Maintenance rule: any PR that changes models, endpoints, permissions, or side effects must update the relevant section of this file and `API_DOCUMENTATION.md` in the same commit.*
