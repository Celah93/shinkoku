"""年分別の追加税、高所得特例、住民税資料からのふるさと納税上限推定。"""

from __future__ import annotations

from shinkoku.models import (
    FurusatoLimitInput,
    FurusatoLimitResult,
    IncomeSpecialTaxResult,
    MinimumIncomeTaxInput,
    MinimumIncomeTaxResult,
)
from shinkoku.tax_constants import (
    FURUSATO_FIXED_SPECIAL_CREDIT_CAPS,
    FURUSATO_SELF_BURDEN,
    INCOME_TAX_TABLE,
    INCOME_TAX_TOP_RATE,
    MINIMUM_INCOME_TAX_RULES,
    RECONSTRUCTION_TAX_DENOMINATOR,
    get_income_tax_constants,
)
from shinkoku.tax_year_support import require_supported_tax_year


def calc_income_special_taxes(base_income_tax: int, fiscal_year: int) -> IncomeSpecialTaxResult:
    """防衛財確法5の22: 税目別の参考内訳と、整数の分子を合算した円単位税額。"""
    if type(base_income_tax) is not int or base_income_tax < 0:
        raise ValueError("base_income_tax は0以上の円単位整数で指定してください")
    constants = get_income_tax_constants(fiscal_year)
    denominator = RECONSTRUCTION_TAX_DENOMINATOR
    reconstruction_numerator = base_income_tax * constants.reconstruction_tax_rate_per_mille
    defense_numerator = base_income_tax * constants.defense_tax_rate_per_mille
    reconstruction_tax = reconstruction_numerator // denominator
    defense_tax = defense_numerator // denominator
    combined = (reconstruction_numerator + defense_numerator) // denominator
    return IncomeSpecialTaxResult(
        reconstruction_tax=reconstruction_tax,
        defense_tax=defense_tax,
        combined_special_tax=combined,
        rounding_adjustment=combined - reconstruction_tax - defense_tax,
        reconstruction_numerator=reconstruction_numerator,
        defense_numerator=defense_numerator,
        denominator=denominator,
    )


def calc_minimum_income_tax(data: MinimumIncomeTaxInput) -> MinimumIncomeTaxResult:
    """国税庁適用判定表⑬〜㉔。申告不要所得がある場合は二段階で判定する。"""
    require_supported_tax_year(data.fiscal_year, "minimum_income_tax")
    if data.income_scope_confirmed is False or (
        data.calculation_mode == "filing" and data.income_scope_confirmed is not True
    ):
        raise ValueError(
            "高所得特例では申告不要所得を含む全所得の確認が必要です（income_scope_confirmed）"
        )
    threshold, rate = MINIMUM_INCOME_TAX_RULES[data.fiscal_year]
    base_income = sum(data.incomes.model_dump().values())
    # 計算書⑭で千円未満切捨て。個々の所得では丸めない。
    excess = max(0, base_income - threshold) // 1000 * 1000
    benchmark = excess * rate // 1000
    special = calc_income_special_taxes(data.ordinary_income_tax, data.fiscal_year)
    ordinary_total = data.ordinary_income_tax + special.combined_special_tax
    initial_base = ordinary_total + data.nonfiling_income_withheld_tax
    initial_additional = max(0, benchmark - initial_base)
    warnings = (
        []
        if data.income_scope_confirmed
        else ["全所得の確認前の試算です。所得の漏れがあれば判定が変わります"]
    )
    common = dict(
        fiscal_year=data.fiscal_year,
        calculation_mode=data.calculation_mode,
        income_scope_confirmed=data.income_scope_confirmed is True,
        base_income_amount=base_income,
        threshold=threshold,
        rate_numerator=rate,
        rate_denominator=1000,
        rounded_excess_income=excess,
        benchmark_tax=benchmark,
        ordinary_tax_with_special=ordinary_total,
        initial_base_tax=initial_base,
        initial_additional_tax=initial_additional,
        warnings=warnings,
    )
    if initial_additional == 0:
        return MinimumIncomeTaxResult(
            **common,
            status="not_applicable",
            additional_income_tax=0,
            adjusted_income_tax=data.ordinary_income_tax,
            final_special_taxes=special,
            total_tax=ordinary_total,
        )
    if data.uses_nonfiling_system and data.recalculated_income_tax is None:
        return MinimumIncomeTaxResult(**common, status="requires_recalculation")
    # 計算書⑳: 申告不要制度を適用せず、人的控除等の所得制限も再判定した所得税。
    recomputed = (
        data.recalculated_income_tax if data.uses_nonfiling_system else data.ordinary_income_tax
    )
    assert recomputed is not None
    recomputed_special = calc_income_special_taxes(recomputed, data.fiscal_year)
    recomputed_base = recomputed + recomputed_special.combined_special_tax
    additional = max(0, benchmark - recomputed_base)
    if additional == 0:
        # 計算書㉓が0以下なら特例なし。申告不要制度を強制解除せず元の申告を保持する。
        return MinimumIncomeTaxResult(
            **common,
            status="not_applicable",
            recalculated_income_tax=recomputed,
            recalculated_base_tax=recomputed_base,
            additional_income_tax=0,
            adjusted_income_tax=data.ordinary_income_tax,
            final_special_taxes=special,
            total_tax=ordinary_total,
        )
    adjusted = recomputed + additional
    # ㉓の追加所得税も復興・防衛税の課税標準に加える。1.021で割り戻さない。
    final_special = calc_income_special_taxes(adjusted, data.fiscal_year)
    return MinimumIncomeTaxResult(
        **common,
        status="applicable",
        recalculated_income_tax=recomputed,
        recalculated_base_tax=recomputed_base,
        additional_income_tax=additional,
        adjusted_income_tax=adjusted,
        final_special_taxes=final_special,
        total_tax=adjusted + final_special.combined_special_tax,
    )


