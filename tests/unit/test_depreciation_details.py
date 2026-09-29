"""共通の内訳と、国税庁No.2106に基づく年次の終端を検証する。"""

from __future__ import annotations

from datetime import date

import pytest

from shinkoku.models import (
    DepreciationCalculationInput,
    DepreciationDetailResult,
    SmallAssetTreatmentInput,
)
from shinkoku.tools.depreciation import depreciation_details_from_input, depreciation_months
from shinkoku.tools.tax_calc import select_small_asset_treatment_details
from tests.helpers.depreciation import annual_context, depreciation_input


def _annual(context: dict | None = None, **values: object) -> DepreciationDetailResult:
    return depreciation_details_from_input(
        DepreciationCalculationInput(
            **depreciation_input(
                annual_context=annual_context() if context is None else context,
                **values,
            )
        )
    )


@pytest.mark.parametrize(
    "year,service,months",
    [
        (2026, "2025-12-31", 12),
        (2026, "2026-01-01", 12),
        (2026, "2026-01-31", 12),
        (2026, "2026-02-28", 11),
        (2024, "2024-02-29", 11),
        (2026, "2026-04-30", 9),
        (2026, "2026-12-01", 1),
        (2026, "2026-12-31", 1),
        (2026, "2027-01-01", 0),
    ],
)
def test_calendar_months_include_the_service_month(year: int, service: str, months: int) -> None:
    assert depreciation_months(year, date.fromisoformat(service)) == months
    assert depreciation_months(year, date.fromisoformat(service), months) == months
    with pytest.raises(ValueError, match="一致しません"):
        depreciation_months(year, date.fromisoformat(service), months + 1)


def test_straight_line_keeps_two_separate_roundings_without_an_annual_balance() -> None:
    detail = depreciation_details_from_input(
        DepreciationCalculationInput(
            **depreciation_input(
                acquisition_cost=100020,
                business_use_ratio=40,
                months=6,
            )
        )
    )
    assert detail.ordinary_amount == 12503
    assert detail.expense_amount == 5002
    assert (detail.rate_numerator, detail.rate_denominator) == (250, 1000)
    assert detail.depreciation_basis == 100020
    assert detail.closing_book_value is None and detail.opening_book_value is None
    assert detail.memo_value is None and not detail.memo_value_constraint_applied


def test_declining_balance_preserves_the_single_truncation() -> None:
    detail = depreciation_details_from_input(
        DepreciationCalculationInput(
            **depreciation_input(
                method="declining_balance",
                book_value=100002,
                declining_rate=167,
                business_use_ratio=67,
                months=7,
            )
        )
    )
    # 100002*167*7//12000=9741。従来は割合を含めて一度だけ切り捨てるため6527となる。
    assert detail.ordinary_amount == 9741
    assert detail.expense_amount == 6527
    assert detail.expense_amount != detail.ordinary_amount * 67 // 100
    assert detail.depreciation_basis == 100002
    assert (detail.rate_numerator, detail.rate_denominator) == (167, 1000)
    assert detail.closing_book_value is None


def test_nta_2106_last_year_example_and_following_year() -> None:
    # 国税庁No.2106「具体例」: 取得100万円・10年、最終年は100000円ではなく99999円。
    context = annual_context(
        fiscal_year=2025,
        acquisition_date="2016-01-01",
        placed_in_service_date="2016-01-01",
        opening_accumulated_depreciation=900000,
    )
    detail = _annual(context, acquisition_cost=1000000, useful_life=10)
    assert detail.unconstrained_ordinary_amount == 100000
    assert detail.ordinary_amount == detail.expense_amount == 99999
    assert detail.opening_book_value == 100000
    assert detail.closing_book_value == detail.memo_value == 1
    assert detail.memo_value_constraint_applied and detail.capped_to_book_value
    after = _annual(
        {**context, "fiscal_year": 2026, "opening_accumulated_depreciation": 999999},
        acquisition_cost=1000000,
        useful_life=10,
    )
    assert after.ordinary_amount == after.expense_amount == 0
    assert after.closing_book_value == 1


