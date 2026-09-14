"""税額計算 CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from shinkoku.models import (
    ConsumptionTaxInput,
    DepreciationCalculationInput,
    DependentInfo,
    DonationRecordRecord,
    HousingLoanDetail,
    HousingLoanCalculationInput,
    ResidentTaxEstimateInput,
    IncomeTaxInput,
    IncomeTaxResult,
    LifeInsurancePremiumInput,
    PensionDeductionInput,
    RetirementIncomeInput,
    SmallAssetTreatmentInput,
    SmallBusinessMutualAidInput,
    TaxEligibilityInput,
    FurusatoLimitInput,
    MinimumIncomeTaxInput,
)
from shinkoku.tools.ledger import ledger_get_fiscal_year_tax_profile
from shinkoku.tools.tax_calc import (
    calc_consumption_tax,
    calc_deductions,
    calc_depreciation_declining_balance,
    calc_depreciation_straight_line,
    calc_furusato_deduction_limit,
    calc_income_tax,
    calc_pension_deduction,
    calc_retirement_income,
    sanity_check_income_tax,
    select_small_asset_treatment,
)
from shinkoku.tools.tax_eligibility import (
    check_blue_return_eligibility,
    check_invoice_special_eligibility,
)
from shinkoku.tools.tax_reform import calc_furusato_limit_detailed, calc_minimum_income_tax
from shinkoku.tools.resident_tax import calc_resident_tax_estimate
from shinkoku.tools.housing_loan import calc_housing_loan

_DEPRECIATION_METHODS = (
    "straight_line",
    "declining_balance",
    "small_asset_treatment",
)


def _load_json(path: str) -> dict:
    """JSON ファイルを読み込んで dict を返す。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _output_json(data: dict) -> None:
    """dict を JSON として stdout に出力する。"""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _error_exit(message: str) -> NoReturn:
    """エラーメッセージを JSON で stdout に出力して終了する。"""
    _output_json({"status": "error", "message": message})
    sys.exit(1)


# ============================================================
# Subcommand handlers
# ============================================================


def _handle_calc_deductions(args: argparse.Namespace) -> None:
    """calc-deductions: 控除額計算。"""
    params = _load_json(args.input)

    # ネストされた Pydantic モデルの構築
    life_insurance_detail = None
    if "life_insurance_detail" in params and params["life_insurance_detail"]:
        life_insurance_detail = LifeInsurancePremiumInput(**params.pop("life_insurance_detail"))
    else:
        params.pop("life_insurance_detail", None)

    housing_loan_detail = None
    if "housing_loan_detail" in params and params["housing_loan_detail"]:
        housing_loan_detail = HousingLoanDetail(**params.pop("housing_loan_detail"))
    else:
        params.pop("housing_loan_detail", None)

    housing_loan_details = None
    if "housing_loan_details" in params and params["housing_loan_details"]:
        housing_loan_details = [HousingLoanDetail(**d) for d in params.pop("housing_loan_details")]
    else:
        params.pop("housing_loan_details", None)

    dependents = None
    if "dependents" in params and params["dependents"]:
        dependents = [DependentInfo(**d) for d in params.pop("dependents")]
    else:
        params.pop("dependents", None)

    donations = None
    if "donations" in params and params["donations"]:
        donations = [DonationRecordRecord(**d) for d in params.pop("donations")]
    else:
        params.pop("donations", None)

    result = calc_deductions(
        **params,
        life_insurance_detail=life_insurance_detail,
        housing_loan_detail=housing_loan_detail,
        housing_loan_details=housing_loan_details,
        dependents=dependents,
        donations=donations,
    )
    _output_json(result.model_dump())


def _handle_calc_income(args: argparse.Namespace) -> None:
    """calc-income: 所得税計算。"""
    params = _load_json(args.input)

    # ネストされた Pydantic モデルの構築
    if "life_insurance_detail" in params and params["life_insurance_detail"]:
        params["life_insurance_detail"] = LifeInsurancePremiumInput(
            **params["life_insurance_detail"]
        )
    else:
        params.pop("life_insurance_detail", None)

    if "housing_loan_detail" in params and params["housing_loan_detail"]:
        params["housing_loan_detail"] = HousingLoanDetail(**params["housing_loan_detail"])
    else:
        params.pop("housing_loan_detail", None)

    if "housing_loan_details" in params and params["housing_loan_details"]:
        params["housing_loan_details"] = [
            HousingLoanDetail(**d) for d in params["housing_loan_details"]
        ]
    else:
        params.pop("housing_loan_details", None)

    if "dependents" in params and params["dependents"]:
        params["dependents"] = [DependentInfo(**d) for d in params["dependents"]]
    else:
        params.pop("dependents", None)

    if "small_business_mutual_aid" in params and params["small_business_mutual_aid"]:
        params["small_business_mutual_aid"] = SmallBusinessMutualAidInput(
            **params["small_business_mutual_aid"]
        )
    else:
        params.pop("small_business_mutual_aid", None)

    if "donations" in params and params["donations"]:
        params["donations"] = [DonationRecordRecord(**d) for d in params["donations"]]
    else:
        params.pop("donations", None)

    input_data = IncomeTaxInput(**params)
    result = calc_income_tax(input_data)
    _output_json(result.model_dump())


