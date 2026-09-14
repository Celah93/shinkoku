"""Pydantic models for MCP tool input/output types."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


DonationType = Literal["political", "npo", "public_interest", "specified", "other"]


# --- 帳簿管理 (ledger) ---


class FiscalYearTaxProfile(BaseModel):
    """年度別に確定した納税者の消費税プロファイル。"""

    taxpayer_status: Literal["taxable", "exempt"] | None = None
    consumption_tax_method: (
        Literal["standard", "simplified", "special_20pct", "special_30pct"] | None
    ) = None
    simplified_business_type: int | None = Field(default=None, ge=1, le=6)

    @model_validator(mode="after")
    def require_business_type_for_simplified(self) -> FiscalYearTaxProfile:
        """簡易課税の確定時は事業区分を必須とする。"""
        if self.consumption_tax_method == "simplified" and self.simplified_business_type is None:
            raise ValueError("簡易課税では simplified_business_type が必要です")
        return self

    @model_validator(mode="after")
    def reject_method_for_exempt_taxpayer(self) -> FiscalYearTaxProfile:
        """免税事業者には確定申告方法を保持しない。"""
        if self.taxpayer_status == "exempt" and self.consumption_tax_method is not None:
            raise ValueError("免税事業者の consumption_tax_method は null である必要があります")
        return self

    @model_validator(mode="after")
    def reject_orphan_business_type(self) -> FiscalYearTaxProfile:
        """簡易課税以外では事業区分を保持しない。"""
        if (
            self.simplified_business_type is not None
            and self.consumption_tax_method != "simplified"
        ):
            raise ValueError(
                "simplified_business_type は consumption_tax_method=simplified の場合のみ設定できます"
            )
        return self


class FiscalYearTaxProfileUpdate(BaseModel):
    """年度別消費税プロファイルの部分更新入力。相関検証はマージ後に行う。"""

    taxpayer_status: Literal["taxable", "exempt"] | None = None
    consumption_tax_method: (
        Literal["standard", "simplified", "special_20pct", "special_30pct"] | None
    ) = None
    simplified_business_type: int | None = Field(default=None, ge=1, le=6)


class JournalLine(BaseModel):
    """仕訳明細（借方または貸方の1行）。"""

    side: str = Field(pattern=r"^(debit|credit)$")
    account_code: str
    amount: int = Field(gt=0, description="円単位の整数")
    # 勘定科目の分類ではなく、journal_linesのCHECK制約と同じ税率別区分を使う。
    tax_category: (
        Literal[
            "taxable_10", "taxable_8", "taxable_8_reduced", "non_taxable", "exempt", "out_of_scope"
        ]
        | None
    ) = None
    tax_amount: int = 0


class JournalEntry(BaseModel):
    """仕訳1件の入力データ。"""

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    description: str | None = None
    counterparty: str | None = None
    lines: list[JournalLine] = Field(min_length=2)
    source: Literal["csv_import", "receipt_ocr", "invoice_ocr", "manual", "adjustment"] | None = (
        None
    )
    source_file: str | None = None
    is_adjustment: bool = False


class JournalSearchParams(BaseModel):
    """仕訳検索の条件。"""

    fiscal_year: int
    date_from: str | None = None
    date_to: str | None = None
    account_code: str | None = None
    description_contains: str | None = None
    counterparty_contains: str | None = None
    amount_min: int | None = None
    amount_max: int | None = None
    source: str | None = None
    limit: int = 100
    offset: int = 0


class JournalRecord(BaseModel):
    """DB上の仕訳レコード。"""

    id: int
    fiscal_year: int
    date: str
    description: str | None
    counterparty: str | None = None
    source: str | None
    source_file: str | None
    is_adjustment: bool
    lines: list[JournalLineRecord]


class JournalLineRecord(BaseModel):
    """DB上の仕訳明細レコード。"""

    id: int
    side: str
    account_code: str
    amount: int
    tax_category: str | None
    tax_amount: int


class JournalSearchResult(BaseModel):
    """仕訳検索の結果。"""

    journals: list[JournalRecord]
    total_count: int


class AuditLogRecord(BaseModel):
    """仕訳の訂正・削除履歴レコード。"""

    id: int
    journal_id: int
    fiscal_year: int
    operation: str
    before_date: str
    before_description: str | None
    before_counterparty: str | None
    before_lines_json: str
    after_date: str | None = None
    after_description: str | None = None
    after_counterparty: str | None = None
    after_lines_json: str | None = None
    created_at: str


# --- 総勘定元帳 ---


class GeneralLedgerLineRecord(BaseModel):
    """総勘定元帳の1行。"""

    journal_id: int
    date: str
    description: str | None
    counterparty: str | None
    counter_account_code: str  # 相手勘定科目コード（複合仕訳は「*」）
    counter_account_name: str  # 相手勘定科目名（複合仕訳は「諸口」）
    debit: int
    credit: int
    balance: int  # 累積残高


class GeneralLedgerResult(BaseModel):
    """総勘定元帳の出力。"""

    account_code: str
    account_name: str
    fiscal_year: int
    opening_balance: int
    entries: list[GeneralLedgerLineRecord]
    closing_balance: int


# --- 財務諸表 ---


class TrialBalanceAccount(BaseModel):
    """残高試算表の1行。"""

    account_code: str
    account_name: str
    category: str
    debit_total: int = 0
    credit_total: int = 0
    balance: int = 0


class TrialBalanceResult(BaseModel):
    """残高試算表。"""

    fiscal_year: int
    accounts: list[TrialBalanceAccount]
    total_debit: int
    total_credit: int


class PLItem(BaseModel):
    """損益計算書の1行。"""

    account_code: str
    account_name: str
    amount: int


class PLResult(BaseModel):
    """損益計算書。"""

    fiscal_year: int
    revenues: list[PLItem]
    expenses: list[PLItem]
    total_revenue: int
    total_expense: int
    net_income: int


class BSItem(BaseModel):
    """貸借対照表の1行。"""

    account_code: str
    account_name: str
    amount: int


class BSResult(BaseModel):
    """貸借対照表。"""

    fiscal_year: int
    assets: list[BSItem]
    liabilities: list[BSItem]
    equity: list[BSItem]
    total_assets: int
    total_liabilities: int
    total_equity: int
    # 期首残高（None = 未取得）
    opening_assets: list[BSItem] | None = None
    opening_liabilities: list[BSItem] | None = None
    opening_equity: list[BSItem] | None = None
    opening_total_assets: int | None = None
    opening_total_liabilities: int | None = None
    opening_total_equity: int | None = None


class OpeningBalanceInput(BaseModel):
    """期首残高の入力。"""

    account_code: str
    amount: int = Field(description="円単位の整数")


# --- データ取り込み (import) ---


class CSVImportCandidate(BaseModel):
    """CSV取り込み候補の1行。"""

    row_number: int
    date: str
    description: str
    amount: int
    original_data: dict


class CSVImportResult(BaseModel):
    """CSV取り込み結果。"""

    file_path: str
    encoding: str
    total_rows: int
    candidates: list[CSVImportCandidate]
    skipped_rows: list[int] = []
    errors: list[str] = []


class ReceiptData(BaseModel):
    """レシート読み取りテンプレート。"""

    file_path: str
    date: str | None = None
    vendor: str | None = None
    total_amount: int | None = None
    items: list[dict] = []
    tax_included: bool = True


class InvoiceData(BaseModel):
    """請求書読み取り結果。"""

    file_path: str
    extracted_text: str
    vendor: str | None = None
    invoice_number: str | None = None
    date: str | None = None
    total_amount: int | None = None
    tax_amount: int | None = None


class WithholdingSlipData(BaseModel):
    """源泉徴収票の構造化データ。"""

    file_path: str
    extracted_text: str
    payer_name: str | None = None
    payment_amount: int = 0
    withheld_tax: int = 0
    social_insurance: int = 0
    life_insurance_deduction: int = 0
    earthquake_insurance_deduction: int = 0
    housing_loan_deduction: int = 0


# --- 税額計算 (tax) ---


class DeductionItem(BaseModel):
    """控除1項目。"""

    type: str
    name: str
    amount: int
    details: str | None = None


class DeductionsResult(BaseModel):
    """控除計算結果。"""

    income_deductions: list[DeductionItem] = Field(default_factory=list, description="所得控除")
    tax_credits: list[DeductionItem] = Field(default_factory=list, description="税額控除")
    total_income_deductions: int = 0
    total_tax_credits: int = 0
    housing_loan_credit_entries: list[HousingLoanCreditEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, description="計算上の警告")
    notes: list[str] = Field(default_factory=list, description="注意事項")


class DonationIncomeDeductionCalculation(BaseModel):
    """寄附金の所得控除に使う調整額。"""

    original_amount: int = 0
    eligible_amount: int = 0
    threshold_amount: int = 0
    final_amount: int = 0


class DonationTaxCreditCalculation(BaseModel):
    """区分別の寄附金特別控除に使う調整額。"""

    original_amount: int = 0
    eligible_amount: int = 0
    threshold_amount: int = 0
    formula_amount: int = 0
    tax_credit_cap: int = 0
    final_amount: int = 0


class DonationAdjustmentResult(BaseModel):
    """寄附金控除の40%枠・2,000円足切り・25%枠を調整した結果。"""

    income_limit: int = 0
    income_deduction: DonationIncomeDeductionCalculation
    public_interest: DonationTaxCreditCalculation
    npo: DonationTaxCreditCalculation
    political: DonationTaxCreditCalculation


class DonationMethodSelection(BaseModel):
    """3区分ごとに選んだ寄附金控除方式。"""

    public_interest: Literal["income", "credit"] = "income"
    npo: Literal["income", "credit"] = "income"
    political: Literal["income", "credit"] = "income"


class DepreciationAsset(BaseModel):
    """減価償却計算結果の1資産。"""

    asset_id: int
    name: str
    acquisition_cost: int
    method: str
    useful_life: int
    business_use_ratio: int
    current_year_amount: int
    accumulated: int


class DepreciationResult(BaseModel):
    """減価償却費計算結果。"""

    fiscal_year: int
    assets: list[DepreciationAsset]
    total_depreciation: int


SmallAssetTreatment = Literal[
    "immediate_expense",
    "pooled_depreciation",
    "small_asset_special",
    "normal_depreciation",
]
SmallAssetTreatmentStatus = Literal[
    "available",
    "ineligible",
    "indeterminate",
    "requires_confirmation",
]


class DepreciationCalculationInput(BaseModel):
    """既存の定額法・定率法を計算する入力。"""

    # 未知キーを警告だけで通すと、取得日など制度判定に必要な入力を受け取ったように
    # 見せながら無視する旧挙動が残るため、警告ではなくエラーに固定する。
    model_config = ConfigDict(extra="forbid")

    method: Literal["straight_line", "declining_balance"] = "straight_line"
    acquisition_cost: int = Field(
        gt=0,
        description=(
            "税込経理なら税込額、税抜経理なら税抜額で確定した"
            "税法上の取得価額（円）。この入力層は経理方式を変換しない"
        ),
    )
    useful_life: int = Field(gt=0, description="法定耐用年数")
    business_use_ratio: int = Field(default=100, ge=0, le=100)
    months: int = Field(default=12, ge=1, le=12)
    book_value: int | None = Field(default=None, gt=0)
    declining_rate: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_method_parameters(self) -> DepreciationCalculationInput:
        """償却方式ごとの必須値と未使用値を検証する。"""
        if self.method == "declining_balance":
            if self.book_value is None or self.declining_rate is None:
                raise ValueError("定率法では book_value と declining_rate が必要です")
        elif self.book_value is not None or self.declining_rate is not None:
            raise ValueError("book_value と declining_rate は定率法でのみ指定できます")
        return self


class SmallAssetTreatmentInput(BaseModel):
    """少額減価償却資産の処理候補を選ぶ入力。"""

    model_config = ConfigDict(extra="forbid")

    method: Literal["small_asset_treatment"] = "small_asset_treatment"
    acquisition_date: date
    placed_in_service_date: date
    # 税込・税抜の変換をこの層へ入れると経理方式の確認まで範囲が広がるため、
    # 取得価額は税法上の判定額として確定済みの円額を必須にする。
    acquisition_cost: int = Field(
        gt=0,
        description=(
            "税込経理なら税込額、税抜経理なら税抜額で確定した"
            "税法上の取得価額（円）。この入力層は経理方式を変換しない"
        ),
    )
    useful_life: int = Field(gt=0, description="通常償却を選ぶ場合の法定耐用年数")
    depreciation_method: Literal["straight_line", "declining_balance"] = "straight_line"
    business_use_ratio: int = Field(default=100, ge=0, le=100)
    months: int = Field(default=12, ge=1, le=12)
    book_value: int | None = Field(default=None, gt=0)
    declining_rate: int | None = Field(default=None, gt=0)
    usable_period_under_one_year: bool = False
    is_blue_return: bool | None = None
    employee_count_at_acquisition: int | None = Field(default=None, ge=0)
    employee_count_at_placed_in_service: int | None = Field(default=None, ge=0)
    is_lending_use: bool
    is_main_business_lending: bool
    special_cap_used: int = Field(ge=0, description="供用年に既に特例適用した取得価額")
    business_start_date: date | None = None
    business_end_date: date | None = None
    selected_treatment: SmallAssetTreatment | None = None

    @model_validator(mode="after")
    def validate_related_fields(self) -> SmallAssetTreatmentInput:
        """償却方式・貸付け・業務期間の相関を検証する。"""
        if self.placed_in_service_date < self.acquisition_date:
            raise ValueError("placed_in_service_date は acquisition_date 以後である必要があります")
        if self.depreciation_method == "declining_balance":
            if self.book_value is None or self.declining_rate is None:
                raise ValueError("定率法では book_value と declining_rate が必要です")
        elif self.book_value is not None or self.declining_rate is not None:
            raise ValueError("book_value と declining_rate は定率法でのみ指定できます")

        if self.is_main_business_lending and not self.is_lending_use:
            raise ValueError("主要業務としての貸付けは is_lending_use=true の場合のみ指定できます")
        if self.business_start_date is not None and (
            self.business_start_date > self.placed_in_service_date
        ):
            raise ValueError("business_start_date は業務供用日以前である必要があります")
        if self.business_end_date is not None and (
            self.business_end_date < self.placed_in_service_date
        ):
            raise ValueError("business_end_date は業務供用日以後である必要があります")
        if (
            self.business_start_date is not None
            and self.business_end_date is not None
            and self.business_start_date > self.business_end_date
        ):
            raise ValueError("business_start_date は business_end_date 以前である必要があります")
        return self


class SmallAssetTreatmentOption(BaseModel):
    """少額資産について選べる一つの処理候補。"""

    treatment: SmallAssetTreatment
    status: SmallAssetTreatmentStatus
    eligible: bool | None
    current_year_expense: int | None = None
    remaining_balance: int | None = None
    calculation_years: int | None = None
    monthly_proration_applied: bool | None = None
    continues_after_disposal: bool = False
    reason: str | None = None
    legal_basis: str
    warnings: list[str] = Field(default_factory=list)


class SmallAssetTreatmentResult(BaseModel):
    """少額資産の処理候補、選択結果、年300万円枠の状態。"""

    status: Literal["options_ready", "selected", "indeterminate", "requires_confirmation"]
    options: list[SmallAssetTreatmentOption]
    selected_treatment: SmallAssetTreatment | None = None
    selected_current_year_expense: int | None = None
    special_period_start: date | None = None
    special_period_end: date | None = None
    special_acquisition_cost_exclusive_max: int | None = None
    special_employee_max: int | None = None
    special_cap_limit: int | None = None
    special_cap_used: int
    special_cap_remaining: int | None = None
    special_cap_overage: int = 0
    warnings: list[str] = Field(default_factory=list)


class DependentInfo(BaseModel):
    """扶養親族の情報。"""

    name: str
    relationship: str  # 配偶者/子/親 等
    birth_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    income: int = 0  # 年間所得
    disability: str | None = Field(default=None, pattern=r"^(general|special|special_cohabiting)$")
    cohabiting: bool = True  # 同居
    other_taxpayer_dependent: bool = False  # 他の納税者の扶養親族に該当する


class HousingLoanEvidenceInput(BaseModel):
    """住宅の経過措置・立地・借入期間に関する確認情報。未確認はNoneで保持する。"""

    building_confirmation_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    building_completion_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_disaster_red_zone: StrictBool | None = None
    is_rebuilding: StrictBool | None = None
    loan_term_years: int | None = Field(default=None, gt=0, strict=True)

    @field_validator("building_confirmation_date", "building_completion_date")
    @classmethod
    def valid_building_date(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)
        return value


class HousingLoanDetail(HousingLoanEvidenceInput):
    """住宅ローン控除の詳細情報。"""

    housing_type: str = Field(
        pattern=(r"^(new_custom|new_subdivision|broker_renovated_resale|resale|used|renovation)$"),
        description="住宅区分: new_custom=注文新築, new_subdivision=分譲新築, "
        "broker_renovated_resale=買取再販, used=通常の既存住宅, renovation=増改築。"
        "resaleは旧入力の検出専用",
    )
    housing_category: str = Field(
        pattern=r"^(general|certified|zeh|energy_efficient)$",
        description="住宅性能区分: general=一般, certified=認定住宅, "
        "zeh=ZEH水準省エネ, energy_efficient=省エネ基準適合",
    )
    move_in_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    year_end_balance: int = Field(ge=0, description="年末残高（円）")
    is_new_construction: bool | None = None  # 旧入力との整合確認にのみ使う
    is_special_target_individual: bool | None = None  # 特例対象個人。Noneは世帯情報から導出
    is_childcare_household: bool | None = None  # 非推奨エイリアス
    has_pre_r6_building_permit: bool = False  # R5以前の建築確認済み（一般住宅のみ関連）
    dual_application_group: str | None = None  # 重複適用グループID
    cost_for_proration: int = 0  # 按分用コスト（円）: 購入価格 or リフォーム費用
    total_floor_area: int = Field(default=0, ge=0, strict=True)  # 平方メートル×100
    residential_floor_area: int = Field(default=0, ge=0, strict=True)


class HousingLoanDetailInput(HousingLoanEvidenceInput):
    """住宅ローン控除詳細の登録入力。"""

    housing_type: str = Field(
        pattern=(r"^(new_custom|new_subdivision|broker_renovated_resale|resale|used|renovation)$"),
    )
    housing_category: str = Field(
        pattern=r"^(general|certified|zeh|energy_efficient)$",
    )
    move_in_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    year_end_balance: int = Field(ge=0, description="年末残高（円）")
    is_new_construction: bool | None = None
    is_special_target_individual: bool | None = None
    is_childcare_household: bool | None = None
    has_pre_r6_building_permit: bool = False
    purchase_date: str | None = None  # 住宅購入日
    purchase_price: int = 0  # 住宅の価格（円）
    total_floor_area: int = 0  # 総床面積（平方メートル×100: 10063=100.63㎡）
    residential_floor_area: int = 0  # 居住用部分の面積（同上）
    property_number: str | None = None  # 不動産番号
    application_submitted: bool = False  # 適用申請書提出有無
    dual_application_group: str | None = None  # 重複適用グループID
    cost_for_proration: int = 0  # 按分用コスト（円）


class HousingLoanDetailRecord(HousingLoanEvidenceInput):
    """住宅ローン控除詳細のDBレコード。"""

    id: int
    fiscal_year: int
    housing_type: str
    housing_category: str
    move_in_date: str
    year_end_balance: int
    is_new_construction: bool | None = None
    is_special_target_individual: bool | None = None
    is_childcare_household: bool | None = None
    has_pre_r6_building_permit: bool = False
    purchase_date: str | None = None
    purchase_price: int = 0
    total_floor_area: int = 0
    residential_floor_area: int = 0
    property_number: str | None = None
    application_submitted: bool = False
    dual_application_group: str | None = None
    cost_for_proration: int = 0


class HousingLoanCreditEntry(BaseModel):
    """重複適用の個別明細の計算結果。"""

    housing_type: str
    move_in_year: int
    claim_fiscal_year: int
    claim_year_number: int
    credit_period: int
    prorated_balance: int  # 按分後の年末残高
    balance_limit: int  # 適用される借入限度額
    capped_balance: int  # min(按分後残高, 限度額)
    credit: int  # 控除額（100円未満切捨）
    proration_ratio_pct: int  # 按分比率（万分率: 6667 = 66.67%）
    status: str = Field(pattern=r"^(active|expired|ineligible)$")


class HousingLoanCalculationDetailInput(HousingLoanDetail):
    """単体CLI用の厳密な住宅明細。旧年間計算の型強制契約を変更しない。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class HousingLoanDependentInput(DependentInfo):
    """住宅単体計算の世帯判定に使う、型強制を行わない親族入力。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class HousingLoanCalculationInput(BaseModel):
    """住宅ローン単体計算。年間所得税の対応年分を拡張せず控除可能額を求める。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    claim_fiscal_year: int = Field(ge=2022, le=2042, strict=True)
    aggregate_income: int = Field(ge=0, strict=True)
    other_requirements_confirmed: StrictBool
    housing_loan_details: list[HousingLoanCalculationDetailInput] = Field(min_length=1)
    taxpayer_birth_date: str | None = None
    spouse_birth_date: str | None = None
    spouse_income: int | None = Field(default=None, ge=0, strict=True)
    dependents: list[HousingLoanDependentInput] = Field(default_factory=list)


