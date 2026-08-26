# src/messages/validator.py

import hmac
import hashlib
import os

from loguru import logger

from src.configs.settings import META_APP_SECRET


def verify_signature(payload: bytes, signature_header: str) -> bool:
    """Checks the X-Hub-Signature-256 header Meta sends on every webhook POST.

    If META_APP_SECRET isn't configured:
    - In explicit local/dev mode (`LOCAL_DEV=1`), the check is skipped with a warning.
    - Otherwise the request is rejected so webhooks aren't silently accepted.
    """
    if not META_APP_SECRET:
        if os.getenv("LOCAL_DEV", "").lower() in ("1", "true", "yes"):
            logger.warning(
                "META_APP_SECRET is not set — webhook signature verification bypassed (local dev mode)"
            )
            return True
        logger.error("META_APP_SECRET is not set — rejecting webhook for security")
        return False

    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(META_APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    received = signature_header.split("sha256=", 1)[1]
    return hmac.compare_digest(expected, received)