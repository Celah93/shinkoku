# income-tax: 源泉徴収票を読み取り、控除内訳を検算するとき

該当する作業でだけ参照する。コマンドとパスはプロジェクトルートを基準とする。給与の原本値と、給与以外の所得も含めた申告時の控除額を区別する。

## 1. ファイルを受け付け、原本から構造化する

```bash
shinkoku import withholding --file-path withholding.pdf
```

画像ファイルの場合の実出力は次のNULLテンプレートである。PDFでは`extracted_text`へ抽出したテキストが入る。`status=ok`はファイル受付・抽出の成功を示し、金額の読取り完了ではない。

```json
{
  "status": "ok",
  "payer_name": null,
  "payment_amount": null,
  "withheld_tax": null,
  "social_insurance": null,
  "life_insurance_deduction": null,
  "earthquake_insurance_deduction": null,
  "housing_loan_deduction": null,
  "spouse_deduction": null,
  "dependent_deduction": null,
  "basic_deduction": null,
  "life_insurance_general_new": null,
  "life_insurance_general_old": null,
  "life_insurance_medical_care": null,
  "life_insurance_annuity_new": null,
  "life_insurance_annuity_old": null,
  "national_pension_premium": null,
  "old_long_term_insurance_premium": null,
  "specific_relative_special_deduction": null,
  "total_income_deductions": null,
  "salary_income_after_deduction": null,
  "social_insurance_small_business_mutual_aid": null,
  "other_personal_deductions": null,
  "document_fiscal_year": null,
  "year_end_adjusted": null,
  "source_confirmed": null,
  "blank_fields": [],
  "deduction_derivation_note": null,
  "source_file": null,
  "file_path": "withholding.pdf",
  "extracted_text": ""
}
```

原本の読取りと構造化には[reading-withholding](../../reading-withholding/SKILL.md)を使う。`file_path`を`source_file`へ対応付ける。金額、空欄、内書き、年分、年末調整状態、派生額の根拠を平坦なJSONにまとめる。未読・不明を0へ変換しない。

## 2. 控除合計を検算し、原本を照合する

```bash
shinkoku ledger ws-check --fiscal-year 2025 --input salary.json
```

以下は原本照合が完了した2025年分の架空例である。

```json
{
  "payer_name": "架空勤務先",
  "payment_amount": 5000000,
  "withheld_tax": 77500,
  "social_insurance": 750000,
  "life_insurance_deduction": 0,
  "earthquake_insurance_deduction": 0,
  "housing_loan_deduction": 0,
  "spouse_deduction": 0,
  "dependent_deduction": 0,
  "basic_deduction": 680000,
  "life_insurance_general_new": null,
  "life_insurance_general_old": null,
  "life_insurance_medical_care": null,
  "life_insurance_annuity_new": null,
  "life_insurance_annuity_old": null,
  "national_pension_premium": null,
  "old_long_term_insurance_premium": null,
  "specific_relative_special_deduction": 610000,
  "total_income_deductions": 2040000,
  "salary_income_after_deduction": 3560000,
  "social_insurance_small_business_mutual_aid": null,
  "other_personal_deductions": 0,
  "document_fiscal_year": 2025,
  "year_end_adjusted": true,
  "source_confirmed": true,
  "blank_fields": [
    "life_insurance_general_new",
    "life_insurance_general_old",
    "life_insurance_medical_care",
    "life_insurance_annuity_new",
    "life_insurance_annuity_old",
    "national_pension_premium",
    "old_long_term_insurance_premium",
    "social_insurance_small_business_mutual_aid"
  ],
  "deduction_derivation_note": "NTA-2025-TABLE、2025年分。扶養控除対象者0人、その他人的控除の対象者0人。各0円。",
  "source_file": "withholding.pdf"
}
```

控除内訳の合計は、社会保険料等 + 生命保険料控除 + 地震保険料控除 + 配偶者控除 + 確認した扶養控除 + 特定親族特別控除 + 原本の基礎控除 + その他人的控除である。社会保険の内書き・国民年金・住宅ローン控除・給与所得控除後の金額は再加算しない。基礎控除が未記載なら未確認のままにし、申告全体の所得から穴埋めしない。

