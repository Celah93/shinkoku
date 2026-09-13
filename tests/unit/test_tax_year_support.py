"""未対応年分を旧制度で計算・検算しないことを検証する。"""

from __future__ import annotations

import pytest

from shinkoku.models import ConsumptionTaxInput, IncomeTaxInput
from shinkoku.tools.tax_calc import (
    calc_consumption_tax,
    calc_deductions,
    calc_furusato_deduction_limit,
    calc_income_tax,
    sanity_check_income_tax,
)


@pytest.mark.parametrize("fiscal_year", [2024, 2028, 2035])
@pytest.mark.parametrize("salary_income", [0, 5_000_000])
def test_income_rejects_unsupported_year_even_without_taxable_income(
    fiscal_year: int, salary_income: int
) -> None:
    with pytest.raises(ValueError, match=f"fiscal_year={fiscal_year} は未対応") as caught:
        calc_income_tax(
            IncomeTaxInput(
                fiscal_year=fiscal_year,
                salary_income=salary_income,
                blue_return_deduction=0,
            )
        )
    assert "対応年分: [2025, 2026, 2027]" in str(caught.value)


@pytest.mark.parametrize("fiscal_year", [2024, 2028, 2035])
def test_deductions_reject_unsupported_year(fiscal_year: int) -> None:
    with pytest.raises(ValueError, match=f"fiscal_year={fiscal_year} は未対応"):
        calc_deductions(
            total_income=3_000_000, fiscal_year=fiscal_year, widow_status="single_parent"
        )


@pytest.mark.parametrize("fiscal_year", [2024, 2027, 2028, 2035])
@pytest.mark.parametrize("method", ["standard", "simplified", "special_20pct"])
def test_all_consumption_methods_reject_unsupported_year(fiscal_year: int, method: str) -> None:
    data = ConsumptionTaxInput(
        fiscal_year=fiscal_year,
        method=method,
        simplified_business_type=5 if method == "simplified" else None,
    )
    with pytest.raises(ValueError, match=f"fiscal_year={fiscal_year} は未対応"):
        calc_consumption_tax(data)


@pytest.mark.parametrize("fiscal_year", [2024, 2028, 2035])
def test_furusato_limit_rejects_unsupported_donation_year(fiscal_year: int) -> None:
    with pytest.raises(ValueError, match=f"fiscal_year={fiscal_year} は未対応"):
        calc_furusato_deduction_limit(0, 0, fiscal_year=fiscal_year)


@pytest.mark.parametrize("input_year,result_year", [(2028, 2028), (2028, 2026), (2026, 2028)])
def test_sanity_check_rejects_old_saved_results_for_unsupported_year(
    input_year: int, result_year: int
) -> None:
    supported_input = IncomeTaxInput(fiscal_year=2026, blue_return_deduction=0)
    saved_result = calc_income_tax(supported_input).model_copy(update={"fiscal_year": result_year})
    input_data = supported_input.model_copy(update={"fiscal_year": input_year})

    with pytest.raises(ValueError, match="fiscal_year=2028 は未対応"):
        sanity_check_income_tax(input_data, saved_result)


def test_sanity_check_requires_same_year_for_input_and_result() -> None:
    input_data = IncomeTaxInput(fiscal_year=2026, blue_return_deduction=0)
    saved_result = calc_income_tax(input_data).model_copy(update={"fiscal_year": 2025})
    with pytest.raises(ValueError, match="入力と計算結果の年分が一致しません"):
        sanity_check_income_tax(input_data, saved_result)


@pytest.mark.parametrize(
    "fiscal_year,basic_deduction,reconstruction_tax,tax_due",
    [(2025, 680_000, 4_000, 194_500), (2026, 1_040_000, 3_244, 157_700)],
)
def test_supported_income_results_are_preserved(
    fiscal_year: int, basic_deduction: int, reconstruction_tax: int, tax_due: int
) -> None:
    input_data = IncomeTaxInput(
        fiscal_year=fiscal_year, salary_income=5_000_000, blue_return_deduction=0
    )
    result = calc_income_tax(input_data)
    assert result.total_income_deductions == basic_deduction
    assert result.reconstruction_tax == reconstruction_tax
    assert result.tax_due == tax_due
    assert sanity_check_income_tax(input_data, result).passed is True


@pytest.mark.parametrize("fiscal_year", [2025, 2026])
@pytest.mark.parametrize(
    "method,total_due", [("standard", 100_000), ("simplified", 50_000), ("special_20pct", 20_000)]
)
def test_supported_consumption_results_are_preserved(
    fiscal_year: int, method: str, total_due: int
) -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=fiscal_year,
            method=method,
            taxable_sales_10=1_100_000,
            simplified_business_type=5 if method == "simplified" else None,
        )
    )
    assert result.total_due == total_due


def test_furusato_legacy_default_and_explicit_supported_years_are_preserved() -> None:
    assert calc_furusato_deduction_limit(5_000_000, 1_500_000) == 102_574
    for fiscal_year in (2025, 2026):
        assert (
            calc_furusato_deduction_limit(5_000_000, 1_500_000, fiscal_year=fiscal_year) == 102_574
        )
