"""税額計算テスト専用の、確認済み事実を持つ架空データ。"""

from __future__ import annotations

from shinkoku.models import BlueReturnEligibilityFacts, InvoiceSpecialEligibilityFacts


def verified_blue_facts(**changes: object) -> BlueReturnEligibilityFacts:
    values = {
        "blue_return_approved": True,
        "eligible_business_income": True,
        "bookkeeping": "double_entry",
        "cash_basis_special": False,
        "filing_within_deadline": True,
        "required_statements_included": True,
        "deduction_claim_recorded": True,
        "etax_filing": True,
    }
    return BlueReturnEligibilityFacts.model_validate({**values, **changes})


def verified_invoice_facts(**changes: object) -> InvoiceSpecialEligibilityFacts:
    values = {
        "domestic_individual": True,
        "invoice_registration_effective": True,
        "base_period_taxable_sales": 5_000_000,
        "specific_period_taxation_applies": False,
        "inheritance_taxation_applies": False,
        "asset_tax_exemption_restriction": False,
        "other_tax_exemption_restriction": False,
        "shortened_tax_period": False,
    }
    return InvoiceSpecialEligibilityFacts.model_validate({**values, **changes})
