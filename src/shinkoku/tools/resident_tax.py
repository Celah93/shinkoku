"""住民税の控除元データから標準所得割を推定し、ふるさと納税計算へ接続する。"""

from __future__ import annotations

from shinkoku.models import (
    FurusatoLimitInput,
    ResidentLifeInsuranceInput,
    ResidentTaxDeductionItem,
    ResidentTaxEstimateInput,
    ResidentTaxEstimateResult,
    ResidentTaxRelativeInput,
)
from shinkoku.tax_constants import (
    MEDICAL_EXPENSE_MAX,
    MEDICAL_EXPENSE_THRESHOLD,
    MEDICAL_EXPENSE_INCOME_RATIO,
    PERSONAL_DEDUCTION_INCOME_LIMIT,
    RESIDENT_ADJUSTMENT_INCOME_LIMIT,
    RESIDENT_ADJUSTMENT_MIN_BASE,
    RESIDENT_ADJUSTMENT_RATE,
    RESIDENT_ADJUSTMENT_TAXABLE_THRESHOLD,
    RESIDENT_BASIC_DEDUCTIONS,
    RESIDENT_BASIC_PERSONAL_DIFFERENCE,
    RESIDENT_DEPENDENT_DEDUCTIONS,
    RESIDENT_DISABILITY_DEDUCTIONS,
    RESIDENT_EARTHQUAKE_CAP,
    RESIDENT_ELDERLY_SPOUSE_DEDUCTIONS,
    RESIDENT_ELDERLY_SPOUSE_DIFFERENCES,
    RESIDENT_INCOME_LEVY_RATE,
    RESIDENT_LIFE_COMBINED_CAP,
    RESIDENT_LIFE_TOTAL_CAP,
    RESIDENT_NEW_LIFE_SCHEDULE,
    RESIDENT_OLD_LIFE_SCHEDULE,
    RESIDENT_OLD_LONG_TERM_CAP,
    RESIDENT_SINGLE_PARENT_DEDUCTIONS,
    RESIDENT_SPECIFIC_RELATIVE_DEDUCTIONS,
    RESIDENT_SPOUSE_DEDUCTIONS,
    RESIDENT_SPOUSE_DIFFERENCES,
    RESIDENT_SPOUSE_SPECIAL_DEDUCTIONS,
    SELF_MEDICATION_MAX,
    SELF_MEDICATION_THRESHOLD,
    SPOUSE_TAXPAYER_INCOME_LIMIT,
    get_income_tax_constants,
)
from shinkoku.tax_year_support import require_supported_tax_year
from shinkoku.tools.tax_calc import (
    _calc_age,
    _calc_life_insurance_deduction_by_schedule,
    calc_basic_deduction,
)
from shinkoku.tools.tax_reform import calc_furusato_limit_detailed


def _life_category(new_premium: int, old_premium: int) -> int:
    new = _calc_life_insurance_deduction_by_schedule(new_premium, RESIDENT_NEW_LIFE_SCHEDULE)
    old = _calc_life_insurance_deduction_by_schedule(old_premium, RESIDENT_OLD_LIFE_SCHEDULE)
    if new_premium and old_premium:
        return max(old, min(new + old, RESIDENT_LIFE_COMBINED_CAP))
    return new if new_premium else old


def calc_resident_life_insurance(data: ResidentLifeInsuranceInput) -> int:
    """住民税の新旧3区分。所得税の23歳未満特例は適用しない。"""
    return min(
        _life_category(data.general_new, data.general_old)
        + _life_category(data.medical_care, 0)
        + _life_category(data.annuity_new, data.annuity_old),
        RESIDENT_LIFE_TOTAL_CAP,
    )


