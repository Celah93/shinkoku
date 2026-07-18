"""配偶者・特定親族の年分別控除表テスト。"""

from __future__ import annotations

import pytest

from shinkoku.models import DeductionItem, DependentInfo
from shinkoku.tax_constants import (
    SPOUSE_DEDUCTION_AMOUNT_LE_1000,
    SPOUSE_DEDUCTION_AMOUNT_LE_900,
    SPOUSE_DEDUCTION_AMOUNT_LE_950,
    SPOUSE_DEDUCTION_TABLE,
    SPOUSE_DEDUCTION_TABLE_10M,
    SPOUSE_DEDUCTION_TABLE_9M,
    get_income_tax_constants,
)
from shinkoku.tools.tax_calc import (
    calc_deductions,
    calc_dependents_deduction,
    calc_spouse_deduction,
)


def _spouse_item(
    fiscal_year: int,
    spouse_income: int,
    taxpayer_income: int = 5_000_000,
) -> DeductionItem | None:
    result = calc_deductions(
        total_income=taxpayer_income,
        spouse_income=spouse_income,
        fiscal_year=fiscal_year,
    )
    return next(
        (item for item in result.income_deductions if item.type in {"spouse", "spouse_special"}),
        None,
    )


def test_year_constants_include_spouse_and_specific_relative_tables() -> None:
    constants = get_income_tax_constants(2025)

    assert constants.spouse_income_limit == 580_000
    assert constants.spouse_special_deduction_table
    assert constants.specific_relative_special_deduction_table


def test_calc_spouse_deduction_accepts_year_and_rejects_unsupported_year() -> None:
    assert calc_spouse_deduction(5_000_000, 700_000, fiscal_year=2025) == 380_000
    with pytest.raises(ValueError, match="2028"):
        calc_spouse_deduction(5_000_000, 700_000, fiscal_year=2028)


@pytest.mark.parametrize(
    ("fiscal_year", "spouse_income", "expected_type"),
    [
        (2025, 580_001, "spouse_special"),
        (2026, 580_001, "spouse"),
        (2026, 620_000, "spouse"),
        (2026, 620_001, "spouse_special"),
    ],
)
def test_spouse_classification_uses_year_boundary(
    fiscal_year: int, spouse_income: int, expected_type: str
) -> None:
    item = _spouse_item(fiscal_year, spouse_income)

    assert item is not None
    assert item.type == expected_type


@pytest.mark.parametrize("fiscal_year", [2025, 2026])
def test_special_tables_align_with_year_income_limits(fiscal_year: int) -> None:
    constants = get_income_tax_constants(fiscal_year)

    assert constants.spouse_special_deduction_table[0][0] == constants.spouse_income_limit
    assert (
        constants.specific_relative_special_deduction_table[0][0]
        == constants.dependent_income_limit
    )
    assert constants.spouse_special_deduction_table[-1][1] == 1_330_000
    assert constants.specific_relative_special_deduction_table[-1][1] == 1_230_000


def test_legacy_spouse_tables_match_2025_year_constants() -> None:
    constants = get_income_tax_constants(2025)
    special_rows = constants.spouse_special_deduction_table

    reconstructed_le_900 = (
        (constants.spouse_income_limit, SPOUSE_DEDUCTION_AMOUNT_LE_900),
    ) + tuple(
        (income_up_to, amount_le_900) for _, income_up_to, amount_le_900, _, _ in special_rows
    )
    reconstructed_le_950 = (
        (constants.spouse_income_limit, SPOUSE_DEDUCTION_AMOUNT_LE_950),
    ) + tuple(
        (income_up_to, amount_le_950) for _, income_up_to, _, amount_le_950, _ in special_rows
    )
    reconstructed_le_1000 = (
        (constants.spouse_income_limit, SPOUSE_DEDUCTION_AMOUNT_LE_1000),
    ) + tuple(
        (income_up_to, amount_le_1000) for _, income_up_to, _, _, amount_le_1000 in special_rows
    )

    assert tuple(SPOUSE_DEDUCTION_TABLE) == reconstructed_le_900
    assert tuple(SPOUSE_DEDUCTION_TABLE_9M) == reconstructed_le_950
    assert tuple(SPOUSE_DEDUCTION_TABLE_10M) == reconstructed_le_1000


