"""年齢計算と扶養控除の生年月日境界テスト。"""

from __future__ import annotations

import re

import pytest

from shinkoku.models import DependentInfo
from shinkoku.tools.tax_calc import _calc_age, calc_dependents_deduction


@pytest.mark.parametrize(
    ("birth_date", "fiscal_year", "expected_age"),
    [
        ("2010-01-01", 2025, 16),
        ("2010-01-02", 2025, 15),
        ("2010-12-31", 2025, 15),
        ("2009-12-31", 2025, 16),
        ("2007-01-01", 2025, 19),
        ("2007-01-02", 2025, 18),
        ("2003-01-01", 2025, 23),
        ("2003-01-02", 2025, 22),
        ("1956-01-01", 2025, 70),
        ("1956-01-02", 2025, 69),
        ("2008-02-29", 2025, 17),
        ("2010-01-01", 2026, 17),
        ("2007-01-01", 2026, 20),
    ],
)
def test_calc_age_at_year_end(birth_date: str, fiscal_year: int, expected_age: int) -> None:
    assert _calc_age(birth_date, fiscal_year) == expected_age


@pytest.mark.parametrize("birth_date", ["2025-99-99", "not-a-date"])
def test_calc_age_rejects_invalid_birth_date(birth_date: str) -> None:
    with pytest.raises(
        ValueError,
        match=re.escape(f"扶養親族の生年月日 '{birth_date}' が不正です"),
    ):
        _calc_age(birth_date, 2025)


@pytest.mark.parametrize(
    (
        "birth_date",
        "fiscal_year",
        "cohabiting",
        "relationship",
        "expected_type",
        "expected_amount",
        "expected_classification",
    ),
    [
        ("2010-01-01", 2025, False, "子", "dependent", 380_000, "一般扶養"),
        ("2010-01-02", 2025, False, "子", None, 0, None),
        ("2007-01-01", 2025, False, "子", "dependent", 630_000, "特定扶養"),
        ("2007-01-02", 2025, False, "子", "dependent", 380_000, "一般扶養"),
        ("2003-01-01", 2025, False, "子", "dependent", 380_000, "一般扶養"),
        ("2003-01-02", 2025, False, "子", "dependent", 630_000, "特定扶養"),
        ("1956-01-01", 2025, False, "親", "dependent", 480_000, "老人扶養・別居"),
        ("1956-01-01", 2025, True, "親", "dependent", 580_000, "老人扶養・同居"),
        ("1956-01-02", 2025, False, "親", "dependent", 380_000, "一般扶養"),
        ("2011-01-01", 2026, False, "子", "dependent", 380_000, "一般扶養"),
    ],
)
def test_dependent_deduction_uses_legal_age_at_year_end(
    birth_date: str,
    fiscal_year: int,
    cohabiting: bool,
    relationship: str,
    expected_type: str | None,
    expected_amount: int,
    expected_classification: str | None,
) -> None:
    dependent = DependentInfo(
        name="境界親族",
        relationship=relationship,
        birth_date=birth_date,
        income=0,
        cohabiting=cohabiting,
    )

    result = calc_dependents_deduction(
        [dependent], taxpayer_income=3_000_000, fiscal_year=fiscal_year
    )

    if expected_type is None:
        assert result == []
        return

    assert [(item.type, item.amount) for item in result] == [(expected_type, expected_amount)]
    assert expected_classification is not None
    assert result[0].details is not None
    assert expected_classification in result[0].details


@pytest.mark.parametrize(
    ("fiscal_year", "expected_type"),
    [
        (2025, "specific_relative_special"),
        (2026, "dependent"),
    ],
)
def test_january_first_age_crosses_fiscal_year_dependent_income_rules(
    fiscal_year: int, expected_type: str
) -> None:
    dependent = DependentInfo(
        name="特定親族境界",
        relationship="子",
        birth_date="2007-01-01",
        income=600_000,
        cohabiting=False,
    )

    result = calc_dependents_deduction(
        [dependent], taxpayer_income=3_000_000, fiscal_year=fiscal_year
    )

    assert [(item.type, item.amount) for item in result] == [(expected_type, 630_000)]


@pytest.mark.parametrize(
    ("birth_date", "expected_type", "expected_amount"),
    [
        ("2004-01-01", None, 0),
        ("2004-01-02", "specific_relative_special", 630_000),
        ("2008-01-01", "specific_relative_special", 630_000),
        ("2008-01-02", None, 0),
    ],
)
def test_2026_specific_relative_income_boundary_uses_legal_age(
    birth_date: str,
    expected_type: str | None,
    expected_amount: int,
) -> None:
    dependent = DependentInfo(
        name="特定親族年齢境界",
        relationship="子",
        birth_date=birth_date,
        income=630_000,
    )

    result = calc_dependents_deduction(
        [dependent],
        taxpayer_income=3_000_000,
        fiscal_year=2026,
    )

    if expected_type is None:
        assert result == []
        return
    assert [(item.type, item.amount) for item in result] == [(expected_type, expected_amount)]
