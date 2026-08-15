"""
Central application configuration.

All environment-derived and tunable constants live here so they are not
scattered across the codebase. Values that are genuinely secret (DB creds,
JWT secret, AI key) are read from the environment and never hardcoded.
"""

import os


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
TURSO_DATABASE_URL = os.environ["TURSO_DATABASE_URL"]
TURSO_AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]

# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

# ---------------------------------------------------------------------------
# AI provider (optional)
# ---------------------------------------------------------------------------
AI_PROVIDER = os.environ.get("AI_PROVIDER")  # e.g. "anthropic", "gemini", None
AI_API_KEY = os.environ.get("AI_API_KEY")
AI_MODEL = os.environ.get("AI_MODEL")
# Secondary model tried if the primary model's request fails (e.g. free-tier
# quota exhausted). Only used by providers that support a fallback chain.
AI_MODEL_FALLBACK = os.environ.get("AI_MODEL_FALLBACK")
AI_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("AI_REQUEST_TIMEOUT_SECONDS", "8"))

# ---------------------------------------------------------------------------
# Email / OTP delivery (optional)
# ---------------------------------------------------------------------------
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER")  # e.g. "resend", None
EMAIL_API_KEY = os.environ.get("EMAIL_API_KEY")
EMAIL_FROM_ADDRESS = os.environ.get("EMAIL_FROM_ADDRESS", "no-reply@urbanpulse.local")

OTP_LENGTH = 6
OTP_EXPIRE_MINUTES = 10
OTP_MAX_ATTEMPTS = 5

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")
    if origin.strip()
]

# ---------------------------------------------------------------------------
# Spatial matching
# ---------------------------------------------------------------------------
SPATIAL_MATCH_RADIUS_METERS = float(os.environ.get("SPATIAL_MATCH_RADIUS_METERS", "15"))

# ---------------------------------------------------------------------------
# Status thresholds (hackathon defaults — tune freely)
# ---------------------------------------------------------------------------
STATUS_REPEATING_MIN_REPORTS = 2
STATUS_HIGH_CONFIDENCE_MIN_REPORTS = 3
STATUS_HIGH_CONFIDENCE_MIN_UNIQUE_DEVICES = 2
STATUS_CONFIRMED_MIN_REPORTS = 5
STATUS_CONFIRMED_MIN_UNIQUE_DEVICES = 2
STATUS_CONFIRMED_MIN_CONFIDENCE = 0.85
STATUS_HIGH_CONFIDENCE_MIN_CONFIDENCE = 0.65

# ---------------------------------------------------------------------------
# Confidence formula weights (see app/issues/confidence.py)
# ---------------------------------------------------------------------------
CONF_WEIGHT_PHONE = 0.35
CONF_WEIGHT_AI = 0.65

CONF_WEIGHT_EVENT_QUALITY = 0.45
CONF_WEIGHT_INDEPENDENCE = 0.30
CONF_WEIGHT_REPEAT = 0.15
CONF_WEIGHT_SPATIAL = 0.10

# Diminishing-returns curves: value at k reports/devices approaches 1.0
INDEPENDENCE_SATURATION_DEVICES = 5  # unique devices at which factor ~ saturates
REPEAT_SATURATION_REPORTS = 8        # report count at which factor ~ saturates

VISION_EVIDENCE_BOOST_MAX = 0.10  # max additive boost from vision evidence

ISSUE_ID_PREFIX = "UP-"
ISSUE_ID_PAD = 6