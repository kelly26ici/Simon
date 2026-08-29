"""Tests for memory schemas in src/tools/memory/schemas.py."""

from src.tools.memory.schemas import (
    SaveCustomerFactSchema,
    UpdateConversationSummarySchema,
    NotifyOwnerSchema,
    GetCustomerPreferencesSchema,
)


def test_save_customer_fact_schema_get_field_and_value():
    s = SaveCustomerFactSchema(phone_number="254700000000", field="budget_range", value="10M KES")
    f, v = s.get_field_and_value()
    assert f == "budget_range"
    assert v == "10M KES"


def test_save_customer_fact_schema_fallback_fact_key():
    s = SaveCustomerFactSchema(phone_number="254700000000", fact_key="location", fact_value="Westlands")
    f, v = s.get_field_and_value()
    assert f == "location"
    assert v == "Westlands"


def test_update_conversation_summary_schema():
    s = UpdateConversationSummarySchema(phone_number="254700000000", summary="Summary text")
    assert s.phone_number == "254700000000"
    assert s.summary == "Summary text"


def test_notify_owner_schema():
    s = NotifyOwnerSchema(phone_number="254700000000", message="Hot lead alert")
    assert s.message == "Hot lead alert"
