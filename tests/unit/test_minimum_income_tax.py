"""国税庁計算書と記載例、財務省の2027年改正による高所得特例の検証。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shinkoku.models import (
    DonationRecordRecord,
    IncomeTaxInput,
    MinimumIncomeTaxInput,
    MinimumTaxIncomeBreakdown,
)
from shinkoku.tools.tax_calc import calc_income_tax, sanity_check_income_tax
from shinkoku.tools.tax_reform import calc_minimum_income_tax


def _input(**changes: object) -> MinimumIncomeTaxInput:
    values = dict(
        fiscal_year=2027,
        incomes={"comprehensive_income": 500000000},
        ordinary_income_tax=40000000,
        income_scope_confirmed=True,
        calculation_mode="filing",
    )
    return MinimumIncomeTaxInput.model_validate({**values, **changes})


def test_nta_2025_two_stage_worked_example() -> None:
    # 国税庁 tokutei.pdf。掲載された値をそのまま期待値にする。
    result = calc_minimum_income_tax(
        _input(
            fiscal_year=2025,
            incomes={"comprehensive_income": 3000000, "listed_stock_dividends": 1050000000},
            ordinary_income_tax=91000,
            uses_nonfiling_system=True,
            nonfiling_income_withheld_tax=160807500,
            recalculated_income_tax=157672500,
        )
    )
    assert result.base_income_amount == 1053000000
    assert result.rounded_excess_income == 723000000
    assert result.benchmark_tax == 162675000
    assert result.ordinary_tax_with_special == 92911
    assert result.initial_base_tax == 160900411
    assert result.initial_additional_tax == 1774589
    assert result.recalculated_base_tax == 160983622
    assert result.additional_income_tax == 1691378
    assert result.adjusted_income_tax == 159363878
    assert result.final_special_taxes.reconstruction_tax == 3346641
    assert result.total_tax == 162710519
    assert (result.total_tax - 160807500) // 100 * 100 == 1903000


@pytest.mark.parametrize(
    "year,threshold,rate", [(2025, 330000000, 225), (2026, 330000000, 225), (2027, 165000000, 300)]
)
@pytest.mark.parametrize("excess,rounded", [(-1, 0), (0, 0), (1, 0), (999, 0), (1000, 1000)])
def test_year_and_thousand_yen_boundaries(
    year: int, threshold: int, rate: int, excess: int, rounded: int
) -> None:
    result = calc_minimum_income_tax(
        _input(
            fiscal_year=year,
            incomes={"comprehensive_income": threshold + excess},
            ordinary_income_tax=0,
        )
    )
    assert result.threshold == threshold
    assert result.rate_numerator == rate
    assert result.rounded_excess_income == rounded
    assert result.benchmark_tax == (rate if rounded else 0)


def test_sum_income_before_rounding_excess() -> None:
    result = calc_minimum_income_tax(
        _input(
            incomes={"comprehensive_income": 165000999, "listed_stock_gains": 1},
            ordinary_income_tax=0,
        )
    )
    assert result.benchmark_tax == 300


def test_stage_one_positive_requires_recalculation_without_final_tax() -> None:
    result = calc_minimum_income_tax(_input(uses_nonfiling_system=True))
    assert result.status == "requires_recalculation"
    assert result.initial_additional_tax == 59660000
    assert result.total_tax is result.additional_income_tax is result.adjusted_income_tax is None


def test_recalculation_can_cancel_the_special_scheme() -> None:
    params = _input(uses_nonfiling_system=True, recalculated_income_tax=100000000)
    result = calc_minimum_income_tax(params)
    assert result.initial_additional_tax > 0
    assert result.recalculated_base_tax == 102100000
    assert result.status == "not_applicable"
    assert result.additional_income_tax == 0
    assert result.adjusted_income_tax == 40000000
    assert result.total_tax == 40840000


def test_2027_minimum_tax_and_both_special_taxes() -> None:
    result = calc_minimum_income_tax(_input())
    assert result.benchmark_tax == 100500000
    assert result.initial_base_tax == 40840000
    assert result.additional_income_tax == 59660000
    assert result.adjusted_income_tax == 99660000
    assert result.final_special_taxes.reconstruction_tax == 1096260
    assert result.final_special_taxes.defense_tax == 996600
    assert result.total_tax == 101752860


@pytest.mark.parametrize(
    "mode,confirmed", [("filing", None), ("filing", False), ("estimate", False)]
)
def test_incomplete_income_cannot_be_finalized(mode: str, confirmed: bool | None) -> None:
    with pytest.raises(ValueError, match="income_scope_confirmed"):
        calc_minimum_income_tax(_input(calculation_mode=mode, income_scope_confirmed=confirmed))


@pytest.mark.parametrize("year", [2024, 2028, 2030])
def test_unsupported_minimum_tax_years(year: int) -> None:
    with pytest.raises(ValueError, match="未対応"):
        calc_minimum_income_tax(_input(fiscal_year=year))


@pytest.mark.parametrize("value", [-1, 1.1, True, "1000"])
def test_income_amounts_are_nonnegative_integer_yen(value: object) -> None:
    with pytest.raises(ValidationError):
        MinimumTaxIncomeBreakdown(comprehensive_income=value)


@pytest.mark.parametrize(
    "changes", [{"nonfiling_income_withheld_tax": 1}, {"recalculated_income_tax": 1}]
)
def test_nonfiling_context_cannot_be_mixed(changes: dict) -> None:
    with pytest.raises(ValidationError):
        _input(**changes)


def test_annual_high_income_is_computed_and_scope_is_checked() -> None:
    params = IncomeTaxInput(
        fiscal_year=2027,
        business_revenue=200000000,
        blue_return_deduction=0,
        calculation_mode="filing",
    )
    with pytest.raises(ValueError, match="minimum_tax_income_complete"):
        calc_income_tax(params)
    params.minimum_tax_income_complete = True
    result = calc_income_tax(params)
    assert result.income_tax_after_credits == 85204000
    assert result.minimum_tax_additional_income_tax == 0
    assert result.minimum_tax_detail.status == "not_applicable"
    assert result.minimum_tax_detail.calculation_mode == "filing"
    assert sanity_check_income_tax(params, result).passed


def test_annual_minimum_tax_uses_income_after_loss_carryforward() -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=2027,
            business_revenue=500000000,
            blue_return_deduction=0,
            loss_carryforward_amount=400000000,
            calculation_mode="filing",
        )
    )
    assert result.total_income == 100000000
    assert result.minimum_tax_additional_income_tax == 0
    assert result.minimum_tax_detail is None


def test_annual_large_donation_can_trigger_minimum_tax() -> None:
    params = IncomeTaxInput(
        fiscal_year=2027,
        business_revenue=2000000000,
        blue_return_deduction=0,
        furusato_nozei=800000000,
        calculation_mode="filing",
        minimum_tax_income_complete=True,
    )
    result = calc_income_tax(params)
    # 所得控除は寄附8億-2000、課税所得1,200,002,000。
    assert result.income_tax_after_credits == 535204900
    assert result.minimum_tax_detail.benchmark_tax == 550500000
    assert result.minimum_tax_additional_income_tax == 4055798
    assert result.income_tax_after_minimum_tax == 539260698
    assert result.total_tax == 550585172
    assert result.tax_due == 550585100
    assert sanity_check_income_tax(params, result).passed
    tampered = result.model_copy(update={"minimum_tax_additional_income_tax": 0})
    assert not sanity_check_income_tax(params, tampered).passed
    tampered = result.model_copy(update={"minimum_tax_detail": None})
    assert "MINIMUM_TAX_DETAIL_MISMATCH" in {
        item.code for item in sanity_check_income_tax(params, tampered).items
    }


def test_donation_choice_compares_tax_including_the_minimum_tax() -> None:
    donation = DonationRecordRecord(
        id=1,
        fiscal_year=2027,
        donation_type="npo",
        recipient_name="架空の認定NPO",
        amount=10000000,
        date="2027-12-01",
        receipt_number=None,
        source_file=None,
    )
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=2027,
            business_revenue=2000000000,
            blue_return_deduction=0,
            furusato_nozei=790000000,
            donations=[donation],
            minimum_tax_income_complete=True,
            calculation_mode="filing",
        )
    )
    # 全額所得控除なら550,585,172円。通常税額だけでは所得控除が有利だが、
    # 高所得特例を含む最終額ではNPO税額控除の550,574,452円が小さい。
    assert result.donation_selection.npo == "credit"
    assert result.income_tax_after_credits == 535704900
    assert result.minimum_tax_additional_income_tax == 3545298
    assert result.total_tax == 550574452
