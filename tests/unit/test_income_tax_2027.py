"""財務省の令和8年度改正解説102・129・149・170・208・428頁に基づく回帰。"""

from __future__ import annotations

import pytest

from shinkoku.models import DependentInfo, IncomeTaxInput, PensionDeductionInput
from shinkoku.tools.tax_calc import (
    calc_income_special_taxes,
    calc_income_tax,
    calc_pension_deduction,
    sanity_check_income_tax,
)
from tests.helpers.tax_eligibility import verified_blue_facts


@pytest.mark.parametrize(
    "base,reconstruction,defense,combined,adjustment",
    [
        (0, 0, 0, 0, 0),
        (999, 10, 9, 20, 1),
        (154500, 1699, 1545, 3244, 0),
        (1234567, 13580, 12345, 25925, 0),
    ],
)
def test_special_taxes_keep_fractions_until_aggregation(
    base: int,
    reconstruction: int,
    defense: int,
    combined: int,
    adjustment: int,
) -> None:
    result = calc_income_special_taxes(base, 2027)
    assert (
        result.reconstruction_tax,
        result.defense_tax,
        result.combined_special_tax,
        result.rounding_adjustment,
    ) == (reconstruction, defense, combined, adjustment)
    assert result.reconstruction_numerator == base * 11
    assert result.defense_numerator == base * 10
    assert result.denominator == 1000
    assert calc_income_special_taxes(base, 2026).combined_special_tax == combined


@pytest.mark.parametrize("withheld,expected", [(0, 157700), (200000, -42256)])
def test_salary_filing_and_refund(withheld: int, expected: int) -> None:
    params = IncomeTaxInput(
        fiscal_year=2027,
        salary_income=5000000,
        blue_return_deduction=0,
        calculation_mode="filing",
        withheld_tax=withheld,
    )
    result = calc_income_tax(params)
    assert (
        result.income_tax_base,
        result.reconstruction_tax,
        result.defense_tax,
        result.total_tax,
        result.tax_due,
    ) == (154500, 1699, 1545, 157744, expected)
    assert sanity_check_income_tax(params, result).passed


def test_blue_75_is_used_in_the_annual_filing_calculation() -> None:
    params = IncomeTaxInput(
        fiscal_year=2027,
        business_revenue=3000000,
        business_expenses=1000000,
        blue_return_deduction=750000,
        calculation_mode="filing",
        blue_return_eligibility=verified_blue_facts(
            qualified_electronic_books=True, electronic_books_notice_requirement_met=True
        ),
    )
    result = calc_income_tax(params)
    assert result.eligibility_checks[0].status == "eligible"
    assert (
        result.business_income,
        result.taxable_income,
        result.income_tax_base,
        result.reconstruction_tax,
        result.defense_tax,
        result.tax_due,
    ) == (1250000, 210000, 10500, 115, 105, 10700)
    assert sanity_check_income_tax(params, result).passed


@pytest.mark.parametrize("year,amount", [(2025, 350000), (2026, 350000), (2027, 380000)])
def test_single_parent_is_switched_by_year(year: int, amount: int) -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=year,
            salary_income=5000000,
            blue_return_deduction=0,
            widow_status="single_parent",
        )
    )
    assert (
        next(d.amount for d in result.deductions_detail.income_deductions if d.type == "widow")
        == amount
    )
    if year == 2027:
        assert (result.income_tax_base, result.total_tax, result.tax_due) == (
            116500,
            118946,
            118900,
        )


def test_salary_and_pension_cap_and_overlap_are_separate() -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=2027,
            salary_income=9000000,
            salary_income_adjustment_eligible=False,
            pension_income=3000000,
            pension_is_over_65=True,
            blue_return_deduction=0,
            calculation_mode="filing",
        )
    )
    assert (
        result.pension_deduction,
        result.pension_salary_cap_adjustment,
        result.salary_pension_adjustment,
        result.salary_income_after_deduction,
        result.pension_income_after_deduction,
        result.total_income,
    ) == (850000, 250000, 100000, 6950000, 2150000, 9100000)
    assert (result.income_tax_base, result.total_tax, result.tax_due) == (1314400, 1342002, 1342000)


def test_pension_overlap_uses_income_before_the_new_cap() -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=2027,
            salary_income=9000000,
            salary_income_adjustment_eligible=False,
            pension_income=1000000,
            pension_is_over_65=True,
            blue_return_deduction=0,
        )
    )
    assert result.pension_income_after_deduction == 150000
    assert result.salary_pension_adjustment == 0


@pytest.mark.parametrize(
    "eligible,business,carryforward,cap_adjustment",
    [(True, 3000000, 0, 250000), (False, 3000000, 0, 150000), (False, 4000000, 2000000, 150000)],
)
def test_pension_other_income_bracket_uses_child_adjustment_but_not_overlap_or_carryforward(
    eligible: bool,
    business: int,
    carryforward: int,
    cap_adjustment: int,
) -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=2027,
            salary_income=9000000,
            salary_income_adjustment_eligible=eligible,
            business_revenue=business,
            blue_return_deduction=0,
            pension_income=3000000,
            pension_is_over_65=True,
            loss_carryforward_amount=carryforward,
        )
    )
    assert result.pension_salary_cap_adjustment == cap_adjustment