class HousingLoanCalculationResult(BaseModel):
    """所得税額上限を適用する前の控除可能額と、明細別の適用期間。"""

    claim_fiscal_year: int
    housing_loan_credit: int
    entries: list[HousingLoanCreditEntry]
    warnings: list[str]


class LifeInsurancePremiumInput(BaseModel):
    """生命保険料控除の3区分入力（新旧制度対応）。"""

    general_new: int = 0  # 一般生命保険料（新制度）
    general_old: int = 0  # 一般生命保険料（旧制度）
    medical_care: int = 0  # 介護医療保険料（新制度のみ）
    annuity_new: int = 0  # 個人年金保険料（新制度）
    annuity_old: int = 0  # 個人年金保険料（旧制度）


class SmallBusinessMutualAidInput(BaseModel):
    """小規模企業共済等掛金控除のサブタイプ。"""

    small_business_mutual_aid: int = 0  # 小規模企業共済
    ideco: int = 0  # iDeCo（個人型確定拠出年金）
    disability_mutual_aid: int = 0  # 心身障害者扶養共済

    @property
    def total(self) -> int:
        return self.small_business_mutual_aid + self.ideco + self.disability_mutual_aid


class BlueReturnEligibilityFacts(BaseModel):
    """青色控除の確認済み事実。未確認はNoneとし、単なる電子保存と優良帳簿を区別する。"""

    model_config = ConfigDict(extra="forbid")

    blue_return_approved: StrictBool | None = None
    eligible_business_income: StrictBool | None = None
    bookkeeping: Literal["double_entry", "simple"] | None = None
    cash_basis_special: StrictBool | None = None
    filing_within_deadline: StrictBool | None = None
    required_statements_included: StrictBool | None = None
    deduction_claim_recorded: StrictBool | None = None
    etax_filing: StrictBool | None = None
    qualified_electronic_books: StrictBool | None = None
    electronic_books_notice_requirement_met: StrictBool | None = None
    digital_seamless_recordkeeping: StrictBool | None = None
    digital_notice_requirement_met: StrictBool | None = None
    prior_prior_year_business_revenue: int | None = Field(default=None, ge=0, strict=True)


