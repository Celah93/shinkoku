# income-tax: 税額を計算しサニティチェックで検算するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ3: 所得税額の計算

申告用には `calculation_mode: "filing"` と確認済みの `blue_return_eligibility` を入力する。以下の従来例は試算用であり、適用要件を確認した申告用入力の例は `docs/tax-eligibility.md` を参照する。推測でフラグを埋めない。

### `shinkoku tax calc-income --input income_input.json` の呼び出し

```bash
shinkoku tax calc-income --input income_input.json
```
入力 JSON (IncomeTaxInput):
```json
{
  "fiscal_year": 2025,
  "salary_income": 5000000,
  "business_revenue": 3000000,
  "business_expenses": 1000000,
  "blue_return_deduction": 650000,
  "social_insurance": 700000,
  "life_insurance_premium": 80000,
  "earthquake_insurance_premium": 30000,
  "medical_expenses": 0,
  "furusato_nozei": 50000,
  "housing_loan_balance": 0,
  "taxpayer_birth_date": null,
  "spouse_income": null,
  "spouse_birth_date": null,
  "ideco_contribution": 276000,
  "withheld_tax": 100000,
  "business_withheld_tax": 30000,
  "estimated_tax_payment": 0,
  "loss_carryforward_amount": 0
}
```
出力 (IncomeTaxResult):
- `salary_income_after_deduction`: 給与所得控除・所得金額調整後の金額
- `salary_child_adjustment` / `salary_pension_adjustment`: 給与の所得金額調整の内訳
- `pension_income_after_deduction` / `pension_deduction` / `pension_salary_cap_adjustment`: 年金所得・控除・給与との合計上限による減額
- `business_income`: 事業所得
- `aggregate_income_before_loss_carryforward`: 人的控除の所得制限に使う合計所得金額（繰越控除前）
- `total_income`: 総所得金額等（繰越控除後）
- `total_income_deductions`: 所得控除合計
- `taxable_income`: 課税所得金額（1,000円未満切り捨て）
- `income_tax_base`: 算出税額
- `total_tax_credits`: 税額控除合計
- `housing_loan_credit_entries`: 住宅ローン控除の年数・期間・状態を含む個別明細
- `income_tax_after_credits`: 税額控除後
- `reconstruction_tax`: 復興特別所得税の円単位参考内訳（2025・2026年2.1%、2027年1.1%）
- `defense_tax`: 防衛特別所得税の円単位参考内訳（2027年1%）
- `special_tax_rounding_adjustment` / `income_special_tax_detail`: 合算端数・整数の分子と分母。内訳だけを足して税額を作り直さない
- `total_tax`: 所得税と特別所得税の合算額（円単位、精算前）
- `withheld_tax`: 源泉徴収税額（給与分）
- `business_withheld_tax`: 事業所得の源泉徴収税額
- `estimated_tax_payment`: 予定納税額
- `loss_carryforward_applied`: 適用した繰越損失額
- `tax_due`: 合計税額から給与・事業・その他所得の源泉徴収と予定納税を引いた額。納付だけ100円未満切捨て、負は還付

**寄附金控除の反映:**

ふるさと納税以外の寄附金控除（ステップ1.14で登録）は、`calc_income_tax` が3区分の方式を選択し、最終結果へ反映する。以下のパラメータを渡す:
- `furusato_nozei`: ふるさと納税の寄附金合計
- `donations`: 政治・認定NPO・公益社団法人等・特定公益増進法人・その他の寄附金レコード

結果では次を確認する:

- `donation_selection`: 公益・NPO・政治ごとの選択方式（`income` / `credit`）
- `public_interest_donation_credit` / `npo_donation_credit` / `political_donation_credit`: 区分別の最終税額控除
- `donation_adjustment`: 所得控除、40%枠適用後の対象額、残りの2,000円、100円丸め後の算式額、25%上限、最終控除額
- `deductions_detail` の `details`: 選択後に所得控除へ残った寄附金内訳

`calc_deductions` を個別に呼ぶ場合は `donations` を渡せるが、その寄附金出力は所得控除候補と税額控除候補を併記した中間値である。申告書・計算明細書へ転記しないこと。

**青色申告特別控除の自動キャップ:**

`blue_return_deduction` の config 値は候補額であり、適格性の証明にはならない。申告用では `blue_return_eligibility` で要件を確認した上で渡す。計算エンジンは事業利益による上限も適用する（租特法25条の2）。
結果の `effective_blue_return_deduction` と `warnings` を必ず確認すること。

**計算結果の確認:**

1. 合計所得金額の内訳を表示する
2. `effective_blue_return_deduction` を確認し、自動調整があれば `warnings` の内容を表示する
3. 繰越損失が適用されている場合はその額を明示する
4. 所得税の速算表の適用が正しいか確認する
5. 年分に対応した復興・防衛特別所得税と合算端数を確認する
6. 源泉徴収税額（給与分 + 事業分）が正しく控除されているか確認する
7. 予定納税額が正しく控除されているか確認する
8. 最終的な納付額（または還付額）を明示する

所得税の速算表・配偶者控除テーブル・住宅ローン限度額等は `references/deduction-tables.md` を参照。


## ステップ3.1: サニティチェック（必須）

`calc-income` の結果を自動検証する。このステップはスキップ不可。

### `shinkoku tax sanity-check --input sanity_input.json` の呼び出し

```bash
shinkoku tax sanity-check --input sanity_input.json
```
入力 JSON:
```json
{
  "input": { ... },
  "result": { ... }
}
```
- `input`: ステップ3で `calc-income` に渡した IncomeTaxInput
- `result`: ステップ3で `calc-income` から返された IncomeTaxResult

出力 (TaxSanityCheckResult):
- `passed`: true/false
- `items`: チェック項目のリスト（severity, code, message）
- `error_count`: エラー件数
- `warning_count`: 警告件数

### 結果に応じた対応

- **error > 0**: 計算結果に問題があります。エラー内容を確認し、入力を修正してステップ3を再実行してください
- **warning > 0**: 警告内容をユーザーに提示し、確認してから続行してください
- **passed = true**: 問題なし。次のステップに進む