def _earthquake_deduction(data: ResidentTaxEstimateInput) -> int:
    earthquake = min(-(-data.earthquake_premium // 2), RESIDENT_EARTHQUAKE_CAP)
    premium = data.old_long_term_premium
    old = premium if premium <= 5_000 else min(-(-premium // 2) + 2_500, RESIDENT_OLD_LONG_TERM_CAP)
    # 同じ契約は選択適用。別契約は合算し、全体に2.5万円の上限を適用する。
    return (
        max(earthquake, old)
        if data.same_earthquake_contract
        else min(earthquake + old, RESIDENT_EARTHQUAKE_CAP)
    )


def _spouse_deduction(
    relative: ResidentTaxRelativeInput, aggregate_income: int, year: int
) -> tuple[int, int]:
    age = _calc_age(relative.birth_date, year)
    if aggregate_income > SPOUSE_TAXPAYER_INCOME_LIMIT:
        return 0, 0
    bracket = 0 if aggregate_income <= 9_000_000 else 1 if aggregate_income <= 9_500_000 else 2
    if relative.income <= get_income_tax_constants(year).spouse_income_limit:
        amounts = RESIDENT_ELDERLY_SPOUSE_DEDUCTIONS if age >= 70 else RESIDENT_SPOUSE_DEDUCTIONS
        differences = (
            RESIDENT_ELDERLY_SPOUSE_DIFFERENCES if age >= 70 else RESIDENT_SPOUSE_DIFFERENCES
        )
        return amounts[bracket], differences[bracket]
    # 2026年度以後の配偶者特別控除に係る人的控除差は0。現行控除額の差ではない。
    for upper, amounts in RESIDENT_SPOUSE_SPECIAL_DEDUCTIONS:
        if relative.income <= upper:
            return amounts[bracket], 0
    return 0, 0


def _dependent_deduction(relative: ResidentTaxRelativeInput, year: int) -> tuple[int, int]:
    age = _calc_age(relative.birth_date, year)
    if relative.income > get_income_tax_constants(year).dependent_income_limit:
        if 19 <= age < 23:
            for upper, amount in RESIDENT_SPECIFIC_RELATIVE_DEDUCTIONS:
                if relative.income <= upper:
                    # 特定親族特別控除は税源移譲時に存在せず、人的控除差は0。
                    return amount, 0
        return 0, 0
    if age < 16:
        return 0, 0
    if age >= 70:
        key = (
            "elderly_cohabiting"
            if relative.cohabiting and relative.is_lineal_ascendant
            else "elderly"
        )
    else:
        key = "specific" if 19 <= age < 23 else "general"
    return RESIDENT_DEPENDENT_DEDUCTIONS[key]


def _adjustment_credit(taxable_income: int, personal_diff: int, aggregate_income: int) -> int:
    if aggregate_income > RESIDENT_ADJUSTMENT_INCOME_LIMIT or taxable_income <= 0:
        return 0
    if taxable_income <= RESIDENT_ADJUSTMENT_TAXABLE_THRESHOLD:
        base = min(taxable_income, personal_diff)
    else:
        base = max(
            personal_diff - (taxable_income - RESIDENT_ADJUSTMENT_TAXABLE_THRESHOLD),
            RESIDENT_ADJUSTMENT_MIN_BASE,
        )
    return base * RESIDENT_ADJUSTMENT_RATE // 100


def calc_resident_tax_estimate(data: ResidentTaxEstimateInput) -> ResidentTaxEstimateResult:
    """確認済みの総合課税所得・課税区分を使う推定。実住民税の確定計算ではない。"""
    year = data.fiscal_year
    require_supported_tax_year(year, "resident_tax_estimate")
    constants = get_income_tax_constants(year)
    items: list[ResidentTaxDeductionItem] = []

    def add(kind: str, name: str, amount: int, difference: int = 0) -> None:
        if amount or difference:
            items.append(
                ResidentTaxDeductionItem(
                    type=kind, name=name, amount=amount, personal_difference=difference
                )
            )

    basic = next(
        (amount for upper, amount in RESIDENT_BASIC_DEDUCTIONS if data.aggregate_income <= upper), 0
    )
    # 高所得で調整控除そのものがなくても、寄附金の税率判定用の基礎控除差5万円は保持する。
    add("basic", "基礎控除", basic, RESIDENT_BASIC_PERSONAL_DIFFERENCE)
    add("social_insurance", "社会保険料控除", data.social_insurance)
    add("small_business_mutual_aid", "小規模企業共済等掛金控除", data.small_business_mutual_aid)
    add("life_insurance", "生命保険料控除", calc_resident_life_insurance(data.life_insurance))
    add("earthquake_insurance", "地震保険料控除", _earthquake_deduction(data))

    if data.medical_method == "medical":
        threshold = min(
            data.total_income * MEDICAL_EXPENSE_INCOME_RATIO // 100, MEDICAL_EXPENSE_THRESHOLD
        )
        add(
            "medical",
            "医療費控除",
            min(max(0, data.medical_expenses_net - threshold), MEDICAL_EXPENSE_MAX),
        )
    elif data.medical_method == "self_medication":
        add(
            "self_medication",
            "セルフメディケーション控除",
            min(
                max(0, data.self_medication_expenses_net - SELF_MEDICATION_THRESHOLD),
                SELF_MEDICATION_MAX,
            ),
        )

    relatives = ([data.spouse] if data.spouse is not None else []) + data.dependents
    seen: set[tuple[str, str]] = set()
    for relative in relatives:
        identity = (relative.name, relative.birth_date)
        if identity in seen:
            raise ValueError("同じ親族が重複しています。配偶者を dependents にも含めないでください")
        seen.add(identity)
        _calc_age(relative.birth_date, year)
        if not relative.eligible or relative.other_taxpayer_dependent:
            continue
        if relative is data.spouse:
            amount, diff = _spouse_deduction(relative, data.aggregate_income, year)
            kind = (
                "spouse" if relative.income <= constants.spouse_income_limit else "spouse_special"
            )
        else:
            amount, diff = _dependent_deduction(relative, year)
            kind = (
                "dependent"
                if relative.income <= constants.dependent_income_limit
                else "specific_relative_special"
            )
        add(kind, relative.name, amount, diff)
        # 特定親族特別控除の対象でも、所得要件を超える親族は障害者控除の扶養親族ではない。
        if relative.disability and relative.income <= constants.dependent_income_limit:
            amount, diff = RESIDENT_DISABILITY_DEDUCTIONS[relative.disability]
            add("relative_disability", relative.name, amount, diff)

    if data.disability:
        amount, diff = RESIDENT_DISABILITY_DEDUCTIONS[data.disability]
        add("disability", "本人の障害者控除", amount, diff)
    if data.aggregate_income <= PERSONAL_DEDUCTION_INCOME_LIMIT:
        if data.widow_status == "widow":
            add("widow", "寡婦控除", 260_000, 10_000)
        elif data.widow_status.startswith("single_parent"):
            diff = 50_000 if data.widow_status == "single_parent_mother" else 10_000
            add("single_parent", "ひとり親控除", RESIDENT_SINGLE_PARENT_DEDUCTIONS[year], diff)
    if (
        data.working_student
        and data.aggregate_income <= constants.working_student_income_limit
        and data.working_student_nonwork_income is not None
        and data.working_student_nonwork_income <= 100_000
    ):
        add("working_student", "勤労学生控除", 260_000, 10_000)

    total = sum(item.amount for item in items)
    personal_diff = sum(item.personal_difference for item in items)
    taxable = max(0, data.total_income - total) // 1000 * 1000
    adjustment = (
        _adjustment_credit(taxable, personal_diff, data.aggregate_income)
        if data.income_levy_taxable
        else 0
    )
    levy = (
        max(0, taxable * RESIDENT_INCOME_LEVY_RATE // 100 - adjustment)
        if data.income_levy_taxable
        else 0
    )
    furusato_input = FurusatoLimitInput(
        fiscal_year=year,
        resident_tax_income_levy=levy,
        resident_taxable_income=taxable,
        personal_deduction_difference=personal_diff,
        income_tax_basic_deduction=calc_basic_deduction(data.aggregate_income, year),
    )
    return ResidentTaxEstimateResult(
        fiscal_year=year,
        resident_tax_assessment_year=year + 1,
        income_levy_taxable=data.income_levy_taxable,
        deductions=items,
        resident_tax_deductions_total=total,
        resident_taxable_income=taxable,
        personal_deduction_difference=personal_diff,
        adjustment_credit=adjustment,
        resident_tax_income_levy=levy,
        furusato_input=furusato_input,
        furusato_limit=calc_furusato_limit_detailed(furusato_input),
        warnings=[
            "課税・非課税と親族等の適格性は入力の確認結果を使用しています。",
            "標準税率の合算所得割の推定です。自治体の超過税率、税目別の百円端数、均等割等は含みません。",
            "住宅ローン控除、高所得特例、他の寄附、分離課税等による実負担を確定するものではありません。",
        ],
    )
