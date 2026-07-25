"""令和8年入居の住宅ローン控除ルールと適用期間のテスト。"""

from __future__ import annotations

import pytest

from shinkoku.models import DependentInfo, HousingLoanDetail, IncomeTaxInput
from shinkoku.tools.tax_calc import (
    calc_deductions,
    calc_housing_loan_credit,
    calc_income_tax,
    resolve_housing_loan_rule,
)


def _detail(
    *,
    housing_type: str = "new_custom",
    housing_category: str = "certified",
    year_end_balance: int = 60_000_000,
    move_in_date: str = "2026-04-01",
    is_special_target_individual: bool | None = False,
    is_childcare_household: bool | None = None,
    is_new_construction: bool | None = None,
    has_pre_r6_building_permit: bool = False,
) -> HousingLoanDetail:
    return HousingLoanDetail(
        housing_type=housing_type,
        housing_category=housing_category,
        move_in_date=move_in_date,
        year_end_balance=year_end_balance,
        is_new_construction=is_new_construction,
        is_special_target_individual=is_special_target_individual,
        is_childcare_household=is_childcare_household,
        has_pre_r6_building_permit=has_pre_r6_building_permit,
    )


@pytest.mark.parametrize(
    ("housing_type", "category", "special", "limit", "period"),
    [
        ("new_custom", "certified", False, 45_000_000, 13),
        ("new_custom", "certified", True, 50_000_000, 13),
        ("new_subdivision", "zeh", False, 35_000_000, 13),
        ("new_subdivision", "zeh", True, 45_000_000, 13),
        ("new_custom", "energy_efficient", False, 20_000_000, 13),
        ("new_custom", "energy_efficient", True, 30_000_000, 13),
        ("broker_renovated_resale", "certified", False, 45_000_000, 13),
        ("broker_renovated_resale", "certified", True, 50_000_000, 13),
        ("broker_renovated_resale", "zeh", False, 35_000_000, 13),
        ("broker_renovated_resale", "zeh", True, 45_000_000, 13),
        ("broker_renovated_resale", "energy_efficient", False, 20_000_000, 13),
        ("broker_renovated_resale", "energy_efficient", True, 30_000_000, 13),
        ("broker_renovated_resale", "general", False, 20_000_000, 10),
        ("broker_renovated_resale", "general", True, 20_000_000, 10),
        ("used", "certified", False, 35_000_000, 13),
        ("used", "certified", True, 45_000_000, 13),
        ("used", "zeh", False, 35_000_000, 13),
        ("used", "zeh", True, 45_000_000, 13),
        ("used", "energy_efficient", False, 20_000_000, 13),
        ("used", "energy_efficient", True, 30_000_000, 13),
        ("used", "general", False, 20_000_000, 10),
        ("used", "general", True, 20_000_000, 10),
        ("renovation", "general", False, 20_000_000, 10),
        ("renovation", "certified", True, 20_000_000, 10),
    ],
)
def test_2026_rule_table(
    housing_type: str,
    category: str,
    special: bool,
    limit: int,
    period: int,
) -> None:
    detail = _detail(
        housing_type=housing_type,
        housing_category=category,
        is_special_target_individual=special,
    )

    rule = resolve_housing_loan_rule(detail)

    assert rule.balance_limit == limit
    assert rule.credit_period == period
    assert rule.rate_numerator == 7
    assert rule.rate_denominator == 1000


@pytest.mark.parametrize(
    ("balance", "expected"),
    [
        (20_000_000, 140_000),
        (20_000_001, 140_000),
        (19_999_999, 139_900),
        (12_345_678, 86_400),
        (0, 0),
    ],
)
def test_2026_rounding_boundaries(balance: int, expected: int) -> None:
    detail = _detail(
        housing_category="energy_efficient",
        year_end_balance=balance,
    )

    assert calc_housing_loan_credit(balance, detail, claim_fiscal_year=2026) == expected


def test_general_new_transition_with_building_permit() -> None:
    detail = _detail(
        housing_category="general",
        has_pre_r6_building_permit=True,
        is_special_target_individual=True,
    )

    rule = resolve_housing_loan_rule(detail)

    assert rule.balance_limit == 20_000_000
    assert rule.credit_period == 10
    assert rule.warning is None


def test_general_new_without_building_permit_returns_zero_with_warning() -> None:
    detail = _detail(housing_category="general")

    result = calc_deductions(
        total_income=5_000_000,
        fiscal_year=2026,
        housing_loan_detail=detail,
    )

    assert not [item for item in result.tax_credits if item.type == "housing_loan"]
    assert result.housing_loan_credit_entries[0].status == "ineligible"
    assert result.housing_loan_credit_entries[0].credit == 0
    assert any("令和6年6月30日までに建築" in warning for warning in result.warnings)


@pytest.mark.parametrize("move_in_year", [2027, 2030])
def test_future_move_in_year_fails_closed_even_with_zero_balance(move_in_year: int) -> None:
    detail = _detail(
        move_in_date=f"{move_in_year}-01-01",
        year_end_balance=0,
    )

    with pytest.raises(ValueError, match="実装範囲外"):
        calc_housing_loan_credit(0, detail, claim_fiscal_year=move_in_year)


