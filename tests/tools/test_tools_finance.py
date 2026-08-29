"""Tests for calculate_mortgage tool in src/tools/finance.py."""

import pytest
from src.tools.finance import calculate_mortgage, MortgageCalculatorSchema


@pytest.mark.asyncio
async def test_calculate_mortgage_standard():
    payload = MortgageCalculatorSchema(
        property_price=10_000_000,
        down_payment_percentage=20.0,
        interest_rate_annual=13.5,
        loan_term_years=20,
    )
    result = await calculate_mortgage(payload)
    assert result["down_payment"]["amount"] == 2_000_000
    assert result["loan_details"]["principal_loan_amount"] == 8_000_000
    assert result["loan_details"]["estimated_monthly_payment"] > 0
    assert "estimated_acquisition_costs" in result
    assert result["estimated_acquisition_costs"]["stamp_duty_4pct"] == 400_000