@pytest.mark.parametrize(
    "salary_deduction,adjustment", [(1700000, 0), (1700001, 1), (1950000, 250000)]
)
def test_combined_deduction_cap_boundary(salary_deduction: int, adjustment: int) -> None:
    result = calc_pension_deduction(
        PensionDeductionInput(
            fiscal_year=2027,
            pension_income=3000000,
            is_over_65=True,
            salary_income_deduction=salary_deduction,
        )
    )
    assert result.salary_cap_adjustment == adjustment


@pytest.mark.parametrize("year", [2025, 2026, 2027])
@pytest.mark.parametrize(
    "pension,over65,other,taxable",
    [
        (3500000, True, 0, 2350000),
        (3500001, True, 0, 2350000),
        (1300001, False, 0, 700000),
        (4100001, True, 0, 2800000),
        (7700001, True, 0, 5860000),
        (10000001, True, 0, 8045001),
        (500000, True, 20000001, 0),
        (500000, False, 20000001, 100000),
        (1000000, True, 10000000, 0),
        (1000000, True, 10000001, 0),
        (1000000, True, 20000001, 100000),
    ],
)
def test_pension_matches_statutory_table_and_fraction_rules(
    year: int,
    pension: int,
    over65: bool,
    other: int,
    taxable: int,
) -> None:
    # NTA No.1600、財務省解説127・128頁。給与なしでは新しい合計上限に達しない。
    result = calc_pension_deduction(
        PensionDeductionInput(
            fiscal_year=year,
            pension_income=pension,
            is_over_65=over65,
            other_income=other,
            salary_income_deduction=0,
        )
    )
    assert result.taxable_pension_income == taxable


@pytest.mark.parametrize(
    "revenue,adjustment",
    [(8500000, 0), (8500001, 1), (9000000, 50000), (10000000, 150000), (11000000, 150000)],
)
def test_child_adjustment_boundaries(revenue: int, adjustment: int) -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=2027,
            salary_income=revenue,
            blue_return_deduction=0,
            salary_income_adjustment_eligible=True,
        )
    )
    assert result.salary_child_adjustment == adjustment


def test_both_parents_can_use_child_adjustment_and_filing_requires_unknown_facts() -> None:
    params = IncomeTaxInput(
        fiscal_year=2027, salary_income=9000000, blue_return_deduction=0, calculation_mode="filing"
    )
    with pytest.raises(ValueError, match="salary_income_adjustment_eligible"):
        calc_income_tax(params)
    params.dependents = [
        DependentInfo(
            name="架空の子",
            birth_date="2020-01-01",
            relationship="子",
            income=0,
            other_taxpayer_dependent=True,
        )
    ]
    assert calc_income_tax(params).salary_child_adjustment == 50000
    params.salary_income_adjustment_eligible = False
    with pytest.raises(ValueError, match="矛盾"):
        calc_income_tax(params)


def test_pension_age_must_be_provided() -> None:
    with pytest.raises(ValueError, match="pension_is_over_65"):
        calc_income_tax(IncomeTaxInput(fiscal_year=2027, pension_income=3000000))


def test_standalone_2027_pension_requires_the_salary_deduction() -> None:
    with pytest.raises(ValueError, match="salary_income_deduction"):
        calc_pension_deduction(
            PensionDeductionInput(fiscal_year=2027, pension_income=3000000, is_over_65=True)
        )


def test_filing_sanity_revalidates_required_salary_facts() -> None:
    params = IncomeTaxInput(
        fiscal_year=2027,
        salary_income=9000000,
        salary_income_adjustment_eligible=True,
        blue_return_deduction=0,
        calculation_mode="filing",
    )
    saved = calc_income_tax(params)
    params.salary_income_adjustment_eligible = None
    with pytest.raises(ValueError, match="salary_income_adjustment_eligible"):
        sanity_check_income_tax(params, saved)
    params.salary_income_adjustment_eligible = False
    assert not sanity_check_income_tax(params, saved).passed


def test_deductions_use_income_before_loss_carryforward_for_personal_limits() -> None:
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=2027,
            business_revenue=26000000,
            blue_return_deduction=0,
            loss_carryforward_amount=25000000,
            medical_expenses=100000,
        )
    )
    assert result.aggregate_income_before_loss_carryforward == 26000000
    assert result.total_income == 1000000
    deductions = {d.type: d.amount for d in result.deductions_detail.income_deductions}
    assert deductions.get("basic", 0) == 0
    assert deductions["medical"] == 50000


def test_high_income_special_scheme_requires_complete_income_for_filing() -> None:
    with pytest.raises(ValueError, match="minimum_tax_income_complete"):
        calc_income_tax(
            IncomeTaxInput(
                fiscal_year=2027,
                business_revenue=165000001,
                blue_return_deduction=0,
                calculation_mode="filing",
            )
        )


def test_sanity_rejects_2026_rates_relabelled_as_2027() -> None:
    params = IncomeTaxInput(fiscal_year=2026, salary_income=5000000, blue_return_deduction=0)
    saved = calc_income_tax(params).model_copy(update={"fiscal_year": 2027})
    params.fiscal_year = 2027
    check = sanity_check_income_tax(params, saved)
    assert not check.passed
    assert {item.code for item in check.items} >= {
        "RECONSTRUCTION_TAX_MISMATCH",
        "DEFENSE_TAX_MISMATCH",
    }
