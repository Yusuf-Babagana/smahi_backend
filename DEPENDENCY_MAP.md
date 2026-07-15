# S-MAHII Backend — Dependency Map

> Companion to `KNOWLEDGE_BASE.md`. Generated from a full import/FK audit on 2026-07-14.
> Every edge below was verified by grepping actual `import` statements and model field definitions — nothing is assumed.

---

## 1. App-Level Dependency Diagram

Arrows point **from the dependent app to the app it depends on** (A ──▶ B means "A imports from B").

```
                    ┌─────────────────────────────────────────────┐
                    │                                             │
                    │            ┌───────────────┐                │
                    │            │   locations   │  (foundation:  │
                    │            │ Country/State │   depends on   │
                    │            │     /LGA      │   nothing)     │
                    │            └───────▲───────┘                │
                    │                    │                        │
                    │        ┌───────────┼───────────┐            │
                    │        │           │           │            │
                    │  models FK    serializers   models FK       │
                    │        │           │        + M2M           │
                    │  ┌─────┴─────┐     │     ┌─────┴─────┐      │
                    │  │ accounts  │◀────┼─────│   core    │      │
                    │  │  (User)   │─ ─ ─┼─ ─ ▶│ (domain)  │      │
                    │  └─────▲─────┘     │     └───────────┘      │
                    │        │      solid: core.serializers       │
                    │        │        imports accounts.UserSerializer
                    │        │      dashed: accounts.serializers  │
                    │        │        imports core.ArtisanProfile │
                    │        │        (⚠ MUTUAL COUPLING, §6)     │
                    │  ┌─────┴─────┐                              │
                    │  │   chat    │  (depends only on accounts)  │
                    │  └───────────┘                              │
                    └─────────────────────────────────────────────┘

  smahi_backend (project pkg) ──▶ all four apps (urls.py includes; settings INSTALLED_APPS)
```

**Layering (clean direction):** `locations` → `accounts` → `core`, with `chat` hanging off `accounts`.
**Violation of layering:** the `accounts ⇄ core` mutual edge (dashed above) — detailed in §6.

---

## 2. App Dependency Table

| App | Depends on (imports FROM) | Depended on by (imported BY) | Nature of the edges |
|---|---|---|---|
| **locations** | — (nothing) | accounts, core | `accounts/models.py` + `core/models.py` FK/M2M to Country/State/LGA; `accounts/serializers.py` + `core/serializers.py` embed its serializers |
| **accounts** | locations (models + serializers), **core (models — reverse edge!)** | core, chat, *(every app implicitly via `AUTH_USER_MODEL` / `get_user_model()`)* | Supplies `User` + `UserSerializer` to everyone; consumes `ArtisanProfile` at registration |
| **core** | locations (models + serializers), accounts (serializers; User via `get_user_model()`) | **accounts** (serializers import `ArtisanProfile`), root `seed_categories.py` | The domain hub — most edges terminate here |
| **chat** | accounts (serializers; User via `get_user_model()`) | — (nothing imports chat) | Leaf app; safest to modify |
| **smahi_backend** (project) | all apps (URL includes, INSTALLED_APPS, `AUTH_USER_MODEL`) | all apps (implicitly, via `django.conf.settings`) | Config only |

---

## 3. Model → Model Reference Map

Legend: `FK` ForeignKey, `1:1` OneToOne, `M2M` ManyToMany. Cross-app edges are **bold**.

