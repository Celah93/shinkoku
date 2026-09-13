"""3割特例の計算・年分・保存。既存方式を2027年へ一緒に開放しない。"""

from __future__ import annotations

from pathlib import Path

import pytest

from shinkoku.models import ConsumptionTaxInput, FiscalYearTaxProfileUpdate
from shinkoku.tools.ledger import (
    ledger_get_fiscal_year_tax_profile,
    ledger_init,
    ledger_update_fiscal_year_tax_profile,
)
from shinkoku.tools.tax_calc import calc_consumption_tax
from tests.helpers.tax_eligibility import verified_invoice_facts


@pytest.mark.parametrize("year", [2027, 2028])
@pytest.mark.parametrize(
    "sales_10,sales_8,national,purchase_credit,net,local,total",
    [
        (1_100_000, 0, 78_000, 54_600, 23_400, 6_600, 30_000),
        (0, 1_080_000, 62_400, 43_680, 18_700, 5_200, 23_900),
        (1_100_000, 1_080_000, 140_400, 98_280, 42_100, 11_800, 53_900),
        (0, 0, 0, 0, 0, 0, 0),
    ],
)
def test_special_30_national_and_local_rounding(
    year: int,
    sales_10: int,
    sales_8: int,
    national: int,
    purchase_credit: int,
    net: int,
    local: int,
    total: int,
) -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=year,
            method="special_30pct",
            calculation_mode="filing",
            invoice_special_eligibility=verified_invoice_facts(),
            taxable_sales_10=sales_10,
            taxable_sales_8=sales_8,
        )
    )
    assert result.national_tax_on_sales == national
    assert result.tax_on_purchases == purchase_credit
    assert result.net_tax == net
    assert result.local_tax_due == local
    assert result.total_due == total
    assert result.eligibility_checks[0].status == "eligible"


@pytest.mark.parametrize("year", [2025, 2026, 2029, 2030])
def test_special_30_rejects_other_years(year: int) -> None:
    with pytest.raises(ValueError, match=f"fiscal_year={year} は未対応"):
        calc_consumption_tax(ConsumptionTaxInput(fiscal_year=year, method="special_30pct"))


@pytest.mark.parametrize("method", ["standard", "simplified", "special_20pct"])
def test_other_methods_are_not_opened_for_2027(method: str) -> None:
    with pytest.raises(ValueError, match="fiscal_year=2027 は未対応"):
        calc_consumption_tax(
            ConsumptionTaxInput(
                fiscal_year=2027,
                method=method,
                simplified_business_type=5 if method == "simplified" else None,
            )
        )


def test_special_30_unverified_estimate_is_not_filing() -> None:
    params = ConsumptionTaxInput(fiscal_year=2027, method="special_30pct", taxable_sales_10=1100000)
    result = calc_consumption_tax(params)
    assert result.calculation_mode == "estimate"
    assert result.eligibility_checks[0].status == "indeterminate"
    params.calculation_mode = "filing"
    with pytest.raises(ValueError, match="TAX_ELIGIBILITY_UNCONFIRMED"):
        calc_consumption_tax(params)


def test_special_30_does_not_ignore_unhandled_local_interim_payments() -> None:
    with pytest.raises(ValueError, match="中間納付"):
        calc_consumption_tax(
            ConsumptionTaxInput(
                fiscal_year=2027,
                method="special_30pct",
                interim_payment=10000,
                calculation_mode="filing",
                invoice_special_eligibility=verified_invoice_facts(),
            )
        )


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"base_period_taxable_sales": 10_000_001}, "INELIGIBLE"),
        ({"domestic_individual": False}, "UNSUPPORTED"),
        ({"shortened_tax_period": True}, "INELIGIBLE"),
        ({"inheritance_taxation_applies": True}, "UNSUPPORTED"),
    ],
)
def test_special_30_filing_does_not_bypass_exclusions(changes: dict, code: str) -> None:
    with pytest.raises(ValueError, match=f"TAX_ELIGIBILITY_{code}"):
        calc_consumption_tax(
            ConsumptionTaxInput(
                fiscal_year=2027,
                method="special_30pct",
                calculation_mode="filing",
                invoice_special_eligibility=verified_invoice_facts(**changes),
            )
        )


@pytest.mark.parametrize("year", [2027, 2028])
def test_special_30_profile_roundtrip_and_wrong_year_rollback(tmp_path: Path, year: int) -> None:
    db_path = str(tmp_path / "future-profile.db")
    ledger_init(db_path=db_path, fiscal_year=year)
    ledger_init(db_path=db_path, fiscal_year=2026)
    patch = FiscalYearTaxProfileUpdate(
        taxpayer_status="taxable", consumption_tax_method="special_30pct"
    )
    result = ledger_update_fiscal_year_tax_profile(db_path=db_path, fiscal_year=year, update=patch)
    assert result["after"]["consumption_tax_method"] == "special_30pct"
    assert (
        ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=year)[
            "consumption_tax_method"
        ]
        == "special_30pct"
    )
    before = ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2026)
    with pytest.raises(ValueError, match="fiscal_year=2026 は未対応"):
        ledger_update_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2026, update=patch)
    assert ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2026) == before