class InvoiceSpecialEligibilityFacts(BaseModel):
    """国内の個人事業者の2割・3割特例。除外条件の不明をFalseにしない。"""

    model_config = ConfigDict(extra="forbid")

    domestic_individual: StrictBool | None = None
    invoice_registration_effective: StrictBool | None = None
    base_period_taxable_sales: int | None = Field(default=None, ge=0, strict=True)
    specific_period_taxation_applies: StrictBool | None = None
    inheritance_taxation_applies: StrictBool | None = None
    asset_tax_exemption_restriction: StrictBool | None = None
    other_tax_exemption_restriction: StrictBool | None = None
    shortened_tax_period: StrictBool | None = None
    inheritance_date: date | None = None
    invoice_registration_date: date | None = None


class TaxEligibilityCheck(BaseModel):
    """個別制度の適用判定。申告全体の適格性や提出済みを意味しない。"""

    scheme: Literal["blue_return", "special_20pct", "special_30pct"]
    fiscal_year: int
    status: Literal["eligible", "ineligible", "indeterminate", "not_applicable", "unsupported"]
    missing_fields: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class TaxEligibilityInput(BaseModel):
    """計算の実行可否とは独立した、個別制度の要件確認CLI入力。"""

    model_config = ConfigDict(extra="forbid")

    scheme: Literal["blue_return", "special_20pct", "special_30pct"]
    fiscal_year: int = Field(strict=True)
    requested_deduction: int | None = Field(default=None, ge=0, strict=True)
    blue_return: BlueReturnEligibilityFacts | None = None
    invoice_special: InvoiceSpecialEligibilityFacts | None = None

    @model_validator(mode="after")
    def require_matching_facts(self) -> TaxEligibilityInput:
        if self.scheme == "blue_return":
            if self.requested_deduction is None:
                raise ValueError("blue_return では requested_deduction が必要です")
            if self.invoice_special is not None:
                raise ValueError("blue_return に invoice_special は指定できません")
        elif self.blue_return is not None or self.requested_deduction is not None:
            raise ValueError("インボイス特例に青色控除の入力は指定できません")
        return self


