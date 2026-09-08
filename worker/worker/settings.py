import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False

INSTALLED_APPS = [
    "django.contrib.postgres",
    "shared",
    "ingestion",
]

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

CELERY_BROKER_URL = os.environ["CELERY_BROKER_URL"]
# The remote-control mailbox declares a transient non-exclusive queue, which RabbitMQ 4 refuses by
# default. Nothing here uses remote control, so turn it off rather than re-enabling a deprecated
# broker feature (gossip, which declares the same kind of queue, is disabled on the command line).
CELERY_WORKER_ENABLE_REMOTE_CONTROL = False

DOC_URLS_PATH = REPO_ROOT / "docs" / "doc_urls.json"

VOYAGE_API_KEY = os.environ["VOYAGE_API_KEY"]

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
