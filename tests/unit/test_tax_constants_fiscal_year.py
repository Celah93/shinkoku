"""年分別の所得税定数と計算経路のテスト。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shinkoku.models import DependentInfo, IncomeTaxInput
from shinkoku.tax_constants import (
    BASIC_DEDUCTION_TABLE,
    DEPENDENT_INCOME_LIMIT,
    INCOME_TAX_CONSTANTS_BY_YEAR,
    SALARY_DEDUCTION_MIN,
    WORKING_STUDENT_DEDUCTION,
    WORKING_STUDENT_INCOME_LIMIT,
    get_income_tax_constants,
)
from shinkoku.tools.tax_calc import (
    calc_basic_deduction,
    calc_deductions,
    calc_dependents_deduction,
    calc_income_tax,
    calc_salary_deduction,
    calc_working_student_deduction,
)


class TestIncomeTaxYearConstants:
    def test_supported_years_are_explicit(self) -> None:
        assert set(INCOME_TAX_CONSTANTS_BY_YEAR) == {2025, 2026, 2027}

    def test_2025_matches_existing_constants(self) -> None:
        constants = get_income_tax_constants(2025)

        assert constants.basic_deduction_table == tuple(BASIC_DEDUCTION_TABLE)
        assert constants.salary_deduction_min == SALARY_DEDUCTION_MIN
        assert constants.dependent_income_limit == DEPENDENT_INCOME_LIMIT
        assert constants.working_student_income_limit == WORKING_STUDENT_INCOME_LIMIT
        assert constants.salary_income_step_table is None

    def test_2026_values(self) -> None:
        constants = get_income_tax_constants(2026)

        assert constants.basic_deduction_table[:5] == (
            (1_320_000, 1_040_000),
            (3_360_000, 1_040_000),
            (4_890_000, 1_040_000),
            (6_550_000, 670_000),
            (23_500_000, 620_000),
        )
        assert constants.salary_deduction_min == 740_000
        assert constants.dependent_income_limit == 620_000
        assert constants.working_student_income_limit == 890_000
        assert constants.salary_income_step_table is not None

    def test_2027_shares_immutable_2026_values(self) -> None:
        assert get_income_tax_constants(2027) is get_income_tax_constants(2026)

    def test_tables_and_year_constants_are_immutable(self) -> None:
        constants = get_income_tax_constants(2026)

        assert isinstance(constants.basic_deduction_table, tuple)
        assert isinstance(constants.salary_income_step_table, tuple)
        with pytest.raises(FrozenInstanceError):
            setattr(constants, "salary_deduction_min", 0)

    @pytest.mark.parametrize("fiscal_year", [2020, 2024, 2028])
    def test_unsupported_year_raises_with_supported_years(self, fiscal_year: int) -> None:
        with pytest.raises(ValueError) as exc_info:
            get_income_tax_constants(fiscal_year)

        message = str(exc_info.value)
        assert str(fiscal_year) in message
        assert "[2025, 2026, 2027]" in message


@pytest.mark.parametrize(
    ("total_income", "expected_2025", "expected_2026"),
    [
        (4_890_000, 680_000, 1_040_000),
        (4_890_001, 630_000, 670_000),
        (6_550_000, 630_000, 670_000),
        (6_550_001, 580_000, 620_000),
        (23_500_000, 580_000, 620_000),
        (23_500_001, 480_000, 480_000),
    ],
)
def test_basic_deduction_boundaries_by_year(
    total_income: int, expected_2025: int, expected_2026: int
) -> None:
    assert calc_basic_deduction(total_income, 2025) == expected_2025
    assert calc_basic_deduction(total_income, 2026) == expected_2026


def _salary_income_after_deduction(salary_revenue: int, fiscal_year: int) -> int:
    deduction = calc_salary_deduction(salary_revenue, fiscal_year)
    return max(0, salary_revenue - deduction)


@pytest.mark.parametrize(
    ("salary_revenue", "expected_income"),
    [
        (690_999, 0),
        (691_000, 0),
        (740_999, 0),
        (741_000, 1_000),
        (1_900_000, 1_160_000),
        (1_900_001, 1_160_001),
        (2_190_999, 1_450_999),
        (2_191_000, 1_451_000),
        (2_192_999, 1_451_000),
        (2_193_000, 1_453_000),
        (2_195_999, 1_453_000),
        (2_196_000, 1_456_000),
        (2_199_999, 1_456_000),
        (2_200_000, 1_460_000),
    ],
)
def test_salary_income_2026_step_table(salary_revenue: int, expected_income: int) -> None:
    assert _salary_income_after_deduction(salary_revenue, 2026) == expected_income
    assert _salary_income_after_deduction(salary_revenue, 2027) == expected_income


@pytest.mark.parametrize(
    ("salary_revenue", "expected_income"),
    [
        (690_999, 40_999),
        (691_000, 41_000),
        (740_999, 90_999),
        (741_000, 91_000),
        (1_900_000, 1_250_000),
        (1_900_001, 1_250_001),
        (2_190_999, 1_453_700),
        (2_191_000, 1_453_700),
        (2_192_999, 1_455_100),
        (2_193_000, 1_455_100),
        (2_195_999, 1_457_200),
        (2_196_000, 1_457_200),
        (2_199_999, 1_460_000),
        (2_200_000, 1_460_000),
    ],
)
def test_salary_income_2025_is_unchanged(salary_revenue: int, expected_income: int) -> None:
    assert _salary_income_after_deduction(salary_revenue, 2025) == expected_income


@pytest.mark.parametrize(
    ("fiscal_year", "dependent_income", "eligible"),
    [
        (2025, 580_000, True),
        (2025, 580_001, False),
        (2026, 620_000, True),
        (2026, 620_001, False),
    ],
)
def test_general_dependent_income_boundary(
    fiscal_year: int, dependent_income: int, eligible: bool
) -> None:
    dependent = DependentInfo(
        name="一般扶養",
        relationship="親",
        birth_date="1980-06-15",
        income=dependent_income,
    )

    result = calc_dependents_deduction(
        [dependent], taxpayer_income=3_000_000, fiscal_year=fiscal_year
    )

    assert any(item.type == "dependent" for item in result) is eligible


@pytest.mark.parametrize("fiscal_year", [2026, 2027])
def test_specific_relative_classification_changes_from_2026(fiscal_year: int) -> None:
    dependent = DependentInfo(
        name="特定親族",
        relationship="子",
        birth_date="2005-06-15",
        income=600_000,
    )

    result_2025 = calc_dependents_deduction(
        [dependent], taxpayer_income=3_000_000, fiscal_year=2025
    )
    result_new = calc_dependents_deduction(
        [dependent], taxpayer_income=3_000_000, fiscal_year=fiscal_year
    )

    assert [(item.type, item.amount) for item in result_2025] == [
        ("specific_relative_special", 630_000)
    ]
    assert [(item.type, item.amount) for item in result_new] == [("dependent", 630_000)]


@pytest.mark.parametrize(
    ("fiscal_year", "total_income", "expected"),
    [
        (2025, 850_000, WORKING_STUDENT_DEDUCTION),
        (2025, 850_001, 0),
        (2026, 890_000, WORKING_STUDENT_DEDUCTION),
        (2026, 890_001, 0),
        (2027, 890_000, WORKING_STUDENT_DEDUCTION),
        (2027, 890_001, 0),
    ],
)
def test_working_student_income_boundary(
    fiscal_year: int, total_income: int, expected: int
) -> None:
    assert calc_working_student_deduction(True, total_income, fiscal_year) == expected


def test_calc_deductions_passes_fiscal_year_to_working_student() -> None:
    result_2025 = calc_deductions(total_income=890_000, fiscal_year=2025, working_student=True)
    result_2026 = calc_deductions(total_income=890_000, fiscal_year=2026, working_student=True)

    assert not any(item.type == "working_student" for item in result_2025.income_deductions)
    assert any(item.type == "working_student" for item in result_2026.income_deductions)


@pytest.mark.parametrize(
    ("fiscal_year", "expected_basic"),
    [(2025, 880_000), (2026, 1_040_000)],
)
def test_calc_income_tax_uses_basic_deduction_for_year(
    fiscal_year: int, expected_basic: int
) -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=fiscal_year,
            business_revenue=3_000_000,
            blue_return_deduction=0,
        )
    )

    assert result.deductions_detail is not None
    basic = next(
        item for item in result.deductions_detail.income_deductions if item.type == "basic"
    )
    assert basic.amount == expected_basic


@pytest.mark.parametrize(
    ("fiscal_year", "expected_salary_income"),
    [(2025, 1_320_000), (2026, 1_260_000)],
)
def test_calc_income_tax_uses_salary_table_for_year(
    fiscal_year: int, expected_salary_income: int
) -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=fiscal_year,
            salary_income=2_000_000,
            blue_return_deduction=0,
        )
    )

    assert result.salary_income_after_deduction == expected_salary_income


def test_unsupported_year_fails_before_input_dependent_branches() -> None:
    with pytest.raises(ValueError, match="2028"):
        calc_income_tax(IncomeTaxInput(fiscal_year=2028, blue_return_deduction=0))

    with pytest.raises(ValueError, match="2028"):
        calc_deductions(total_income=0, fiscal_year=2028)
