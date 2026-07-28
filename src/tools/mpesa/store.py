"""
Maps CheckoutRequestID -> transaction state, so the async callback from
Daraja can be matched back to the right conversation.

This is an in-memory placeholder. Swap the guts for my existing Upstash
Redis client (same one backing the rolling conversation buffer) so state
survives restarts and works across more than one Render worker - right
now a redeploy or a second worker process just loses every pending
transaction.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


from src.core.redis import RedisStore

transaction_store = RedisStore(prefix="mpesa_tx")