def calc_furusato_limit_detailed(data: FurusatoLimitInput) -> FurusatoLimitResult:
    """地法37の2・314の7。住民税所得割と税率判定用所得から寄附上限を概算する。"""
    require_supported_tax_year(data.fiscal_year, "furusato_limit")
    # 財務省932頁: 基礎控除の48万円超部分のみ0を下限とする。
    adjustment = data.personal_deduction_difference + max(
        0, data.income_tax_basic_deduction - 480_000
    )
    taxable = data.resident_taxable_income // 1000 * 1000
    rate_income = max(0, taxable - adjustment)
    rate: int
    if data.income_tax_rate_percent is None:
        rate = 0 if rate_income == 0 else INCOME_TAX_TOP_RATE
        if rate_income > 0:
            for upper, bracket_rate, _ in INCOME_TAX_TABLE:
                if rate_income <= upper:
                    rate = bracket_rate
                    break
    else:
        rate = data.income_tax_rate_percent
    year = get_income_tax_constants(data.fiscal_year)
    special_multiplier = (
        1000 + year.reconstruction_tax_rate_per_mille + year.defense_tax_rate_per_mille
    )
    # 率を途中で丸めない: 90% - 限界税率*(1+追加税率)。分母は100000。
    denominator = 100_000
    special_rate = 90_000 - rate * special_multiplier
    proportional_cap = data.resident_tax_income_levy * 20 // 100
    fixed_cap = FURUSATO_FIXED_SPECIAL_CREDIT_CAPS[data.fiscal_year]
    credit_limit = min(proportional_cap, fixed_cap) if fixed_cap is not None else proportional_cap
    limit = credit_limit * denominator // special_rate + FURUSATO_SELF_BURDEN if credit_limit else 0
    return FurusatoLimitResult(
        fiscal_year=data.fiscal_year,
        resident_tax_assessment_year=data.fiscal_year + 1,
        estimated_limit=limit,
        resident_tax_income_levy=data.resident_tax_income_levy,
        rate_adjustment=adjustment,
        rate_taxable_income=rate_income,
        income_tax_rate_percent=rate,
        special_credit_rate_numerator=special_rate,
        special_credit_rate_denominator=denominator,
        income_levy_twenty_percent=proportional_cap,
        fixed_special_credit_cap=fixed_cap,
        special_credit_limit=credit_limit,
        fixed_cap_applied=fixed_cap is not None and proportional_cap > fixed_cap,
        warnings=[
            "標準税率による住民税所得割（調整控除後・他の税額控除前）を使う概算です。",
            "住宅ローン控除・高所得特例・分離課税・他の寄附や所得変動による実負担は別に確認してください。",
        ],
    )
