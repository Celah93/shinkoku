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
from tests.helpers.withholding import withholding_input


def _make_input(**kwargs) -> IncomeTaxInput:
    defaults = {"fiscal_year": 2025}
    defaults.update(kwargs)
    return IncomeTaxInput(**defaults)


def _make_result(**kwargs) -> IncomeTaxResult:
    defaults = {"fiscal_year": 2025, "tax_due": 0}
    defaults.update(kwargs)
    return IncomeTaxResult(**defaults)


def _salary_db(tmp_path: Path, **changes) -> tuple[str, int]:
    from shinkoku.models import WithholdingSlipInput
    from shinkoku.tools.ledger import ledger_save_withholding_slip

    db = str(tmp_path / "salary.db")
    ledger_init(db_path=db, fiscal_year=2025)
    saved = ledger_save_withholding_slip(
        db_path=db, fiscal_year=2025, detail=WithholdingSlipInput(**withholding_input(**changes))
    )
    assert saved["status"] == "ok"
    return db, saved["withholding_slip_id"]


def _salary_params(mode: str = "estimate", **changes) -> IncomeTaxInput:
    return _make_input(
        salary_income=5000000,
        withheld_tax=77500,
        social_insurance=750000,
        blue_return_deduction=0,
        minimum_tax_income_complete=True,
        calculation_mode=mode,
        **changes,
    )


@pytest.mark.parametrize("value", [[], [1, 1], [0], [-1], [True], [1.0], ["1"]])
def test_salary_evidence_selection_is_strict(value: list) -> None:
    from pydantic import ValidationError
    from shinkoku.models import SalaryEvidenceInput

    with pytest.raises(ValidationError):
        SalaryEvidenceInput(slip_ids=value)


@pytest.mark.parametrize("mode,severity", [("estimate", "warning"), ("filing", "error")])
def test_salary_evidence_required_by_mode(tmp_path: Path, mode: str, severity: str) -> None:
    from shinkoku.tools.tax_calc import calc_income_tax

    db, _ = _salary_db(tmp_path)
    params = _salary_params(mode)
    checked = sanity_check_income_tax(params, calc_income_tax(params), db_path=db)
    item = next(item for item in checked.items if item.code == "SALARY_EVIDENCE_UNCONFIRMED")
    assert item.severity == severity
    assert checked.passed is (mode == "estimate")


@pytest.mark.parametrize("mode", ["estimate", "filing"])
@pytest.mark.parametrize(
    "field,code",
    [
        ("salary_income", "SALARY_AMOUNT_LEDGER_MISMATCH"),
        ("withheld_tax", "SALARY_WITHHOLDING_LEDGER_MISMATCH"),
        ("social_insurance", "SALARY_SOCIAL_INSURANCE_LEDGER_MISMATCH"),
        ("result_withheld_tax", "SALARY_WITHHOLDING_LEDGER_MISMATCH"),
    ],
)
def test_salary_ledger_mismatches_are_errors_in_both_modes(
    tmp_path: Path, mode: str, field: str, code: str
) -> None:
    from shinkoku.models import SalaryEvidenceInput
    from shinkoku.tools.tax_calc import calc_income_tax

    db, wid = _salary_db(tmp_path)
    params = _salary_params(mode)
    if field != "result_withheld_tax":
        params = params.model_copy(update={field: getattr(params, field) + 1})
    result = calc_income_tax(params)
    if field == "result_withheld_tax":
        result = result.model_copy(update={"withheld_tax": result.withheld_tax + 1})
    checked = sanity_check_income_tax(
        params,
        result,
        db_path=db,
        salary_evidence=SalaryEvidenceInput(
            slip_ids=[wid], selection_confirmed=True, additional_social_insurance=0
        ),
    )
    assert any(item.code == code and item.severity == "error" for item in checked.items)
    assert checked.passed is False


