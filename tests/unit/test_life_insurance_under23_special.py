"""23歳未満の扶養親族を有する場合の生命保険料控除特例のテスト。"""

from __future__ import annotations

import pytest

from shinkoku.models import DependentInfo, IncomeTaxInput, LifeInsurancePremiumInput
from shinkoku.tools.tax_calc import (
    calc_deductions,
    calc_income_tax,
    calc_life_insurance_deduction,
)


def _dependent(
    *,
    birth_date: str = "2004-01-02",
    income: int = 0,
    relationship: str = "子",
    other_taxpayer_dependent: bool = False,
) -> DependentInfo:
    return DependentInfo(
        name="特例判定親族",
        relationship=relationship,
        birth_date=birth_date,
        income=income,
        other_taxpayer_dependent=other_taxpayer_dependent,
    )


def _life_item(
    *,
    fiscal_year: int,
    general_new: int = 0,
    general_old: int = 0,
    medical_care: int = 0,
    annuity_new: int = 0,
    annuity_old: int = 0,
    dependents: list[DependentInfo] | None = None,
):
    result = calc_deductions(
        total_income=3_000_000,
        fiscal_year=fiscal_year,
        life_insurance_detail=LifeInsurancePremiumInput(
            general_new=general_new,
            general_old=general_old,
            medical_care=medical_care,
            annuity_new=annuity_new,
            annuity_old=annuity_old,
        ),
        dependents=dependents,
    )
    return next(item for item in result.income_deductions if item.type == "life_insurance")


@pytest.mark.parametrize(
    ("premium", "expected"),
    [
        (20_000, 20_000),
        (20_001, 20_001),
        (40_000, 30_000),
        (40_001, 30_001),
        (80_000, 40_000),
        (80_001, 40_000),
    ],
)
def test_standard_new_contract_schedule_is_unchanged(premium: int, expected: int) -> None:
    assert calc_life_insurance_deduction(premium) == expected


@pytest.mark.parametrize(
    ("premium", "expected"),
    [
        (30_000, 30_000),
        (30_001, 30_001),
        (60_000, 45_000),
        (60_001, 45_001),
        (120_000, 60_000),
        (120_001, 60_000),
    ],
)
def test_2026_special_new_general_schedule_boundaries(premium: int, expected: int) -> None:
    item = _life_item(
        fiscal_year=2026,
        general_new=premium,
        dependents=[_dependent()],
    )

    assert item.amount == expected
    assert item.details is not None
    assert "23歳未満扶養親族特例適用" in item.details


@pytest.mark.parametrize(
    ("fiscal_year", "dependents", "expected"),
    [
        (2025, [_dependent(birth_date="2004-01-02")], 40_000),
        (2026, [], 40_000),
        (2027, [_dependent(birth_date="2005-01-02")], 60_000),
    ],
)
def test_special_depends_on_supported_year_and_eligible_relative(
    fiscal_year: int,
    dependents: list[DependentInfo],
    expected: int,
) -> None:
    item = _life_item(
        fiscal_year=fiscal_year,
        general_new=120_000,
        dependents=dependents,
    )

    assert item.amount == expected


