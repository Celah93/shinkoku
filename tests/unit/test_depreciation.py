"""Tests for depreciation calculations."""

from __future__ import annotations

import pytest

from shinkoku.tools.tax_calc import calc_depreciation_straight_line


OFFICIAL_STRAIGHT_LINE_RATES_PERMILLE = {
    2: 500,
    3: 334,
    4: 250,
    5: 200,
    6: 167,
    7: 143,
    8: 125,
    9: 112,
    10: 100,
    11: 91,
    12: 84,
    13: 77,
    14: 72,
    15: 67,
    16: 63,
    17: 59,
    18: 56,
    19: 53,
    20: 50,
    21: 48,
    22: 46,
    23: 44,
    24: 42,
    25: 40,
    26: 39,
    27: 38,
    28: 36,
    29: 35,
    30: 34,
    31: 33,
    32: 32,
    33: 31,
    34: 30,
    35: 29,
    36: 28,
    37: 28,
    38: 27,
    39: 26,
    40: 25,
    41: 25,
    42: 24,
    43: 24,
    44: 23,
    45: 23,
    46: 22,
    47: 22,
    48: 21,
    49: 21,
    50: 20,
}


@pytest.mark.parametrize(
    ("useful_life", "rate_permille"),
    OFFICIAL_STRAIGHT_LINE_RATES_PERMILLE.items(),
)
def test_straight_line_rate_matches_official_table_2_to_50_years(
    useful_life: int, rate_permille: int
) -> None:
    """令和7年分の公式手引きに載る2〜50年の定額法償却率と一致する。"""
    assert calc_depreciation_straight_line(1_000_000, useful_life, 100) == (1_000 * rate_permille)


def test_straight_line_3years_applies_statutory_rate_0334() -> None:
    assert calc_depreciation_straight_line(300_000, 3, 100) == 100_200


def test_straight_line_6years_600000_yields_100200() -> None:
    assert calc_depreciation_straight_line(600_000, 6, 100) == 100_200


def test_straight_line_fractional_yen_rounds_up() -> None:
    assert calc_depreciation_straight_line(300_001, 3, 100) == 100_201


def test_straight_line_month_proration_rounds_up() -> None:
    assert calc_depreciation_straight_line(300_001, 3, 100, months=7) == 58_451


def test_straight_line_business_ratio_no_fraction() -> None:
    assert calc_depreciation_straight_line(300_000, 3, 80) == 80_160


def test_straight_line_ratio_applied_to_rounded_ordinary_amount() -> None:
    assert calc_depreciation_straight_line(100_020, 4, 40, months=6) == 5_002


def test_straight_line_investigation_report_case() -> None:
    assert calc_depreciation_straight_line(100_002, 4, 67, months=7) == 9_772


def test_straight_line_4years_without_fraction_unchanged() -> None:
    assert calc_depreciation_straight_line(300_000, 4, 100) == 75_000


@pytest.mark.parametrize(("useful_life", "months"), [(0, 12), (-1, 12), (4, 0), (4, -1)])
def test_straight_line_zero_or_negative_inputs_return_zero(useful_life: int, months: int) -> None:
    assert calc_depreciation_straight_line(300_000, useful_life, 100, months=months) == 0