@pytest.mark.parametrize(
    ("spouse_income", "expected_amount", "expected_type"),
    [
        (620_000, 380_000, "spouse"),
        (620_001, 380_000, "spouse_special"),
        (950_000, 380_000, "spouse_special"),
        (950_001, 360_000, "spouse_special"),
        (1_000_000, 360_000, "spouse_special"),
        (1_000_001, 310_000, "spouse_special"),
        (1_050_000, 310_000, "spouse_special"),
        (1_050_001, 260_000, "spouse_special"),
        (1_100_000, 260_000, "spouse_special"),
        (1_100_001, 210_000, "spouse_special"),
        (1_150_000, 210_000, "spouse_special"),
        (1_150_001, 160_000, "spouse_special"),
        (1_200_000, 160_000, "spouse_special"),
        (1_200_001, 110_000, "spouse_special"),
        (1_250_000, 110_000, "spouse_special"),
        (1_250_001, 60_000, "spouse_special"),
        (1_300_000, 60_000, "spouse_special"),
        (1_300_001, 30_000, "spouse_special"),
        (1_330_000, 30_000, "spouse_special"),
        (1_330_001, 0, None),
    ],
)
def test_2026_spouse_income_boundaries_return_expected_classification(
    spouse_income: int,
    expected_amount: int,
    expected_type: str | None,
) -> None:
    item = _spouse_item(2026, spouse_income)

    if expected_type is None:
        assert item is None
        assert calc_spouse_deduction(5_000_000, spouse_income, 2026) == 0
        return
    assert item is not None
    assert (item.amount, item.type) == (expected_amount, expected_type)
    assert calc_spouse_deduction(5_000_000, spouse_income, 2026) == expected_amount


@pytest.mark.parametrize(
    ("taxpayer_income", "expected_amount"),
    [
        (9_000_000, 380_000),
        (9_000_001, 260_000),
        (9_500_000, 260_000),
        (9_500_001, 130_000),
        (10_000_000, 130_000),
        (10_000_001, 0),
    ],
)
def test_2026_spouse_taxpayer_income_boundaries_return_expected_amount(
    taxpayer_income: int,
    expected_amount: int,
) -> None:
    assert calc_spouse_deduction(taxpayer_income, 700_000, 2026) == expected_amount


def test_2025_spouse_middle_taxpayer_bracket_is_unchanged() -> None:
    assert calc_spouse_deduction(9_000_001, 700_000, 2025) == 260_000


@pytest.mark.parametrize(
    ("spouse_income", "expected_amount", "expected_type"),
    [
        (580_000, 380_000, "spouse"),
        (580_001, 380_000, "spouse_special"),
        (950_000, 380_000, "spouse_special"),
        (950_001, 360_000, "spouse_special"),
        (1_000_000, 360_000, "spouse_special"),
        (1_000_001, 310_000, "spouse_special"),
        (1_050_000, 310_000, "spouse_special"),
        (1_050_001, 260_000, "spouse_special"),
        (1_100_000, 260_000, "spouse_special"),
        (1_100_001, 210_000, "spouse_special"),
        (1_150_000, 210_000, "spouse_special"),
        (1_150_001, 160_000, "spouse_special"),
        (1_200_000, 160_000, "spouse_special"),
        (1_200_001, 110_000, "spouse_special"),
        (1_250_000, 110_000, "spouse_special"),
        (1_250_001, 60_000, "spouse_special"),
        (1_300_000, 60_000, "spouse_special"),
        (1_300_001, 30_000, "spouse_special"),
        (1_330_000, 30_000, "spouse_special"),
        (1_330_001, 0, None),
    ],
)
def test_2025_spouse_income_boundaries_keep_amounts_and_fix_classification(
    spouse_income: int,
    expected_amount: int,
    expected_type: str | None,
) -> None:
    item = _spouse_item(2025, spouse_income)

    if expected_type is None:
        assert item is None
        return
    assert item is not None
    assert (item.amount, item.type) == (expected_amount, expected_type)


