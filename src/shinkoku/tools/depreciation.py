"""DBアクセスを持たない償却の詳細計算。従来の方式別の丸めを維持する。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from shinkoku.models import (
    DepreciationAnnualContext,
    DepreciationCalculationInput,
    DepreciationDetailResult,
    SmallAssetTreatment,
)
from shinkoku.tax_constants import (
    DEPRECIATION_MODERN_ACQUISITION_START,
    DEPRECIATION_TANGIBLE_MEMO_VALUE,
    SMALL_ASSET_POOLED_DEPRECIATION_YEARS,
)


def depreciation_months(
    fiscal_year: int, placed_in_service_date: date, explicit_months: int | None = None
) -> int:
    """処分のない暦年の供用月数。月途中でも供用月を含める（一般用手引き4頁）。"""
    date(fiscal_year, 12, 31)  # 有効な暦年かを先に検証する。
    if placed_in_service_date.year > fiscal_year:
        months = 0
    elif placed_in_service_date.year < fiscal_year:
        months = 12
    else:
        months = 13 - placed_in_service_date.month
    if explicit_months is not None and explicit_months != months:
        raise ValueError(
            f"months={explicit_months} は供用日と年分から求めた月数{months}と一致しません"
        )
    return months


def calculate_depreciation_details(
    *,
    method: Literal["straight_line", "declining_balance"],
    acquisition_cost: int,
    useful_life: int,
    business_use_ratio: int,
    months: int | None = None,
    book_value: int | None = None,
    declining_rate: int | None = None,
    treatment: SmallAssetTreatment = "normal_depreciation",
    annual_context: DepreciationAnnualContext | None = None,
) -> DepreciationDetailResult:
    """従来の単発算式と、確認済みの年次文脈による終端制約を一箇所で計算する。"""
    opening = None
    memo_value = None
    if annual_context is not None:
        if (
            method != "straight_line"
            or treatment != "normal_depreciation"
            or business_use_ratio != 100
        ):
            raise ValueError("年次計算は定額法・通常償却・100％事業用だけに対応しています")
        if acquisition_cost <= 0 or useful_life <= 0:
            raise ValueError("取得価額と耐用年数は正の整数が必要です")
        acquired = date.fromisoformat(annual_context.acquisition_date)
        service = date.fromisoformat(annual_context.placed_in_service_date)
        if acquired < DEPRECIATION_MODERN_ACQUISITION_START:
            raise ValueError("年次計算は旧定額法の取得時期には対応していません")
        if acquired.year > annual_context.fiscal_year:
            raise ValueError("取得年が対象年度より後です")
        accumulated = annual_context.opening_accumulated_depreciation
        if service.year >= annual_context.fiscal_year and accumulated != 0:
            raise ValueError("当年以後に初めて供用する資産の期首累計は0である必要があります")
        memo_value = DEPRECIATION_TANGIBLE_MEMO_VALUE
        opening = acquisition_cost - accumulated
        if opening < memo_value:
            raise ValueError("期首簿価が備忘価額を下回っています。期首累計を確認してください")
        months = depreciation_months(annual_context.fiscal_year, service, months)
    elif months is None:
        months = 12

    basis = acquisition_cost
    denominator = 1000
    prorated = treatment == "normal_depreciation"
    if treatment != "normal_depreciation":
        if business_use_ratio != 100:
            raise ValueError("少額資産の特別な処理と事業割合の丸め位置は未確認です")
        denominator = (
            SMALL_ASSET_POOLED_DEPRECIATION_YEARS if treatment == "pooled_depreciation" else 1
        )
        numerator = 1
        ordinary = -(-acquisition_cost // denominator)
        expense = ordinary
    elif method == "straight_line":
        numerator = -(-1000 // useful_life) if useful_life > 0 else 0
        if useful_life <= 0 or months <= 0:
            ordinary = expense = 0
        else:
            # 既存の二段階の切上げをそのまま移す。最後にまとめて丸めない。
            ordinary = -(-(acquisition_cost * numerator * months) // (1000 * 12))
            expense = -(-(ordinary * business_use_ratio) // 100)
    else:
        if book_value is None or declining_rate is None:
            raise ValueError("定率法では book_value と declining_rate が必要です")
        basis, numerator = book_value, declining_rate
        if book_value <= 0 or months <= 0:
            ordinary = expense = 0
        else:
            ordinary = book_value * declining_rate * months // (1000 * 12)
            # 表示用ordinaryへ再度割合を掛けると従来額が変わるため、一段階を維持する。
            expense = book_value * declining_rate * business_use_ratio * months // (1000 * 100 * 12)

    unconstrained = ordinary
    closing = None
    if opening is not None:
        assert memo_value is not None
        ordinary = min(ordinary, opening - memo_value)
        expense = ordinary  # 年次の初版は100％事業用だけである。
        closing = opening - ordinary
    return DepreciationDetailResult(
        method=method if prorated else treatment,
        treatment=treatment,
        depreciation_basis=basis,
        rate_numerator=numerator,
        rate_denominator=denominator,
        months=months,
        monthly_proration_applied=prorated,
        business_use_ratio=business_use_ratio,
        unconstrained_ordinary_amount=unconstrained,
        ordinary_amount=ordinary,
        expense_amount=expense,
        annual_context_applied=annual_context is not None,
        memo_value_constraint_applied=annual_context is not None,
        capped_to_book_value=ordinary != unconstrained,
        memo_value=memo_value,
        opening_book_value=opening,
        closing_book_value=closing,
    )


def depreciation_details_from_input(data: DepreciationCalculationInput) -> DepreciationDetailResult:
    """月数の省略と、明示された月数を区別して共通計算へ渡す。"""
    months = (
        data.months if data.annual_context is None or "months" in data.model_fields_set else None
    )
    return calculate_depreciation_details(
        method=data.method,
        acquisition_cost=data.acquisition_cost,
        useful_life=data.useful_life,
        business_use_ratio=data.business_use_ratio,
        months=months,
        book_value=data.book_value,
        declining_rate=data.declining_rate,
        annual_context=data.annual_context,
    )
