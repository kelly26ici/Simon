"""Tests for parse_incoming() in src/messages/parser.py."""

import pytest
from src.messages.parser import parse_incoming, IncomingMessage


SAMPLE_PAYLOAD = {
    "entry": [{
        "changes": [{
            "value": {
                "metadata": {"phone_number_id": "12345"},
                "messages": [{
                    "from": "254700000000",
                    "type": "text",
                    "id": "msg-abc-123",
                    "text": {"body": "Hello"}
                }]
            }
        }]
    }]
}


def test_parse_incoming_returns_incoming_message():
    result = parse_incoming(SAMPLE_PAYLOAD)
    assert isinstance(result, IncomingMessage)


def test_parse_incoming_extracts_sender():
    result = parse_incoming(SAMPLE_PAYLOAD)
    assert result.sender == "254700000000"


def test_parse_incoming_extracts_msg_type():
    result = parse_incoming(SAMPLE_PAYLOAD)
    assert result.msg_type == "text"


def test_parse_incoming_extracts_phone_number_id():
    result = parse_incoming(SAMPLE_PAYLOAD)
    assert result.phone_number_id == "12345"


def test_parse_incoming_returns_none_for_status_update():
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{"id": "some-status"}]
                }
            }]
        }]
    }
    result = parse_incoming(payload)
    assert result is None


def test_parse_incoming_returns_none_for_empty_messages():
    payload = {
        "entry": [{
            "changes": [{
                "value": {"messages": []}
            }]
        }]
    }
    assert parse_incoming(payload) is None


def test_parse_incoming_returns_none_for_missing_entry():
    assert parse_incoming({}) is None


def test_parse_incoming_returns_none_for_malformed():
    assert parse_incoming({"entry": []}) is None
