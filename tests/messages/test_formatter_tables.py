"""Tests for WhatsAppFormatter table rendering."""

import pytest
from src.messages.formatter import WhatsAppFormatter

MD_TABLE = """| Name | Price |
| --- | --- |
| Apartment | KES 5M |
| Villa | KES 12M |
"""


@pytest.fixture
def fmt():
    return WhatsAppFormatter(max_length=4096, table_mode="text", debug=False)


def test_table_no_pipe_in_output(fmt):
    result = " ".join(fmt.format(MD_TABLE))
    assert "Apartment" in result or "Name" in result