@pytest.mark.parametrize("move_in_year", [2019, 2021])
def test_unsupported_past_move_in_year_is_error(move_in_year: int) -> None:
    detail = _detail(move_in_date=f"{move_in_year}-04-01")

    with pytest.raises(ValueError, match="実装範囲外"):
        calc_housing_loan_credit(
            detail.year_end_balance,
            detail,
            claim_fiscal_year=move_in_year,
        )


def test_legacy_resale_is_rejected() -> None:
    detail = _detail(housing_type="resale", is_new_construction=False)

    with pytest.raises(ValueError, match="used.*broker_renovated_resale"):
        resolve_housing_loan_rule(detail)


@pytest.mark.parametrize(
    ("housing_type", "is_new_construction"),
    [("new_custom", False), ("used", True), ("broker_renovated_resale", True)],
)
def test_housing_type_and_legacy_boolean_conflict(
    housing_type: str, is_new_construction: bool
) -> None:
    detail = _detail(
        housing_type=housing_type,
        is_new_construction=is_new_construction,
    )

    with pytest.raises(ValueError, match="is_new_construction"):
        resolve_housing_loan_rule(detail)


@pytest.mark.parametrize(
    ("claim_year", "expected_year_number"),
    [(2026, 1), (2027, 2)],
)
def test_13_year_rule_accepts_valid_claim_years(claim_year: int, expected_year_number: int) -> None:
    detail = _detail()

    result = calc_deductions(
        total_income=5_000_000,
        fiscal_year=claim_year,
        housing_loan_detail=detail,
    )

    entry = result.housing_loan_credit_entries[0]
    assert entry.claim_year_number == expected_year_number
    assert entry.credit_period == 13
    assert entry.status == "active"


def test_13_year_rule_accepts_year_13_in_direct_calculation() -> None:
    detail = _detail()

    assert calc_housing_loan_credit(60_000_000, detail, claim_fiscal_year=2038) == 315_000


@pytest.mark.parametrize("claim_year", [0, 2025, 2039])
def test_13_year_rule_rejects_invalid_claim_year(claim_year: int) -> None:
    detail = _detail()

    with pytest.raises(ValueError, match="入居前|控除期間"):
        calc_housing_loan_credit(60_000_000, detail, claim_fiscal_year=claim_year)


@pytest.mark.parametrize(
    ("claim_year", "expected_year_number"),
    [(2026, 1)],
)
def test_10_year_rule_accepts_valid_claim_years(claim_year: int, expected_year_number: int) -> None:
    detail = _detail(housing_type="renovation", housing_category="general")

    result = calc_deductions(
        total_income=5_000_000,
        fiscal_year=claim_year,
        housing_loan_detail=detail,
    )

    assert result.housing_loan_credit_entries[0].claim_year_number == expected_year_number


def test_10_year_rule_accepts_year_10_in_direct_calculation() -> None:
    detail = _detail(housing_type="renovation", housing_category="general")

    assert calc_housing_loan_credit(60_000_000, detail, claim_fiscal_year=2035) == 140_000


def test_10_year_rule_rejects_year_11() -> None:
    detail = _detail(housing_type="renovation", housing_category="general")

    with pytest.raises(ValueError, match="控除期間"):
        calc_housing_loan_credit(60_000_000, detail, claim_fiscal_year=2036)


def test_2024_and_2025_rules_keep_existing_limits() -> None:
    detail_2024 = _detail(
        move_in_date="2024-04-01",
        housing_category="energy_efficient",
    )
    detail_2025 = detail_2024.model_copy(update={"move_in_date": "2025-04-01"})

    assert resolve_housing_loan_rule(detail_2024).balance_limit == 30_000_000
    assert resolve_housing_loan_rule(detail_2025).balance_limit == 30_000_000


def test_2023_rule_ignores_later_transition_flag() -> None:
    detail = _detail(
        move_in_date="2023-04-01",
        housing_category="general",
        has_pre_r6_building_permit=True,
    )

    assert resolve_housing_loan_rule(detail).balance_limit == 30_000_000


def test_special_target_taxpayer_under_40_with_spouse() -> None:
    detail = _detail(is_special_target_individual=None)

    rule = resolve_housing_loan_rule(
        detail,
        taxpayer_birth_date="1987-07-01",
        spouse_birth_date="1987-08-01",
        spouse_income=0,
    )

    assert rule.balance_limit == 50_000_000


def test_special_target_spouse_under_40() -> None:
    detail = _detail(is_special_target_individual=None)

    rule = resolve_housing_loan_rule(
        detail,
        taxpayer_birth_date="1986-07-01",
        spouse_birth_date="1987-07-01",
        spouse_income=0,
    )

    assert rule.balance_limit == 50_000_000


