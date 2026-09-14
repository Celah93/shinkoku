"""住宅ローンの単体計算。入居年ルールと年間所得税の対応年分を分ける。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from shinkoku.models import (
    HousingLoanCalculationInput,
    HousingLoanCalculationResult,
    HousingLoanCreditEntry,
    HousingLoanDetail,
)
from shinkoku.tax_constants import HousingLoanRule
from shinkoku.tools.tax_calc import (
    _calc_housing_loan_credit_dual_details,
    _calculate_housing_loan_entry,
    resolve_housing_loan_rule,
)


def _checked_rule(data: HousingLoanCalculationInput, detail: HousingLoanDetail) -> HousingLoanRule:
    move_in = date.fromisoformat(detail.move_in_date)
    for value in (detail.building_confirmation_date, detail.building_completion_date):
        if value and date.fromisoformat(value) > move_in:
            raise ValueError("建築確認日・建築日は入居日より後にはできません")
    area, residential = detail.total_floor_area, detail.residential_floor_area
    if not area or not residential:
        raise ValueError(
            "total_floor_area と residential_floor_area を平方メートル×100で指定してください"
        )
    if residential > area:
        raise ValueError("residential_floor_area は total_floor_area を超えられません")
    if detail.loan_term_years is None:
        raise ValueError("loan_term_years の確認が必要です")
    if 4000 <= area < 5000 and move_in.year < 2026:
        raise ValueError("2025年以前入居の40㎡以上50㎡未満の特例は単体計算の対象外です")

    rule = resolve_housing_loan_rule(
        detail,
        taxpayer_birth_date=data.taxpayer_birth_date,
        spouse_birth_date=data.spouse_birth_date,
        spouse_income=data.spouse_income,
        dependents=list(data.dependents),
        allow_childcare_increase=area >= 5000,
    )
    reason = None
    if data.aggregate_income > 20_000_000:
        reason = "合計所得金額が2,000万円を超える年は対象外です"
    elif area < 4000:
        reason = "床面積が40㎡未満の住宅は対象外です"
    elif area < 5000 and data.aggregate_income > 10_000_000:
        reason = "40㎡以上50㎡未満の特例は合計所得金額1,000万円以下の年に限ります"
    elif residential * 2 < area:
        reason = "居住用部分が床面積の2分の1未満の住宅は対象外です"
    elif detail.loan_term_years < 10:
        reason = "償還期間が10年未満の借入れは対象外です"
    if reason:
        return replace(rule, eligible=False, warning=reason)
    if area < 5000 and rule.eligible:
        return replace(
            rule, warning="40㎡以上50㎡未満の特例を適用し、子育て世帯等の限度額上乗せは使いません"
        )
    return rule


def calc_housing_loan(data: HousingLoanCalculationInput) -> HousingLoanCalculationResult:
    """確認済みの借入対象残高について、税額上限を適用する前の控除可能額を返す。"""
    if not data.other_requirements_confirmed:
        raise ValueError("居住・取得・借入対象残高等の残る適用要件を確認してください")
    groups: dict[str, list[HousingLoanDetail]] = {}
    for i, input_detail in enumerate(data.housing_loan_details):
        key = (
            f"group:{input_detail.dual_application_group}"
            if input_detail.dual_application_group
            else f"single:{i}"
        )
        groups.setdefault(key, []).append(input_detail)
    total = 0
    entries: list[HousingLoanCreditEntry] = []
    warnings = [
        "年間所得税・住民税の税額上限を適用する前の控除可能額です。申告税額ではありません。",
        "居住・取得・借入残高の対象範囲等は other_requirements_confirmed の確認結果を使用しています。",
    ]
    for details in groups.values():
        rules = [_checked_rule(data, detail) for detail in details]
        if len(details) > 1:
            credit, group_entries, group_warnings = _calc_housing_loan_credit_dual_details(
                details,
                claim_fiscal_year=data.claim_fiscal_year,
                taxpayer_birth_date=data.taxpayer_birth_date,
                spouse_birth_date=data.spouse_birth_date,
                spouse_income=data.spouse_income,
                dependents=list(data.dependents),
                resolved_rules=rules,
            )
            total += credit
            entries.extend(group_entries)
            warnings.extend(group_warnings)
        else:
            detail, rule = details[0], rules[0]
            entry, _ = _calculate_housing_loan_entry(
                detail=detail,
                balance=detail.year_end_balance,
                claim_fiscal_year=data.claim_fiscal_year,
                proration_ratio_pct=10_000,
                allow_expired=True,
                taxpayer_birth_date=data.taxpayer_birth_date,
                spouse_birth_date=data.spouse_birth_date,
                spouse_income=data.spouse_income,
                dependents=list(data.dependents),
                resolved_rule=rule,
            )
            total += entry.credit
            entries.append(entry)
            if rule.warning:
                warnings.append(rule.warning)
    return HousingLoanCalculationResult(
        claim_fiscal_year=data.claim_fiscal_year,
        housing_loan_credit=total,
        entries=entries,
        warnings=list(dict.fromkeys(warnings)),
    )