| Source model | Field | Target model | Type | on_delete | Notes |
|---|---|---|---|---|---|
| locations.State | `country` | locations.Country | FK | CASCADE | delete country ⇒ delete its states |
| locations.LGA | `state` | locations.State | FK | CASCADE | delete state ⇒ delete its LGAs |
| **accounts.User** | `country` / `state` / `lga` | **locations.\*** | FK | SET_NULL | user survives location deletion |
| core.Category | `parent` | core.Category (self) | FK | CASCADE | **delete parent ⇒ delete all subcategories** |
| **core.ArtisanProfile** | `user` | **accounts.User** | 1:1 | CASCADE | `related_name='artisan_profile'` — accessed all over core |
| core.ArtisanProfile | `category` | core.Category | FK | SET_NULL | |
| **core.ArtisanProfile** | `service_countries/states/lgas` | **locations.\*** | M2M | — | ⚠ schema-only; NOT used in search |
| **core.VerificationRequest** | `artisan` | **accounts.User** | FK | CASCADE | `limit_choices_to role='artisan'` |
| **core.VerificationRequest** | `reviewed_by` | **accounts.User** | FK | SET_NULL | the approving agent |
| **core.Booking** | `client` | **accounts.User** | FK | CASCADE | `related_name='client_bookings'` |
| **core.Booking** | `artisan` | **accounts.User** | FK | CASCADE | `related_name='artisan_bookings'` |
| **core.Booking** | `country` / `state` / `lga` | **locations.\*** | FK | SET_NULL | |
| core.Review | `booking` | core.Booking | 1:1 | CASCADE | one review per booking (DB-enforced) |
| **chat.Conversation** | `participants` | **accounts.User** | M2M | — | always used as a pair |
| chat.Message | `conversation` | chat.Conversation | FK | CASCADE | |
| **chat.Message** | `sender` | **accounts.User** | FK | CASCADE | |

**Cascade blast radius of deleting a User:** ArtisanProfile, all VerificationRequests, all Bookings (as client AND as artisan) → which cascades to their Reviews, all sent Messages. Conversations survive (M2M) but become half-empty.

**Hidden model-level side-effect edges** (not FKs, but runtime dependencies):
- `core.Review.save()` → `booking.artisan.artisan_profile.update_rating()` (Review depends on ArtisanProfile existing).
- `chat.Message.save()` → writes `conversation.updated_at` (Message mutates Conversation).
- `core.BookingViewSet.perform_create` → increments `ArtisanProfile.total_bookings`.

---

## 4. Serializer → Serializer Reference Map

Composition = "embeds as nested `_details` field".

```
locations.LGASerializer ◀── locations.StateSerializer ◀── locations.CountrySerializer
        ▲  ▲  ▲            (nested lgas)                  (nested states)
        │  │  │
        │  │  └──────────────────────────────┐
        │  └──────────────┐                  │
        │                 │                  │
accounts.UserSerializer  core.ArtisanProfileSerializer   core.BookingSerializer
  (country/state/lga      (service_* details +           (country/state/lga
   _details)               user_details ──▶ UserSerializer)  _details + client/artisan
        ▲                                                  _details ──▶ UserSerializer)
        │                                                        ▲
        ├── core.VerificationRequestSerializer                   │
        │     (artisan_details, reviewed_by_details)   core.ReviewSerializer
        ├── chat.ConversationSerializer                  (booking_details ──▶ BookingSerializer)
        │     (participants_details)
        └── chat.MessageSerializer (sender_email only — source lookup, no embed)

core.CategorySerializer ◀── core.SubcategorySerializer   (nested subcategories)
core.FlatCategorySerializer (standalone)
locations.CountryLiteSerializer / StateLiteSerializer (standalone, dropdowns)
```

