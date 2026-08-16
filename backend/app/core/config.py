import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# ---------------------------------------------------------------------------
# Required
# ---------------------------------------------------------------------------
TURSO_DATABASE_URL = os.environ["TURSO_DATABASE_URL"]
TURSO_AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

# ---------------------------------------------------------------------------
# Gemini (optional — app runs on fallback-only if unset)
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Fast + high free-tier quota. One model, no fallback-chain — chaining
# models on 429 just doubles the rate-limit hits.
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_TIMEOUT_SECONDS = 6
GEMINI_MAX_CONCURRENT_REQUESTS = 3

# ---------------------------------------------------------------------------
# Brevo (optional — OTP email is skipped, not broken, if unset)
# ---------------------------------------------------------------------------
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL")
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "Urban Pulse")

OTP_LENGTH = 6
OTP_EXPIRE_MINUTES = 10
OTP_MAX_ATTEMPTS = 5

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOW_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()
]

# ---------------------------------------------------------------------------
# Spatial matching
# ---------------------------------------------------------------------------
SPATIAL_MATCH_RADIUS_METERS = 15

# ---------------------------------------------------------------------------
# Local pre-filter — decides whether an event is worth a Gemini call at all
# ---------------------------------------------------------------------------
PREFILTER_MIN_ACCEL_PEAK = 1.2
PREFILTER_MIN_GYRO_PEAK = 0.6
PREFILTER_MIN_PHONE_CONFIDENCE = 0.55

# ---------------------------------------------------------------------------
# Status thresholds
# ---------------------------------------------------------------------------
STATUS_REPEATING_MIN_REPORTS = 2
STATUS_HIGH_CONFIDENCE_MIN_REPORTS = 3
STATUS_HIGH_CONFIDENCE_MIN_UNIQUE_DEVICES = 2
STATUS_HIGH_CONFIDENCE_MIN_CONFIDENCE = 0.60
STATUS_CONFIRMED_MIN_REPORTS = 5
STATUS_CONFIRMED_MIN_UNIQUE_DEVICES = 2
STATUS_CONFIRMED_MIN_CONFIDENCE = 0.82

# ---------------------------------------------------------------------------
# Confidence formula weights (app/issues/confidence.py)
# ---------------------------------------------------------------------------
CONF_WEIGHT_PHONE = 0.35
CONF_WEIGHT_AI = 0.65

# event_quality carries most of the weight since a single strong report
# should already be detectable — independence/repeat push it higher with
# more evidence, they shouldn't be required to clear the detection bar.
CONF_WEIGHT_EVENT_QUALITY = 0.62
CONF_WEIGHT_INDEPENDENCE = 0.12
CONF_WEIGHT_REPEAT = 0.10
CONF_WEIGHT_SPATIAL = 0.16

INDEPENDENCE_SATURATION_DEVICES = 5
REPEAT_SATURATION_REPORTS = 8

VISION_EVIDENCE_BOOST_MAX = 0.10

ISSUE_ID_PREFIX = "UP-"
ISSUE_ID_PAD = 6
