"""サニティチェックのユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from shinkoku.models import (
    BusinessWithholdingInput,
    IncomeTaxInput,
    IncomeTaxResult,
    ProfessionalFeeInput,
)
from shinkoku.tools.ledger import (
    ledger_add_business_withholding,
    ledger_add_professional_fee,
    ledger_init,
)
from shinkoku.tools.tax_calc import sanity_check_income_tax


def _make_input(**kwargs) -> IncomeTaxInput:
    defaults = {"fiscal_year": 2025}
    defaults.update(kwargs)
    return IncomeTaxInput(**defaults)


def _make_result(**kwargs) -> IncomeTaxResult:
    defaults = {"fiscal_year": 2025, "tax_due": 0}
    defaults.update(kwargs)
    return IncomeTaxResult(**defaults)


# --- 1. BLUE_DEDUCTION_ON_LOSS ---


def test_blue_deduction_on_loss() -> None:
    """赤字なのに控除適用 → error。"""
    inp = _make_input(business_revenue=100_000, business_expenses=200_000)
    res = _make_result(effective_blue_return_deduction=50_000)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "BLUE_DEDUCTION_ON_LOSS" in codes
    assert not check.passed


def test_no_blue_deduction_on_loss() -> None:
    """赤字で控除0 → OK。"""
    inp = _make_input(business_revenue=100_000, business_expenses=200_000)
    res = _make_result(effective_blue_return_deduction=0)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "BLUE_DEDUCTION_ON_LOSS" not in codes


# --- 2. BLUE_DEDUCTION_EXCEEDS_PROFIT ---


def test_blue_deduction_exceeds_profit() -> None:
    """控除が利益超過 → error。"""
    inp = _make_input(business_revenue=500_000, business_expenses=200_000)
    # 利益=300,000 だが控除が400,000（通常はキャップされるが、手動構築を想定）
    res = _make_result(effective_blue_return_deduction=400_000)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "BLUE_DEDUCTION_EXCEEDS_PROFIT" in codes


def test_blue_deduction_within_profit() -> None:
    """控除が利益以下 → OK。"""
    inp = _make_input(business_revenue=3_000_000, business_expenses=1_000_000)
    res = _make_result(effective_blue_return_deduction=650_000)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "BLUE_DEDUCTION_EXCEEDS_PROFIT" not in codes


# --- 3. LARGE_BUSINESS_LOSS ---


def test_large_business_loss() -> None:
    """事業損失が1,000万円超 → warning。"""
    inp = _make_input(business_revenue=1_000_000, business_expenses=12_000_000)
    res = _make_result(business_income=-11_000_000)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "LARGE_BUSINESS_LOSS" in codes


def test_moderate_business_loss() -> None:
    """事業損失が1,000万以下 → OK。"""
    inp = _make_input(business_revenue=1_000_000, business_expenses=5_000_000)
    res = _make_result(business_income=-4_000_000)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "LARGE_BUSINESS_LOSS" not in codes


# --- 4. TAX_ON_ZERO_INCOME ---


def test_tax_on_zero_income() -> None:
    """課税所得0なのに税額発生 → error。"""
    inp = _make_input()
    res = _make_result(taxable_income=0, income_tax_base=10_000)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "TAX_ON_ZERO_INCOME" in codes


def test_no_tax_on_zero_income() -> None:
    """課税所得0で税額0 → OK。"""
    inp = _make_input()
    res = _make_result(taxable_income=0, income_tax_base=0)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "TAX_ON_ZERO_INCOME" not in codes


# --- 5. NEGATIVE_TOTAL_INCOME ---


def test_negative_total_income() -> None:
    """合計所得が負 → info。"""
    inp = _make_input()
    res = _make_result(
        salary_income_after_deduction=100_000,
        business_income=-500_000,
    )
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "NEGATIVE_TOTAL_INCOME" in codes


def test_positive_total_income() -> None:
    """合計所得が正 → OK。"""
    inp = _make_input()
    res = _make_result(
        salary_income_after_deduction=3_000_000,
        business_income=500_000,
    )
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "NEGATIVE_TOTAL_INCOME" not in codes


# --- 6. TAXABLE_INCOME_ROUNDING ---


def test_taxable_income_rounding_error() -> None:
    """課税所得が1,000円単位でない → error。"""
    inp = _make_input()
    res = _make_result(taxable_income=1_234_567)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "TAXABLE_INCOME_ROUNDING" in codes


def test_taxable_income_properly_rounded() -> None:
    """課税所得が1,000円単位 → OK。"""
    inp = _make_input()
    res = _make_result(taxable_income=1_234_000)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "TAXABLE_INCOME_ROUNDING" not in codes


# --- 7. RECONSTRUCTION_TAX_MISMATCH ---


def test_reconstruction_tax_mismatch() -> None:
    """復興特別所得税の計算不一致 → error。"""
    inp = _make_input()
    res = _make_result(
        income_tax_after_credits=100_000,
        reconstruction_tax=9_999,  # 正しくは 100,000 * 21 // 1000 = 2,100
    )
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "RECONSTRUCTION_TAX_MISMATCH" in codes


def test_reconstruction_tax_correct() -> None:
    """復興特別所得税が正しい → OK。"""
    inp = _make_input()
    res = _make_result(
        income_tax_after_credits=100_000,
        reconstruction_tax=2_100,
    )
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "RECONSTRUCTION_TAX_MISMATCH" not in codes


# --- 8. CREDITS_EXCEED_TAX ---


def test_credits_exceed_tax() -> None:
    """税額控除が算出税額超過 → warning。"""
    inp = _make_input()
    res = _make_result(
        income_tax_base=50_000,
        total_tax_credits=100_000,
    )
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "CREDITS_EXCEED_TAX" in codes


def test_credits_within_tax() -> None:
    """税額控除が算出税額以下 → OK。"""
    inp = _make_input()
    res = _make_result(
        income_tax_base=200_000,
        total_tax_credits=100_000,
    )
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "CREDITS_EXCEED_TAX" not in codes


# --- 9. NO_WITHHOLDING_ON_SALARY ---


def test_no_withholding_on_salary() -> None:
    """給与ありなのに源泉徴収0 → warning。"""
    inp = _make_input(salary_income=5_000_000, withheld_tax=0)
    res = _make_result()
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "NO_WITHHOLDING_ON_SALARY" in codes


def test_withholding_on_salary() -> None:
    """給与ありで源泉徴収あり → OK。"""
    inp = _make_input(salary_income=5_000_000, withheld_tax=100_000)
    res = _make_result()
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "NO_WITHHOLDING_ON_SALARY" not in codes


# --- 10. REFUND_EXCEEDS_WITHHELD ---


def test_refund_exceeds_withheld() -> None:
    """還付額が源泉徴収+予定納税の合計超過 → error。"""
    inp = _make_input(withheld_tax=100_000, estimated_tax_payment=50_000)
    res = _make_result(tax_due=-200_000)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "REFUND_EXCEEDS_WITHHELD" in codes


def test_refund_within_withheld() -> None:
    """還付額が合計以下 → OK。"""
    inp = _make_input(withheld_tax=100_000, estimated_tax_payment=50_000)
    res = _make_result(tax_due=-100_000)
    check = sanity_check_income_tax(inp, res)
    codes = [item.code for item in check.items]
    assert "REFUND_EXCEEDS_WITHHELD" not in codes


# --- 全チェック pass のケース ---


def test_all_pass() -> None:
    """正常な入出力 → passed=True, items=[]。"""
    inp = _make_input(
        business_revenue=3_000_000,
        business_expenses=1_000_000,
        salary_income=5_000_000,
        withheld_tax=100_000,
    )
    res = _make_result(
        salary_income_after_deduction=3_560_000,
        business_income=1_350_000,
        effective_blue_return_deduction=650_000,
        taxable_income=3_000_000,
        income_tax_base=202_500,
        total_tax_credits=0,
        income_tax_after_credits=202_500,
        reconstruction_tax=4_252,
        total_tax=206_752,
    )
    check = sanity_check_income_tax(inp, res)
    assert check.passed
    assert check.error_count == 0


def _withholding_db(tmp_path: Path, business_tax: int, fee_tax: int) -> str:
    path = str(tmp_path / "withholding.db")
    ledger_init(db_path=path, fiscal_year=2026)
    if business_tax:
        ledger_add_business_withholding(
            db_path=path,
            fiscal_year=2026,
            detail=BusinessWithholdingInput(
                client_name="架空取引先", gross_amount=1320000, withholding_tax=business_tax
            ),
        )
    ledger_add_professional_fee(
        db_path=path,
        fiscal_year=2026,
        detail=ProfessionalFeeInput(
            payer_name="架空税理士",
            payer_address="架空の支払先住所",
            fee_amount=220000,
            expense_deduction=220000,
            withheld_tax=fee_tax,
        ),
    )
    return path


@pytest.mark.parametrize("wrong_side", ["input", "result", "both"])
def test_detects_professional_fee_withholding_mixed_into_personal_tax(
    tmp_path: Path, wrong_side: str
) -> None:
    db = _withholding_db(tmp_path, 134772, 20420)
    input_tax = 155192 if wrong_side in ("input", "both") else 134772
    result_tax = 155192 if wrong_side in ("result", "both") else 134772
    inp = _make_input(fiscal_year=2026, business_withheld_tax=input_tax)
    res = _make_result(fiscal_year=2026, business_withheld_tax=result_tax)

    check = sanity_check_income_tax(inp, res, db_path=db)

    assert not check.passed
    assert "PROFESSIONAL_FEE_WITHHOLDING_MIXED" in [item.code for item in check.items]
    assert inp.business_withheld_tax == input_tax  # 検査だけで自動減算しない。


def test_correct_withholding_is_not_flagged_when_fee_withholding_exists(tmp_path: Path) -> None:
    db = _withholding_db(tmp_path, 134772, 20420)

    check = sanity_check_income_tax(
        _make_input(fiscal_year=2026, business_withheld_tax=134772),
        _make_result(fiscal_year=2026, business_withheld_tax=134772),
        db_path=db,
    )

    assert check.passed
    assert check.items == []


def test_withholding_mismatch_does_not_claim_fee_mixing_without_equal_difference(
    tmp_path: Path,
) -> None:
    db = _withholding_db(tmp_path, 134772, 20420)

    check = sanity_check_income_tax(
        _make_input(fiscal_year=2026, business_withheld_tax=150000),
        _make_result(fiscal_year=2026, business_withheld_tax=150000),
        db_path=db,
    )

    assert not check.passed
    assert [item.code for item in check.items] == ["BUSINESS_WITHHOLDING_LEDGER_MISMATCH"]


def test_fee_withholding_without_personal_withholding_is_detected(tmp_path: Path) -> None:
    db = _withholding_db(tmp_path, 0, 20420)

    check = sanity_check_income_tax(
        _make_input(fiscal_year=2026, business_withheld_tax=20420),
        _make_result(fiscal_year=2026, business_withheld_tax=20420),
        db_path=db,
    )

    assert [item.code for item in check.items] == ["PROFESSIONAL_FEE_WITHHOLDING_MIXED"]


def test_zero_fee_tax_does_not_label_mismatch_as_mixing(tmp_path: Path) -> None:
    db = _withholding_db(tmp_path, 134772, 0)
    check = sanity_check_income_tax(
        _make_input(fiscal_year=2026, business_withheld_tax=140000),
        _make_result(fiscal_year=2026, business_withheld_tax=140000),
        db_path=db,
    )
    assert [item.code for item in check.items] == ["BUSINESS_WITHHOLDING_LEDGER_MISMATCH"]


def test_withholding_check_uses_only_the_selected_year(tmp_path: Path) -> None:
    db = _withholding_db(tmp_path, 134772, 20420)
    ledger_init(db_path=db, fiscal_year=2025)
    ledger_add_professional_fee(
        db_path=db,
        fiscal_year=2025,
        detail=ProfessionalFeeInput(
            payer_name="別年の架空税理士",
            payer_address="架空住所",
            fee_amount=1000000,
            withheld_tax=100000,
        ),
    )
    check = sanity_check_income_tax(
        _make_input(fiscal_year=2026, business_withheld_tax=155192),
        _make_result(fiscal_year=2026, business_withheld_tax=155192),
        db_path=db,
    )
    assert [item.code for item in check.items] == ["PROFESSIONAL_FEE_WITHHOLDING_MIXED"]


def test_withholding_check_never_creates_a_missing_db(tmp_path: Path) -> None:
    db = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        sanity_check_income_tax(_make_input(), _make_result(), db_path=str(db))
    assert not db.exists()


def test_withholding_check_rejects_a_missing_fiscal_year(tmp_path: Path) -> None:
    db = _withholding_db(tmp_path, 134772, 20420)
    with pytest.raises(ValueError, match="2025"):
        sanity_check_income_tax(_make_input(), _make_result(), db_path=db)
