# src/messages/validator.py

import hmac
import hashlib

from src.configs.settings import META_APP_SECRET


def verify_signature(payload: bytes, signature_header: str) -> bool:
    """Checks the X-Hub-Signature-256 header Meta sends on every webhook POST.

    If META_APP_SECRET isn't configured (e.g. local/dev testing), the check
    is skipped and this returns True — same behaviour as the original code.
    """
    if not META_APP_SECRET:
        return True

    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(META_APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    received = signature_header.split("sha256=", 1)[1]
    return hmac.compare_digest(expected, received)