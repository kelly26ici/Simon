"""
Real Estate Financial & Mortgage Calculation Tools.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from loguru import logger

from src.tools.registry import registry


class MortgageCalculatorSchema(BaseModel):
    """Input for calculate_mortgage tool."""

    property_price: float = Field(
        ...,
        gt=0,
        description="The total property purchase price in KES (e.g. 18500000 for 18.5M KES)",
    )
    down_payment_percentage: float = Field(
        default=20.0,
        ge=5.0,
        le=90.0,
        description="Down payment percentage (typical: 10% to 20%)",
    )
    interest_rate_annual: float = Field(
        default=13.5,
        ge=1.0,
        le=30.0,
        description="Annual interest rate percentage (typical Kenyan commercial bank rate: 12% - 15%)",
    )
    loan_term_years: int = Field(
        default=20,
        ge=1,
        le=30,
        description="Loan repayment period in years (typical: 15 to 25 years)",
    )


@registry.register("calculate_mortgage", MortgageCalculatorSchema)
async def calculate_mortgage(payload: MortgageCalculatorSchema) -> Dict[str, Any]:
    """
    Calculate estimated mortgage repayments, required down payment, statutory acquisition
    costs, and minimum monthly income criteria for buying real estate in Kenya.

    Use this tool ONLY when:
    - The customer explicitly asks for a mortgage breakdown, loan repayment calculation,
      or specific financing estimate (e.g. "What are the monthly loan repayments?", "Calculate mortgage with 10% down").
    - Do NOT call this tool proactively or offer unsolicited mortgage advice during casual property discovery.

    Returns:
    - Monthly mortgage payment (KES)
    - Total down payment amount (KES)
    - Total loan principal (KES)
    - Total interest paid over loan life (KES)
    - Estimated Kenyan statutory acquisition costs (4% Stamp Duty, ~1.5% Legal fees, ~0.25% Valuation)
    - Recommended minimum monthly household income
    """
    price = payload.property_price
    down_pct = payload.down_payment_percentage / 100.0
    down_payment = round(price * down_pct, 2)
    principal = price - down_payment

    monthly_rate = (payload.interest_rate_annual / 100.0) / 12.0
    num_months = payload.loan_term_years * 12

    if monthly_rate > 0:
        monthly_payment = principal * (
            monthly_rate * (1 + monthly_rate) ** num_months
        ) / ((1 + monthly_rate) ** num_months - 1)
    else:
        monthly_payment = principal / num_months

    monthly_payment = round(monthly_payment, 2)
    total_repayment = round(monthly_payment * num_months, 2)
    total_interest = round(total_repayment - principal, 2)

    # Kenyan statutory transaction costs
    stamp_duty = round(price * 0.04, 2)  # 4% in municipalities/Nairobi
    legal_fees = round(price * 0.015, 2)  # approx 1.5%
    valuation_fee = round(price * 0.0025, 2)  # approx 0.25%
    total_closing_costs = round(stamp_duty + legal_fees + valuation_fee, 2)

    # Banks generally require monthly installment ≤ 33% of gross monthly income
    min_recommended_income = round(monthly_payment / 0.33, 2)

    logger.success(
        "Mortgage calculated successfully | price=KES {:,.2f} monthly=KES {:,.2f} deposit=KES {:,.2f}",
        price,
        monthly_payment,
        down_payment,
    )

    return {
        "currency": "KES",
        "property_price": price,
        "down_payment": {
            "percentage": payload.down_payment_percentage,
            "amount": down_payment,
        },
        "loan_details": {
            "principal_loan_amount": principal,
            "interest_rate_annual": payload.interest_rate_annual,
            "term_years": payload.loan_term_years,
            "term_months": num_months,
            "estimated_monthly_payment": monthly_payment,
            "total_interest": total_interest,
            "total_repayment": total_repayment,
        },
        "repayment_summary": (
            f"{payload.loan_term_years} years at {payload.interest_rate_annual}% p.a.: "
            f"KES {monthly_payment:,.2f} per month (Total repayment: KES {total_repayment:,.2f})"
        ),
        "estimated_acquisition_costs": {
            "stamp_duty_4pct": stamp_duty,
            "legal_fees_approx": legal_fees,
            "valuation_fee_approx": valuation_fee,
            "total_estimated_closing_costs": total_closing_costs,
            "total_upfront_cash_needed": round(down_payment + total_closing_costs, 2),
        },
        "affordability": {
            "recommended_min_gross_monthly_income": min_recommended_income,
            "guideline": "Banks typically require monthly mortgage installments to not exceed 33% of gross monthly income.",
        },
    }
