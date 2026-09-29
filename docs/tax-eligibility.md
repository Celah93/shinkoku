# 青色控除・インボイス特例の適用判定

所得税と消費税の入力・出力に `calculation_mode` を追加した。省略時は互換性のため `estimate`（試算）となる。申告に使う計算では `filing` を明示する。

検証対象は青色申告特別控除と2割・3割特例の確認済み条件。全控除・全課税方式・申告全体の法令適合を保証するものではない。

## 試算と申告用計算

| 条件 | `estimate` | `filing` |
|---|---|---|
| 適格・控除なし | 計算と判定を出力 | 計算と判定を出力 |
| 必要な事実が不明 | 条件を仮定した試算を返し、判定は `indeterminate` | `TAX_ELIGIBILITY_UNCONFIRMED` エラー |
| 確認済みの事実が不適格 | `TAX_ELIGIBILITY_INELIGIBLE` エラー | 同左 |
| 判定対象外の年分・例外 | `TAX_ELIGIBILITY_UNSUPPORTED` エラー | 同左 |

結果の `eligibility_checks` に判定、不足項目の `missing_fields`、不適格理由の `reasons` を返す。電子申告と優良帳簿などの選択要件では、候補分岐の不足項目が出る。一つの経路を満たせば他の経路の未確認項目は不要になる。

計算年分のガードはモードより先に適用する。所得税の年間計算は2025〜2027年分に対応するが、個別の要件判定だけで対象外の所得や画面入力まで対応済みとは扱わない。消費税3割特例の計算は2027・2028年分に限定して有効にする。

## 所得税の入力例

以下は架空の確認済みデータ。未確認の値を例からコピーしない。

```json
{
  "fiscal_year": 2026,
  "calculation_mode": "filing",
  "business_revenue": 3000000,
  "business_expenses": 1000000,
  "blue_return_deduction": 650000,
  "blue_return_eligibility": {
    "blue_return_approved": true,
    "eligible_business_income": true,
    "bookkeeping": "double_entry",
    "cash_basis_special": false,
    "filing_within_deadline": true,
    "required_statements_included": true,
    "deduction_claim_recorded": true,
    "etax_filing": true
  }
}
```

`filing_within_deadline` は申告予定又は実績を根拠に確認するもので、本人の送信完了を意味しない。単なる「電子保存あり」という設定は `qualified_electronic_books` の証明にならない。優良帳簿の全要件と必要な届出を別に確認する。

2027年の75万円控除では、期限内の電子申告に加えて、優良帳簿又はデジタルシームレス保存と対応する届出条件を判定する。簡易記帳の10万円控除には前々年の事業収入を使う。前々年収入1,000万円超の簡易記帳を除外する制限は、所得税法67条の現金主義特例の適用者には及ばない。`cash_basis_special: true` の確認があればこの制限から除外するが、青色承認など他の要件は別に確認する。現金主義の確認値が不明なら申告用は停止する。

## 消費税の入力例

国内の個人事業者の暦年課税を対象とする。2割・3割特例の申告用計算には確認済みの `invoice_special_eligibility` を渡す。以下は2026年分の2割特例。2027・2028年分の3割特例では対象年を変え、`method` を `special_30pct` とする。

```json
{
  "fiscal_year": 2026,
  "calculation_mode": "filing",
  "method": "special_20pct",
  "taxable_sales_10": 1100000,
  "invoice_special_eligibility": {
    "domestic_individual": true,
    "invoice_registration_effective": true,
    "base_period_taxable_sales": 5000000,
    "specific_period_taxation_applies": false,
    "inheritance_taxation_applies": false,
    "asset_tax_exemption_restriction": false,
    "other_tax_exemption_restriction": false,
    "shortened_tax_period": false
  }
}
```

基準期間は対象年の2年前。不明な課税売上は `null` とし、0で代用しない。新規開業等で売上がないと確認できた場合は0を使える。除外フラグは、その年分に制限が適用されるか調べた結果。資産の取得歴だけから決めず、特定期間・相続・高額資産等の条件と適用期間を確認する。課税選択の届出だけを理由に自動除外しない。

2割・3割特例は同じ相続の除外条件を使う。`inheritance_taxation_applies: true` のとき、`inheritance_date` が対象年内で、`invoice_registration_date` が相続日以前なら、この相続事由だけでは除外しない。登録が相続日より後又は相続年が別なら不適格、必要な日付が不明なら未確認とする。その他の免税制限も引き続き確認する。

