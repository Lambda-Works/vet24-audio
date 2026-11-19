"""Environment-based configuration. Fails fast when a required variable is missing."""

import os
import sys


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"FATAL: required environment variable {name} is not set")
    return value


OPENAI_API_KEY = _required("OPENAI_API_KEY")
OPENAI_WEBHOOK_SECRET = _required("OPENAI_WEBHOOK_SECRET")
OPENAI_REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "").strip() or "gpt-realtime-2.1"
OPENAI_REALTIME_VOICE = os.environ.get("OPENAI_REALTIME_VOICE", "").strip() or "marin"
TRANSFER_TARGET_URI = (
    os.environ.get("TRANSFER_TARGET_URI", "").strip() or "sip:urgencias@sip-lab.lambdaworks.ar"
)
PORT = int(os.environ.get("PORT", "").strip() or "3001")
