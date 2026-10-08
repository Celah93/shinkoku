"""未読・空欄・明示的な0を区別した証憑の共通検算。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shinkoku.models import WithholdingSlipData, WithholdingSlipInput, WithholdingSlipRecord
from tests.helpers.withholding import withholding_input


def check(**changes):
    from shinkoku.tools.withholding import check_withholding_slip

    return check_withholding_slip(
        WithholdingSlipInput(**withholding_input(**changes)), fiscal_year=2025
    )


@pytest.mark.parametrize(
    "model,extra",
    [
        (WithholdingSlipInput, {}),
        (WithholdingSlipData, {"file_path": "fictional.pdf", "extracted_text": ""}),
        (WithholdingSlipRecord, {"id": 1, "fiscal_year": 2025}),
    ],
)
def test_amount_contract_and_blank_fields(model, extra) -> None:
    value = model(**extra)
    assert value.payment_amount is None
    assert value.year_end_adjusted is None
    assert model(payment_amount=0, year_end_adjusted=False, **extra).payment_amount == 0
    assert model(payment_amount=0, year_end_adjusted=False, **extra).year_end_adjusted is False
    assert value.blank_fields == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("payment_amount", True),
        ("payment_amount", 1.0),
        ("payment_amount", "1"),
        ("payment_amount", -1),
        ("document_fiscal_year", True),
        ("document_fiscal_year", "2025"),
        ("year_end_adjusted", 0),
        ("source_confirmed", "true"),
        ("unknown", 1),
        ("blank_fields", ["unknown"]),
        ("blank_fields", ["payment_amount", "payment_amount"]),
    ],
)
def test_invalid_amount_contract_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        WithholdingSlipInput(**{field: value})


def test_blank_and_value_are_not_accepted_together() -> None:
    with pytest.raises(ValidationError):
        WithholdingSlipInput(payment_amount=0, blank_fields=["payment_amount"])


def test_deduction_total_and_adjacent_misread() -> None:
    good = check()
    assert (good.status, good.calculated_total, good.difference) == ("matched", 2040000, 0)
    assert good.ready_for_calculation is True
    bad = check(social_insurance=610000)
    assert (bad.status, bad.calculated_total, bad.difference) == ("mismatched", 1900000, -140000)
    assert "WS_DEDUCTION_TOTAL_MISMATCH" in {issue.code for issue in bad.issues}
    assert bad.ready_for_calculation is False


@pytest.mark.parametrize(
    "field", ["specific_relative_special_deduction", "basic_deduction", "total_income_deductions"]
)
def test_unread_required_fields_are_not_completed(field: str) -> None:
    result = check(**{field: None})
    assert result.status == "incomplete"
    assert result.ready_for_calculation is False
    assert field in result.missing_fields


def test_inner_pension_housing_amounts_are_not_added_twice() -> None:
    result = check(
        social_insurance_small_business_mutual_aid=120000,
        national_pension_premium=150000,
        housing_loan_deduction=200000,
        blank_fields=[],
    )
    assert result.status == "matched"
    assert result.calculated_total == 2040000
    from shinkoku.tools.withholding import get_withholding_social_insurance

    assert (
        get_withholding_social_insurance(
            WithholdingSlipInput(
                **withholding_input(
                    social_insurance_small_business_mutual_aid=120000, blank_fields=[]
                )
            )
        )
        == 630000
    )


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"document_fiscal_year": 2026}, "WS_FISCAL_YEAR_MISMATCH"),
        (
            {"social_insurance_small_business_mutual_aid": 750001, "blank_fields": []},
            "WS_INVALID_INNER_AMOUNT",
        ),
        ({"year_end_adjusted": False}, "WS_YEAR_END_STATUS_CONFLICT"),
        ({"source_confirmed": False}, "WS_SOURCE_NOT_CONFIRMED"),
        ({"document_fiscal_year": None}, "WS_FIELDS_UNCONFIRMED"),
        (
            {"dependent_deduction": 380000, "deduction_derivation_note": None},
            "WS_FIELDS_UNCONFIRMED",
        ),
    ],
)
def test_invalid_or_unconfirmed_slip_is_not_ready(changes: dict, code: str) -> None:
    result = check(**changes)
    assert code in {issue.code for issue in result.issues}
    assert result.ready_for_calculation is False


def test_exchange_can_match_but_unconfirmed_source_cannot_be_ready() -> None:
    result = check(
        social_insurance=610000, specific_relative_special_deduction=750000, source_confirmed=None
    )
    assert result.status == "matched"
    assert result.ready_for_calculation is False


def test_missing_salary_after_deduction_does_not_change_total_status() -> None:
    result = check(salary_income_after_deduction=None)
    assert result.status == "matched"
    assert result.ready_for_calculation is False
    assert "salary_income_after_deduction" in result.missing_fields


def test_unknown_year_end_status_and_unadjusted_blank() -> None:
    assert check(year_end_adjusted=None).status == "incomplete"
    from shinkoku.tools.withholding import check_withholding_slip

    slip = WithholdingSlipInput(**withholding_input("2025-unadjusted"))
    result = check_withholding_slip(slip, fiscal_year=2025)
    assert result.status == "not_applicable"
    assert result.calculated_total is None and result.difference is None
    assert result.ready_for_calculation is True


def test_social_insurance_confirmed_blank_and_unread_null() -> None:
    from shinkoku.tools.withholding import get_withholding_social_insurance

    blank = ["social_insurance", "social_insurance_small_business_mutual_aid"]
    slip = WithholdingSlipInput(social_insurance=None, blank_fields=blank)
    assert get_withholding_social_insurance(slip) == 0
    assert slip.social_insurance is None
    assert get_withholding_social_insurance(WithholdingSlipInput()) is None
    assert get_withholding_social_insurance(WithholdingSlipInput(social_insurance=100)) is None


def test_confirmed_blank_is_not_zero_for_mandatory_or_derived_fields() -> None:
    for field in (
        "payment_amount",
        "withheld_tax",
        "basic_deduction",
        "dependent_deduction",
        "other_personal_deductions",
    ):
        raw = withholding_input()
        raw[field] = None
        raw["blank_fields"].append(field)
        from shinkoku.tools.withholding import check_withholding_slip

        assert not check_withholding_slip(
            WithholdingSlipInput(**raw), fiscal_year=2025
        ).ready_for_calculation


def test_year_specific_and_early_amounts_are_not_overwritten() -> None:
    from shinkoku.tools.withholding import check_withholding_slip

    slip = WithholdingSlipInput(**withholding_input("2026-specific"))
    assert check_withholding_slip(slip, fiscal_year=2026).calculated_total == 2400000
    early = WithholdingSlipInput(
        **withholding_input(
            "2026-specific", basic_deduction=680000, total_income_deductions=2040000
        )
    )
    assert check_withholding_slip(early, fiscal_year=2026).calculated_total == 2040000
    assert early.basic_deduction == 680000