def test_both_spouses_40_or_older_are_not_special() -> None:
    detail = _detail(is_special_target_individual=None)

    rule = resolve_housing_loan_rule(
        detail,
        taxpayer_birth_date="1986-01-01",
        spouse_birth_date="1986-01-01",
        spouse_income=0,
    )

    assert rule.balance_limit == 45_000_000


@pytest.mark.parametrize(
    ("birth_date", "expected_limit"),
    [("2008-01-01", 45_000_000), ("2008-01-02", 50_000_000)],
)
def test_under_19_dependent_uses_move_in_year_boundary(
    birth_date: str, expected_limit: int
) -> None:
    detail = _detail(is_special_target_individual=None)
    dependent = DependentInfo(
        name="子",
        relationship="子",
        birth_date=birth_date,
        income=0,
        other_taxpayer_dependent=True,
    )

    rule = resolve_housing_loan_rule(detail, dependents=[dependent])

    assert rule.balance_limit == expected_limit


def test_spouse_in_dependents_is_not_under_19_dependent() -> None:
    detail = _detail(is_special_target_individual=None)
    spouse = DependentInfo(
        name="配偶者",
        relationship="配偶者",
        birth_date="2008-01-02",
        income=0,
    )

    rule = resolve_housing_loan_rule(detail, dependents=[spouse])

    assert rule.balance_limit == 45_000_000


def test_under_19_dependent_resolves_missing_spouse_birth_date() -> None:
    detail = _detail(is_special_target_individual=None)
    dependent = DependentInfo(
        name="子",
        relationship="子",
        birth_date="2008-01-02",
        income=0,
    )

    rule = resolve_housing_loan_rule(
        detail,
        taxpayer_birth_date="1980-01-01",
        spouse_income=0,
        dependents=[dependent],
    )

    assert rule.balance_limit == 50_000_000


def test_missing_spouse_birth_date_without_other_condition_is_error() -> None:
    detail = _detail(is_special_target_individual=None)

    with pytest.raises(ValueError, match="判定できません"):
        resolve_housing_loan_rule(
            detail,
            taxpayer_birth_date="1980-01-01",
            spouse_income=0,
        )


def test_explicit_false_allows_missing_spouse_birth_date() -> None:
    detail = _detail(is_special_target_individual=False)

    rule = resolve_housing_loan_rule(
        detail,
        taxpayer_birth_date="1980-01-01",
        spouse_income=0,
    )

    assert rule.balance_limit == 45_000_000


def test_explicit_value_conflicting_with_derived_value_is_error() -> None:
    detail = _detail(is_special_target_individual=False)
    dependent = DependentInfo(
        name="子",
        relationship="子",
        birth_date="2008-01-02",
        income=0,
    )

    with pytest.raises(ValueError, match="導出結果"):
        resolve_housing_loan_rule(detail, dependents=[dependent])


def test_legacy_and_new_special_flags_conflict() -> None:
    detail = _detail(
        is_special_target_individual=False,
        is_childcare_household=True,
    )

    with pytest.raises(ValueError, match="矛盾"):
        resolve_housing_loan_rule(detail)


def test_legacy_special_flag_still_works_without_household_context() -> None:
    detail = _detail(
        is_special_target_individual=None,
        is_childcare_household=True,
    )

    assert resolve_housing_loan_rule(detail).balance_limit == 50_000_000


@pytest.mark.parametrize("birth_date", ["2027-01-01", "2026-99-99"])
def test_invalid_or_future_household_birth_date_is_error(birth_date: str) -> None:
    detail = _detail(is_special_target_individual=None)

    with pytest.raises(ValueError, match="生年月日"):
        resolve_housing_loan_rule(
            detail,
            taxpayer_birth_date=birth_date,
            spouse_income=0,
            spouse_birth_date="1980-01-01",
        )


def test_special_status_stays_based_on_move_in_year_for_later_claim() -> None:
    detail = _detail(is_special_target_individual=None)
    dependent = DependentInfo(
        name="子",
        relationship="子",
        birth_date="2008-01-02",
        income=0,
    )

    assert (
        calc_housing_loan_credit(
            60_000_000,
            detail,
            claim_fiscal_year=2030,
            dependents=[dependent],
        )
        == 350_000
    )


def test_income_tax_result_contains_housing_entry_and_warning() -> None:
    detail = _detail(
        housing_category="general",
        is_special_target_individual=False,
    )
    input_data = IncomeTaxInput(
        fiscal_year=2026,
        business_revenue=5_000_000,
        blue_return_deduction=0,
        taxpayer_birth_date="1980-01-01",
        housing_loan_detail=detail,
    )

    result = calc_income_tax(input_data)

    assert result.housing_loan_credit_entries[0].status == "ineligible"
    assert any("令和6年6月30日までに建築" in warning for warning in result.warnings)


def test_legacy_balance_only_path_is_not_silent() -> None:
    result = calc_deductions(
        total_income=5_000_000,
        fiscal_year=2026,
        housing_loan_balance=10_000_000,
    )

    credit = next(item for item in result.tax_credits if item.type == "housing_loan")
    assert credit.amount == 70_000
    assert any("住宅ローン詳細" in warning and "非推奨" in warning for warning in result.warnings)
