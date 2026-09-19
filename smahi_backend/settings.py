import os
from pathlib import Path
from datetime import timedelta
from decouple import config
import environ
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')  # no insecure fallback — fail loudly if unset

DEBUG = config('DEBUG', default=False, cast=bool)

INSTALLED_APPS = [
    # unfold (and its contrib apps) must be listed before
    # django.contrib.admin — it overrides the built-in admin templates.
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'accounts',
    'locations',
    'core',
    'chat',
    'notifications',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    # Compresses every response body (JSON API responses especially —
    # artisan lists, category/location lookups) before it goes out over the
    # network. Placed this high so it's the last thing to touch the
    # response (Django processes response-phase middleware bottom-to-top).
    # On a mobile connection this cuts real transfer time on top of
    # whatever server-side processing time the request already took.
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'smahi_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Must win over unfold's own admin/index.html via app_directories
        # (unfold is listed before our local apps in INSTALLED_APPS, so
        # without an explicit DIRS override its template would always be
        # found first) — see templates/admin/index.html.
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'smahi_backend.wsgi.application'

# Defaults to the existing SQLite file when DATABASE_URL is unset — local
# dev and any environment without it in .env keep working exactly as
# before. Setting DATABASE_URL (e.g. mysql://user:pass@host:3306/dbname)
# in production's .env is the only thing that switches the engine; no code
# change needed to move between SQLite and MySQL/Postgres.
DATABASES = {
    'default': environ.Env.db_url_config(
        config('DATABASE_URL', default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
    )
}

# utf8mb4 (not MySQL's older 3-byte-only "utf8") is required for emoji and
# other 4-byte characters in chat messages/names to save instead of raising
# an encoding error — irrelevant for SQLite, harmless to set unconditionally.
if DATABASES['default']['ENGINE'] == 'django.db.backends.mysql':
    DATABASES['default'].setdefault('OPTIONS', {})['charset'] = 'utf8mb4'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Storage for identity/verification documents (national IDs, proof of trade).
# Deliberately OUTSIDE MEDIA_ROOT and never wired to a URL/static mapping —
# these files must only ever be reachable through the authenticated,
# ownership-checked view in core.views.serve_verification_document, never
# via a raw MEDIA_URL path or a host static-file mapping (e.g. PythonAnywhere's
# "Static files" tab, which serves MEDIA_ROOT directly with no permission
# check at all).
PRIVATE_MEDIA_ROOT = BASE_DIR / 'private_media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        # Scoped throttles applied explicitly via throttle_scope on
        # sensitive/costly views (login, AI chat/transcribe, filing a
        # dispute report).
        'login': '10/min',
        'ai': '20/hour',
        'dispute': '10/hour',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=6),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# CORS_ALLOW_ALL_ORIGINS deliberately NOT enabled — this API is consumed by
# the mobile app (JWT bearer, no cookies) plus a small set of known web
# origins. Combining allow-all with allow-credentials is a known anti-pattern.
#
# Hardcoded rather than env-driven: a stale/malformed CORS_ALLOWED_ORIGINS
# value in the live .env (missing scheme, trailing comma producing an empty
# entry) repeatedly broke `manage.py migrate` in production. The mobile app
# doesn't need CORS at all (JWT bearer, not a browser) — only the website
# and local dev genuinely need to be listed here, so there's no real need
# for this to be configurable per-environment.
CORS_ALLOW_ALL_ORIGINS = False

CORS_ALLOWED_ORIGINS = [
    'https://www.smahiglobalservices.com',
    'https://smahiglobalservices.com',
    'http://localhost:3000',
    'http://localhost:19006',
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Hardcoded rather than env-driven, same reasoning as CORS_ALLOWED_ORIGINS
# above — a stale env value took the entire live site down with
# DisallowedHost errors on every request. This app has one deployment
# target; there's no real need for this to be configurable.
ALLOWED_HOSTS = ['smahi1.pythonanywhere.com', 'localhost', '127.0.0.1']

# Cookie hardening for production. SECURE_SSL_REDIRECT/HSTS deliberately NOT
# set here — PythonAnywhere terminates SSL at a proxy, and enabling a
# redirect without confirming SECURE_PROXY_SSL_HEADER matches its actual
# X-Forwarded-Proto behavior risks a redirect loop on the live site.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

OPENAI_API_KEY = config('OPENAI_API_KEY', default='')

# Public S-MAHII website the AI assistant reads live info from
# (coordinator phone numbers, announcements, ...). Optional extra pages
# as comma-separated paths, e.g. /contact,/coordinators
SMAHI_WEBSITE_URL = config('SMAHI_WEBSITE_URL', default='')
SMAHI_INFO_PAGES = config('SMAHI_INFO_PAGES', default='')

# Brevo (transactional email — OTP delivery)
BREVO_API_KEY = config('BREVO_API_KEY', default='')
BREVO_SENDER_EMAIL = config('BREVO_SENDER_EMAIL', default='no-reply@smahi.app')
BREVO_SENDER_NAME = config('BREVO_SENDER_NAME', default='S-MAHII')

# Optional standard SMTP fallback (e.g. Brevo SMTP relay or Gmail)
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp-relay.brevo.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

# Paystack (artisan registration fee)
PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY', default='')
PAYSTACK_PUBLIC_KEY = config('PAYSTACK_PUBLIC_KEY', default='')
ARTISAN_REGISTRATION_FEE = 2500  # Naira

# Custom sidebar nav — replaces Unfold's auto-generated app_label
# grouping (which just dumps every model under its raw Django app:
# "accounts", "core", "token_blacklist"...) with business-domain
# sections and a per-model icon, neither of which Unfold derives
# automatically from a plain ModelAdmin registration (verified: no
# `icon`/app-icon attribute is read anywhere in unfold/sites.py's
# get_app_list handling — icons only ever come from this exact
# SIDEBAR.navigation config). reverse_lazy is required, not reverse:
# urls.py hasn't loaded yet when settings.py is evaluated.
#
# Every entry here was generated from the actual admin.site._registry
# (all 27 registered models, Sep 2026) — if a new model is registered
# later, it simply won't appear in the sidebar (still reachable by
# direct URL / global search) until it's added here.
_UNFOLD_NAVIGATION = [
    {
        "title": "Overview",
        "separator": False,
        "items": [
            {"title": "Dashboard", "icon": "space_dashboard", "link": reverse_lazy("admin:index")},
        ],
    },
    {
        "title": "People",
        "separator": True,
        "items": [
            {"title": "Users", "icon": "person", "link": reverse_lazy("admin:accounts_user_changelist")},
            {"title": "Coordinators", "icon": "supervisor_account", "link": reverse_lazy("admin:accounts_coordinator_changelist")},
            {"title": "Agents", "icon": "badge", "link": reverse_lazy("admin:accounts_agent_changelist")},
            {"title": "Business Owners", "icon": "storefront", "link": reverse_lazy("admin:accounts_businessowner_changelist")},
            {"title": "Clients", "icon": "group", "link": reverse_lazy("admin:accounts_client_changelist")},
        ],
    },
    {
        "title": "Verification & Directory",
        "separator": True,
        "items": [
            {"title": "Artisan Profiles", "icon": "engineering", "link": reverse_lazy("admin:core_artisanprofile_changelist")},
            {"title": "Business Profiles", "icon": "domain", "link": reverse_lazy("admin:core_businessprofile_changelist")},
            {"title": "Verification Requests", "icon": "fact_check", "link": reverse_lazy("admin:core_verificationrequest_changelist")},
        ],
    },
    {
        "title": "Marketplace",
        "separator": True,
        "items": [
            {"title": "Bookings", "icon": "event_available", "link": reverse_lazy("admin:core_booking_changelist")},
            {"title": "Reviews", "icon": "star", "link": reverse_lazy("admin:core_review_changelist")},
            {"title": "Registration Payments", "icon": "payments", "link": reverse_lazy("admin:core_registrationpayment_changelist")},
            {"title": "Dispute Reports", "icon": "report", "link": reverse_lazy("admin:core_disputereport_changelist")},
            {"title": "Favorites", "icon": "favorite", "link": reverse_lazy("admin:core_favorite_changelist")},
        ],
    },
    {
        "title": "Locations",
        "separator": True,
        "items": [
            {"title": "Countries", "icon": "public", "link": reverse_lazy("admin:locations_country_changelist")},
            {"title": "States", "icon": "map", "link": reverse_lazy("admin:locations_state_changelist")},
            {"title": "LGAs", "icon": "location_city", "link": reverse_lazy("admin:locations_lga_changelist")},
        ],
    },
    {
        "title": "Communication",
        "separator": True,
        "items": [
            {"title": "Conversations", "icon": "forum", "link": reverse_lazy("admin:chat_conversation_changelist")},
            {"title": "Messages", "icon": "chat", "link": reverse_lazy("admin:chat_message_changelist")},
            {"title": "Notifications", "icon": "notifications", "link": reverse_lazy("admin:notifications_notification_changelist")},
        ],
    },
    {
        "title": "Platform",
        "separator": True,
        "items": [
            {"title": "Platform Settings", "icon": "settings", "link": reverse_lazy("admin:core_platformsettings_changelist")},
            {"title": "Categories", "icon": "category", "link": reverse_lazy("admin:core_category_changelist")},
            {"title": "Service Taxonomy", "icon": "account_tree", "link": reverse_lazy("admin:core_servicetaxonomy_changelist")},
            {"title": "Activity Logs", "icon": "history", "link": reverse_lazy("admin:core_activitylog_changelist")},
        ],
    },
    {
        "title": "Security & Access",
        "separator": True,
        "items": [
            {"title": "Groups", "icon": "shield", "link": reverse_lazy("admin:auth_group_changelist")},
            {"title": "OTP Codes", "icon": "pin", "link": reverse_lazy("admin:notifications_otpcode_changelist")},
            {"title": "Device Tokens", "icon": "smartphone", "link": reverse_lazy("admin:notifications_devicetoken_changelist")},
            {"title": "Outstanding Tokens", "icon": "vpn_key", "link": reverse_lazy("admin:token_blacklist_outstandingtoken_changelist")},
            {"title": "Blacklisted Tokens", "icon": "block", "link": reverse_lazy("admin:token_blacklist_blacklistedtoken_changelist")},
        ],
    },
]

# django-unfold — purely cosmetic theming for the admin site (mounted at
# the site root, see smahi_backend/urls.py). Every model's CRUD/list/
# filter/search behavior is unchanged; this only restyles it. Colors
# match the mobile app's own brand900/brand600 tokens
# (constants/theme.ts in the app repo) so the two feel like one product.
UNFOLD = {
    "SITE_TITLE": "S-MAHII Admin",
    "SITE_HEADER": "S-MAHII",
    "SITE_SUBHEADER": "Platform Administration",
    # This backend is API-only — '/' itself renders nothing, so "View
    # site" points at the actual public website instead.
    "SITE_URL": "https://www.smahiglobalservices.com",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "DASHBOARD_CALLBACK": "core.dashboard.dashboard_callback",
    # Built-in Cmd/Ctrl+K search across every registered model — reuses
    # each ModelAdmin's own already-permission-checked get_queryset() /
    # search_fields (see unfold.sites.AdminSite._search_models), so it can
    # never surface anything a user couldn't already reach via the normal
    # changelist search box. SIDEBAR.show_search/command_search are what
    # actually render the search box + Ctrl+K modal at all (confirmed in
    # unfold/templates/unfold/helpers/search.html) — COMMAND.search_models
    # alone enables the backend but leaves it with no visible entry point.
    "COMMAND": {"search_models": True, "show_history": True},
    "SIDEBAR": {"show_search": True, "command_search": True, "navigation": _UNFOLD_NAVIGATION},
    # A smooth ramp interpolated from the app's own three brand anchors
    # (constants/theme.ts: brand100/brand600/brand900) rather than eyeballed
    # per-step — the previous version literally duplicated brand600 into
    # both "500" and "600" (copy-paste), which made hover/active states on
    # buttons and the sidebar indistinguishable from their resting color.
    "COLORS": {
        "primary": {
            "50": "246 249 254", "100": "234 241 253", "200": "188 209 245",
            "300": "147 180 238", "400": "106 150 231", "500": "64 121 223",
            "600": "27 95 217", "700": "21 78 173", "800": "16 62 131",
            "900": "11 46 91", "950": "7 30 59",
        },
    },
}