| Serializer | Directly embeds | Transitive payload depth |
|---|---|---|
| `accounts.UserSerializer` | Country/State/LGA serializers | 2 levels (⚠ StateSerializer nests ALL its LGAs; CountrySerializer nests ALL states→LGAs — a user in Nigeria serializes the full Nigeria tree in `country_details`) |
| `core.ArtisanProfileSerializer` | UserSerializer + 3 location serializers ×2 (user's + service_*) | 3 levels — the heaviest payload in the API |
| `core.BookingSerializer` | UserSerializer ×2 + location ×3 | 3 levels |
| `core.ReviewSerializer` | BookingSerializer | 4 levels (review → booking → users → locations) |
| `chat.ConversationSerializer` | UserSerializer (many) + MessageSerializer (last_message) | 3 levels |

**Implication:** widening `UserSerializer` or `StateSerializer` fattens nearly every response in the API. Changing `UserSerializer.fields` is a project-wide API contract change.

---

## 5. ViewSet / View → Dependency Map

There is **no formal service layer**; "services" here are the helpers, model methods, and external clients each view actually calls.

| View / ViewSet (file) | Serializers used | Permissions | Internal helpers / side effects | External services |
|---|---|---|---|---|
| `register_view` (accounts) | UserRegistrationSerializer, UserSerializer | AllowAny | `UserManager.create_user`; **creates core.ArtisanProfile** | SimpleJWT `RefreshToken.for_user` |
| `login_view` (accounts) | UserSerializer | AllowAny | `check_password`, `is_active` check | SimpleJWT |
| `ProfileView` (accounts) | UserSerializer / UserUpdateSerializer | IsAuthenticated | — | — |
| `CountryList/Detail`, `StateList/Detail`, `LGAList`, `location_search` (locations) | Country/State/LGA (+Lite) serializers | AllowAny | — | — |
| `CategoryViewSet` (core) | CategorySerializer / FlatCategorySerializer | AllowAny | EN/HA search branching | — |
| `ArtisanViewSet` (core) | ArtisanProfileSerializer | AllowAny | **`calculate_haversine_distance`** (module-level helper); parent-category expansion; in-Python sort/filter | — |
| `ArtisanProfileView` (core) | ArtisanProfileSerializer / UpdateSerializer | IsAuthenticated + **IsArtisan** | `get_or_create` profile | — |
| `VerificationRequestViewSet` (core) | VerificationRequestSerializer / ProcessSerializer | IsAuthenticated; `process` action: + **IsAgent** | approval flips ArtisanProfile.verification_status AND User.is_verified | — |
| `BookingViewSet` (core) | Booking / Create / Update serializers | IsAuthenticated (role-scoped queryset) | `total_bookings += 1` on create | — |
| `ReviewViewSet` (core) | ReviewSerializer | IsAuthenticated (role-scoped queryset) | triggers `Review.save()` → `update_rating()` | — |
| `AIChatView` (core) | — (raw dict) | **AllowAny** | reads `settings.OPENAI_API_KEY` | **OpenAI** `gpt-4o-mini` (synchronous) |
| `ConversationViewSet` (chat) | ConversationSerializer | IsAuthenticated (own conversations) | get_or_create pair logic | — |
| `MessageViewSet` (chat) | MessageSerializer | IsAuthenticated (participant-scoped) | `Message.save()` bumps conversation | — |

Shared building blocks and their consumers:

| Reusable unit | Location | Consumed by |
|---|---|---|
| `calculate_haversine_distance` | `core/views.py` | ArtisanViewSet.list (only) |
| `IsArtisan` / `IsAgent` | `core/permissions.py` | ArtisanProfileView / VerificationRequestViewSet.process |
| `IsClient` / `IsAdmin` | `core/permissions.py` | **nobody (dead but available)** |
| `ArtisanProfile.update_rating()` | `core/models.py` | `Review.save()` |
| `UserSerializer` | `accounts/serializers.py` | core (3 serializers), chat (1), accounts views |

---

## 6. Coupling Hotspots & Circular Dependencies

### 🔴 The one true circular coupling: `accounts ⇄ core`

```
accounts/serializers.py ──imports──▶ core.models.ArtisanProfile     (line 6)
core/serializers.py     ──imports──▶ accounts.serializers.UserSerializer  (line 4)
```

**Why it doesn't crash:** the two edges touch different modules (`accounts.serializers → core.models`, and `core.serializers → accounts.serializers`), so Python never completes a cycle at import time. `core.models` imports nothing from accounts (it uses `get_user_model()`, resolved lazily via settings).

**Why it's fragile:** one careless addition closes the loop —
- `core/models.py` importing anything from `accounts.serializers` ⇒ ImportError at startup.
- `accounts/serializers.py` importing from `core.serializers` (instead of `core.models`) ⇒ ImportError at startup.

**Rule for new code:** cross-app imports must flow **models ← serializers** and respect the layer order `locations → accounts → core → (chat)`. If accounts ever needs more core behavior, invert it: move the "create profile on artisan registration" side effect into core (e.g., called from the view) rather than adding more core imports into accounts.

### 🟠 Tight-coupling hotspots (not circular, but high blast radius)

| Hotspot | Coupled parties | Risk when changed |
|---|---|---|
| `UserSerializer` | accounts ← core(×3) + chat(×1) embeds | Field changes ripple into artisan, booking, verification, conversation payloads simultaneously |
| `User.role` string values | permissions.py, every `get_queryset()` role branch, `limit_choices_to`, registration side effect | Renaming a role string silently empties querysets (string comparison, no FK integrity) |
| `ArtisanProfile` | accounts.serializers (creation), core views (search, verification, bookings counter), core models (Review.save) | Renaming/moving it breaks registration + rating chain |
| `artisan.distance` attribute contract | `ArtisanViewSet.list` (producer) ↔ `ArtisanProfileSerializer.get_distance` (consumer) | Invisible contract via `setattr`; refactoring list() must preserve it |
| Nested location serializers | `StateSerializer.lgas` / `CountrySerializer.states` full trees | Embedded in UserSerializer → every `_details` payload; payload size scales with location data volume |
| `smahi_backend.settings` | `OPENAI_API_KEY` read directly in `AIChatView` | View is untestable without settings; key rotation = redeploy |
| Frontend response shapes | unpaginated bare arrays vs. paginated envelopes; `_details` convention | Mobile app parses these exactly; see KNOWLEDGE_BASE §16 |

### 🟢 Clean/low-coupling zones
- **locations**: zero inbound imports into it from its own dependencies; pure foundation. Safe to extend.
- **chat**: leaf app, nothing imports it; only touches User. Safest place to work.
- **Management commands**: each imports only its own app's models (+ locations for seed_data); no runtime coupling.

---

## 7. Full Import Edge List (ground truth)

Every cross-app `import` statement in the codebase (excluding same-app and framework imports):

| # | File | Imports | Direction |
|---|---|---|---|
| 1 | `accounts/models.py:3` | `locations.models` (Country, State, LGA) | accounts → locations |
| 2 | `accounts/serializers.py:3` | `locations.serializers` (3 serializers) | accounts → locations |
| 3 | `accounts/serializers.py:6` | `core.models` (ArtisanProfile) | **accounts → core** ⚠ reverse edge |
| 4 | `core/models.py:4` | `locations.models` (Country, State, LGA) | core → locations |
| 5 | `core/serializers.py:4` | `accounts.serializers` (UserSerializer) | core → accounts |
| 6 | `core/serializers.py:5` | `locations.serializers` (3 serializers) | core → locations |
| 7 | `chat/serializers.py:4` | `accounts.serializers` (UserSerializer) | chat → accounts |
| 8 | `core/management/commands/seed_data.py:4` | `locations.models` | core → locations |
| 9 | `seed_categories.py:8` (root, legacy) | `core.models` (Category) | script → core |
| — | `core/models.py`, `chat/models.py` | `get_user_model()` (lazy) | core/chat → accounts (via settings, cycle-safe) |
| — | `core/views.py:285` | `openai` + `django.conf.settings` | core → external |

---

*Maintenance rule: adding any cross-app import updates §7 (and usually §1/§2). If a new edge points "backwards" against `locations → accounts → core → chat`, stop and redesign — see §6.*