@pytest.mark.parametrize(
    ("dependent", "expected_life", "expected_relative_type", "expected_relative_amount"),
    [
        (_dependent(birth_date="2004-01-02"), 60_000, "dependent", 630_000),
        (_dependent(birth_date="2004-01-01"), 40_000, "dependent", 380_000),
        (_dependent(birth_date="2006-06-01", income=620_000), 60_000, "dependent", 630_000),
        (
            _dependent(birth_date="2006-06-01", income=620_001),
            40_000,
            "specific_relative_special",
            630_000,
        ),
        (_dependent(birth_date="2020-05-01"), 60_000, None, 0),
        (
            _dependent(birth_date="2004-01-02", other_taxpayer_dependent=True),
            60_000,
            None,
            0,
        ),
        (_dependent(birth_date="2004-01-02", relationship="配偶者"), 40_000, None, 0),
    ],
)
def test_special_relative_boundaries(
    dependent: DependentInfo,
    expected_life: int,
    expected_relative_type: str | None,
    expected_relative_amount: int,
) -> None:
    result = calc_deductions(
        total_income=3_000_000,
        fiscal_year=2026,
        life_insurance_detail=LifeInsurancePremiumInput(general_new=120_000),
        dependents=[dependent],
    )

    life_item = next(item for item in result.income_deductions if item.type == "life_insurance")
    relative_items = [
        item
        for item in result.income_deductions
        if item.type in {"dependent", "specific_relative_special"}
    ]
    assert life_item.amount == expected_life
    if expected_relative_type is None:
        assert relative_items == []
    else:
        assert [(item.type, item.amount) for item in relative_items] == [
            (expected_relative_type, expected_relative_amount)
        ]


def test_future_birth_date_is_rejected() -> None:
    with pytest.raises(ValueError, match="課税年分より後"):
        calc_deductions(
            total_income=3_000_000,
            fiscal_year=2026,
            life_insurance_detail=LifeInsurancePremiumInput(general_new=120_000),
            dependents=[_dependent(birth_date="2027-01-02")],
        )


@pytest.mark.parametrize(
    ("fiscal_year", "dependents", "general_new", "general_old", "expected"),
    [
        (2026, [_dependent()], 120_000, 100_000, 60_000),
        (2026, [_dependent()], 60_000, 40_000, 60_000),
        (2025, [_dependent()], 60_000, 40_000, 40_000),
        (2026, [], 120_000, 100_000, 50_000),
    ],
)
def test_general_new_old_combination_uses_year_specific_limit(
    fiscal_year: int,
    dependents: list[DependentInfo],
    general_new: int,
    general_old: int,
    expected: int,
) -> None:
    item = _life_item(
        fiscal_year=fiscal_year,
        general_new=general_new,
        general_old=general_old,
        dependents=dependents,
    )

    assert item.amount == expected


def test_special_changes_only_general_category_and_keeps_total_limit() -> None:
    item = _life_item(
        fiscal_year=2026,
        general_new=120_000,
        medical_care=80_000,
        annuity_new=80_000,
        dependents=[_dependent()],
    )

    assert item.amount == 120_000


def test_compatibility_input_uses_same_special_schedule_as_detail_input() -> None:
    kwargs = {
        "total_income": 3_000_000,
        "fiscal_year": 2026,
        "dependents": [_dependent()],
    }
    compatibility = calc_deductions(life_insurance_premium=120_000, **kwargs)
    detail = calc_deductions(
        life_insurance_detail=LifeInsurancePremiumInput(general_new=120_000),
        **kwargs,
    )
    compatibility_item = next(
        item for item in compatibility.income_deductions if item.type == "life_insurance"
    )
    detail_item = next(item for item in detail.income_deductions if item.type == "life_insurance")

    assert compatibility_item.amount == detail_item.amount == 60_000
    assert compatibility_item.details == "23歳未満扶養親族特例適用"


def test_calc_income_keeps_special_application_detail_after_candidate_selection() -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=2026,
            business_revenue=3_000_000,
            blue_return_deduction=0,
            life_insurance_detail=LifeInsurancePremiumInput(general_new=120_000),
            dependents=[_dependent()],
        )
    )
    item = next(
        item for item in result.deductions_detail.income_deductions if item.type == "life_insurance"
    )

    assert item.amount == 60_000
    assert item.details is not None
    assert "23歳未満扶養親族特例適用" in item.details


def test_unsupported_2028_still_raises() -> None:
    with pytest.raises(ValueError, match="fiscal_year=2028 は未対応"):
        _life_item(
            fiscal_year=2028,
            general_new=120_000,
            dependents=[_dependent(birth_date="2006-01-02")],
        )