def _specific_relative_items(
    fiscal_year: int,
    relative_income: int,
    taxpayer_income: int = 5_000_000,
) -> list[DeductionItem]:
    relative = DependentInfo(
        name="特定親族",
        relationship="子",
        birth_date="2005-06-15",
        income=relative_income,
    )
    return calc_dependents_deduction(
        [relative],
        taxpayer_income=taxpayer_income,
        fiscal_year=fiscal_year,
    )


@pytest.mark.parametrize(
    ("relative_income", "expected_amount", "expected_type"),
    [
        (620_000, 630_000, "dependent"),
        (620_001, 630_000, "specific_relative_special"),
        (850_000, 630_000, "specific_relative_special"),
        (850_001, 610_000, "specific_relative_special"),
        (900_000, 610_000, "specific_relative_special"),
        (900_001, 510_000, "specific_relative_special"),
        (950_000, 510_000, "specific_relative_special"),
        (950_001, 410_000, "specific_relative_special"),
        (1_000_000, 410_000, "specific_relative_special"),
        (1_000_001, 310_000, "specific_relative_special"),
        (1_050_000, 310_000, "specific_relative_special"),
        (1_050_001, 210_000, "specific_relative_special"),
        (1_100_000, 210_000, "specific_relative_special"),
        (1_100_001, 110_000, "specific_relative_special"),
        (1_150_000, 110_000, "specific_relative_special"),
        (1_150_001, 60_000, "specific_relative_special"),
        (1_200_000, 60_000, "specific_relative_special"),
        (1_200_001, 30_000, "specific_relative_special"),
        (1_230_000, 30_000, "specific_relative_special"),
        (1_230_001, 0, None),
    ],
)
def test_2026_specific_relative_income_boundaries_are_unchanged(
    relative_income: int,
    expected_amount: int,
    expected_type: str | None,
) -> None:
    items = _specific_relative_items(2026, relative_income)

    if expected_type is None:
        assert items == []
        return
    assert [(item.amount, item.type) for item in items] == [(expected_amount, expected_type)]


@pytest.mark.parametrize(
    ("relative_income", "expected_amount", "expected_type"),
    [
        (580_000, 630_000, "dependent"),
        (580_001, 630_000, "specific_relative_special"),
        (1_230_000, 30_000, "specific_relative_special"),
        (1_230_001, 0, None),
    ],
)
def test_2025_specific_relative_spots_are_unchanged(
    relative_income: int,
    expected_amount: int,
    expected_type: str | None,
) -> None:
    items = _specific_relative_items(2025, relative_income)

    if expected_type is None:
        assert items == []
        return
    assert [(item.amount, item.type) for item in items] == [(expected_amount, expected_type)]


def test_specific_relative_has_no_taxpayer_income_limit() -> None:
    items = _specific_relative_items(
        2026,
        relative_income=630_000,
        taxpayer_income=10_000_001,
    )

    assert [(item.amount, item.type) for item in items] == [(630_000, "specific_relative_special")]


@pytest.mark.parametrize(
    ("fiscal_year", "spouse_income", "expected_amount", "expected_type"),
    [
        (2026, 620_001, 380_000, "spouse_special"),
        (2027, 620_001, 380_000, "spouse_special"),
        (2026, 1_330_000, 30_000, "spouse_special"),
        (2027, 1_330_000, 30_000, "spouse_special"),
    ],
)
def test_2027_spouse_representative_boundaries_match_2026(
    fiscal_year: int,
    spouse_income: int,
    expected_amount: int,
    expected_type: str,
) -> None:
    item = _spouse_item(fiscal_year, spouse_income)

    assert item is not None
    assert (item.amount, item.type) == (expected_amount, expected_type)


@pytest.mark.parametrize("fiscal_year", [2026, 2027])
def test_2027_specific_relative_upper_boundary_matches_2026(fiscal_year: int) -> None:
    assert _specific_relative_items(fiscal_year, 1_230_001) == []
