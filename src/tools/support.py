"""
Customer Support & Agent Escalation Tools for Realtors Round Tables.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from loguru import logger

from src.tools.registry import registry
from src.services.db import db


def _format_wa_link(phone: str, message: Optional[str] = None) -> str:
    """Sanitizes phone number into international format for WhatsApp wa.me link."""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif digits.startswith("7") and len(digits) == 9:
        digits = "254" + digits
    elif not digits.startswith("254") and len(digits) == 9:
        digits = "254" + digits

    base_link = f"https://wa.me/{digits}"
    if message:
        import urllib.parse
        encoded_msg = urllib.parse.quote(message)
        return f"{base_link}?text={encoded_msg}"
    return base_link


class ContactSupportSchema(BaseModel):
    """Input for get_support_contact tool."""

    property_id: Optional[str] = Field(
        default=None,
        description="Optional property UUID if the customer is inquiring about a specific listing.",
    )
    inquiry_topic: Optional[str] = Field(
        default=None,
        description="Brief description of the customer's question or reason for connecting (e.g. 'schedule visit', 'talk to human agent', 'pricing question').",
    )


@registry.register("get_support_contact", ContactSupportSchema)
async def get_support_contact(payload: ContactSupportSchema) -> Dict[str, Any]:
    """
    Get official contact details to speak directly with the Customer Service Executive
    or a dedicated listing agent.

    Use this tool when:
    - A customer wants to speak with a human agent or executive.
    - A customer asks: "Can I talk to someone?", "Give me a phone number", "Who can I call?",
      "Can I speak with an agent directly?", "Customer care contact".
    - A customer needs human assistance, custom requirements, or has complex questions.

    Returns:
    - Customer Service Executive details (Simon, phone: 0701454854, clickable WhatsApp link, call link)
    - Company website (https://realtorsroundtables.co.ke)
    - Specific listing agent details (if property_id was provided)
    - Formatted clickable response summary for WhatsApp
    """
    exec_phone_display = "0701454854"
    exec_phone_intl = "+254 701 454 854"
    exec_whatsapp_link = _format_wa_link(exec_phone_display, "Hello Simon, I'd like to inquire about properties at Realtors Round Tables.")
    website_url = "https://realtorsroundtables.co.ke"

    response: Dict[str, Any] = {
        "status": "success",
        "company": "Realtors Round Tables",
        "website": website_url,
        "customer_service_executive": {
            "name": "Simon",
            "role": "Customer Service Executive",
            "phone": exec_phone_display,
            "international_phone": exec_phone_intl,
            "whatsapp_link": exec_whatsapp_link,
            "tel_link": "tel:+254701454854",
        },
    }

    # If asking about a specific property, fetch the assigned agent
    if payload.property_id:
        try:
            prop = await db.get_property_by_id(payload.property_id)
            if prop:
                agent_name = prop.get("agent_name") or "Realtors Round Tables Listing Agent"
                agent_phone = prop.get("agent_phone") or exec_phone_display
                agent_email = prop.get("agent_email")
                agent_wa = _format_wa_link(
                    agent_phone,
                    f"Hello {agent_name}, I am inquiring about '{prop.get('title', 'the property')}'.",
                )
                response["listing_agent"] = {
                    "property_title": prop.get("title"),
                    "agent_name": agent_name,
                    "agent_phone": agent_phone,
                    "agent_email": agent_email,
                    "whatsapp_link": agent_wa,
                }
        except Exception as exc:
            logger.warning("Could not fetch property details for support contact: {}", exc)

    logger.info("Provided support and agent contact info | property_id={} topic={}", payload.property_id, payload.inquiry_topic)
    return response
