"""国税と地方消費税の中間納付を別々に精算する。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shinkoku.models import ConsumptionTaxInput, PurchaseDetail
from shinkoku.tools.tax_calc import calc_consumption_tax
from shinkoku.tools.tax_eligibility import check_invoice_special_eligibility
from tests.helpers.tax_eligibility import verified_invoice_facts


@pytest.mark.parametrize(
    "national_paid,local_paid,national_due,local_due,total_due,local_refund",
    [
        (10_000, 2_000, 13_400, 4_600, 18_000, 0),
        (15_000, 10_000, 8_400, -3_400, 5_000, 3_400),
        (50_000, 15_000, -26_600, -8_400, -35_000, 8_400),
        (23_400, 6_600, 0, 0, 0, 0),
        (0, 10_000, 23_400, -3_400, 20_000, 3_400),
    ],
)
def test_special_30_interim_payment_and_refund(
    national_paid: int,
    local_paid: int,
    national_due: int,
    local_due: int,
    total_due: int,
    local_refund: int,
) -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2027,
            method="special_30pct",
            calculation_mode="filing",
            invoice_special_eligibility=verified_invoice_facts(),
            taxable_sales_10=1_100_000,
            interim_payment=national_paid,
            local_interim_payment=local_paid,
        )
    )
    assert result.net_tax == 23_400
    assert result.local_tax_due == 6_600  # 既存フィールドは中間納付前の年税額
    assert result.tax_due == national_due
    assert result.local_tax_due_after_interim_payment == local_due
    assert result.local_interim_refund == local_refund
    assert result.total_due == total_due


def test_annual_purchase_refund_and_interim_refund_are_separate() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            calculation_mode="filing",
            purchase_details=[
                PurchaseDetail(
                    tax_recognition_date="2026-01-10",
                    amount_inclusive=1_100_000,
                    tax_rate="standard_10",
                    credit_category="qualified_invoice",
                )
            ],
            interim_payment=10_000,
            local_interim_payment=3_000,
        )
    )
    assert result.refund_shortfall == 78_000
    assert result.tax_due == -10_000
    assert result.local_tax_due == -22_000
    assert result.local_tax_due_after_interim_payment == -25_000
    assert result.local_interim_refund == 3_000
    assert result.total_due == -113_000


def test_missing_local_payment_remains_visible_in_legacy_estimate() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="special_20pct",
            taxable_sales_10=1_100_000,
            interim_payment=10_000,
        )
    )
    assert result.total_due == 10_000
    assert any("地方消費税の中間納付額が未確認" in warning for warning in result.warnings)


def test_filing_requires_explicit_local_payment_when_national_payment_exists() -> None:
    data = ConsumptionTaxInput(
        fiscal_year=2027,
        method="special_30pct",
        calculation_mode="filing",
        invoice_special_eligibility=verified_invoice_facts(),
        interim_payment=10_000,
    )
    with pytest.raises(ValueError, match="地方消費税の中間納付額を明示"):
        calc_consumption_tax(data)
    data.local_interim_payment = 0
    assert calc_consumption_tax(data).total_due == -10_000


@pytest.mark.parametrize("field", ["interim_payment", "local_interim_payment"])
def test_negative_interim_payments_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        ConsumptionTaxInput(fiscal_year=2027, method="special_30pct", **{field: -1})


@pytest.mark.parametrize(
    "year,method", [(2026, "special_20pct"), (2027, "special_30pct"), (2028, "special_30pct")]
)
@pytest.mark.parametrize(
    "registration_day,status", [(9, "eligible"), (10, "eligible"), (11, "ineligible")]
)
def test_inheritance_exception_is_shared_by_two_and_three_percent_schemes(
    year: int,
    method: str,
    registration_day: int,
    status: str,
) -> None:
    facts = verified_invoice_facts(
        inheritance_taxation_applies=True,
        inheritance_date=f"{year}-06-10",
        invoice_registration_date=f"{year}-06-{registration_day:02d}",
    )
    result = check_invoice_special_eligibility(year, method, facts)
    assert result.status == status
    if status == "eligible":
        tax = calc_consumption_tax(
            ConsumptionTaxInput(
                fiscal_year=year,
                method=method,
                calculation_mode="filing",
                invoice_special_eligibility=facts,
                taxable_sales_10=1_100_000,
                interim_payment=5_000,
                local_interim_payment=1_000,
            )
        )
        assert tax.total_due == (14_000 if method == "special_20pct" else 24_000)
