import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
# The dev server only ever runs behind Docker Compose, where the host header is the service name.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.postgres",
    "shared",
    "retrieval",
]

# The project has no accounts, so DRF's default session/basic authentication has nothing to
# authenticate against — and the AnonymousUser it otherwise falls back to would pull
# django.contrib.auth and its tables into a project that owns no migration history.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}

ROOT_URLCONF = "api.urls"
WSGI_APPLICATION = "api.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ["POSTGRES_HOST"],
        "PORT": os.environ["POSTGRES_PORT"],
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "UTC"

VOYAGE_API_KEY = os.environ["VOYAGE_API_KEY"]

WEAVIATE_URL = os.environ["WEAVIATE_URL"]

GROQ_API_KEY = os.environ["GROQ_API_KEY"]

GROQ_MODEL = os.environ["GROQ_MODEL"]

# Soft-defaulted, unlike the credentials above: the real number comes from running
# `manage.py calibrate_threshold` against labelled questions, so 0.5 is only a starting point.
RELEVANCE_THRESHOLD = float(os.environ.get("RELEVANCE_THRESHOLD", "0.5"))

CALIBRATION_QUESTIONS_PATH = REPO_ROOT / "docs" / "calibration_questions.json"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
