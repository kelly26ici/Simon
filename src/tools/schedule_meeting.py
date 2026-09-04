"""
Real Estate Property Viewing and Meeting Scheduling Tools.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from loguru import logger

from src.tools.registry import registry
from src.services.db import db

DEFAULT_AGENT_NAME = "Simon | Realtors Round Tables"
DEFAULT_AGENT_PHONE = "0701454854"


def _agent_display_name(agent: Optional[Dict[str, Any]]) -> str:
	"""Human-readable agent name from a normalized agent row (or empty string)."""
	if not agent:
		return ""
	return " ".join(p for p in [agent.get("first_name"), agent.get("last_name")] if p)


def _wa_link(phone: str) -> str:
	"""Build a clickable WhatsApp link from a phone number string."""
	if not phone:
		return f"https://wa.me/254701454854"
	digits = "".join(ch for ch in phone if ch.isdigit())
	if digits.startswith("254") and len(digits) == 12:
		pass
	elif digits.startswith("0") and len(digits) == 10:
		digits = "254" + digits[1:]
	elif len(digits) == 9 and digits.startswith("7"):
		digits = "254" + digits
	return f"https://wa.me/{digits}"


class ScheduleViewingSchema(BaseModel):
    """Input for schedule_property_viewing tool."""

    property_id: Optional[str] = Field(
        default=None,
        description="The UUID of the property to view. If unknown, leave empty and specify in notes.",
    )
    customer_phone: str = Field(
        ...,
        description="Customer WhatsApp number or phone number (e.g. '254706716616')",
    )
    customer_name: Optional[str] = Field(
        default=None,
        description="Customer's preferred name",
    )
    preferred_date_time: str = Field(
        ...,
        description="Preferred date and time for the viewing (e.g. '2026-08-22 14:00' or ISO 8601 format)",
    )
    duration_minutes: int = Field(
        default=30,
        ge=15,
        le=180,
        description="Estimated viewing duration in minutes (default 30)",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Any specific requirements (e.g. 'Customer interested in floor 5', 'Needs physical viewing')",
    )


class GetMyViewingsSchema(BaseModel):
    """Input for get_my_scheduled_viewings tool."""

    customer_phone: str = Field(
        ...,
        description="The customer's phone number / WhatsApp ID",
    )


class CancelViewingSchema(BaseModel):
    """Input for cancel_property_viewing tool."""

    viewing_id: str = Field(..., description="The viewing ID to cancel")
    customer_phone: str = Field(..., description="The customer's phone number")


@registry.register("schedule_property_viewing", ScheduleViewingSchema)
async def schedule_property_viewing(payload: ScheduleViewingSchema) -> Dict[str, Any]:
    """
    Schedule a physical or virtual property viewing / site visit appointment.

    Use this tool when:
    - A customer wants to visit, tour, or inspect a property.
    - A customer asks: "Can I see this apartment on Saturday?", "Book a viewing for tomorrow 2 PM".

    This records the appointment in the database and returns a confirmed booking
    summary including assigned agent details and meeting location.
    """
    logger.info(
        "Scheduling viewing for phone {} on property {}",
        payload.customer_phone,
        payload.property_id,
    )

    prop = None
    if payload.property_id:
        prop = await db.get_property_by_id(payload.property_id)

    # Save to database
    viewing = await db.create_scheduled_viewing(
        property_id=payload.property_id,
        customer_phone=payload.customer_phone,
        customer_name=payload.customer_name,
        viewing_date=payload.preferred_date_time,
        duration_minutes=payload.duration_minutes,
        notes=payload.notes,
    )

    # Update customer profile with preferred name if supplied
    if payload.customer_name:
        await db.upsert_customer_profile(
            payload.customer_phone,
            {"preferred_name": payload.customer_name},
        )

    if prop:
        agent = None
        if prop.get("agent_id"):
            agent = await db.get_agent(prop["agent_id"]) or None
        name = _agent_display_name(agent) or DEFAULT_AGENT_NAME
        phone = (agent or {}).get("phone") or DEFAULT_AGENT_PHONE
        prop_title = prop.get("title", "Selected Property")
        location = prop.get("location", "Nairobi")
    else:
        name = DEFAULT_AGENT_NAME
        phone = DEFAULT_AGENT_PHONE
        prop_title = "Real Estate Consultation"
        location = "Nairobi"

    booking_id = viewing.get("id")
    logger.success(
        "Viewing successfully scheduled | booking_id={} customer={} property={}",
        booking_id,
        payload.customer_phone,
        payload.property_id,
    )

    return {
        "status": "confirmed",
        "booking_id": booking_id,
        "property_title": prop_title,
        "location": location,
        "viewing_time": payload.preferred_date_time,
        "duration_minutes": payload.duration_minutes,
        "customer_phone": payload.customer_phone,
        "customer_name": payload.customer_name,
        "assigned_agent": {
            "name": name,
            "phone": phone,
            "whatsapp_link": _wa_link(phone),
        },
        "customer_service": {
            "name": "Simon",
            "phone": "0701454854",
            "whatsapp_link": "https://wa.me/254701454854",
            "website": "https://realtorsroundtables.co.ke",
        },
        "instructions": "Please arrive 10 minutes early. Our agent will meet you at the property entrance. For questions or adjustments, reach Simon on 0701454854.",
    }


@registry.register("get_my_scheduled_viewings", GetMyViewingsSchema)
async def get_my_scheduled_viewings(payload: GetMyViewingsSchema) -> Dict[str, Any]:
    """Retrieve all upcoming and past scheduled property viewings for a customer."""
    viewings = await db.get_customer_viewings(payload.customer_phone)
    logger.success("Retrieved {} scheduled viewing(s) for customer {}", len(viewings), payload.customer_phone)
    return {
        "total": len(viewings),
        "customer_phone": payload.customer_phone,
        "viewings": viewings,
    }


@registry.register("cancel_property_viewing", CancelViewingSchema)
async def cancel_property_viewing(payload: CancelViewingSchema) -> Dict[str, Any]:
    """Cancel a scheduled viewing appointment."""
    success = await db.cancel_scheduled_viewing(payload.viewing_id, payload.customer_phone)
    if success:
        logger.success("Viewing {} successfully cancelled for customer {}", payload.viewing_id, payload.customer_phone)
        return {"status": "success", "message": "Viewing has been cancelled."}
    logger.warning("Failed to cancel viewing {}: not found or phone mismatch", payload.viewing_id)
    return {"status": "error", "message": "Could not cancel viewing. Please check the viewing ID."}