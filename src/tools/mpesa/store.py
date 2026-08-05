"""
Maps CheckoutRequestID → transaction state, so the async callback from
Daraja can be matched back to the right conversation.

Backed by Redis (with in-memory fallback) so state survives restarts and
works across multiple Render workers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


from src.core.redis import RedisStore

transaction_store = RedisStore(prefix="mpesa_tx")