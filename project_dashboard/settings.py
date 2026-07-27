import os
from pathlib import Path

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
# System environment variables take precedence. The local .env file only
# supplies values that are not already present in the process environment.
load_dotenv(BASE_DIR / ".env", override=False)
DEBUG = os.environ.get("DASHBOARD_DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("DASHBOARD_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DASHBOARD_SECRET_KEY is required when DASHBOARD_DEBUG=0.")
    SECRET_KEY = "local-dashboard-development-key"
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DASHBOARD_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DASHBOARD_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
PUBLIC_SITE_URL = os.environ.get("DASHBOARD_PUBLIC_SITE_URL", "").strip().rstrip("/")
GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "api_mocker",
    "document_viewer",
    "workspace",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "project_dashboard.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "workspace.context_processors.page_visibility",
    ]},
}]
WSGI_APPLICATION = "project_dashboard.wsgi.application"
ASGI_APPLICATION = "project_dashboard.asgi.application"
DATABASE_ENGINE = os.environ.get("DASHBOARD_DATABASE_ENGINE", "sqlite").strip().lower()
if DATABASE_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(
                os.environ.get("SQLITE_DATABASE_PATH", BASE_DIR / "data" / "dashboard.sqlite3")
            ).expanduser().resolve(),
        }
    }
elif DATABASE_ENGINE == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("MYSQL_DATABASE", "local_project_dashboard"),
            "USER": os.environ.get("MYSQL_USER", "root"),
            "PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
            "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),
            "PORT": os.environ.get("MYSQL_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
            "CONN_MAX_AGE": 60,
        }
    }
else:
    raise ImproperlyConfigured(
        "DASHBOARD_DATABASE_ENGINE must be either 'mysql' or 'sqlite'."
    )
AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DASHBOARD_TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOG_LEVEL = os.environ.get("DASHBOARD_LOG_LEVEL", "INFO").upper()
DATABASE_LOG_LEVEL = os.environ.get("DASHBOARD_DATABASE_LOG_LEVEL", "WARNING").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": (
                "{asctime} {levelname} {name} "
                "process={process:d} thread={thread:d} {message}"
            ),
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": DATABASE_LOG_LEVEL,
            "propagate": False,
        },
        "gunicorn.access": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "gunicorn.error": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

API_MOCKER_LEGACY_DATA_FILE = Path(
    os.environ.get(
        "API_MOCKER_LEGACY_DATA_FILE",
        os.environ.get("API_MOCKER_DATA_FILE", BASE_DIR / "data" / "mocks.json"),
    )
).expanduser().resolve()

WORKSPACE_ROOT = Path(os.environ.get("DASHBOARD_WORKSPACE_ROOT", BASE_DIR.parent)).expanduser().resolve()
DOCUMENT_VIEWER_DEFAULT_DIRECTORY = Path(
    os.environ.get("DOCUMENT_VIEWER_DEFAULT_DIRECTORY", WORKSPACE_ROOT)
).expanduser().resolve()
REPOSITORY_LIMIT = int(os.environ.get("DASHBOARD_REPOSITORY_LIMIT", "12"))
SERVICE_ENDPOINTS = os.environ.get(
    "DASHBOARD_SERVICE_ENDPOINTS",
    "Dashboard|http://127.0.0.1:8001/health/,Gringotts API|http://127.0.0.1:8000,Local App|http://127.0.0.1:3000,Admin Console|http://127.0.0.1:8080",
)

if os.environ.get("DASHBOARD_TRUST_PROXY_HEADERS", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

if os.environ.get("DASHBOARD_SECURE_COOKIES", "0") == "1":
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