def _handle_calc_depreciation(args: argparse.Namespace) -> None:
    """calc-depreciation: 減価償却計算。"""
    params = _load_json(args.input)
    method = params.get("method", "straight_line")
    if method not in _DEPRECIATION_METHODS:
        valid_methods = " / ".join(f"'{value}'" for value in _DEPRECIATION_METHODS)
        raise ValueError(f"method は {valid_methods} のいずれかを指定してください")

    if method == "small_asset_treatment":
        small_asset_input = SmallAssetTreatmentInput(**params)
        result = select_small_asset_treatment(small_asset_input)
        _output_json(result.model_dump(mode="json"))
        return

    calc_input = DepreciationCalculationInput(**params)
    if calc_input.method == "declining_balance":
        assert calc_input.book_value is not None
        assert calc_input.declining_rate is not None
        amount = calc_depreciation_declining_balance(
            book_value=calc_input.book_value,
            declining_rate=calc_input.declining_rate,
            business_use_ratio=calc_input.business_use_ratio,
            months=calc_input.months,
        )
    else:
        amount = calc_depreciation_straight_line(
            acquisition_cost=calc_input.acquisition_cost,
            useful_life=calc_input.useful_life,
            business_use_ratio=calc_input.business_use_ratio,
            months=calc_input.months,
        )

    _output_json(
        {
            "method": calc_input.method,
            "depreciation_amount": amount,
            "acquisition_cost": calc_input.acquisition_cost,
            "useful_life": calc_input.useful_life,
            "business_use_ratio": calc_input.business_use_ratio,
            "months": calc_input.months,
        }
    )


def _handle_calc_consumption(args: argparse.Namespace) -> None:
    """calc-consumption: 消費税計算。"""
    params = _load_json(args.input)
    input_data = ConsumptionTaxInput(**params)
    # 副作用のない計算で年分・要件・入力を検証してからDB照合へ進む。
    result = calc_consumption_tax(input_data)
    db_path = getattr(args, "db_path", None)
    method_verified: bool | None = None

    if db_path is not None:
        profile = ledger_get_fiscal_year_tax_profile(
            db_path=db_path,
            fiscal_year=input_data.fiscal_year,
        )
        db_method = profile["consumption_tax_method"]
        if input_data.calculation_mode == "filing":
            if profile["taxpayer_status"] != "taxable":
                raise ValueError("申告用計算ではDBの課税事業者区分を確定・照合してください")
            if db_method is None:
                raise ValueError("申告用計算ではDBの消費税申告方法を確定してください")
        if db_method is None:
            method_verified = False
        else:
            if db_method != input_data.method:
                raise ValueError(
                    f"消費税申告方法が一致しません: DB={db_method!r}, input={input_data.method!r}"
                )
            if input_data.method == "simplified":
                db_business_type = profile["simplified_business_type"]
                if db_business_type != input_data.simplified_business_type:
                    raise ValueError(
                        "簡易課税事業区分が一致しません: "
                        f"DB={db_business_type!r}, input={input_data.simplified_business_type!r}"
                    )
            method_verified = True

    output = result.model_dump()
    if method_verified is not None:
        output["method_verified"] = method_verified
    _output_json(output)


def _handle_calc_furusato_limit(args: argparse.Namespace) -> None:
    """calc-furusato-limit: ふるさと納税控除上限推定。"""
    params = _load_json(args.input)
    limit = calc_furusato_deduction_limit(**params)
    _output_json({"estimated_limit": limit})


def _handle_calc_furusato_limit_detailed(args: argparse.Namespace) -> None:
    result = calc_furusato_limit_detailed(FurusatoLimitInput.model_validate(_load_json(args.input)))
    _output_json(result.model_dump())


def _handle_calc_minimum_income(args: argparse.Namespace) -> None:
    result = calc_minimum_income_tax(MinimumIncomeTaxInput.model_validate(_load_json(args.input)))
    _output_json(result.model_dump())


def _handle_calc_resident_tax_estimate(args: argparse.Namespace) -> None:
    result = calc_resident_tax_estimate(
        ResidentTaxEstimateInput.model_validate(_load_json(args.input), strict=True)
    )
    _output_json(result.model_dump())


def _handle_calc_housing_loan(args: argparse.Namespace) -> None:
    result = calc_housing_loan(
        HousingLoanCalculationInput.model_validate(_load_json(args.input), strict=True)
    )
    _output_json(result.model_dump())


def _handle_calc_pension(args: argparse.Namespace) -> None:
    """calc-pension: 公的年金等控除計算。"""
    params = _load_json(args.input)
    input_data = PensionDeductionInput(**params)
    result = calc_pension_deduction(input_data)
    _output_json(result.model_dump())