class IncomeSpecialTaxResult(BaseModel):
    """各追加税の参考内訳と、端数を保持して合算した結果。分子の単位は円×税率分子。"""

    reconstruction_tax: int
    defense_tax: int
    combined_special_tax: int
    rounding_adjustment: int
    reconstruction_numerator: int
    defense_numerator: int
    denominator: int


class MinimumTaxIncomeBreakdown(BaseModel):
    """NTA適用判定表①〜⑫。繰越控除・土地等特別控除後、申告不要制度を使わない所得額。"""

    model_config = ConfigDict(extra="forbid")

    comprehensive_income: int = Field(ge=0, strict=True)
    short_term_capital_general: int = Field(default=0, ge=0, strict=True)
    short_term_capital_reduced: int = Field(default=0, ge=0, strict=True)
    long_term_capital_general: int = Field(default=0, ge=0, strict=True)
    long_term_capital_specific: int = Field(default=0, ge=0, strict=True)
    long_term_capital_reduced: int = Field(default=0, ge=0, strict=True)
    general_stock_gains: int = Field(default=0, ge=0, strict=True)
    listed_stock_gains: int = Field(default=0, ge=0, strict=True)
    listed_stock_dividends: int = Field(default=0, ge=0, strict=True)
    futures_income: int = Field(default=0, ge=0, strict=True)
    forestry_income: int = Field(default=0, ge=0, strict=True)
    retirement_income: int = Field(default=0, ge=0, strict=True)


class MinimumIncomeTaxInput(BaseModel):
    """高所得特例の二段階判定。税額は源泉・予定納税控除前、外国税額控除前の国税。"""

    model_config = ConfigDict(extra="forbid")

    fiscal_year: int = Field(strict=True)
    incomes: MinimumTaxIncomeBreakdown
    ordinary_income_tax: int = Field(ge=0, strict=True)  # 特例・追加税を加算する前
    uses_nonfiling_system: StrictBool = False
    nonfiling_income_withheld_tax: int = Field(default=0, ge=0, strict=True)  # 追加税を含む国税
    recalculated_income_tax: int | None = Field(default=None, ge=0, strict=True)
    calculation_mode: Literal["estimate", "filing"] = "estimate"
    income_scope_confirmed: StrictBool | None = None

    @model_validator(mode="after")
    def check_recalculation_context(self) -> MinimumIncomeTaxInput:
        if not self.uses_nonfiling_system:
            if self.nonfiling_income_withheld_tax:
                raise ValueError(
                    "申告不要制度を使わない入力に、その対象所得の源泉税は指定できません"
                )
            if self.recalculated_income_tax not in (None, self.ordinary_income_tax):
                raise ValueError(
                    "申告不要制度を使わない場合、再計算税額は通常の所得税額と一致させてください"
                )
        return self


class MinimumIncomeTaxResult(BaseModel):
    """基準所得・初回判定・再計算・加算税額。申告書全体の作成とは区別する。"""

    fiscal_year: int
    calculation_mode: Literal["estimate", "filing"]
    status: Literal["not_applicable", "requires_recalculation", "applicable"]
    income_scope_confirmed: bool
    base_income_amount: int
    threshold: int
    rate_numerator: int
    rate_denominator: int
    rounded_excess_income: int
    benchmark_tax: int
    ordinary_tax_with_special: int
    initial_base_tax: int
    initial_additional_tax: int
    recalculated_income_tax: int | None = None
    recalculated_base_tax: int | None = None
    additional_income_tax: int | None = None
    adjusted_income_tax: int | None = None
    final_special_taxes: IncomeSpecialTaxResult | None = None
    total_tax: int | None = None
    warnings: list[str] = Field(default_factory=list)


class FurusatoLimitInput(BaseModel):
    """住民税の資料から求める上限推定。標準税率の所得割・調整控除後の額を使う。"""

    model_config = ConfigDict(extra="forbid")

    fiscal_year: int = Field(strict=True)  # 寄附年。住民税年度は+1
    resident_tax_income_levy: int = Field(ge=0, strict=True)
    resident_taxable_income: int = Field(ge=0, strict=True)
    personal_deduction_difference: int = Field(ge=0, strict=True)
    income_tax_basic_deduction: int = Field(ge=0, strict=True)
    income_tax_rate_percent: Literal[0, 5, 10, 20, 23, 33, 40, 45] | None = None

    @field_validator("income_tax_rate_percent", mode="before")
    @classmethod
    def require_integer_rate(cls, value: object) -> object:
        if value is not None and type(value) is not int:
            raise ValueError("income_tax_rate_percent は整数で指定してください")
        return value


class FurusatoLimitResult(BaseModel):
    """全額控除を保証しない概算。寄附額と住民税特例控除額の上限を区別する。"""

    fiscal_year: int
    resident_tax_assessment_year: int
    estimated_limit: int
    resident_tax_income_levy: int
    rate_adjustment: int
    rate_taxable_income: int
    income_tax_rate_percent: int
    special_credit_rate_numerator: int
    special_credit_rate_denominator: int
    income_levy_twenty_percent: int
    fixed_special_credit_cap: int | None
    special_credit_limit: int
    fixed_cap_applied: bool
    warnings: list[str] = Field(default_factory=list)