中間納付は `interim_payment`（国税）と `local_interim_payment`（地方税）に分けて入力する。国税の中間納付が正で地方税額が未入力の場合、申告用は停止し、試算だけは地方0円と仮定した警告を返す。実額が0円と確認できた場合は0を明示する。地方額を22/78で推測しない。

`local_tax_due` は従来どおり中間納付前の地方税額。新しい `local_tax_due_after_interim_payment` が精算後の符号付き額、`local_interim_refund` が地方の中間納付に対する還付額。`total_due = tax_due - refund_shortfall + local_tax_due_after_interim_payment` とする。例えば3割特例で税込売上110万円、国税中間納付1万円・地方2千円なら、残額は国税13,400円・地方4,600円、合計18,000円。納め過ぎの場合も符号付きで精算する。

本則・簡易課税の適格性を検査済みとする機能は、この変更には含まない。

## 個別の要件確認と引継ぎ

```bash
shinkoku tax check-eligibility --input eligibility.json
```

入力は `scheme`（`blue_return` / `special_20pct` / `special_30pct`）、`fiscal_year`、事実オブジェクト（`blue_return` 又は `invoice_special`）。青色控除には `requested_deduction` も必須。

判定が完了すれば終了コード0で `eligible`・`ineligible`・`indeterminate`・`unsupported` 等を返す。終了コード0だけで適格と判断しない。入力形式の誤りは終了コード1。2027年の青色控除、2027・2028年の3割特例の確認にも使えるが、個別の適用判定だけで年分全体の所得税計算や画面入力に対応したとは扱わない。

`estimate` の結果を申告画面へ転記しない。条件を確認して `filing` で再計算する。所得税の申告用検算では入力事実を再判定し、保存済み結果も `filing` か検査する。年分や本人操作の境界は[対応年分](tax-year-support.md)と各Skillに従う。

## 設定から引き継ぐ確認状態

設定と `profile` の `family`（`has_spouse`・`has_dependents`・`dependent_count`）、`housing_loan`（`applicable`・`first_year`）、`estimated_tax`（`applicable`・`amount`）では、項目の省略・空欄・`null` は未確認、真偽値の `false` は該当しないことの確認済み、整数の `0` は人数又は金額が0であることの確認済みを表す。真偽値には整数や文字列を、人数・円単位の金額には真偽値や文字列を代入せず、整数は0以上とする。旧設定でセクションごと省略・空欄にした場合も、各項目を `null` として読み込み、`profile` は3セクションと全7項目を返す。`income-tax` と `furusato` は、必要な項目が `null` なら確認を求め、その値に依存する計算・適用判断だけを保留する。`or 0` や真偽判定によって未確認を0・不適用へ置き換えず、確認済みの値から他の未確認項目を自動補完しない。家族の有無・人数だけでは控除の適格性を証明せず、適用する控除の明細・要件も確認する。予定納税は所得税の精算額であって住民税の所得控除ではないため、ふるさと納税の上限計算へ控除として加えない。

## 根拠

2026-09-13に次の国税庁・財務省資料を確認した。

- [財務省・青色控除改正の解説428〜429頁](https://www.mof.go.jp/tax_policy/tax_reform/outline/fy2026/explanation/PDF/p0210-0436.pdf)
- [財務省・消費税改正の解説847〜848頁](https://www.mof.go.jp/tax_policy/tax_reform/outline/fy2026/explanation/PDF/p0823-0860.pdf)
- [国税庁・2割特例の申告書例](https://www.nta.go.jp/publication/pamph/pdf/0023008-043.pdf): 国税と地方税の中間納付・還付欄を確認。3割特例の画面確認を代替するものではない。

- [No.2072 青色申告特別控除](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2072.htm)
- [No.6501 納税義務の免除](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6501.htm)
- [2027年分からの75万円控除（2026年8月）](https://www.nta.go.jp/taxes/shiraberu/shinkoku/kojin_jigyo/0026007-003_02.pdf)
- [2割特例](https://www.nta.go.jp/publication/pamph/shohi/kaisei/202304/01.htm)
- [インボイスQ&A問115](https://www.nta.go.jp/taxes/shiraberu/zeimokubetsu/shohi/keigenzeiritsu/pdf/qa/115.pdf)
- [令和8年度税制改正特集・3割特例](https://www.nta.go.jp/taxes/shiraberu/zeimokubetsu/shohi/keigenzeiritsu/invoice-review/index.htm)