@pytest.mark.parametrize("mode,severity", [("estimate", "warning"), ("filing", "error")])
@pytest.mark.parametrize("changes", [{"source_confirmed": None}, {"payment_amount": None}])
def test_unconfirmed_salary_slip_is_reported_by_mode(
    tmp_path: Path, mode: str, severity: str, changes: dict
) -> None:
    from shinkoku.models import SalaryEvidenceInput
    from shinkoku.tools.tax_calc import calc_income_tax

    db, wid = _salary_db(tmp_path, **changes)
    params = _salary_params(mode)
    checked = sanity_check_income_tax(
        params,
        calc_income_tax(params),
        db_path=db,
        salary_evidence=SalaryEvidenceInput(
            slip_ids=[wid], selection_confirmed=True, additional_social_insurance=0
        ),
    )
    assert any(
        item.code == "SALARY_EVIDENCE_UNCONFIRMED" and item.severity == severity
        for item in checked.items
    )


def test_salary_ledger_uses_confirmed_blank_without_hiding_unread_null(tmp_path: Path) -> None:
    from shinkoku.db import get_connection
    from shinkoku.models import SalaryEvidenceInput
    from shinkoku.tools.tax_calc import calc_income_tax

    blank = withholding_input()["blank_fields"] + ["social_insurance"]
    db, wid = _salary_db(
        tmp_path, social_insurance=None, total_income_deductions=1290000, blank_fields=blank
    )
    params = _salary_params().model_copy(update={"social_insurance": 0})
    evidence = SalaryEvidenceInput(
        slip_ids=[wid], selection_confirmed=True, additional_social_insurance=0
    )
    checked = sanity_check_income_tax(
        params, calc_income_tax(params), db_path=db, salary_evidence=evidence
    )
    assert not any(item.code.startswith("SALARY_") for item in checked.items)
    conn = get_connection(db)
    conn.execute(
        "UPDATE withholding_slips SET blank_fields=? WHERE id=?",
        ('["social_insurance_small_business_mutual_aid"]', wid),
    )
    conn.commit()
    conn.close()
    checked = sanity_check_income_tax(
        params, calc_income_tax(params), db_path=db, salary_evidence=evidence
    )
    assert any(item.code == "SALARY_EVIDENCE_UNCONFIRMED" for item in checked.items)


def test_salary_evidence_requires_db_and_checks_selected_zero_salary(tmp_path: Path) -> None:
    from shinkoku.models import SalaryEvidenceInput
    from shinkoku.tools.tax_calc import calc_income_tax

    evidence = SalaryEvidenceInput(
        slip_ids=[999], selection_confirmed=True, additional_social_insurance=0
    )
    params = _make_input(blue_return_deduction=0)
    result = calc_income_tax(params)
    with pytest.raises(ValueError, match="DB"):
        sanity_check_income_tax(params, result, salary_evidence=evidence)
    db, _ = _salary_db(tmp_path)
    checked = sanity_check_income_tax(params, result, db_path=db, salary_evidence=evidence)
    assert any(item.code == "SALARY_EVIDENCE_NOT_FOUND" for item in checked.items)


def test_salary_check_is_read_only_and_uses_only_selected_ids(tmp_path: Path, monkeypatch) -> None:
    import shinkoku.db as database
    from shinkoku.models import SalaryEvidenceInput, WithholdingSlipInput
    from shinkoku.tools.ledger import ledger_save_withholding_slip
    from shinkoku.tools.tax_calc import calc_income_tax

    db, wid = _salary_db(tmp_path)
    ledger_save_withholding_slip(
        db_path=db, fiscal_year=2025, detail=WithholdingSlipInput(**withholding_input())
    )
    original = database.get_connection
    conn = original(db)
    before = list(conn.iterdump())
    conn.close()

    def read_only(path):
        connection = original(path)
        connection.execute("PRAGMA query_only=ON")
        return connection

    monkeypatch.setattr(database, "get_connection", read_only)
    params = _salary_params()
    checked = sanity_check_income_tax(
        params,
        calc_income_tax(params),
        db_path=db,
        salary_evidence=SalaryEvidenceInput(
            slip_ids=[wid], selection_confirmed=True, additional_social_insurance=0
        ),
    )
    assert not any(item.code.startswith("SALARY_") for item in checked.items)
    conn = original(db)
    assert list(conn.iterdump()) == before
    conn.close()