`validation.status`がmatchedでもOCR精度や税務上の適用要件を証明しない。二欄の交換は合計では検出できないので、それぞれのラベルと枠内の額を原本へ戻って確認する。未済の適切な空欄はnot_applicable、状態不明や必要内訳の不足はincompleteになる。未済と調整済み専用の記載額との矛盾は確認へ戻す。

有効な入力の不一致・不足はws-checkの終了コード0で返る。外側のstatusだけで判断せずvalidationとready_for_calculationを確認する。年分不一致・内書き超過・控除合計不一致などを機械的に補正しない。

## 3. 確認した対象を保存し、読戻す

原本の照合と、実データを保存する対象内容への確認を済ませる。同じ内容が確認済みなら再承認を求めない。

```bash
shinkoku ledger ws-save --db-path DB_PATH --fiscal-year 2025 --input salary.json
```

```json
{
  "payer_name": "架空勤務先",
  "payment_amount": 5000000,
  "withheld_tax": 77500,
  "social_insurance": 750000,
  "life_insurance_deduction": 0,
  "earthquake_insurance_deduction": 0,
  "housing_loan_deduction": 0,
  "spouse_deduction": 0,
  "dependent_deduction": 0,
  "basic_deduction": 680000,
  "life_insurance_general_new": null,
  "life_insurance_general_old": null,
  "life_insurance_medical_care": null,
  "life_insurance_annuity_new": null,
  "life_insurance_annuity_old": null,
  "national_pension_premium": null,
  "old_long_term_insurance_premium": null,
  "specific_relative_special_deduction": 610000,
  "total_income_deductions": 2040000,
  "salary_income_after_deduction": 3560000,
  "social_insurance_small_business_mutual_aid": null,
  "other_personal_deductions": 0,
  "document_fiscal_year": 2025,
  "year_end_adjusted": true,
  "source_confirmed": true,
  "blank_fields": [
    "life_insurance_general_new",
    "life_insurance_general_old",
    "life_insurance_medical_care",
    "life_insurance_annuity_new",
    "life_insurance_annuity_old",
    "national_pension_premium",
    "old_long_term_insurance_premium",
    "social_insurance_small_business_mutual_aid"
  ],
  "deduction_derivation_note": "NTA-2025-TABLE、2025年分。扶養控除対象者0人、その他人的控除の対象者0人。各0円。",
  "source_file": "withholding.pdf"
}
```

未確認を含む票は下書きとして保存できるが、戻り値のready_for_calculationはfalseになる。型不正・年分不一致・内書き矛盾・控除合計不一致・年末調整状態の矛盾は保存されない。

```bash
shinkoku ledger ws-list --db-path DB_PATH --fiscal-year 2025
```

各票のvalidationは読戻し時に再検算される。訂正は同じ年分のIDを指定し、確認した新しい全項目JSONを渡す。省略した項目はNULLになるため、部分パッチとして使わない。ID・作成日時は保持されるが、旧source_confirmedは引き継がない。

```bash
shinkoku ledger ws-save --db-path DB_PATH --fiscal-year 2025 --withholding-slip-id 1 --input corrected-salary.json
```

## 4. 給与の申告入力を組み立てる

ready_for_calculationがtrueの票だけを使う。年間の給与を網羅する票を選び、前職分を通算した票と通算前の票を重ねて合算しない。氏名や金額だけでは自動除外しない。

- payment_amountをcalc-incomeのsalary_incomeへ、給与のwithheld_taxを同名の給与源泉欄へ渡す。salary_income_after_deductionをsalary_incomeへ代入しない。
- 票のsocial_insuranceからsocial_insurance_small_business_mutual_aidの有効額を差し引き、重複を除いた追加の社会保険料を加える。確認済み空欄は検算時だけ0にできるが、未読NULLは0にできない。
- 内書きの掛金は種類を確認して既存のiDeCo等の入力へ配分し、給与天引き分と別証明書分を二重計上しない。種類・重複が未確認なら入力組立てを止める。
- 配偶者・扶養・特定親族・基礎等の記載額は照合用である。申告時の控除は本人・親族の事実と全所得・対象年分から既存関数が計算する。生命保険料の控除額を保険料欄へ渡さない。

DB付きsanity-checkには選択IDと確認情報をsalary_evidenceとして渡す。[計算と検査](workflow-calculation.md)に従い、未確認の票を申告用に採用しない。票のpayer_nameは給与の勤務先であり、pf-addの支払先名義とは異なる。