class ResidentTaxRelativeInput(BaseModel):
    """住民税控除用の親族情報。適格性には生計・専従者・国外居住等の確認を含む。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    birth_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    income: int = Field(ge=0, strict=True)
    eligible: StrictBool
    cohabiting: StrictBool = False
    is_lineal_ascendant: StrictBool = False
    other_taxpayer_dependent: StrictBool = False
    disability: Literal["general", "special", "special_cohabiting"] | None = None

    @field_validator("birth_date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def validate_cohabiting_disability(self) -> ResidentTaxRelativeInput:
        if self.disability == "special_cohabiting" and not self.cohabiting:
            raise ValueError("同居特別障害者には cohabiting=true が必要です")
        return self


class ResidentLifeInsuranceInput(BaseModel):
    """住民税用の新旧契約別保険料。所得税の計算済み控除額は受け取らない。"""

    model_config = ConfigDict(extra="forbid")

    general_new: int = Field(default=0, ge=0, strict=True)
    general_old: int = Field(default=0, ge=0, strict=True)
    medical_care: int = Field(default=0, ge=0, strict=True)
    annuity_new: int = Field(default=0, ge=0, strict=True)
    annuity_old: int = Field(default=0, ge=0, strict=True)


class ResidentTaxEstimateInput(BaseModel):
    """総合課税の所得と控除元データから住民税の標準所得割を推定する。"""

    model_config = ConfigDict(extra="forbid")

    fiscal_year: int = Field(strict=True)  # 所得年。住民税課税年度は翌年
    income_scope: Literal["comprehensive_only"]
    income_levy_taxable: StrictBool  # 自治体の非課税要件を確認した結果
    aggregate_income: int = Field(ge=0, strict=True)  # 繰越控除前の合計所得金額
    total_income: int = Field(ge=0, strict=True)  # 繰越控除後の総所得金額等
    social_insurance: int = Field(default=0, ge=0, strict=True)
    small_business_mutual_aid: int = Field(default=0, ge=0, strict=True)  # iDeCo等を含む合計
    life_insurance: ResidentLifeInsuranceInput = Field(default_factory=ResidentLifeInsuranceInput)
    earthquake_premium: int = Field(default=0, ge=0, strict=True)
    old_long_term_premium: int = Field(default=0, ge=0, strict=True)
    same_earthquake_contract: StrictBool | None = None
    medical_method: Literal["none", "medical", "self_medication"] = "none"
    medical_expenses_net: int = Field(default=0, ge=0, strict=True)  # 補填後
    self_medication_expenses_net: int = Field(default=0, ge=0, strict=True)
    self_medication_eligible: StrictBool | None = None
    spouse: ResidentTaxRelativeInput | None = None
    dependents: list[ResidentTaxRelativeInput] = Field(default_factory=list)
    widow_status: Literal["none", "widow", "single_parent_mother", "single_parent_father"] = "none"
    disability: Literal["general", "special"] | None = None
    working_student: StrictBool = False
    working_student_nonwork_income: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def validate_estimate_inputs(self) -> ResidentTaxEstimateInput:
        if self.total_income > self.aggregate_income:
            raise ValueError("total_income は繰越控除前の aggregate_income を超えられません")
        if self.earthquake_premium and self.old_long_term_premium:
            if self.same_earthquake_contract is None:
                raise ValueError(
                    "地震保険と旧長期契約の同一性を same_earthquake_contract で確認してください"
                )
        if self.medical_method == "none" and (
            self.medical_expenses_net or self.self_medication_expenses_net
        ):
            raise ValueError("医療費を入力する場合は medical_method を選択してください")
        if self.medical_method == "medical" and self.self_medication_expenses_net:
            raise ValueError("通常の医療費控除とセルフメディケーションは併用できません")
        if self.medical_method == "self_medication":
            if self.medical_expenses_net or self.self_medication_eligible is not True:
                raise ValueError("セルフメディケーションには要件確認と通常医療費との選択が必要です")
        if self.working_student and self.working_student_nonwork_income is None:
            raise ValueError(
                "勤労学生には給与所得等以外の所得 working_student_nonwork_income が必要です"
            )
        if self.widow_status != "none" and self.spouse is not None:
            raise ValueError("寡婦・ひとり親の指定と現在の配偶者情報は併用できません")
        if (
            self.working_student_nonwork_income is not None
            and self.working_student_nonwork_income > self.aggregate_income
        ):
            raise ValueError("勤労学生の給与所得等以外の所得は aggregate_income を超えられません")
        return self


class ResidentTaxDeductionItem(BaseModel):
    """住民税控除額と、税源移譲時の制度による人的控除差。"""

    type: str
    name: str
    amount: int
    personal_difference: int = 0


class ResidentTaxEstimateResult(BaseModel):
    """標準税率の推定内訳と、既存ふるさと納税CLIへ渡せる入力。"""

    fiscal_year: int
    resident_tax_assessment_year: int
    income_levy_taxable: bool
    deductions: list[ResidentTaxDeductionItem]
    resident_tax_deductions_total: int
    resident_taxable_income: int
    personal_deduction_difference: int
    adjustment_credit: int
    resident_tax_income_levy: int
    furusato_input: FurusatoLimitInput
    furusato_limit: FurusatoLimitResult
    warnings: list[str]


class IncomeTaxInput(BaseModel):
    """所得税計算の入力。"""

    fiscal_year: int
    salary_income: int = 0
    salary_income_adjustment_eligible: StrictBool | None = None
    pension_income: int = Field(default=0, ge=0)
    pension_is_over_65: StrictBool | None = None
    minimum_tax_income_complete: StrictBool | None = None
    business_revenue: int = 0
    business_expenses: int = 0
    blue_return_deduction: int = Field(default=650_000, ge=0)
    calculation_mode: Literal["estimate", "filing"] = "estimate"
    blue_return_eligibility: BlueReturnEligibilityFacts | None = None
    social_insurance: int = 0
    life_insurance_premium: int = 0
    life_insurance_detail: LifeInsurancePremiumInput | None = None  # 3区分詳細（Phase 3）
    earthquake_insurance_premium: int = 0
    old_long_term_insurance_premium: int = 0  # 旧長期損害保険料（Phase 4）
    medical_expenses: int = 0
    self_medication_expenses: int = 0  # セルフメディケーション税制（Phase 8）
    self_medication_eligible: bool = False  # 特定健康診査等を受けているか
    furusato_nozei: int = 0
    housing_loan_balance: int = 0
    housing_loan_year: int | None = None
    housing_loan_detail: HousingLoanDetail | None = None
    housing_loan_details: list[HousingLoanDetail] = Field(
        default_factory=list, description="複数明細（重複適用対応）"
    )
    taxpayer_birth_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    spouse_income: int | None = None
    spouse_birth_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    dependents: list[DependentInfo] = Field(default_factory=list)
    ideco_contribution: int = 0  # iDeCo掛金（小規模企業共済等掛金控除）
    small_business_mutual_aid: SmallBusinessMutualAidInput | None = None  # Phase 7
    widow_status: str = "none"  # none / widow / single_parent（Phase 5）
    disability_status: str = "none"  # none / general / special（Phase 5）
    working_student: bool = False  # 勤労学生（Phase 5）
    withheld_tax: int = 0  # 給与の源泉徴収税額
    business_withheld_tax: int = 0  # 事業所得の源泉徴収税額（取引先別合計）
    loss_carryforward_amount: int = 0  # 繰越損失額
    estimated_tax_payment: int = 0  # 予定納税額（第1期+第2期）
    # Phase 10: その他所得（総合課税）
    misc_income: int = 0  # 雑所得
    dividend_income_comprehensive: int = 0  # 配当所得（総合課税）
    one_time_income: int = 0  # 一時所得（1/2適用前の金額）
    other_income_withheld_tax: int = 0  # その他所得の源泉徴収税額
    # 寄附金（ふるさと納税以外）
    donations: list[DonationRecordRecord] = Field(default_factory=list)


class IncomeTaxResult(BaseModel):
    """所得税計算結果。"""

    fiscal_year: int
    calculation_mode: Literal["estimate", "filing"] = "estimate"
    eligibility_checks: list[TaxEligibilityCheck] = Field(default_factory=list)
    # 所得
    salary_income_after_deduction: int = 0
    salary_child_adjustment: int = 0
    salary_pension_adjustment: int = 0
    pension_income_after_deduction: int = 0
    pension_deduction: int = 0
    pension_salary_cap_adjustment: int = 0
    aggregate_income_before_loss_carryforward: int = 0
    business_income: int = 0
    total_income: int = 0
    # 青色申告特別控除（実効額）
    effective_blue_return_deduction: int = 0
    # 所得控除
    total_income_deductions: int = 0
    taxable_income: int = 0
    # 税額
    income_tax_base: int = 0
    dividend_credit: int = 0  # 配当控除（税額控除）
    housing_loan_credit: int = 0  # 住宅ローン控除（税額控除）
    housing_loan_credit_entries: list[HousingLoanCreditEntry] = Field(default_factory=list)
    public_interest_donation_credit: int = 0  # 公益社団法人等寄附金特別控除
    npo_donation_credit: int = 0  # 認定NPO法人等寄附金特別控除
    political_donation_credit: int = 0  # 政党等寄附金特別控除
    total_tax_credits: int = 0
    income_tax_after_credits: int = 0
    minimum_tax_additional_income_tax: int = 0
    income_tax_after_minimum_tax: int = 0
    minimum_tax_detail: MinimumIncomeTaxResult | None = None
    reconstruction_tax: int = 0
    defense_tax: int = 0
    special_tax_rounding_adjustment: int = 0
    income_special_tax_detail: IncomeSpecialTaxResult | None = None
    total_tax: int = 0
    withheld_tax: int = 0
    business_withheld_tax: int = 0  # 事業所得の源泉徴収税額
    estimated_tax_payment: int = 0  # 予定納税額
    loss_carryforward_applied: int = 0  # 適用した繰越損失額
    tax_due: int = Field(
        description="正:納付、負:還付 = total_tax - withheld_tax - "
        "business_withheld_tax - estimated_tax_payment"
    )
    # 内訳
    deductions_detail: DeductionsResult | None = None
    donation_adjustment: DonationAdjustmentResult | None = None
    donation_selection: DonationMethodSelection | None = None
    # 警告（自動調整等）
    warnings: list[str] = Field(default_factory=list)


class PurchaseDetail(BaseModel):
    """仕入税額控除を判定するための課税仕入れ明細。"""

    model_config = ConfigDict(extra="forbid")

    tax_recognition_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    amount_inclusive: int
    tax_rate: Literal["standard_10", "reduced_8"]
    credit_category: Literal[
        "qualified_invoice",
        "nonqualified_transitional",
        "book_only_full_credit",
        "small_amount_full_credit",
        "noncreditable",
        "unknown",
    ]
    supplier_key: str | None = None

    @field_validator("tax_recognition_date")
    @classmethod
    def validate_tax_recognition_date(cls, value: str) -> str:
        """実在する暦日かを検証する。"""
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "tax_recognition_date は実在する YYYY-MM-DD 形式の日付が必要です"
            ) from exc
        return value

    @model_validator(mode="after")
    def validate_small_amount_period(self) -> PurchaseDetail:
        """少額特例の法定期限後の指定を拒否する。"""
        if self.credit_category == "small_amount_full_credit" and date.fromisoformat(
            self.tax_recognition_date
        ) >= date(2029, 10, 1):
            raise ValueError("small_amount_full_credit は 2029-09-30 まで指定できます")
        return self


class ConsumptionTaxInput(BaseModel):
    """消費税計算の入力。

    売上・仕入は税込金額で入力する。
    """

    model_config = ConfigDict(extra="forbid")

    fiscal_year: int
    method: Literal["standard", "simplified", "special_20pct", "special_30pct"]
    calculation_mode: Literal["estimate", "filing"] = "estimate"
    invoice_special_eligibility: InvoiceSpecialEligibilityFacts | None = None
    taxable_sales_10: int = 0  # 課税売上高(税込, 標準税率10%)
    taxable_sales_8: int = 0  # 課税売上高(税込, 軽減税率8%)
    taxable_purchases_10: int = 0  # 課税仕入高(税込, 標準税率10%)
    taxable_purchases_8: int = 0  # 課税仕入高(税込, 軽減税率8%)
    purchase_details: list[PurchaseDetail] | None = None
    legacy_purchase_assumption: Literal["all_qualified"] | None = None
    simplified_business_type: int | None = Field(
        default=None, ge=1, le=6, description="簡易課税の事業区分(1-6)"
    )
    interim_payment: int = Field(default=0, ge=0)  # 国税の中間納付税額
    local_interim_payment: int | None = Field(default=None, ge=0)  # 地方消費税の中間納付譲渡割額

    @model_validator(mode="after")
    def require_simplified_business_type(self) -> ConsumptionTaxInput:
        """簡易課税ではみなし仕入率を決める事業区分を必須とする。"""
        if self.method == "simplified" and self.simplified_business_type is None:
            raise ValueError("簡易課税では simplified_business_type が必要です")
        if self.method == "standard":
            has_legacy_amounts = bool(self.taxable_purchases_10 or self.taxable_purchases_8)
            if self.purchase_details is not None and (
                has_legacy_amounts or self.legacy_purchase_assumption is not None
            ):
                raise ValueError("purchase_details と旧形式の仕入入力は併用できません")
            if (
                self.purchase_details is None
                and has_legacy_amounts
                and self.legacy_purchase_assumption != "all_qualified"
            ):
                raise ValueError(
                    "旧形式の仕入額を使う場合は legacy_purchase_assumption='all_qualified' が必要です"
                )
        return self


class TaxRateAmountBreakdown(BaseModel):
    """標準税率と軽減税率に分けた金額。"""

    standard_10: int = 0
    reduced_8: int = 0
    total: int = 0


class TransitionalCreditBreakdown(BaseModel):
    """経過措置の控除割合別内訳。"""

    rate_percent: int
    amount_inclusive: TaxRateAmountBreakdown
    tax_equivalent: TaxRateAmountBreakdown
    credit_amount: TaxRateAmountBreakdown


class ConsumptionTaxForm2_3Result(BaseModel):
    """消費税申告書付表2-3の主要欄に対応する集計値。"""

    row_9_purchase_amount: TaxRateAmountBreakdown
    row_10_purchase_tax: TaxRateAmountBreakdown
    row_11_transitional_purchase_amount: TaxRateAmountBreakdown
    row_12_transitional_deemed_tax: TaxRateAmountBreakdown
    row_17_total_input_tax: TaxRateAmountBreakdown


class ConsumptionTaxResult(BaseModel):
    """消費税計算結果。

    正しい計算フロー（消費税法 第28条、第45条）:
    1. 課税標準額 = 税込金額 × 100/110（or 100/108）、1,000円未満切捨（国税通則法118条）
    2. 消費税額(国税) = 課税標準額 × 7.8%（or 6.24%）
    3. 控除対象仕入税額を計算（方式により異なる）
    4. 差引税額(正の場合) = 消費税額 − 控除対象仕入税額、100円未満切捨
       控除不足還付税額(負の場合) = 控除対象仕入税額 − 消費税額、端数処理なし
    5. 地方消費税 = 差引税額または控除不足還付税額 × 22/78
       納税額は100円未満切捨、還付額は1円未満切捨
    """

    fiscal_year: int
    calculation_mode: Literal["estimate", "filing"] = "estimate"
    eligibility_checks: list[TaxEligibilityCheck] = Field(default_factory=list)
    method: str
    # 課税売上
    taxable_sales_total: int = 0  # 課税売上高合計（税込）— 表示用
    taxable_base_10: int = 0  # 課税標準額(10%分, 税抜, 1000円切捨)
    taxable_base_8: int = 0  # 課税標準額(8%分, 税抜, 1000円切捨)
    # 消費税額
    national_tax_on_sales: int = 0  # 消費税額(国税: 7.8%分+6.24%分)
    tax_on_sales: int = 0  # = national_tax_on_sales（後方互換エイリアス）
    tax_on_purchases: int = 0  # 控除対象仕入税額(国税部分)
    full_credit_purchase_amount: TaxRateAmountBreakdown = Field(
        default_factory=TaxRateAmountBreakdown
    )
    full_credit_tax_amount: TaxRateAmountBreakdown = Field(default_factory=TaxRateAmountBreakdown)
    transitional_credit_breakdown: list[TransitionalCreditBreakdown] = Field(default_factory=list)
    noncreditable_amount: TaxRateAmountBreakdown = Field(default_factory=TaxRateAmountBreakdown)
    unclassified_amount: TaxRateAmountBreakdown = Field(default_factory=TaxRateAmountBreakdown)
    unclassified_count: int = 0
    form_2_3: ConsumptionTaxForm2_3Result | None = None
    warnings: list[str] = Field(default_factory=list)
    calculation_method: Literal["tax_inclusive_total"] = "tax_inclusive_total"
    legacy_purchase_assumption: Literal["all_qualified"] | None = None
    # 差引き
    net_tax: int = 0  # 差引税額(100円切捨, 正の場合のみ) AAJ00100
    refund_shortfall: int = 0  # 控除不足還付税額(仕入>売上の場合) AAJ00090
    interim_payment: int = 0  # 国税の中間納付税額 AAJ00110
    local_interim_payment: int = 0
    local_tax_due_after_interim_payment: int = 0  # 地方税の納付・還付の合計差額
    local_interim_refund: int = 0  # 中間納付還付譲渡割額（年税額の還付と区別）
    # 後方互換の符号付き集計値 = net_tax - interim_payment
    # 正=納付税額⑪/AAJ00120、負=中間納付還付税額⑫相当の絶対値
    tax_due: int = 0
    # 地方消費税
    local_tax_due: int = 0  # 納付時は100円未満切捨、還付時は1円未満切捨
    # = tax_due - refund_shortfall + local_tax_due_after_interim_payment（負=還付）
    total_due: int = 0


# --- ふるさと納税 (furusato nozei) ---


class FurusatoReceiptData(BaseModel):
    """ふるさと納税受領証明書テンプレート。"""

    file_path: str
    municipality_name: str | None = None
    municipality_prefecture: str | None = None
    address: str | None = None
    amount: int | None = None
    date: str | None = None
    receipt_number: str | None = None


class FurusatoDonationRecord(BaseModel):
    """ふるさと納税寄附データ（DBレコード）。"""

    id: int
    fiscal_year: int
    municipality_name: str
    municipality_prefecture: str | None
    amount: int
    date: str
    receipt_number: str | None
    one_stop_applied: bool
    source_file: str | None


class FurusatoDonationSummary(BaseModel):
    """ふるさと納税集計結果。"""

    fiscal_year: int
    total_amount: int
    donation_count: int
    municipality_count: int
    deduction_amount: int = Field(description="所得控除額 = 合計 - 2,000円")
    estimated_limit: int | None = Field(
        default=None, description="推定控除上限額（所得情報が必要）"
    )
    over_limit: bool = False
    one_stop_count: int = 0
    needs_tax_return: bool = Field(
        default=True,
        description="確定申告が必要か（副業ユーザーは常にTrue）",
    )
    donations: list[FurusatoDonationRecord] = Field(default_factory=list)


# --- 事業所得の源泉徴収 (business withholding) ---


class BusinessWithholdingInput(BaseModel):
    """取引先別の源泉徴収入力。"""

    client_name: str
    gross_amount: int = Field(gt=0, description="支払金額（円）")
    withholding_tax: int = Field(ge=0, description="源泉徴収税額（円）")


class BusinessWithholdingRecord(BaseModel):
    """取引先別の源泉徴収DBレコード。"""

    id: int
    fiscal_year: int
    client_name: str
    gross_amount: int
    withholding_tax: int


# --- 損失繰越 (loss carryforward) ---


class LossCarryforwardInput(BaseModel):
    """損失繰越の入力。"""

    loss_year: int  # 損失が発生した年
    amount: int = Field(gt=0, description="繰越損失額（円）")


class LossCarryforwardRecord(BaseModel):
    """損失繰越のDBレコード。"""

    id: int
    fiscal_year: int
    loss_year: int
    amount: int
    used_amount: int


# --- 医療費明細 (medical expense details) ---


class MedicalExpenseInput(BaseModel):
    """医療費明細の入力。"""

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    patient_name: str
    medical_institution: str
    amount: int = Field(gt=0, description="医療費（円）")
    insurance_reimbursement: int = 0  # 保険補填額
    description: str | None = None


class MedicalExpenseRecord(BaseModel):
    """医療費明細のDBレコード。"""

    id: int
    fiscal_year: int
    date: str
    patient_name: str
    medical_institution: str
    amount: int
    insurance_reimbursement: int
    description: str | None


# --- 地代家賃の内訳 (rent details) ---


class RentDetailInput(BaseModel):
    """地代家賃の内訳入力。"""

    property_type: str  # 事務所/自宅兼事務所/駐車場
    usage: str  # 事務所/自宅兼事務所
    landlord_name: str
    landlord_address: str
    monthly_rent: int = Field(gt=0, description="月額賃料（円）")
    annual_rent: int = Field(gt=0, description="年間賃料（円）")
    deposit: int = 0  # 権利金等
    business_ratio: int = Field(default=100, ge=1, le=100, description="事業割合（%）")


class RentDetailRecord(BaseModel):
    """地代家賃の内訳DBレコード。"""

    id: int
    fiscal_year: int
    property_type: str
    usage: str
    landlord_name: str
    landlord_address: str
    monthly_rent: int
    annual_rent: int
    deposit: int
    business_ratio: int


# --- 重複検出 (duplicate detection) ---


class DuplicateWarning(BaseModel):
    """登録時の重複警告。"""

    match_type: str = Field(pattern=r"^(exact|similar)$")
    score: int = Field(ge=0, le=100)
    existing_journal_id: int
    reason: str


class DuplicatePair(BaseModel):
    """重複ペア（申告前チェック用）。"""

    journal_id_a: int
    journal_id_b: int
    score: int = Field(ge=0, le=100)
    reason: str


class DuplicateCheckResult(BaseModel):
    """重複チェック結果。"""

    pairs: list[DuplicatePair] = Field(default_factory=list)
    exact_count: int = 0
    suspected_count: int = 0


# --- 配偶者情報 (spouse info) ---


class SpouseInput(BaseModel):
    """配偶者情報の入力。"""

    name: str
    date_of_birth: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    income: int = 0
    disability: str | None = Field(default=None, pattern=r"^(general|special|special_cohabiting)$")
    cohabiting: bool = True
    other_taxpayer_dependent: bool = False


class SpouseRecord(BaseModel):
    """配偶者情報のDBレコード。"""

    id: int
    fiscal_year: int
    name: str
    date_of_birth: str
    income: int
    disability: str | None
    cohabiting: bool
    other_taxpayer_dependent: bool


# --- 扶養親族 (dependents) DB永続化 ---


class DependentInput(BaseModel):
    """扶養親族の登録入力。"""

    name: str
    relationship: str
    date_of_birth: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    income: int = 0
    disability: str | None = Field(default=None, pattern=r"^(general|special|special_cohabiting)$")
    cohabiting: bool = True
    other_taxpayer_dependent: bool = False  # 他の納税者の扶養親族に該当する


class DependentRecord(BaseModel):
    """扶養親族のDBレコード。"""

    id: int
    fiscal_year: int
    name: str
    relationship: str
    date_of_birth: str
    income: int
    disability: str | None
    cohabiting: bool
    other_taxpayer_dependent: bool = False


# --- 源泉徴収票 (withholding slip) 拡張 ---


class WithholdingSlipInput(BaseModel):
    """源泉徴収票の登録入力。"""

    payer_name: str | None = None
    payment_amount: int = 0
    withheld_tax: int = 0
    social_insurance: int = 0
    life_insurance_deduction: int = 0
    earthquake_insurance_deduction: int = 0
    housing_loan_deduction: int = 0
    spouse_deduction: int = 0
    dependent_deduction: int = 0
    basic_deduction: int = 0
    # 拡張フィールド（Phase 6）
    life_insurance_general_new: int = 0
    life_insurance_general_old: int = 0
    life_insurance_medical_care: int = 0
    life_insurance_annuity_new: int = 0
    life_insurance_annuity_old: int = 0
    national_pension_premium: int = 0
    old_long_term_insurance_premium: int = 0
    source_file: str | None = None


class WithholdingSlipRecord(BaseModel):
    """源泉徴収票のDBレコード。"""

    id: int
    fiscal_year: int
    payer_name: str | None
    payment_amount: int
    withheld_tax: int
    social_insurance: int
    life_insurance_deduction: int
    earthquake_insurance_deduction: int
    housing_loan_deduction: int
    spouse_deduction: int
    dependent_deduction: int
    basic_deduction: int
    life_insurance_general_new: int = 0
    life_insurance_general_old: int = 0
    life_insurance_medical_care: int = 0
    life_insurance_annuity_new: int = 0
    life_insurance_annuity_old: int = 0
    national_pension_premium: int = 0
    old_long_term_insurance_premium: int = 0
    source_file: str | None = None


# --- その他所得 (other income) ---


class OtherIncomeInput(BaseModel):
    """その他所得（雑/配当/一時）の入力。"""

    income_type: str = Field(
        pattern=r"^(miscellaneous|dividend_comprehensive|one_time)$",
        description="miscellaneous=雑所得, dividend_comprehensive=配当所得(総合課税), one_time=一時所得",
    )
    description: str
    revenue: int = Field(ge=0, description="収入（円）")
    expenses: int = 0
    withheld_tax: int = 0
    payer_name: str | None = None
    payer_address: str | None = None


class OtherIncomeRecord(BaseModel):
    """その他所得のDBレコード。"""

    id: int
    fiscal_year: int
    income_type: str
    description: str
    revenue: int
    expenses: int
    withheld_tax: int
    payer_name: str | None
    payer_address: str | None


# --- 仮想通貨 (crypto) ---


class CryptoIncomeInput(BaseModel):
    """仮想通貨取引の入力。"""

    exchange_name: str
    gains: int = 0
    expenses: int = 0


class CryptoIncomeRecord(BaseModel):
    """仮想通貨取引のDBレコード。"""

    id: int
    fiscal_year: int
    exchange_name: str
    gains: int
    expenses: int


# --- 在庫棚卸 (inventory) ---


class InventoryInput(BaseModel):
    """在庫棚卸の入力。"""

    period: str = Field(
        pattern=r"^(beginning|ending)$",
        description="beginning=期首棚卸, ending=期末棚卸",
    )
    amount: int = Field(ge=0, description="棚卸高（円）")
    method: str = "cost"  # cost / retail / etc.
    details: str | None = None


class InventoryRecord(BaseModel):
    """在庫棚卸のDBレコード。"""

    id: int
    fiscal_year: int
    period: str
    amount: int
    method: str
    details: str | None


# --- 税理士等報酬 (professional fees) ---


class ProfessionalFeeInput(BaseModel):
    """税理士等報酬の入力。"""

    payer_address: str
    payer_name: str
    fee_amount: int = Field(gt=0, description="報酬金額（円）")
    expense_deduction: int = 0  # 必要経費
    withheld_tax: int = 0


class ProfessionalFeeRecord(BaseModel):
    """税理士等報酬のDBレコード。"""

    id: int
    fiscal_year: int
    payer_address: str
    payer_name: str
    fee_amount: int
    expense_deduction: int
    withheld_tax: int


# --- 株式取引 (stock trading) ---


class StockTradingAccountInput(BaseModel):
    """株式取引口座の入力。"""

    account_type: str = Field(
        pattern=r"^(tokutei_withholding|tokutei_no_withholding|ippan_listed|ippan_unlisted)$",
        description="tokutei_withholding=特定口座(源泉あり), tokutei_no_withholding=特定口座(源泉なし), "
        "ippan_listed=一般口座(上場), ippan_unlisted=一般口座(非上場)",
    )
    broker_name: str
    gains: int = 0
    losses: int = 0
    withheld_income_tax: int = 0
    withheld_residential_tax: int = 0
    dividend_income: int = 0
    dividend_withheld_tax: int = 0


class StockTradingAccountRecord(BaseModel):
    """株式取引口座のDBレコード。"""

    id: int
    fiscal_year: int
    account_type: str
    broker_name: str
    gains: int
    losses: int
    withheld_income_tax: int
    withheld_residential_tax: int
    dividend_income: int
    dividend_withheld_tax: int


class StockLossCarryforwardInput(BaseModel):
    """株式譲渡損失繰越の入力。"""

    loss_year: int
    amount: int = Field(gt=0, description="繰越損失額（円）")


class StockLossCarryforwardRecord(BaseModel):
    """株式譲渡損失繰越のDBレコード。"""

    id: int
    fiscal_year: int
    loss_year: int
    amount: int
    used_amount: int


# --- FX取引 (FX trading) ---


class FXTradingInput(BaseModel):
    """FX取引の入力。"""

    broker_name: str
    realized_gains: int = 0
    swap_income: int = 0
    expenses: int = 0


class FXTradingRecord(BaseModel):
    """FX取引のDBレコード。"""

    id: int
    fiscal_year: int
    broker_name: str
    realized_gains: int
    swap_income: int
    expenses: int


class FXLossCarryforwardInput(BaseModel):
    """FX損失繰越の入力。"""

    loss_year: int
    amount: int = Field(gt=0, description="繰越損失額（円）")


class FXLossCarryforwardRecord(BaseModel):
    """FX損失繰越のDBレコード。"""

    id: int
    fiscal_year: int
    loss_year: int
    amount: int
    used_amount: int


# --- 社会保険料の種別別内訳 (social insurance items) ---


class SocialInsuranceItemInput(BaseModel):
    """社会保険料の種別入力。"""

    insurance_type: str = Field(
        description="種別: national_health / national_pension / national_pension_fund"
        " / nursing_care / labor_insurance / other"
    )
    name: str | None = None  # 保険者名等
    amount: int = Field(gt=0, description="円単位の整数")


class SocialInsuranceItemRecord(BaseModel):
    """社会保険料の種別DBレコード。"""

    id: int
    fiscal_year: int
    insurance_type: str
    name: str | None
    amount: int


# --- 保険契約（生命保険・地震保険の保険会社名） ---


class InsurancePolicyInput(BaseModel):
    """保険契約の入力。"""

    policy_type: str = Field(
        description="種別: life_general_new / life_general_old / life_medical_care"
        " / life_annuity_new / life_annuity_old / earthquake / old_long_term"
    )
    company_name: str  # 保険会社名
    premium: int = Field(gt=0, description="円単位の整数")


class InsurancePolicyRecord(BaseModel):
    """保険契約のDBレコード。"""

    id: int
    fiscal_year: int
    policy_type: str
    company_name: str
    premium: int


# --- 寄附金（ふるさと納税以外） ---


class DonationRecordInput(BaseModel):
    """ふるさと納税以外の寄附金入力。"""

    donation_type: DonationType = Field(
        description="種別: political / npo / public_interest / specified / other"
    )
    recipient_name: str  # 寄附先名
    amount: int = Field(gt=0, description="円単位の整数")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    receipt_number: str | None = None
    source_file: str | None = None


class DonationRecordRecord(BaseModel):
    """寄附金のDBレコード。"""

    id: int
    fiscal_year: int
    donation_type: DonationType
    recipient_name: str
    amount: int
    date: str
    receipt_number: str | None
    source_file: str | None


# --- 公的年金等控除 (pension deduction) ---


class PensionDeductionInput(BaseModel):
    """公的年金等控除の入力。"""

    pension_income: int = Field(ge=0, description="公的年金等の収入金額（円）")
    is_over_65: bool = Field(description="65歳以上かどうか（年度末時点）")
    other_income: int = 0  # 公的年金等以外の合計所得金額
    fiscal_year: int = 2025
    salary_income_deduction: int | None = Field(default=None, ge=0, le=1_950_000)


class PensionDeductionResult(BaseModel):
    """公的年金等控除の計算結果。"""

    pension_income: int  # 入力の年金収入
    deduction_amount: int  # 控除額
    taxable_pension_income: int  # 雑所得（年金） = pension_income - deduction_amount
    is_over_65: bool
    other_income_adjustment: int = 0  # 所得調整額（0, 100000, 200000）
    fiscal_year: int = 2025
    deduction_before_salary_cap: int = 0
    taxable_pension_income_before_salary_cap: int = 0
    salary_cap_adjustment: int = 0


# --- 退職所得 (retirement income) ---


class RetirementIncomeInput(BaseModel):
    """退職所得の入力。"""

    severance_pay: int = Field(ge=0, description="退職手当等の収入金額（円）")
    years_of_service: int = Field(gt=0, description="勤続年数（1年未満切上げ）")
    is_officer: bool = False  # 役員等かどうか（5年以下特例）
    is_disability_retirement: bool = False  # 障害退職かどうか（+100万加算）


class RetirementIncomeResult(BaseModel):
    """退職所得の計算結果。"""

    severance_pay: int
    retirement_income_deduction: int  # 退職所得控除額
    taxable_retirement_income: int  # 退職所得（1/2適用後）
    years_of_service: int
    is_officer: bool
    half_taxation_applied: bool  # 1/2課税が適用されたか


# --- サニティチェック (sanity check) ---


class TaxSanityCheckItem(BaseModel):
    """サニティチェックの1項目。"""

    severity: str = Field(pattern=r"^(error|warning|info)$")
    code: str
    message: str


class TaxSanityCheckResult(BaseModel):
    """サニティチェック結果。"""

    passed: bool
    items: list[TaxSanityCheckItem] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