def test_salary_old_db_is_not_migrated(tmp_path: Path) -> None:
    from tests.unit.test_withholding_migration import make_legacy_withholding_db
    from shinkoku.db import get_connection
    from shinkoku.models import SalaryEvidenceInput
    from shinkoku.tools.tax_calc import calc_income_tax

    db = tmp_path / "old.db"
    make_legacy_withholding_db(db)
    conn = get_connection(str(db))
    before = list(conn.iterdump())
    conn.close()

    params = _salary_params()
    with pytest.raises(ValueError, match="移行"):
        sanity_check_income_tax(
            params,
            calc_income_tax(params),
            db_path=str(db),
            salary_evidence=SalaryEvidenceInput(
                slip_ids=[7], selection_confirmed=True, additional_social_insurance=0
            ),
        )
    conn = get_connection(str(db))
    assert list(conn.iterdump()) == before
    conn.close()


@pytest.mark.parametrize("unconfirmed", ["selection", "source"])
def test_estimate_unconfirmed_salary_evidence_keeps_explicit_assumptions(
    tmp_path: Path, unconfirmed: str
) -> None:
    from shinkoku.models import SalaryEvidenceInput
    from shinkoku.tools.tax_calc import calc_income_tax

    db, wid = _salary_db(
        tmp_path, **({"source_confirmed": None} if unconfirmed == "source" else {})
    )
    params = _salary_params().model_copy(update={"salary_income": 6000000})
    evidence = SalaryEvidenceInput(
        slip_ids=[wid],
        selection_confirmed=None if unconfirmed == "selection" else True,
        additional_social_insurance=0,
    )
    result = sanity_check_income_tax(
        params, calc_income_tax(params), db_path=db, salary_evidence=evidence
    )
    assert any(
        item.code == "SALARY_EVIDENCE_UNCONFIRMED" and item.severity == "warning"
        for item in result.items
    )
    assert not any(item.code.endswith("LEDGER_MISMATCH") for item in result.items)
    assert result.error_count == 0 and result.passed is True


# --- 1. BLUE_DEDUCTION_ON_LOSS ---


def test_salary_other_year_and_known_slip_conflict_remain_errors(tmp_path: Path) -> None:
    from shinkoku.db import get_connection
    from shinkoku.models import SalaryEvidenceInput
    from shinkoku.tools.tax_calc import calc_income_tax

    db, wid = _salary_db(tmp_path)
    evidence = SalaryEvidenceInput(
        slip_ids=[wid], selection_confirmed=True, additional_social_insurance=0
    )
    params = _salary_params()
    conn = get_connection(db)
    conn.execute("UPDATE withholding_slips SET total_income_deductions=1 WHERE id=?", (wid,))
    conn.commit()
    conn.close()
    checked = sanity_check_income_tax(
        params, calc_income_tax(params), db_path=db, salary_evidence=evidence
    )
    assert any(
        item.code == "WS_DEDUCTION_TOTAL_MISMATCH" and item.severity == "error"
        for item in checked.items
    )
    assert checked.passed is False
    ledger_init(db_path=db, fiscal_year=2026)
    params = params.model_copy(update={"fiscal_year": 2026})
    checked = sanity_check_income_tax(
        params, calc_income_tax(params), db_path=db, salary_evidence=evidence
    )
    assert any(
        item.code == "SALARY_EVIDENCE_FISCAL_YEAR_MISMATCH" and item.severity == "error"
        for item in checked.items
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("selection_confirmed", 1),
        ("additional_social_insurance", False),
        ("additional_social_insurance", 1.0),
        ("additional_social_insurance", "0"),
        ("additional_social_insurance", -1),
        ("unknown", 0),
    ],
)
def test_salary_evidence_confirmation_and_amount_are_strict(field: str, value: object) -> None:
    from pydantic import ValidationError
    from shinkoku.models import SalaryEvidenceInput

    with pytest.raises(ValidationError):
        SalaryEvidenceInput(slip_ids=[1], **{field: value})


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
