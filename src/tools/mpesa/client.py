"""
Internal Daraja client. Not exposed to the agent - tools.py wraps this
with the pydantic schemas and is what the agent actually calls.
"""

from __future__ import annotations

import base64
import time
from datetime import datetime
from typing import Any, Dict, Literal, Optional
from zoneinfo import ZoneInfo

from loguru import logger
from httpx import TransportError, TimeoutException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.clients.httpx_client import httpx
from src.configs.settings import (
    CONSUMER_KEY,
    CONSUMER_SECRET,
    MPESA_BASE_URL,
    PASSKEY,
    CALLBACK_URL,
    SHORTCODE,
    RENDER_BASE_URL,
    MPESA_WEBHOOK_SECRET,
)
from src.tools.mpesa.schemas import C2BRegisterSchema

# Daraja wants the STK timestamp/password in East Africa Time. If the
# server's system tz isn't set to this (Render defaults to UTC), the old
# datetime.now() call would silently produce a wrong password hash and
# Safaricom would reject every request with a generic auth error.
NAIROBI_TZ = ZoneInfo("Africa/Nairobi")

# Only retry genuine transient failures. Retrying on rejections (bad auth,
# malformed payload, Daraja-side validation errors) wastes calls.
TRANSIENT_ERRORS = (TransportError, TimeoutException)

# For the STK push specifically I don't retry on TimeoutException - a
# timeout can mean Safaricom already received the request and is just
# slow to answer, and retrying would risk firing a second prompt to the
# customer's phone for a push that already went through. TransportError
# (the request never even reached Safaricom) is safe to retry.
STK_PUSH_RETRYABLE = (TransportError,)


class MpesaAgentClient:
    def __init__(self):
        self.base_url = MPESA_BASE_URL
        self.consumer_key = CONSUMER_KEY
        self.consumer_secret = CONSUMER_SECRET
        self.shortcode = SHORTCODE
        self.passkey = PASSKEY
        self.callback_url = CALLBACK_URL
        self.client = httpx

        # Daraja tokens are valid ~1hr - caching this saves an extra HTTP
        # round trip on every single tool call instead of just the first.
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _timestamp(self) -> str:
        return datetime.now(NAIROBI_TZ).strftime("%Y%m%d%H%M%S")

    def _password(self, timestamp: str) -> str:
        return base64.b64encode(f"{self.shortcode}{self.passkey}{timestamp}".encode()).decode()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
    )
    async def _fetch_access_token(self) -> Dict[str, Any]:
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        encoded_credentials = base64.b64encode(f"{self.consumer_key}:{self.consumer_secret}".encode()).decode()
        headers = {"Authorization": f"Basic {encoded_credentials}"}

        response = await self.client.get(url=url, headers=headers)
        response.raise_for_status()
        return response.json()

    async def generate_access_token(self) -> str:
        # 30s buffer so I never hand out a token that expires mid-request
        if self._cached_token and time.monotonic() < self._token_expires_at - 30:
            return self._cached_token

        body = await self._fetch_access_token()
        access_token = body.get("access_token")
        if not access_token:
            raise ValueError(f"Missing access_token in response: {body}")

        expires_in = int(body.get("expires_in", 3599))
        self._cached_token = access_token
        self._token_expires_at = time.monotonic() + expires_in
        return access_token

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
    )
    async def register_c2b_urls(self, response_type: Literal["Cancelled", "Completed"] = "Completed") -> Dict[str, Any]:
        token = await self.generate_access_token()
        url = f"{self.base_url}/mpesa/c2b/v1/registerurl"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = C2BRegisterSchema(
            ResponseType=response_type,
            ConfirmationURL=f"{RENDER_BASE_URL}/mpesa/c2b/confirmation/{MPESA_WEBHOOK_SECRET}",
            ValidationURL=f"{RENDER_BASE_URL}/mpesa/c2b/validation/{MPESA_WEBHOOK_SECRET}",
        ).model_dump()

        response = await self.client.post(url=url, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        logger.info("C2B registration response: {}", body)
        return body

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(STK_PUSH_RETRYABLE),
    )
    async def stk_push(self, payload) -> Dict[str, Any]:
        token = await self.generate_access_token()
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"

        timestamp = self._timestamp()
        password = self._password(timestamp)

        body_payload = payload.model_dump()
        body_payload.update(
            {
                "BusinessShortCode": self.shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "PartyB": self.shortcode,
                "PhoneNumber": payload.PartyA,
                "CallBackURL": self.callback_url,
            }
        )

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        response = await self.client.post(url=url, headers=headers, json=body_payload)
        response.raise_for_status()
        body = response.json()

        if body.get("ResponseCode") != "0":
            raise ValueError(f"M-Pesa API rejected STK push: {body}")

        return body

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=6),
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
    )
    async def query_stk_status(self, checkout_request_id: str) -> Dict[str, Any]:
        token = await self.generate_access_token()
        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"

        timestamp = self._timestamp()
        password = self._password(timestamp)

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        response = await self.client.post(url=url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


mpesa_client = MpesaAgentClient()