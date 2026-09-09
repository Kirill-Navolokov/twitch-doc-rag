import os

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
# The dev server only ever runs behind Docker Compose, where the host header is the service name.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.postgres",
    "shared",
    "retrieval",
]

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
