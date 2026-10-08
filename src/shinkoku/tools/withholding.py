"""源泉徴収票の原本値を変更しない共通検算。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal, cast

from pydantic import ValidationError

from shinkoku.models import (
    WithholdingSlipInput,
    WithholdingSlipRecord,
    WithholdingSlipValidationIssue,
    WithholdingSlipValidationResult,
)

DEDUCTION_FIELDS = (
    "social_insurance",
    "life_insurance_deduction",
    "earthquake_insurance_deduction",
    "spouse_deduction",
    "dependent_deduction",
    "specific_relative_special_deduction",
    "basic_deduction",
    "other_personal_deductions",
)
BLANK_AS_ZERO = {
    "social_insurance",
    "social_insurance_small_business_mutual_aid",
    "life_insurance_deduction",
    "earthquake_insurance_deduction",
    "spouse_deduction",
    "specific_relative_special_deduction",
}


def withholding_slip_from_row(row: Mapping[str, object]) -> WithholdingSlipRecord:
    """DBのNULL・JSON・確認フラグを、共通の厳密なモデルへ戻す。"""
    data = {name: row.get(name) for name in WithholdingSlipRecord.model_fields}
    try:
        for name in ("year_end_adjusted", "source_confirmed"):
            value = data[name]
            if value is not None:
                if type(value) is not int or value not in (0, 1):
                    raise ValueError("確認フラグの型が不正です")
                data[name] = bool(value)
        blanks = data["blank_fields"]
        data["blank_fields"] = [] if blanks is None else json.loads(cast(str, blanks))
        return WithholdingSlipRecord.model_validate(data)
    except (ValidationError, ValueError, TypeError):
        raise ValueError("保存済みの源泉徴収票の項目、型または空欄指定が不正です") from None


def _effective_amount(slip: WithholdingSlipInput, name: str, *, blank_as_zero: bool) -> int | None:
    value = cast(int | None, getattr(slip, name))
    if value is None and blank_as_zero and name in slip.blank_fields:
        return 0
    return value


def get_withholding_social_insurance(slip: WithholdingSlipInput) -> int | None:
    """掛金の内書きを除く。確認済み空欄は有効値だけを0とする。"""
    total = _effective_amount(slip, "social_insurance", blank_as_zero=True)
    inner = _effective_amount(
        slip, "social_insurance_small_business_mutual_aid", blank_as_zero=True
    )
    if total is None or inner is None or inner > total:
        return None
    return total - inner


def check_withholding_slip(
    slip: WithholdingSlipInput, *, fiscal_year: int
) -> WithholdingSlipValidationResult:
    """年末調整の控除合計を照合する。適用要件やOCR精度は証明しない。"""
    issues: list[WithholdingSlipValidationIssue] = []
    missing: list[str] = []

    def issue(
        severity: Literal["error", "warning", "info"], code: str, fields: list[str], message: str
    ) -> None:
        issues.append(
            WithholdingSlipValidationIssue(
                severity=severity, code=code, fields=fields, message=message
            )
        )

    if slip.document_fiscal_year is None:
        missing.append("document_fiscal_year")
    elif slip.document_fiscal_year != fiscal_year:
        issue(
            "error",
            "WS_FISCAL_YEAR_MISMATCH",
            ["document_fiscal_year"],
            "原本の年分と対象年分が一致しません",
        )
    if slip.year_end_adjusted is None:
        missing.append("year_end_adjusted")
    if slip.source_confirmed is not True:
        issue(
            "warning",
            "WS_SOURCE_NOT_CONFIRMED",
            ["source_confirmed"],
            "原本のラベル・金額・年分・内書き・摘要の照合が完了していません",
        )
    for name in ("payment_amount", "withheld_tax"):
        if getattr(slip, name) is None:
            missing.append(name)
    for name in ("social_insurance", "social_insurance_small_business_mutual_aid"):
        if _effective_amount(slip, name, blank_as_zero=True) is None:
            missing.append(name)
    total = _effective_amount(slip, "social_insurance", blank_as_zero=True)
    inner = _effective_amount(
        slip, "social_insurance_small_business_mutual_aid", blank_as_zero=True
    )
    if total is not None and inner is not None and inner > total:
        issue(
            "error",
            "WS_INVALID_INNER_AMOUNT",
            ["social_insurance", "social_insurance_small_business_mutual_aid"],
            "掛金の内書き額が社会保険料等の総額を超えています",
        )

    calculated: int | None = None
    difference: int | None = None
    status: Literal["matched", "mismatched", "incomplete", "not_applicable"] = "incomplete"
    if slip.year_end_adjusted is False:
        conflicts = [
            name
            for name in (
                "total_income_deductions",
                "salary_income_after_deduction",
                "basic_deduction",
            )
            if getattr(slip, name) is not None
        ]
        if conflicts:
            issue(
                "error",
                "WS_YEAR_END_STATUS_CONFLICT",
                ["year_end_adjusted", *conflicts],
                "年末調整未済という確認と記載額が矛盾しています。原本へ戻って確認してください",
            )
        else:
            status = "not_applicable"
    elif slip.year_end_adjusted is True:
        amounts = {
            name: _effective_amount(slip, name, blank_as_zero=name in BLANK_AS_ZERO)
            for name in DEDUCTION_FIELDS
        }
        for name in ("dependent_deduction", "other_personal_deductions"):
            if amounts[name] and not (slip.deduction_derivation_note or "").strip():
                amounts[name] = None
                missing.append("deduction_derivation_note")
        missing.extend(name for name, value in amounts.items() if value is None)
        if slip.total_income_deductions is None:
            missing.append("total_income_deductions")
        if slip.salary_income_after_deduction is None:
            missing.append("salary_income_after_deduction")
        if (
            all(value is not None for value in amounts.values())
            and slip.total_income_deductions is not None
        ):
            # 内書き・国民年金・住宅ローンは、この8項目へ再加算しない。
            calculated = sum(cast(int, value) for value in amounts.values())
            difference = calculated - slip.total_income_deductions
            status = "matched" if difference == 0 else "mismatched"
            if difference:
                issue(
                    "error",
                    "WS_DEDUCTION_TOTAL_MISMATCH",
                    ["total_income_deductions", *DEDUCTION_FIELDS],
                    f"控除内訳の合計と記載合計が一致しません（差額{difference:,}円）",
                )
    missing = list(dict.fromkeys(missing))
    if missing:
        issue(
            "warning",
            "WS_FIELDS_UNCONFIRMED",
            missing,
            "計算に必要な項目が未確認です。未読を0で補わず原本と資料を確認してください",
        )
    return WithholdingSlipValidationResult(
        status=status,
        reported_total=slip.total_income_deductions,
        calculated_total=calculated,
        difference=difference,
        missing_fields=missing,
        issues=issues,
        ready_for_calculation=(status in {"matched", "not_applicable"} and not issues),
    )
