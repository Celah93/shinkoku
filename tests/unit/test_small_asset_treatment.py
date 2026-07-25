"""少額減価償却資産の処理選択層のテスト。"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from shinkoku.models import SmallAssetTreatmentInput
from shinkoku.tax_constants import get_small_asset_special_period
from shinkoku.tools.tax_calc import select_small_asset_treatment


def _input(**overrides: object) -> SmallAssetTreatmentInput:
    values: dict[str, object] = {
        "method": "small_asset_treatment",
        "acquisition_date": date(2026, 4, 1),
        "placed_in_service_date": date(2026, 4, 1),
        "acquisition_cost": 350_000,
        "useful_life": 4,
        "depreciation_method": "straight_line",
        "business_use_ratio": 100,
        "months": 12,
        "usable_period_under_one_year": False,
        "is_blue_return": True,
        "employee_count_at_acquisition": 400,
        "employee_count_at_placed_in_service": 400,
        "is_lending_use": False,
        "is_main_business_lending": False,
        "special_cap_used": 0,
    }
    values.update(overrides)
    return SmallAssetTreatmentInput(**values)


def _options(input_data: SmallAssetTreatmentInput) -> dict[str, object]:
    result = select_small_asset_treatment(input_data)
    return {option.treatment: option for option in result.options}


@pytest.mark.parametrize(
    ("cost", "special", "pooled", "immediate"),
    [
        (99_999, "ineligible", "ineligible", "available"),
        (100_000, "available", "available", "ineligible"),
        (199_999, "available", "available", "ineligible"),
        (200_000, "available", "ineligible", "ineligible"),
    ],
)
def test_treatment_candidates_follow_income_tax_thresholds(
    cost: int, special: str, pooled: str, immediate: str
) -> None:
    options = _options(_input(acquisition_cost=cost))

    assert options["small_asset_special"].status == special
    assert options["pooled_depreciation"].status == pooled
    assert options["immediate_expense"].status == immediate
    assert options["normal_depreciation"].status == "available"
    if cost == 99_999:
        assert "措法28条の2第1項" in options["small_asset_special"].reason
        assert "10万円未満" in options["small_asset_special"].reason


@pytest.mark.parametrize(
    ("acquisition_date", "cost", "employee_count", "status"),
    [
        (date(2026, 3, 31), 299_999, 500, "available"),
        (date(2026, 3, 31), 300_000, 500, "ineligible"),
        (date(2026, 3, 31), 350_000, 500, "ineligible"),
        (date(2026, 4, 1), 350_000, 400, "available"),
        (date(2026, 4, 1), 399_999, 400, "available"),
        (date(2026, 4, 1), 400_000, 400, "ineligible"),
    ],
)
def test_special_threshold_is_resolved_by_acquisition_date(
    acquisition_date: date, cost: int, employee_count: int, status: str
) -> None:
    options = _options(
        _input(
            acquisition_date=acquisition_date,
            placed_in_service_date=acquisition_date,
            acquisition_cost=cost,
            employee_count_at_acquisition=employee_count,
            employee_count_at_placed_in_service=employee_count,
        )
    )

    assert options["small_asset_special"].status == status


def test_special_period_constants_have_exact_date_boundary() -> None:
    old = get_small_asset_special_period(date(2026, 3, 31))
    new = get_small_asset_special_period(date(2026, 4, 1))

    assert old is not None
    assert old.acquisition_cost_exclusive_max == 300_000
    assert old.employee_max == 500
    assert new is not None
    assert new.acquisition_cost_exclusive_max == 400_000
    assert new.employee_max == 400


@pytest.mark.parametrize(
    ("acquisition_date", "at_acquisition", "at_service", "status", "reason_fragment"),
    [
        (date(2026, 3, 31), 500, 500, "available", None),
        (date(2026, 3, 31), 501, 500, "ineligible", "取得日"),
        (date(2026, 3, 31), 500, 501, "ineligible", "供用日"),
        (date(2026, 4, 1), 400, 400, "available", None),
        (date(2026, 4, 1), 401, 400, "ineligible", "取得日"),
        (date(2026, 4, 1), None, 400, "indeterminate", "両方必要"),
    ],
)
def test_employee_count_is_checked_at_both_dates(
    acquisition_date: date,
    at_acquisition: int | None,
    at_service: int,
    status: str,
    reason_fragment: str | None,
) -> None:
    options = _options(
        _input(
            acquisition_date=acquisition_date,
            placed_in_service_date=acquisition_date,
            acquisition_cost=299_999,
            employee_count_at_acquisition=at_acquisition,
            employee_count_at_placed_in_service=at_service,
        )
    )

    special = options["small_asset_special"]
    assert special.status == status
    if reason_fragment is not None:
        assert reason_fragment in special.reason


def test_missing_employee_count_is_indeterminate_not_ineligible() -> None:
    result = select_small_asset_treatment(_input(employee_count_at_acquisition=None))
    special = next(o for o in result.options if o.treatment == "small_asset_special")

    assert result.status == "indeterminate"
    assert special.status == "indeterminate"
    assert special.eligible is None


def test_missing_blue_return_is_indeterminate() -> None:
    result = select_small_asset_treatment(_input(is_blue_return=None))
    special = next(o for o in result.options if o.treatment == "small_asset_special")

    assert result.status == "indeterminate"
    assert special.status == "indeterminate"


def test_white_return_only_excludes_small_asset_special() -> None:
    options = _options(_input(acquisition_cost=150_000, is_blue_return=False))

    assert options["immediate_expense"].status == "ineligible"
    assert options["pooled_depreciation"].status == "available"
    assert options["small_asset_special"].status == "ineligible"
    assert options["normal_depreciation"].status == "available"


def test_both_employee_counts_over_limit_keeps_year_end_safe_harbor_open() -> None:
    result = select_small_asset_treatment(
        _input(
            employee_count_at_acquisition=401,
            employee_count_at_placed_in_service=401,
        )
    )
    special = next(o for o in result.options if o.treatment == "small_asset_special")

    assert result.status == "indeterminate"
    assert special.status == "indeterminate"
    assert "年末判定" in special.reason


def test_placed_in_service_date_is_required() -> None:
    values = _input().model_dump()
    values.pop("placed_in_service_date")

    with pytest.raises(ValidationError):
        SmallAssetTreatmentInput(**values)


def test_acquisition_before_statutory_start_is_rejected_as_unsupported() -> None:
    with pytest.raises(ValueError, match="対応範囲外"):
        select_small_asset_treatment(
            _input(
                acquisition_date=date(2006, 3, 31),
                placed_in_service_date=date(2006, 3, 31),
            )
        )


def test_annual_cap_exact_and_july_first_opening_proration() -> None:
    full_year = select_small_asset_treatment(
        _input(acquisition_cost=399_999, special_cap_used=2_600_001)
    )
    opening_year = select_small_asset_treatment(
        _input(
            acquisition_cost=399_999,
            placed_in_service_date=date(2026, 7, 1),
            business_start_date=date(2026, 7, 1),
            special_cap_used=1_100_001,
        )
    )

    assert full_year.special_cap_limit == 3_000_000
    assert full_year.special_cap_remaining == 0
    assert full_year.special_cap_overage == 0
    assert opening_year.special_cap_limit == 1_500_000
    assert opening_year.special_cap_remaining == 0


def test_seventh_asset_leaves_200007_yen_cap() -> None:
    result = select_small_asset_treatment(
        _input(acquisition_cost=399_999, special_cap_used=2_399_994)
    )

    assert result.special_cap_remaining == 200_007
    assert result.special_cap_overage == 0


def test_asset_crossing_cap_is_not_automatically_prorated_or_zeroed() -> None:
    result = select_small_asset_treatment(
        _input(acquisition_cost=399_999, special_cap_used=2_799_993)
    )
    special = next(o for o in result.options if o.treatment == "small_asset_special")

    assert result.status == "requires_confirmation"
    assert result.special_cap_remaining == 200_007
    assert result.special_cap_overage == 199_992
    assert special.status == "requires_confirmation"
    assert special.current_year_expense is None


def test_pooled_depreciation_is_one_third_without_month_proration() -> None:
    options = _options(
        _input(acquisition_cost=150_000, placed_in_service_date=date(2026, 11, 1), months=2)
    )
    pooled = options["pooled_depreciation"]

    assert pooled.status == "available"
    assert pooled.current_year_expense == 50_000
    assert pooled.remaining_balance == 100_000
    assert pooled.calculation_years == 3
    assert pooled.monthly_proration_applied is False
    assert pooled.continues_after_disposal is True


def test_non_primary_lending_excludes_three_special_treatments() -> None:
    options = _options(_input(acquisition_cost=150_000, is_lending_use=True))

    assert options["immediate_expense"].status == "ineligible"
    assert options["pooled_depreciation"].status == "ineligible"
    assert options["small_asset_special"].status == "ineligible"
    assert options["normal_depreciation"].status == "available"


def test_primary_business_lending_is_not_excluded() -> None:
    options = _options(
        _input(
            acquisition_cost=150_000,
            is_lending_use=True,
            is_main_business_lending=True,
        )
    )

    assert options["pooled_depreciation"].status == "available"
    assert options["small_asset_special"].status == "available"


def test_service_after_statutory_acquisition_period_is_indeterminate_with_warning() -> None:
    result = select_small_asset_treatment(_input(placed_in_service_date=date(2029, 4, 1)))
    special = next(o for o in result.options if o.treatment == "small_asset_special")

    assert result.status == "indeterminate"
    assert special.status == "indeterminate"
    assert any("供用期限の明文が未確認" in warning for warning in result.warnings)


def test_selected_available_treatment_is_returned() -> None:
    result = select_small_asset_treatment(
        _input(acquisition_cost=150_000, selected_treatment="pooled_depreciation")
    )

    assert result.status == "selected"
    assert result.selected_treatment == "pooled_depreciation"
    assert result.selected_current_year_expense == 50_000
