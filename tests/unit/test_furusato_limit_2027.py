"""財務省931・932頁: 193万円キャップ、適用年度、税率調整の回帰。"""

from __future__ import annotations

from fractions import Fraction

import pytest
from pydantic import ValidationError

from shinkoku.models import FurusatoLimitInput
from shinkoku.tools.tax_calc import calc_furusato_deduction_limit
from shinkoku.tools.tax_reform import calc_furusato_limit_detailed


def _input(**changes: object) -> FurusatoLimitInput:
    return FurusatoLimitInput.model_validate(
        dict(
            fiscal_year=2027,
            resident_tax_income_levy=10000000,
            resident_taxable_income=100000000,
            personal_deduction_difference=0,
            income_tax_basic_deduction=0,
        )
        | changes
    )


@pytest.mark.parametrize(
    "levy,cap,applied",
    [
        (9649999, 1929999, False),
        (9650000, 1930000, False),
        (9650004, 1930000, False),
        (9650005, 1930000, True),
        (10000000, 1930000, True),
    ],
)
def test_fixed_cap_is_for_special_credit_not_donation(levy: int, cap: int, applied: bool) -> None:
    result = calc_furusato_limit_detailed(_input(resident_tax_income_levy=levy))
    assert result.special_credit_limit == cap
    assert result.fixed_cap_applied is applied
    assert result.estimated_limit == int(Fraction(cap, 1) / Fraction(44055, 100000)) + 2000
    assert result.estimated_limit > 1930000
    assert result.resident_tax_assessment_year == 2028


@pytest.mark.parametrize("year", [2025, 2026])
def test_older_donation_years_do_not_apply_fixed_cap(year: int) -> None:
    result = calc_furusato_limit_detailed(_input(fiscal_year=year))
    assert result.fixed_special_credit_cap is None
    assert result.special_credit_limit == 2000000
    assert result.resident_tax_assessment_year == year + 1


@pytest.mark.parametrize(
    "basic,expected_adjustment", [(0, 50000), (480000, 50000), (580000, 150000), (1040000, 610000)]
)
def test_rate_adjustment_floors_only_basic_deduction_excess(
    basic: int, expected_adjustment: int
) -> None:
    result = calc_furusato_limit_detailed(
        _input(
            resident_taxable_income=3500000,
            resident_tax_income_levy=350000,
            personal_deduction_difference=50000,
            income_tax_basic_deduction=basic,
        )
    )
    assert result.rate_adjustment == expected_adjustment
    assert result.rate_taxable_income == 3500000 - expected_adjustment
    assert result.income_tax_rate_percent == (10 if basic == 1040000 else 20)


@pytest.mark.parametrize(
    "taxable,rate",
    [
        (0, 0),
        (1950000, 5),
        (1951000, 10),
        (3300000, 10),
        (3301000, 20),
        (40000000, 40),
        (40001000, 45),
    ],
)
def test_marginal_rate_boundaries(taxable: int, rate: int) -> None:
    result = calc_furusato_limit_detailed(_input(resident_taxable_income=taxable))
    assert result.income_tax_rate_percent == rate
    assert result.special_credit_rate_numerator == 90000 - rate * 1021


def test_old_cli_shape_is_kept_when_using_new_2027_input() -> None:
    data = _input()
    assert (
        calc_furusato_deduction_limit(**data.model_dump())
        == calc_furusato_limit_detailed(data).estimated_limit
    )


def test_2027_cannot_silently_reuse_income_tax_deductions() -> None:
    with pytest.raises(ValueError, match="resident_tax_income_levy"):
        calc_furusato_deduction_limit(5000000, 1500000, fiscal_year=2027)


def test_zero_resident_levy_has_zero_limit() -> None:
    assert calc_furusato_limit_detailed(_input(resident_tax_income_levy=0)).estimated_limit == 0


@pytest.mark.parametrize("rate", [True, 10.0, "10", 99, -1])
def test_invalid_rate_is_not_coerced(rate: object) -> None:
    with pytest.raises(ValidationError):
        _input(income_tax_rate_percent=rate)


@pytest.mark.parametrize("year", [2024, 2028, 2030])
def test_future_donation_years_remain_guarded(year: int) -> None:
    with pytest.raises(ValueError, match="未対応"):
        calc_furusato_limit_detailed(_input(fiscal_year=year))
