from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class ScheduleMeetingSchema(BaseModel):
    """Input for the schedule_meeting tool."""

    title: str = Field(..., description="Meeting title or subject")
    attendees: list[str] = Field(..., description="List of attendee phone numbers or emails")
    date_time: str = Field(..., description="ISO 8601 datetime string for the meeting")
    duration_minutes: int = Field(default=30, ge=15, le=180, description="Meeting duration in minutes")
    description: Optional[str] = Field(default=None, description="Optional meeting description or agenda")