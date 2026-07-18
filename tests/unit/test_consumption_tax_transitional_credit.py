"""免税事業者等からの課税仕入れに係る経過措置のテスト。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from shinkoku.models import (
    ConsumptionTaxInput,
    ConsumptionTaxResult,
    PurchaseDetail,
    TransitionalCreditBreakdown,
)
from shinkoku.tax_constants import (
    TRANSITIONAL_CREDIT_PERIODS,
    get_per_supplier_limit,
    get_transitional_credit_rate,
)
from shinkoku.tools.tax_calc import calc_consumption_tax


def _detail(
    recognition_date: str,
    amount: int,
    tax_rate: str,
    category: str,
    supplier_key: str | None = "supplier-1",
) -> PurchaseDetail:
    return PurchaseDetail(
        tax_recognition_date=recognition_date,
        amount_inclusive=amount,
        tax_rate=tax_rate,
        credit_category=category,
        supplier_key=supplier_key,
    )


def _breakdown(result: ConsumptionTaxResult, rate: int) -> TransitionalCreditBreakdown:
    return next(item for item in result.transitional_credit_breakdown if item.rate_percent == rate)


@pytest.mark.parametrize(
    ("recognition_date", "expected"),
    [
        (date(2023, 10, 1), 80),
        (date(2026, 9, 30), 80),
        (date(2026, 10, 1), 70),
        (date(2028, 9, 30), 70),
        (date(2028, 10, 1), 50),
        (date(2030, 9, 30), 50),
        (date(2030, 10, 1), 30),
        (date(2031, 9, 30), 30),
        (date(2031, 10, 1), 0),
        (date(2035, 1, 1), 0),
    ],
)
def test_transitional_credit_rate_boundaries(recognition_date: date, expected: int) -> None:
    assert get_transitional_credit_rate(recognition_date) == expected


def test_transitional_credit_rejects_date_before_invoice_system() -> None:
    with pytest.raises(ValueError, match="2023-10-01"):
        get_transitional_credit_rate(date(2023, 9, 30))


@pytest.mark.parametrize(
    ("period_start", "expected"),
    [
        (date(2026, 1, 1), 1_000_000_000),
        (date(2026, 10, 1), 100_000_000),
        (date(2027, 1, 1), 100_000_000),
    ],
)
def test_per_supplier_limit(period_start: date, expected: int) -> None:
    assert get_per_supplier_limit(period_start) == expected


def test_standard_rate_mixed_80_and_70_percent() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            purchase_details=[
                _detail("2026-01-10", 2_200_000, "standard_10", "qualified_invoice"),
                _detail("2026-09-30", 550_000, "standard_10", "nonqualified_transitional"),
                _detail("2026-10-01", 1_100_000, "standard_10", "nonqualified_transitional"),
            ],
        )
    )

    assert result.full_credit_tax_amount.standard_10 == 156_000
    assert _breakdown(result, 80).credit_amount.standard_10 == 31_200
    assert _breakdown(result, 70).credit_amount.standard_10 == 54_600
    assert result.tax_on_purchases == 241_800


def test_reduced_rate_mixed_80_and_70_percent() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            purchase_details=[
                _detail("2026-01-10", 540_000, "reduced_8", "qualified_invoice"),
                _detail("2026-09-30", 108_000, "reduced_8", "nonqualified_transitional"),
                _detail("2026-10-01", 216_000, "reduced_8", "nonqualified_transitional"),
            ],
        )
    )

    assert result.full_credit_tax_amount.reduced_8 == 31_200
    assert _breakdown(result, 80).credit_amount.reduced_8 == 4_992
    assert _breakdown(result, 70).credit_amount.reduced_8 == 8_736
    assert result.tax_on_purchases == 44_928


def test_transitional_credit_floors_once_after_grouping() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            purchase_details=[
                _detail("2026-09-01", 550_000, "standard_10", "nonqualified_transitional"),
                _detail("2026-09-02", 169, "standard_10", "nonqualified_transitional"),
            ],
        )
    )

    assert _breakdown(result, 80).credit_amount.standard_10 == 31_209


def test_unknown_category_is_not_credited_and_warns() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            purchase_details=[_detail("2026-04-01", 110_000, "standard_10", "unknown")],
        )
    )

    assert result.tax_on_purchases == 0
    assert result.unclassified_amount.standard_10 == 110_000
    assert result.unclassified_count == 1
    assert any("再計算" in warning for warning in result.warnings)


def test_legacy_purchase_requires_explicit_assumption() -> None:
    with pytest.raises(ValidationError, match="legacy_purchase_assumption"):
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            taxable_purchases_10=110_000,
        )

    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            taxable_purchases_10=110_000,
            legacy_purchase_assumption="all_qualified",
        )
    )
    assert result.tax_on_purchases == 7_800
    assert result.legacy_purchase_assumption == "all_qualified"
    assert any("全件適格請求書" in warning for warning in result.warnings)


def test_purchase_details_and_legacy_amounts_cannot_be_combined() -> None:
    with pytest.raises(ValidationError, match="併用"):
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            taxable_purchases_10=110_000,
            legacy_purchase_assumption="all_qualified",
            purchase_details=[_detail("2026-04-01", 110_000, "standard_10", "qualified_invoice")],
        )


def test_full_credit_categories_and_small_amount_expiry() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            purchase_details=[
                _detail("2026-04-01", 110_000, "standard_10", "book_only_full_credit"),
                _detail("2026-04-01", 108_000, "reduced_8", "small_amount_full_credit"),
            ],
        )
    )
    assert result.tax_on_purchases == 14_040

    with pytest.raises(ValidationError, match="2029-09-30"):
        _detail("2029-10-01", 110_000, "standard_10", "small_amount_full_credit")


def test_full_credit_is_grouped_by_credit_category_before_flooring() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            purchase_details=[
                _detail("2026-04-01", 7, "standard_10", "qualified_invoice"),
                _detail("2026-04-01", 8, "standard_10", "book_only_full_credit"),
            ],
        )
    )

    assert result.full_credit_purchase_amount.standard_10 == 15
    assert result.full_credit_tax_amount.standard_10 == 0


def test_negative_transitional_detail_adjusts_group_without_clipping() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            purchase_details=[
                _detail("2026-09-01", 550_000, "standard_10", "nonqualified_transitional"),
                _detail("2026-09-02", -110_000, "standard_10", "nonqualified_transitional"),
            ],
        )
    )

    assert _breakdown(result, 80).amount_inclusive.standard_10 == 440_000
    assert _breakdown(result, 80).credit_amount.standard_10 == 24_960
    assert result.form_2_3 is not None
    assert result.form_2_3.row_11_transitional_purchase_amount.standard_10 == 440_000


@pytest.mark.parametrize(
    ("fiscal_year", "amount", "limit_text"),
    [(2026, 1_000_000_001, "1,000,000,000"), (2027, 100_000_001, "100,000,000")],
)
def test_supplier_limit_is_warning_only(fiscal_year: int, amount: int, limit_text: str) -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=fiscal_year,
            method="standard",
            purchase_details=[
                _detail(
                    f"{fiscal_year}-01-01",
                    amount,
                    "standard_10",
                    "nonqualified_transitional",
                )
            ],
        )
    )

    assert result.tax_on_purchases != 0
    assert any(limit_text in warning and "未反映" in warning for warning in result.warnings)


def test_missing_supplier_key_warns() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            purchase_details=[
                _detail(
                    "2026-09-01",
                    110_000,
                    "standard_10",
                    "nonqualified_transitional",
                    supplier_key=None,
                )
            ],
        )
    )
    assert any("判定できません" in warning for warning in result.warnings)


def test_unknown_input_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            supplier_is_qualified=True,
        )

    with pytest.raises(ValidationError, match="extra_forbidden"):
        PurchaseDetail(
            tax_recognition_date="2026-04-01",
            amount_inclusive=110_000,
            tax_rate="standard_10",
            credit_category="qualified_invoice",
            supplier_is_qualified=True,
        )


def test_form_2_3_rate_breakdown_matches_mixed_case() -> None:
    result = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2026,
            method="standard",
            purchase_details=[
                _detail("2026-01-10", 2_200_000, "standard_10", "qualified_invoice"),
                _detail("2026-01-10", 540_000, "reduced_8", "qualified_invoice"),
                _detail("2026-09-30", 550_000, "standard_10", "nonqualified_transitional"),
                _detail("2026-10-01", 1_100_000, "standard_10", "nonqualified_transitional"),
                _detail("2026-09-30", 108_000, "reduced_8", "nonqualified_transitional"),
                _detail("2026-10-01", 216_000, "reduced_8", "nonqualified_transitional"),
            ],
        )
    )

    assert result.form_2_3 is not None
    assert result.form_2_3.row_11_transitional_purchase_amount.standard_10 == 1_650_000
    assert result.form_2_3.row_11_transitional_purchase_amount.reduced_8 == 324_000
    assert result.form_2_3.row_12_transitional_deemed_tax.standard_10 == 85_800
    assert result.form_2_3.row_12_transitional_deemed_tax.reduced_8 == 13_728
    assert result.form_2_3.row_17_total_input_tax.total == 286_728


def test_invalid_calendar_date_is_rejected() -> None:
    with pytest.raises(ValidationError, match="実在する"):
        _detail("2026-02-30", 110_000, "standard_10", "qualified_invoice")


def test_markdown_schedules_match_code_constants() -> None:
    expected_periods = [
        (date(2023, 10, 1), date(2026, 9, 30), 80),
        (date(2026, 10, 1), date(2028, 9, 30), 70),
        (date(2028, 10, 1), date(2030, 9, 30), 50),
        (date(2030, 10, 1), date(2031, 9, 30), 30),
        (date(2031, 10, 1), None, 0),
    ]
    assert [
        (period.start_date, period.end_date, period.rate_percent)
        for period in TRANSITIONAL_CREDIT_PERIODS
    ] == expected_periods

    root = Path(__file__).parents[2]
    expected_markdown = {
        "skills/invoice-system/SKILL.md": ["R13.10.1で完全移行"],
        "skills/invoice-system/references/transitional-measures-timeline.md": [
            "R8.10.1〜R10.9.30 | 70%",
            "R10.10.1〜R12.9.30 | 50%",
            "R12.10.1〜R13.9.30 | 30%",
            "R13.10.1〜 | 0%",
        ],
        "skills/invoice-system/references/btoc-and-pricing-strategy.md": [
            "R8.10〜R10.9 | 70%",
            "R10.10〜R12.9 | 50%",
            "R12.10〜R13.9 | 30%",
            "R13.10〜 | 0%",
        ],
        "skills/invoice-system/references/decision-flowchart.md": ["完全移行後（R13.10〜）"],
        "skills/invoice-system/references/common-pitfalls.md": [
            "R8.10.1〜R10.9.30: 70%",
            "R10.10.1〜R12.9.30: 50%",
            "R12.10.1〜R13.9.30: 30%",
            "R13.10.1〜: 0%",
        ],
        "skills/tax-invoice-credit-context/references/input-tax-credit-rules.md": [
            "R8.10.1〜R10.9.30 | 70%",
            "R10.10.1〜R12.9.30 | 50%",
            "R12.10.1〜R13.9.30 | 30%",
            "R13.10.1〜 | 0%",
        ],
        "skills/consumption-tax/references/tax-classification.md": [
            "令和8年10月〜令和10年9月 | 70%",
            "令和10年10月〜令和12年9月 | 50%",
            "令和12年10月〜令和13年9月 | 30%",
            "令和13年10月〜 | 0%",
        ],
        "skills/tax-advisor/reference/tax-reform/transition.md": [
            "令和8年10月1日〜令和10年9月30日 | **70%**",
            "令和10年10月1日〜令和12年9月30日 | **50%**",
            "令和12年10月1日〜令和13年9月30日 | **30%**",
            "令和13年10月1日〜 | **0%**",
        ],
        "skills/tax-advisor/reference/tax-reform/2026.md": [
            "令和8年10月1日〜令和10年9月30日 | **70%**",
            "令和10年10月1日〜令和12年9月30日 | **50%**",
            "令和12年10月1日〜令和13年9月30日 | **30%**",
            "令和13年10月1日〜 | **0%**",
        ],
        "skills/tax-advisor/reference/consumption-tax.md": [
            "令和8年10月1日〜令和10年9月30日 | 仕入税額の70%",
            "令和10年10月1日〜令和12年9月30日 | 仕入税額の50%",
            "令和12年10月1日〜令和13年9月30日 | 仕入税額の30%",
            "令和13年10月1日〜 | 控除不可（0%）",
        ],
    }

    for relative_path, expected_fragments in expected_markdown.items():
        text = (root / relative_path).read_text(encoding="utf-8")
        for fragment in expected_fragments:
            assert fragment in text, f"{relative_path} に期間表の記載がありません: {fragment}"
