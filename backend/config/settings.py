from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_repo_dotenv() -> None:
    """Pull KEY=VALUE from repo-root .env into os.environ (no override)."""
    env_path = BASE_DIR.parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_repo_dotenv()

SECRET_KEY = "django-insecure-shelfie-local-dev-only"

DEBUG = True

# Phones on the LAN need to reach this host; tighten later if we ever deploy.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "books",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Uploaded shelf photos and spine crops (local only).
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Local Expo (web / simulator / device). Native fetch does not use CORS;
# this is here so Expo web and browser checks also work.
CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# Local spine detection (Ultralytics YOLOv8n, COCO pretrained, CPU).
SPINE_DETECTION_MODEL = "yolov8n.pt"
SPINE_DETECTION_CONFIDENCE = 0.25
SPINE_DETECTION_TIMEOUT_S = 60
# Weights land here on first run (gitignored).
SPINE_DETECTION_WEIGHTS_DIR = BASE_DIR / "models"

# Hosted VLM — default OpenAI vision (fast). Cursor is automatic fallback.
# Set VLM_PROVIDER=cursor to force Cursor only.
VLM_PROVIDER = os.environ.get("VLM_PROVIDER", "openai").strip().lower()
if VLM_PROVIDER == "cursor":
    VLM_MODEL = os.environ.get("VLM_MODEL", "default")
    VLM_API_KEY_ENV = "CURSOR_API_KEY"
    VLM_TIMEOUT_S = int(os.environ.get("VLM_TIMEOUT_S", "180"))
else:
    VLM_PROVIDER = "openai"
    VLM_MODEL = os.environ.get("VLM_MODEL", "gpt-4o-mini")
    VLM_API_KEY_ENV = "OPENAI_API_KEY"
    VLM_TIMEOUT_S = int(os.environ.get("VLM_TIMEOUT_S", "45"))
# Cap VLM reads per uploaded photo.
VLM_MAX_SPINES_PER_PHOTO = int(os.environ.get("VLM_MAX_SPINES_PER_PHOTO", "8"))
# Cursor model used when OpenAI fails (or when VLM_PROVIDER=cursor).
VLM_CURSOR_MODEL = os.environ.get("VLM_CURSOR_MODEL", "default")
VLM_CURSOR_TIMEOUT_S = int(os.environ.get("VLM_CURSOR_TIMEOUT_S", "180"))

# Fuzzy catalog matching (see books/matching.py for the confidence formula).
MATCH_AUTO_ACCEPT_THRESHOLD = 0.88  # ≥ this → AUTO_ACCEPTED (unless ambiguous)
MATCH_REVIEW_FLOOR = 0.55  # ≥ floor → PENDING_REVIEW with a suggested match
MATCH_AMBIGUITY_GAP = 0.08  # top − runner-up ≤ gap → surface ambiguity

