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

計算年分のガードはモードより先に適用する。2027年の青色控除の要件判定だけで、所得税計算全体を有効にしない。消費税3割特例の計算は2027・2028年分に限定して有効にする。

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

2027年の75万円控除では、期限内の電子申告に加えて、優良帳簿又はデジタルシームレス保存と対応する届出条件を判定する。簡易記帳の10万円控除には前々年の事業収入を使う。簡易記帳・収入1,000万円超と現金主義特例の併用は追加確認が必要なため適格と判定しない。

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

2割特例の相続の例外では相続年と登録日を比較する。3割特例の相続に係る例外は追加確認が必要なため未対応として返す。3割特例の中間納付がある計算も、地方消費税の中間納付対応まで拒否する。本則・簡易課税の適格性を検査済みとする機能は、この変更には含まない。

## 個別の要件確認と引継ぎ

```bash
shinkoku tax check-eligibility --input eligibility.json
```

入力は `scheme`（`blue_return` / `special_20pct` / `special_30pct`）、`fiscal_year`、事実オブジェクト（`blue_return` 又は `invoice_special`）。青色控除には `requested_deduction` も必須。

判定が完了すれば終了コード0で `eligible`・`ineligible`・`indeterminate`・`unsupported` 等を返す。終了コード0だけで適格と判断しない。入力形式の誤りは終了コード1。2027年の青色控除、2027・2028年の3割特例の確認にも使えるが、個別の適用判定だけで年分全体の所得税計算や画面入力に対応したとは扱わない。

`estimate` の結果を申告画面へ転記しない。条件を確認して `filing` で再計算する。所得税の申告用検算では入力事実を再判定し、保存済み結果も `filing` か検査する。年分や本人操作の境界は[対応年分](tax-year-support.md)と各Skillに従う。

## 根拠

2026-09-13に次の国税庁資料を確認した。

- [No.2072 青色申告特別控除](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2072.htm)
- [No.6501 納税義務の免除](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6501.htm)
- [2027年分からの75万円控除（2026年8月）](https://www.nta.go.jp/taxes/shiraberu/shinkoku/kojin_jigyo/0026007-003_02.pdf)
- [2割特例](https://www.nta.go.jp/publication/pamph/shohi/kaisei/202304/01.htm)
- [インボイスQ&A問115](https://www.nta.go.jp/taxes/shiraberu/zeimokubetsu/shohi/keigenzeiritsu/pdf/qa/115.pdf)
- [令和8年度税制改正特集・3割特例](https://www.nta.go.jp/taxes/shiraberu/zeimokubetsu/shohi/keigenzeiritsu/invoice-review/index.htm)
