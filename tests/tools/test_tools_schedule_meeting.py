"""Tests for schedule viewing tools in src/tools/schedule_meeting.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.schedule_meeting import (
    schedule_property_viewing,
    get_my_scheduled_viewings,
    cancel_property_viewing,
    ScheduleViewingSchema,
    GetMyViewingsSchema,
    CancelViewingSchema,
)


@pytest.mark.asyncio
async def test_schedule_property_viewing_success():
    payload = ScheduleViewingSchema(
        customer_phone="254700000000",
        customer_name="John Doe",
        preferred_date_time="2026-09-01 14:00",
        property_id="prop_123",
    )
    fake_viewing = {
        "id": "view_abc123",
        "property_id": "prop_123",
        "customer_phone": "254700000000",
        "viewing_date": "2026-09-01 14:00",
        "status": "confirmed",
    }
    fake_property = {"title": "Karen Villa", "agent_id": "agent-1"}
    fake_agent = {
        "id": "agent-1",
        "first_name": "James",
        "last_name": "Maina",
        "phone": "0711223344",
        "email": "james@example.com",
        "agency_name": "Realtors Round Tables",
    }
    with patch("src.tools.schedule_meeting.db.create_scheduled_viewing", new=AsyncMock(return_value=fake_viewing)), \
         patch("src.tools.schedule_meeting.db.get_property_by_id", new=AsyncMock(return_value=fake_property)), \
         patch("src.tools.schedule_meeting.db.get_agent", new=AsyncMock(return_value=fake_agent)), \
         patch("src.tools.schedule_meeting.db.upsert_customer_profile", new=AsyncMock()):
        res = await schedule_property_viewing(payload)
        assert res["status"] == "confirmed"
        assert res["booking_id"] == "view_abc123"


@pytest.mark.asyncio
async def test_get_my_scheduled_viewings():
    payload = GetMyViewingsSchema(customer_phone="254700000000")
    fake_list = [{"id": "v1", "viewing_date": "2026-09-01"}]
    with patch("src.tools.schedule_meeting.db.get_customer_viewings", new=AsyncMock(return_value=fake_list)):
        res = await get_my_scheduled_viewings(payload)
        assert res["total"] == 1
        assert len(res["viewings"]) == 1


@pytest.mark.asyncio
async def test_cancel_property_viewing():
    payload = CancelViewingSchema(viewing_id="v1", customer_phone="254700000000")
    with patch("src.tools.schedule_meeting.db.cancel_scheduled_viewing", new=AsyncMock(return_value=True)):
        res = await cancel_property_viewing(payload)
        assert res["status"] == "success"
