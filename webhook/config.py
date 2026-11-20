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

# Turn detection (end-of-turn latency). server_vad: respond after
# OPENAI_VAD_SILENCE_MS of silence (API default 500). semantic_vad: model-based,
# OPENAI_VAD_EAGERNESS low|medium|high|auto (high = max 2 s wait).
OPENAI_VAD_TYPE = os.environ.get("OPENAI_VAD_TYPE", "").strip() or "server_vad"
OPENAI_VAD_SILENCE_MS = int(os.environ.get("OPENAI_VAD_SILENCE_MS", "").strip() or "300")
OPENAI_VAD_THRESHOLD = float(os.environ.get("OPENAI_VAD_THRESHOLD", "").strip() or "0.5")
OPENAI_VAD_PREFIX_MS = int(os.environ.get("OPENAI_VAD_PREFIX_MS", "").strip() or "300")
OPENAI_VAD_EAGERNESS = os.environ.get("OPENAI_VAD_EAGERNESS", "").strip() or "high"
if OPENAI_VAD_TYPE not in ("server_vad", "semantic_vad"):
    sys.exit(f"FATAL: OPENAI_VAD_TYPE must be server_vad or semantic_vad (got {OPENAI_VAD_TYPE!r})")


def turn_detection() -> dict:
    """audio.input.turn_detection for the accept body."""
    if OPENAI_VAD_TYPE == "semantic_vad":
        return {"type": "semantic_vad", "eagerness": OPENAI_VAD_EAGERNESS}
    return {
        "type": "server_vad",
        "threshold": OPENAI_VAD_THRESHOLD,
        "prefix_padding_ms": OPENAI_VAD_PREFIX_MS,
        "silence_duration_ms": OPENAI_VAD_SILENCE_MS,
    }


PORT = int(os.environ.get("PORT", "").strip() or "3001")
