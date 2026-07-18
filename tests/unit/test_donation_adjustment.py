"""寄附金控除の共有枠調整テスト。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shinkoku.models import DonationAdjustmentResult, DonationRecordInput, DonationRecordRecord
from shinkoku.tools.tax_calc import calc_donation_adjustment


def _adjust(
    *,
    income: int = 0,
    public_interest: int = 0,
    npo: int = 0,
    political: int = 0,
    total_income: int = 5_000_000,
    income_tax_base: int = 10_000_000,
) -> DonationAdjustmentResult:
    return calc_donation_adjustment(
        income_deduction_amount=income,
        public_interest_amount=public_interest,
        npo_amount=npo,
        political_amount=political,
        total_income=total_income,
        income_tax_base=income_tax_base,
    )


def test_c1_income_deduction_consumes_threshold_before_political() -> None:
    result = _adjust(income=100_000, political=50_000)

    assert result.income_deduction.final_amount == 98_000
    assert result.political.eligible_amount == 50_000
    assert result.political.threshold_amount == 0
    assert result.political.formula_amount == 15_000
    assert result.political.final_amount == 15_000


def test_c2_income_deduction_consumes_shared_income_limit() -> None:
    result = _adjust(income=300_000, political=200_000, total_income=1_000_000)

    assert result.political.eligible_amount == 100_000
    assert result.political.threshold_amount == 0
    assert result.political.formula_amount == 30_000


def test_c3_political_formula_is_rounded_down_to_hundred() -> None:
    result = _adjust(political=10_500)

    assert result.political.threshold_amount == 2_000
    assert result.political.formula_amount == 2_500
    assert result.political.final_amount == 2_500


def test_c4_npo_formula_is_rounded_down_to_hundred() -> None:
    result = _adjust(npo=10_100)

    assert result.npo.threshold_amount == 2_000
    assert result.npo.formula_amount == 3_200
    assert result.npo.final_amount == 3_200


def test_c5_threshold_is_consumed_once_in_statutory_order() -> None:
    result = _adjust(public_interest=10_000, npo=20_000, political=30_000)

    assert result.public_interest.threshold_amount == 2_000
    assert result.public_interest.formula_amount == 3_200
    assert result.npo.threshold_amount == 0
    assert result.npo.formula_amount == 8_000
    assert result.political.threshold_amount == 0
    assert result.political.formula_amount == 9_000


def test_c6_public_interest_consumes_npo_income_limit() -> None:
    result = _adjust(public_interest=30_000, npo=20_000, total_income=100_000)

    assert result.public_interest.eligible_amount == 30_000
    assert result.public_interest.formula_amount == 11_200
    assert result.npo.eligible_amount == 10_000
    assert result.npo.formula_amount == 4_000


def test_c7_public_and_npo_share_cap_but_political_uses_separate_cap() -> None:
    result = _adjust(
        public_interest=10_000,
        npo=20_000,
        political=10_000,
        income_tax_base=20_000,
    )

    assert result.public_interest.tax_credit_cap == 5_000
    assert result.public_interest.final_amount == 3_200
    assert result.npo.tax_credit_cap == 1_800
    assert result.npo.final_amount == 1_800
    assert result.political.tax_credit_cap == 5_000
    assert result.political.final_amount == 3_000


def test_c8_npo_consumes_threshold_before_political() -> None:
    result = _adjust(npo=50_000, political=50_000)

    assert result.npo.threshold_amount == 2_000
    assert result.npo.formula_amount == 19_200
    assert result.political.threshold_amount == 0
    assert result.political.formula_amount == 15_000


@pytest.mark.parametrize(
    ("income", "expected"),
    [(5_000, 3_000), (1_000, 0)],
)
def test_income_deduction_lower_bound(income: int, expected: int) -> None:
    assert _adjust(income=income).income_deduction.final_amount == expected


@pytest.mark.parametrize(
    ("income", "public_interest", "npo", "political", "field"),
    [
        (40_000, 10_000, 0, 0, "public_interest"),
        (0, 40_000, 10_000, 0, "npo"),
        (0, 0, 40_000, 10_000, "political"),
    ],
)
def test_tax_credit_target_is_zero_when_income_limit_is_exhausted(
    income: int,
    public_interest: int,
    npo: int,
    political: int,
    field: str,
) -> None:
    result = _adjust(
        income=income,
        public_interest=public_interest,
        npo=npo,
        political=political,
        total_income=100_000,
    )

    assert getattr(result, field).eligible_amount == 0


def test_unknown_donation_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DonationRecordInput(
            donation_type="invalid",  # type: ignore[arg-type]
            recipient_name="不明な寄附先",
            amount=10_000,
            date="2025-06-01",
        )

    with pytest.raises(ValidationError):
        DonationRecordRecord(
            id=1,
            fiscal_year=2025,
            donation_type="invalid",  # type: ignore[arg-type]
            recipient_name="不明な寄附先",
            amount=10_000,
            date="2025-06-01",
            receipt_number=None,
            source_file=None,
        )