def _handle_calc_retirement(args: argparse.Namespace) -> None:
    """calc-retirement: 退職所得計算。"""
    params = _load_json(args.input)
    input_data = RetirementIncomeInput(**params)
    result = calc_retirement_income(input_data)
    _output_json(result.model_dump())


def _handle_sanity_check(args: argparse.Namespace) -> None:
    """sanity-check: 所得税計算結果のサニティチェック。"""
    params = _load_json(args.input)

    if "input" not in params or "result" not in params:
        _error_exit("JSON には 'input' と 'result' の両キーが必要です")

    input_raw = params["input"]
    result_raw = params["result"]

    # ネストされた Pydantic モデルの構築（IncomeTaxInput）
    if "life_insurance_detail" in input_raw and input_raw["life_insurance_detail"]:
        input_raw["life_insurance_detail"] = LifeInsurancePremiumInput(
            **input_raw["life_insurance_detail"]
        )
    else:
        input_raw.pop("life_insurance_detail", None)

    if "housing_loan_detail" in input_raw and input_raw["housing_loan_detail"]:
        input_raw["housing_loan_detail"] = HousingLoanDetail(**input_raw["housing_loan_detail"])
    else:
        input_raw.pop("housing_loan_detail", None)

    if "housing_loan_details" in input_raw and input_raw["housing_loan_details"]:
        input_raw["housing_loan_details"] = [
            HousingLoanDetail(**d) for d in input_raw["housing_loan_details"]
        ]
    else:
        input_raw.pop("housing_loan_details", None)

    if "dependents" in input_raw and input_raw["dependents"]:
        input_raw["dependents"] = [DependentInfo(**d) for d in input_raw["dependents"]]
    else:
        input_raw.pop("dependents", None)

    if "small_business_mutual_aid" in input_raw and input_raw["small_business_mutual_aid"]:
        input_raw["small_business_mutual_aid"] = SmallBusinessMutualAidInput(
            **input_raw["small_business_mutual_aid"]
        )
    else:
        input_raw.pop("small_business_mutual_aid", None)

    input_data = IncomeTaxInput(**input_raw)
    tax_result = IncomeTaxResult(**result_raw)
    check_result = sanity_check_income_tax(input_data, tax_result)
    _output_json(check_result.model_dump())


def _handle_check_eligibility(args: argparse.Namespace) -> None:
    """制度の適格性を確認する。判定結果は申告計算や帳簿更新を行わず返す。"""
    request = TaxEligibilityInput(**_load_json(args.input))
    if request.scheme == "blue_return":
        assert request.requested_deduction is not None
        result = check_blue_return_eligibility(
            request.fiscal_year, request.requested_deduction, request.blue_return
        )
    else:
        result = check_invoice_special_eligibility(
            request.fiscal_year, request.scheme, request.invoice_special
        )
    _output_json(result.model_dump())


_HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
    "check-eligibility": _handle_check_eligibility,
    "calc-deductions": _handle_calc_deductions,
    "calc-income": _handle_calc_income,
    "calc-depreciation": _handle_calc_depreciation,
    "calc-consumption": _handle_calc_consumption,
    "calc-furusato-limit": _handle_calc_furusato_limit,
    "calc-furusato-limit-detailed": _handle_calc_furusato_limit_detailed,
    "calc-minimum-income": _handle_calc_minimum_income,
    "calc-resident-tax-estimate": _handle_calc_resident_tax_estimate,
    "calc-housing-loan": _handle_calc_housing_loan,
    "calc-pension": _handle_calc_pension,
    "calc-retirement": _handle_calc_retirement,
    "sanity-check": _handle_sanity_check,
}


def _dispatch(args: argparse.Namespace) -> None:
    """サブコマンドをディスパッチする。"""
    handler = _HANDLERS.get(args.subcommand)
    if handler is None:
        _error_exit(f"Unknown command: {args.subcommand}")
    try:
        handler(args)
    except Exception as e:
        _error_exit(str(e))


def register(parent_subparsers: argparse._SubParsersAction) -> None:
    """tax サブコマンドを親パーサーに登録する。"""
    parser = parent_subparsers.add_parser(
        "tax",
        description="税額計算 CLI",
        help="税額計算",
    )
    sub = parser.add_subparsers(dest="subcommand")

    for name in [
        "check-eligibility",
        "calc-deductions",
        "calc-income",
        "calc-depreciation",
        "calc-consumption",
        "calc-furusato-limit",
        "calc-furusato-limit-detailed",
        "calc-minimum-income",
        "calc-resident-tax-estimate",
        "calc-housing-loan",
        "calc-pension",
        "calc-retirement",
        "sanity-check",
    ]:
        p = sub.add_parser(name)
        p.add_argument("--input", required=True, help="入力 JSON ファイルパス")
        if name == "calc-consumption":
            p.add_argument("--db-path", help="年度別消費税プロファイルを照合するDBパス")
        p.set_defaults(func=_dispatch)

    parser.set_defaults(func=lambda args: parser.print_help() or sys.exit(1))
