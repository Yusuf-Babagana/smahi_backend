import os
from pathlib import Path
from datetime import timedelta
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')  # no insecure fallback — fail loudly if unset

DEBUG = config('DEBUG', default=False, cast=bool)

INSTALLED_APPS = [
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
        'DIRS': [],
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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

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

# Paystack (artisan registration fee)
PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY', default='')
PAYSTACK_PUBLIC_KEY = config('PAYSTACK_PUBLIC_KEY', default='')
ARTISAN_REGISTRATION_FEE = 2500  # Naira