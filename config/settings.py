import os
from pathlib import Path

from config.storage import (
    build_default_storage_config,
    neon_object_storage_enabled,
)


BASE_DIR = Path(__file__).resolve().parent.parent


# Local development only. Production must provide DJANGO_SECRET_KEY.
DJANGO_ENV = os.environ.get("DJANGO_ENV", "development").strip().lower()
IS_RENDER = "RENDER" in os.environ
IS_PRODUCTION = DJANGO_ENV == "production" or IS_RENDER
NEON_OBJECT_STORAGE_ENABLED = neon_object_storage_enabled(os.environ)
DEFAULT_DEBUG = "0" if IS_PRODUCTION else "1"
DEBUG = (
    os.environ.get("DJANGO_DEBUG", DEFAULT_DEBUG).strip().lower()
    in {"1", "true", "yes"}
)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")

if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError(
            "DJANGO_SECRET_KEY must be configured when DEBUG is disabled."
        )

    SECRET_KEY = (
        "django-insecure-local-development-only-not-for-production"
    )


RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = [
        host.strip()
        for host in os.environ.get(
            "DJANGO_ALLOWED_HOSTS",
            "127.0.0.1,localhost",
        ).split(",")
        if host.strip()
    ]

    if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "storages",
    "dashboard.apps.DashboardConfig",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# WhiteNoise is needed only in hosted production; local development keeps Django defaults.
if not DEBUG:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")


ROOT_URLCONF = "config.urls"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


WSGI_APPLICATION = "config.wsgi.application"


# Keep SQLite for local development; use an external persistent PostgreSQL database in production.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
elif DJANGO_ENV == "production" or IS_RENDER:
    raise RuntimeError(
        "DATABASE_URL must point to a persistent PostgreSQL database in production."
    )
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

STORAGES = {
    "default": build_default_storage_config(os.environ),
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "login"
# Production security settings. Render terminates TLS at its trusted proxy.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https") if IS_RENDER else None
)
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = int(
    os.environ.get(
        "DJANGO_SECURE_HSTS_SECONDS",
        "3600" if not DEBUG else "0",
    )
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "SAMEORIGIN" if DEBUG else "DENY"

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
app_url = os.environ.get("APP_URL", "").strip()
if app_url and app_url not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(app_url)
if RENDER_EXTERNAL_HOSTNAME:
    render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)

# Local synthetic demonstration only. Disabled by default and never enabled
# when DEBUG is false. This does not configure or call an AI provider.
SYNTHETIC_DEMO_ENABLED = (
    DEBUG
    and os.environ.get("MIRAI_ENABLE_SYNTHETIC_DEMO", "").strip().lower()
    in {"1", "true", "yes"}
)

# The Groq adapter may be enabled locally for synthetic-only tests.
# This flag alone must never route Doctor clinical notes to an external API.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b").strip() or "openai/gpt-oss-20b"
GROQ_PROVIDER_ENABLED = (
    DEBUG
    and os.environ.get("MIRAI_ENABLE_GROQ_PROVIDER", "").strip().lower()
    in {"1", "true", "yes"}
)

# External processing of actual clinical notes is disabled by default.
# Enable only after Mirai Labs has completed and documented the required
# privacy/security review and approved the selected provider/data flow.
EXTERNAL_CLINICAL_DATA_APPROVED = (
    os.environ.get("MIRAI_EXTERNAL_CLINICAL_DATA_APPROVED", "").strip().lower()
    in {"1", "true", "yes"}
)