def test_fictional_pc_lifetime_has_no_overdepreciation() -> None:
    # 初年は凍結シナリオの手計算。翌年以後は同じ取得価額・率と残存1円から独立に計算した値。
    expected = [
        (2026, 9, 46875, 203125),
        (2027, 12, 62500, 140625),
        (2028, 12, 62500, 78125),
        (2029, 12, 62500, 15625),
        (2030, 12, 15624, 1),
        (2031, 12, 0, 1),
    ]
    accumulated = 0
    for year, months, amount, closing in expected:
        detail = _annual(
            annual_context(fiscal_year=year, opening_accumulated_depreciation=accumulated)
        )
        assert (detail.months, detail.expense_amount, detail.closing_book_value) == (
            months,
            amount,
            closing,
        )
        accumulated += detail.ordinary_amount
    assert accumulated == 249999


def test_service_next_year_is_zero_without_calling_a_legacy_month_zero_input() -> None:
    detail = _annual(annual_context(placed_in_service_date="2027-01-01"), months=0)
    assert detail.months == detail.expense_amount == detail.ordinary_amount == 0
    assert detail.closing_book_value == 250000
    assert detail.memo_value_constraint_applied and not detail.capped_to_book_value
    with pytest.raises(ValueError):
        DepreciationCalculationInput(**depreciation_input(months=0))


def test_explicit_months_are_not_replaced_by_auto_months() -> None:
    assert _annual().months == _annual(months=9).months == 9
    with pytest.raises(ValueError, match="一致しません"):
        _annual(months=12)


@pytest.mark.parametrize(
    "changes",
    [
        {"opening_accumulated_depreciation": 250000},
        {"opening_accumulated_depreciation": -1},
        {"opening_accumulated_depreciation": 1},
        {"opening_accumulated_depreciation": None},
        {"opening_accumulated_depreciation": True},
        {"fiscal_year": 2025},
        {"fiscal_year": True},
        {"placed_in_service_date": "2026-02-30"},
        {"placed_in_service_date": "2026-03-31"},
        {"acquisition_date": "2007-03-31", "placed_in_service_date": "2007-03-31"},
        {"asset_class": "intangible"},
        {"book_basis": "indirect"},
        {"prior_private_use": True},
        {"additional_depreciation_applicable": True},
        {"annual_facts_confirmed": False},
        {"basis_confirmed": None},
        {"annual_facts_confirmed": 1},
    ],
)
def test_unconfirmed_inconsistent_and_unsupported_context_is_rejected(changes: dict) -> None:
    with pytest.raises(ValueError):
        _annual(annual_context(**changes))


@pytest.mark.parametrize(
    "root",
    [
        {"business_use_ratio": 60},
        {"business_use_ratio": 0},
        {"acquisition_cost": "250000"},
        {"acquisition_cost": True},
        {"months": "9"},
        {"method": "declining_balance", "book_value": 250000, "declining_rate": 500},
    ],
)
def test_annual_scope_does_not_silently_use_unsupported_input(root: dict) -> None:
    with pytest.raises(ValueError):
        _annual(**root)


def test_first_supported_acquisition_date_and_one_yen_asset() -> None:
    detail = _annual(
        annual_context(
            fiscal_year=2007, acquisition_date="2007-04-01", placed_in_service_date="2007-04-01"
        )
    )
    assert detail.expense_amount == 46875
    tiny = _annual(acquisition_cost=1)
    assert tiny.expense_amount == 0 and tiny.closing_book_value == 1


def test_small_asset_selection_and_detail_are_separate() -> None:
    data = SmallAssetTreatmentInput(
        acquisition_date=date(2026, 4, 1),
        placed_in_service_date=date(2026, 4, 1),
        acquisition_cost=150001,
        useful_life=4,
        is_lending_use=False,
        is_main_business_lending=False,
        special_cap_used=0,
    )
    result = select_small_asset_treatment_details(data)
    assert result.selection.status == "indeterminate"  # 青色等の要件は未確認のまま。
    assert set(result.calculations) == {"normal_depreciation", "pooled_depreciation"}
    pooled = result.calculations["pooled_depreciation"]
    assert pooled.expense_amount == 50001
    assert (pooled.rate_numerator, pooled.rate_denominator) == (1, 3)
    assert not pooled.monthly_proration_applied
    assert pooled.closing_book_value is None
