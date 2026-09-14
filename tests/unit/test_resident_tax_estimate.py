"""自治体の控除表と税源移譲時の人的控除差、既存上限計算への接続を検証する。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shinkoku.models import ResidentLifeInsuranceInput, ResidentTaxEstimateInput
from shinkoku.tools.resident_tax import calc_resident_life_insurance, calc_resident_tax_estimate
from shinkoku.tools.tax_reform import calc_furusato_limit_detailed


def _input(**changes: object) -> ResidentTaxEstimateInput:
    return ResidentTaxEstimateInput.model_validate(
        dict(
            fiscal_year=2025,
            income_scope="comprehensive_only",
            income_levy_taxable=True,
            aggregate_income=3_560_000,
            total_income=3_560_000,
            social_insurance=750_000,
        )
        | changes
    )


def _relative(**changes: object) -> dict:
    return dict(name="子", birth_date="2005-06-01", income=0, eligible=True) | changes


def test_baseline_matches_resident_levy_calculation_and_reuses_furusato_function() -> None:
    result = calc_resident_tax_estimate(_input())
    assert result.resident_tax_assessment_year == 2026
    assert result.resident_tax_deductions_total == 1_180_000
    assert result.resident_taxable_income == 2_380_000
    assert result.adjustment_credit == 2_500
    assert result.resident_tax_income_levy == 235_500
    assert result.personal_deduction_difference == 50_000
    assert result.furusato_input.income_tax_basic_deduction == 680_000
    assert result.furusato_limit == calc_furusato_limit_detailed(result.furusato_input)


def test_specific_relative_personal_difference_is_not_actual_deduction_difference() -> None:
    result = calc_resident_tax_estimate(_input(dependents=[_relative(income=800_000)]))
    item = next(d for d in result.deductions if d.type == "specific_relative_special")
    assert item.amount == 450_000
    assert item.personal_difference == 0
    assert result.personal_deduction_difference == 50_000


@pytest.mark.parametrize("spouse_income", [600_000, 950_000, 980_000, 1_000_000])
def test_spouse_special_personal_difference_is_zero(spouse_income: int) -> None:
    result = calc_resident_tax_estimate(
        _input(spouse=_relative(name="配偶者", income=spouse_income))
    )
    item = next(d for d in result.deductions if d.type == "spouse_special")
    assert item.amount == 330_000
    assert item.personal_difference == 0


@pytest.mark.parametrize(
    "birth,amount,difference",
    [
        ("2007-01-01", 450_000, 180_000),
        ("2007-01-02", 330_000, 50_000),
        ("2003-01-01", 330_000, 50_000),
        ("2003-01-02", 450_000, 180_000),
    ],
)
def test_january_first_age_boundaries(birth: str, amount: int, difference: int) -> None:
    result = calc_resident_tax_estimate(_input(dependents=[_relative(birth_date=birth)]))
    item = next(d for d in result.deductions if d.type == "dependent")
    assert (item.amount, item.personal_difference) == (amount, difference)


@pytest.mark.parametrize("year,amount", [(2025, 0), (2026, 330_000), (2027, 330_000)])
def test_year_specific_dependent_income_limit(year: int, amount: int) -> None:
    result = calc_resident_tax_estimate(
        _input(fiscal_year=year, dependents=[_relative(birth_date="1990-01-01", income=620_000)])
    )
    assert sum(d.amount for d in result.deductions if d.type == "dependent") == amount


@pytest.mark.parametrize("income,index", [(9_000_000, 0), (9_000_001, 1), (9_500_001, 2)])
def test_elderly_spouse_has_own_amount_and_difference(income: int, index: int) -> None:
    result = calc_resident_tax_estimate(
        _input(
            aggregate_income=income,
            total_income=income,
            spouse=_relative(name="配偶者", birth_date="1956-01-01"),
        )
    )
    item = next(d for d in result.deductions if d.type == "spouse")
    assert item.amount == (380_000, 260_000, 130_000)[index]
    assert item.personal_difference == (100_000, 60_000, 30_000)[index]


def test_loss_carryforward_does_not_restore_spouse_eligibility() -> None:
    result = calc_resident_tax_estimate(
        _input(aggregate_income=11_000_000, total_income=4_000_000, spouse=_relative(name="配偶者"))
    )
    assert not any(d.type == "spouse" for d in result.deductions)
    assert result.furusato_input.income_tax_basic_deduction == 580_000


@pytest.mark.parametrize("lineal,amount", [(True, 450_000), (False, 380_000)])
def test_cohabiting_elderly_requires_lineal_relationship(lineal: bool, amount: int) -> None:
    result = calc_resident_tax_estimate(
        _input(
            dependents=[
                _relative(birth_date="1950-04-01", cohabiting=True, is_lineal_ascendant=lineal)
            ]
        )
    )
    assert next(d.amount for d in result.deductions if d.type == "dependent") == amount


def test_spouse_disability_not_limited_by_taxpayer_spouse_deduction_income_cap() -> None:
    result = calc_resident_tax_estimate(
        _input(
            aggregate_income=11_000_000,
            total_income=11_000_000,
            spouse=_relative(name="配偶者", disability="special_cohabiting", cohabiting=True),
        )
    )
    assert not any(d.type == "spouse" for d in result.deductions)
    assert next(d.amount for d in result.deductions if d.type == "relative_disability") == 530_000


def test_special_relative_above_income_limit_does_not_get_disability_deduction() -> None:
    result = calc_resident_tax_estimate(
        _input(dependents=[_relative(income=800_000, disability="special")])
    )
    assert not any(d.type == "relative_disability" for d in result.deductions)


@pytest.mark.parametrize("change", [{"eligible": False}, {"other_taxpayer_dependent": True}])
def test_ineligible_relatives_are_excluded(change: dict) -> None:
    result = calc_resident_tax_estimate(
        _input(dependents=[_relative(disability="special", **change)])
    )
    assert not any(d.type in ("dependent", "relative_disability") for d in result.deductions)


@pytest.mark.parametrize("year,amount", [(2025, 300_000), (2026, 300_000), (2027, 330_000)])
@pytest.mark.parametrize(
    "status,diff", [("single_parent_mother", 50_000), ("single_parent_father", 10_000)]
)
def test_single_parent_year_and_historical_difference(
    year: int, amount: int, status: str, diff: int
) -> None:
    result = calc_resident_tax_estimate(_input(fiscal_year=year, widow_status=status))
    item = next(d for d in result.deductions if d.type == "single_parent")
    assert (item.amount, item.personal_difference) == (amount, diff)


@pytest.mark.parametrize(
    "premium,expected",
    [(12_000, 12_000), (12_001, 12_001), (32_001, 22_001), (56_000, 28_000), (100_000, 28_000)],
)
def test_resident_life_insurance_ceil_and_limits(premium: int, expected: int) -> None:
    assert calc_resident_life_insurance(ResidentLifeInsuranceInput(general_new=premium)) == expected


def test_life_insurance_old_only_choice_and_total_cap() -> None:
    assert (
        calc_resident_life_insurance(
            ResidentLifeInsuranceInput(general_new=100, general_old=100_000)
        )
        == 35_000
    )
    assert (
        calc_resident_life_insurance(
            ResidentLifeInsuranceInput(
                general_new=150_000, general_old=100_000, medical_care=100_000, annuity_old=100_000
            )
        )
        == 70_000
    )


@pytest.mark.parametrize("same,expected", [(True, 20_000), (False, 25_000)])
def test_earthquake_contract_selection(same: bool, expected: int) -> None:
    result = calc_resident_tax_estimate(
        _input(
            earthquake_premium=40_000, old_long_term_premium=20_000, same_earthquake_contract=same
        )
    )
    assert next(d.amount for d in result.deductions if d.type == "earthquake_insurance") == expected


def test_medical_threshold_uses_income_after_carryforward() -> None:
    result = calc_resident_tax_estimate(
        _input(total_income=1_000_000, medical_method="medical", medical_expenses_net=100_000)
    )
    assert next(d.amount for d in result.deductions if d.type == "medical") == 50_000


def test_self_medication_and_working_student() -> None:
    result = calc_resident_tax_estimate(
        _input(
            aggregate_income=880_000,
            total_income=880_000,
            fiscal_year=2027,
            medical_method="self_medication",
            self_medication_expenses_net=100_000,
            self_medication_eligible=True,
            working_student=True,
            working_student_nonwork_income=0,
        )
    )
    assert next(d.amount for d in result.deductions if d.type == "self_medication") == 88_000
    assert next(d.amount for d in result.deductions if d.type == "working_student") == 260_000


def test_adjustment_for_low_taxable_income_and_high_aggregate_income() -> None:
    low = calc_resident_tax_estimate(
        _input(aggregate_income=440_000, total_income=440_000, social_insurance=0)
    )
    assert low.adjustment_credit == 500
    assert low.resident_tax_income_levy == 500
    high = calc_resident_tax_estimate(
        _input(aggregate_income=26_000_000, total_income=1_000_000, social_insurance=0)
    )
    assert high.adjustment_credit == 0
    assert high.furusato_input.personal_deduction_difference == 50_000
    assert high.furusato_limit.rate_adjustment == 50_000  # 基礎控除0でも負の調整にしない


def test_confirmed_non_taxable_status_has_no_levy_or_donation_limit() -> None:
    result = calc_resident_tax_estimate(_input(income_levy_taxable=False))
    assert (
        result.adjustment_credit
        == result.resident_tax_income_levy
        == result.furusato_limit.estimated_limit
        == 0
    )


def test_high_income_cap_and_rate_precision_are_preserved() -> None:
    result = calc_resident_tax_estimate(
        _input(
            fiscal_year=2027,
            aggregate_income=100_000_000,
            total_income=100_000_000,
            social_insurance=0,
        )
    )
    assert result.furusato_limit.special_credit_limit == 1_930_000
    assert result.furusato_limit.estimated_limit == 4_382_887
    assert result.furusato_limit.resident_tax_assessment_year == 2028


@pytest.mark.parametrize("year", [2024, 2028, 2030])
def test_unsupported_year_stays_closed(year: int) -> None:
    with pytest.raises(ValueError, match="未対応"):
        calc_resident_tax_estimate(_input(fiscal_year=year))


@pytest.mark.parametrize(
    "change",
    [
        {"total_income": 5_000_000},
        {"total_income": 1.5},
        {"total_income": "100"},
        {"income_scope": "separate"},
        {"income_levy_taxable": None},
        {"earthquake_premium": 100, "old_long_term_premium": 100},
        {"medical_method": "self_medication"},
        {"medical_expenses_net": 100},
        {"working_student": True},
        {"spouse": _relative(), "widow_status": "widow"},
    ],
)
def test_missing_conflicting_or_coerced_inputs_fail(change: dict) -> None:
    with pytest.raises(ValidationError):
        _input(**change)


def test_duplicate_or_future_relatives_fail() -> None:
    with pytest.raises(ValueError, match="重複"):
        calc_resident_tax_estimate(_input(spouse=_relative(), dependents=[_relative()]))
    with pytest.raises(ValueError, match="後の日付"):
        calc_resident_tax_estimate(_input(dependents=[_relative(birth_date="2026-01-01")]))
