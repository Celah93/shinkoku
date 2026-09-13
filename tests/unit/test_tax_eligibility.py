"""青色控除・インボイス特例の適用境界と申告用計算の停止を検証する。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shinkoku.models import (
    BlueReturnEligibilityFacts,
    ConsumptionTaxInput,
    IncomeTaxInput,
    InvoiceSpecialEligibilityFacts,
)
from shinkoku.tools.tax_calc import calc_consumption_tax, calc_income_tax, sanity_check_income_tax
from shinkoku.tools.tax_eligibility import (
    check_blue_return_eligibility,
    check_invoice_special_eligibility,
)
from tests.helpers.tax_eligibility import verified_blue_facts, verified_invoice_facts


@pytest.mark.parametrize("fiscal_year", [2025, 2026])
@pytest.mark.parametrize("amount", [100_000, 550_000, 650_000])
def test_current_blue_deductions_with_confirmed_facts(fiscal_year: int, amount: int) -> None:
    result = check_blue_return_eligibility(fiscal_year, amount, verified_blue_facts())
    assert result.status == "eligible"
    assert result.missing_fields == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("blue_return_approved", False),
        ("eligible_business_income", False),
        ("bookkeeping", "simple"),
        ("cash_basis_special", True),
        ("filing_within_deadline", False),
        ("required_statements_included", False),
        ("deduction_claim_recorded", False),
    ],
)
def test_blue_65_rejects_each_failed_requirement(field: str, value: object) -> None:
    result = check_blue_return_eligibility(2026, 650_000, verified_blue_facts(**{field: value}))
    assert result.status == "ineligible"
    assert any(field in reason for reason in result.reasons)


@pytest.mark.parametrize("amount", [550_000, 650_000])
def test_late_filing_does_not_qualify_for_large_blue_deduction(amount: int) -> None:
    result = check_blue_return_eligibility(
        2026, amount, verified_blue_facts(filing_within_deadline=False)
    )
    assert result.status == "ineligible"
    small = check_blue_return_eligibility(
        2026, 100_000, verified_blue_facts(filing_within_deadline=False, bookkeeping="simple")
    )
    assert small.status == "eligible"


def test_paper_65_needs_qualified_books_and_notice() -> None:
    facts = verified_blue_facts(etax_filing=False, qualified_electronic_books=True)
    result = check_blue_return_eligibility(2026, 650_000, facts)
    assert result.status == "indeterminate"
    assert result.missing_fields == ["electronic_books_notice_requirement_met"]
    assert check_blue_return_eligibility(2026, 550_000, facts).status == "eligible"
    facts.electronic_books_notice_requirement_met = True
    assert check_blue_return_eligibility(2026, 650_000, facts).status == "eligible"


def test_etax_does_not_require_unused_books_branch() -> None:
    facts = verified_blue_facts(
        qualified_electronic_books=False, electronic_books_notice_requirement_met=None
    )
    assert check_blue_return_eligibility(2026, 650_000, facts).status == "eligible"


@pytest.mark.parametrize(
    "facts",
    [
        verified_blue_facts(
            qualified_electronic_books=True, electronic_books_notice_requirement_met=True
        ),
        verified_blue_facts(
            digital_seamless_recordkeeping=True, digital_notice_requirement_met=True
        ),
    ],
)
def test_2027_blue_75_save_routes(facts: BlueReturnEligibilityFacts) -> None:
    assert check_blue_return_eligibility(2027, 750_000, facts).status == "eligible"
    assert check_blue_return_eligibility(2026, 750_000, facts).status == "ineligible"
    facts.etax_filing = False
    assert check_blue_return_eligibility(2027, 750_000, facts).status == "ineligible"


def test_2027_paper_does_not_use_old_55_route() -> None:
    facts = verified_blue_facts(etax_filing=False)
    assert check_blue_return_eligibility(2026, 550_000, facts).status == "eligible"
    assert check_blue_return_eligibility(2027, 550_000, facts).status == "ineligible"


@pytest.mark.parametrize("revenue,status", [(10_000_000, "eligible"), (10_000_001, "ineligible")])
def test_2027_simple_books_revenue_boundary(revenue: int, status: str) -> None:
    facts = verified_blue_facts(bookkeeping="simple", prior_prior_year_business_revenue=revenue)
    assert check_blue_return_eligibility(2027, 100_000, facts).status == status
    assert check_blue_return_eligibility(2026, 100_000, facts).status == "eligible"


def test_cash_basis_election_is_excluded_from_the_2027_simple_books_restriction() -> None:
    facts = verified_blue_facts(
        bookkeeping="simple", cash_basis_special=True, prior_prior_year_business_revenue=10_000_001
    )
    assert check_blue_return_eligibility(2027, 100_000, facts).status == "eligible"
    facts.cash_basis_special = None
    assert check_blue_return_eligibility(2027, 100_000, facts).status == "indeterminate"


def test_missing_blue_facts_are_not_assumed_true() -> None:
    result = check_blue_return_eligibility(2026, 650_000, None)
    assert result.status == "indeterminate"
    assert "blue_return_approved" in result.missing_fields
    assert "filing_within_deadline" in result.missing_fields


@pytest.mark.parametrize(
    "year,method,status",
    [
        (2025, "special_20pct", "eligible"),
        (2026, "special_20pct", "eligible"),
        (2027, "special_20pct", "unsupported"),
        (2026, "special_30pct", "unsupported"),
        (2027, "special_30pct", "eligible"),
        (2028, "special_30pct", "eligible"),
        (2029, "special_30pct", "unsupported"),
    ],
)
def test_invoice_scheme_year_boundaries(year: int, method: str, status: str) -> None:
    assert (
        check_invoice_special_eligibility(year, method, verified_invoice_facts()).status == status
    )


@pytest.mark.parametrize("year,method", [(2026, "special_20pct"), (2027, "special_30pct")])
@pytest.mark.parametrize("sales,status", [(10_000_000, "eligible"), (10_000_001, "ineligible")])
def test_invoice_base_period_sales_boundary(
    year: int, method: str, sales: int, status: str
) -> None:
    facts = verified_invoice_facts(base_period_taxable_sales=sales)
    assert check_invoice_special_eligibility(year, method, facts).status == status


@pytest.mark.parametrize(
    "field,value",
    [
        ("invoice_registration_effective", False),
        ("specific_period_taxation_applies", True),
        ("asset_tax_exemption_restriction", True),
        ("other_tax_exemption_restriction", True),
        ("shortened_tax_period", True),
    ],
)
def test_invoice_exclusions_and_unknowns_are_distinct(field: str, value: bool) -> None:
    rejected = verified_invoice_facts(**{field: value})
    missing = verified_invoice_facts(**{field: None})
    assert check_invoice_special_eligibility(2026, "special_20pct", rejected).status == "ineligible"
    result = check_invoice_special_eligibility(2026, "special_20pct", missing)
    assert result.status == "indeterminate"
    assert result.missing_fields == [field]


@pytest.mark.parametrize(
    "registration,inheritance,status",
    [
        ("2026-03-01", "2026-03-01", "eligible"),
        ("2026-02-28", "2026-03-01", "eligible"),
        ("2026-03-02", "2026-03-01", "ineligible"),
        ("2025-02-01", "2025-03-01", "ineligible"),
        (None, "2026-03-01", "indeterminate"),
    ],
)
def test_inheritance_exception_requires_same_year_and_registration_by_inheritance(
    registration: str | None, inheritance: str, status: str
) -> None:
    facts = verified_invoice_facts(
        inheritance_taxation_applies=True,
        inheritance_date=inheritance,
        invoice_registration_date=registration,
    )
    assert check_invoice_special_eligibility(2026, "special_20pct", facts).status == status


def test_special_30_requires_dates_for_inheritance_exception() -> None:
    result = check_invoice_special_eligibility(
        2027, "special_30pct", verified_invoice_facts(inheritance_taxation_applies=True)
    )
    assert result.status == "indeterminate"
    assert set(result.missing_fields) == {"inheritance_date", "invoice_registration_date"}


@pytest.mark.parametrize("value", ["false", 0, "yes"])
def test_verification_flags_require_actual_booleans(value: object) -> None:
    with pytest.raises(ValidationError):
        BlueReturnEligibilityFacts(blue_return_approved=value)
    with pytest.raises(ValidationError):
        InvoiceSpecialEligibilityFacts(shortened_tax_period=value)


def test_estimate_is_marked_unverified_and_filing_requires_facts() -> None:
    income = IncomeTaxInput(fiscal_year=2026, business_revenue=3_000_000)
    result = calc_income_tax(income)
    assert result.calculation_mode == "estimate"
    assert result.eligibility_checks[0].status == "indeterminate"
    income.calculation_mode = "filing"
    with pytest.raises(ValueError, match="TAX_ELIGIBILITY_UNCONFIRMED"):
        calc_income_tax(income)
    income.blue_return_eligibility = verified_blue_facts()
    verified = calc_income_tax(income)
    assert verified.tax_due == result.tax_due
    assert verified.eligibility_checks[0].status == "eligible"
    assert sanity_check_income_tax(income, verified).passed
    with pytest.raises(ValueError, match="試算結果を申告用"):
        sanity_check_income_tax(income, result)


def test_known_ineligible_blue_facts_are_rejected_in_estimate_mode_too() -> None:
    with pytest.raises(ValueError, match="TAX_ELIGIBILITY_INELIGIBLE"):
        calc_income_tax(
            IncomeTaxInput(
                fiscal_year=2026,
                business_revenue=3_000_000,
                blue_return_eligibility=verified_blue_facts(blue_return_approved=False),
            )
        )


def test_filing_special_20_requires_facts_and_preserves_tax_arithmetic() -> None:
    data = ConsumptionTaxInput(fiscal_year=2026, method="special_20pct", taxable_sales_10=1_100_000)
    estimate = calc_consumption_tax(data)
    assert estimate.eligibility_checks[0].status == "indeterminate"
    data.calculation_mode = "filing"
    with pytest.raises(ValueError, match="TAX_ELIGIBILITY_UNCONFIRMED"):
        calc_consumption_tax(data)
    data.invoice_special_eligibility = verified_invoice_facts()
    result = calc_consumption_tax(data)
    assert result.total_due == estimate.total_due == 20_000
    assert result.calculation_mode == "filing"
    assert result.eligibility_checks[0].status == "eligible"


def test_2027_eligibility_flows_into_annual_income_tax() -> None:
    facts = verified_blue_facts(
        qualified_electronic_books=True, electronic_books_notice_requirement_met=True
    )
    assert check_blue_return_eligibility(2027, 750_000, facts).status == "eligible"
    result = calc_income_tax(
        IncomeTaxInput(
            fiscal_year=2027,
            business_revenue=3_000_000,
            blue_return_deduction=750_000,
            calculation_mode="filing",
            blue_return_eligibility=facts,
        )
    )
    assert result.effective_blue_return_deduction == 750_000
    assert result.eligibility_checks[0].status == "eligible"
