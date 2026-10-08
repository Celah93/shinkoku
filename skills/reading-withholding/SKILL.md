---
name: reading-withholding
description: 給与所得の源泉徴収票のラベル・記載額・空欄を読み取り、未確認値を区別するときに使用する。
---

# reading-withholding

[共通の読取・不明値・確認方法](../_shared/ocr.md)に従う。2025年分・2026年分の改正後の受給者交付用を初版の確認対象とする。年分と帳票の版は別々に原本で確認し、同じ年分の旧様式や税務署提出用を同一の配置とみなさない。

## 原本を読む手順

1. PDFでは`shinkoku pdf extract-text --file-path <path>`でテキストを確認する。情報が不足する場合は`shinkoku pdf to-image --file-path <path> --output-dir <dir>`で画像へ変換し、利用できる画像読取ツールで確認する。
2. 「特定親族特別控除の額」と右隣の「社会保険料等の金額」のラベルをそれぞれ確認し、各枠内の金額を別々に読む。社会保険料等の内書きは総額と分ける。国民年金保険料や内書きを総額へ再加算しない。
3. 原本の年分を`document_fiscal_year`へ記録する。年末調整済み・未済は摘要等も確認し、空欄だけから推測しない。年末調整未済の控除合計・給与所得控除後・基礎控除の空欄を適用額0と扱わない。
4. 金額はカンマや「円」を除いた非負の整数にする。未読はJSONの`null`にし、文字列のUNKNOWNや金額0で埋めない。空欄と確認できた金額項目も`null`のままにし、その名前を`blank_fields`へ入れる。印字0や資料で確認した0は整数0で保存する。
5. `dependent_deduction`と`other_personal_deductions`は印字額ではなく照合用の派生額である。該当年の資料又は既存関数で確定し、`deduction_derivation_note`に資料ID・年分・人数・区分・計算過程を残す。空の人数欄だけから0を作らず、控除合計との差額から逆算しない。確定できなければ`null`にする。
6. 未払給与・未徴収税額、掛金の種類、前職分の通算、年途中の適用関係、未検証の様式を確認する。未解決の事項があれば`source_confirmed`をtrueにしない。原本の額を現在の控除表で書き換えない。
7. `ledger ws-check`で検算し、原本のラベル・金額・年分・内書き・摘要を再照合して確認情報を更新する。同じ内容が照合済みなら同じ確認を繰り返さない。

## 出力形式

以下は2025年分の架空例であり、原本照合の完了前なので`source_confirmed`はnullである。元ファイルごとに平坦なJSONを返す。生命保険料の5項目は控除額と分け、ネストしない。

```text
---WITHHOLDING_DATA---
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
  "source_confirmed": null,
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
---END---
```

`file_path`はimportが返す外側のファイル情報であり、構造化時に`source_file`へ明示的に対応付ける。保存入力には`file_path`、`extracted_text`、`status`、`fiscal_year`、`detail`を加えない。

控除合計が一致しても、二欄の完全な交換や同額の取り違えは検出できない。`matched`をOCRの正しさや控除要件の確認済みと説明しない。`ready_for_calculation=false`の票から申告入力を作らない。原本照合の完了は実帳簿への登録や申告送信の承認ではない。

`NTA-2025-TABLE`等の資料IDは、[設計の出典一覧](../../docs/withholding-slip-validation-design.md)と[年分別の取得資料・版・ハッシュ](../../tests/fixtures/withholding/README.md)から辿る。対象年分と適用時点を確認し、原本の記載額を別年度の表へ置き換えない。
