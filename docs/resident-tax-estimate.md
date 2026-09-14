# 住民税控除の自動組立て

`tax calc-resident-tax-estimate` は、2025〜2027年の総合課税所得と控除の元データから、住民税の標準所得割額を推定する。所得税・住民税で異なる控除と調整控除を計算し、既存のふるさと納税上限計算へ接続する。

## 入力例

```bash
shinkoku tax calc-resident-tax-estimate --input resident.json
```

```json
{
  "fiscal_year": 2027,
  "income_scope": "comprehensive_only",
  "income_levy_taxable": true,
  "aggregate_income": 3560000,
  "total_income": 3560000,
  "social_insurance": 750000,
  "life_insurance": {"general_new": 80000}
}
```

これは架空データである。`fiscal_year` は所得・寄附の年で、住民税の課税年度は翌年。`aggregate_income` は繰越控除前の合計所得金額、`total_income` は繰越控除後の総所得金額等であり、給与収入を直接入れない。住民税と所得税の所得の取扱いが異なるケースは各所得を確認してから使う。

`income_scope` は分離課税等を含まない総合課税だけであること、`income_levy_taxable` は自治体の所得割の課税・非課税要件を確認した結果を表す。どちらも必須であり、課税区分が不明な場合は上限を推定しない。非課税を指定した場合は所得割と寄附上限を0円とする。均等割の課税状態とは区別する。

## 控除の元データ

| 入力 | 意味 |
|---|---|
| `social_insurance` | 支払った社会保険料 |
| `small_business_mutual_aid` | 小規模企業共済・iDeCo等の対象掛金の合計。二重加算しない |
| `life_insurance` | `general_new`・`general_old`・`medical_care`・`annuity_new`・`annuity_old` の支払額。住民税では所得税の23歳未満特例を使わない |
| `earthquake_premium`・`old_long_term_premium` | 地震・旧長期保険の支払額。両方ある場合は `same_earthquake_contract` が必須。同じ契約では選択適用する |
| `medical_method` | `none`・`medical`・`self_medication` から選択する。控除額の有利不利を自動で確定しない |
| `medical_expenses_net`・`self_medication_expenses_net` | 補填後の対象支払額。セルフメディケーションには `self_medication_eligible: true` が必要 |
| `spouse`・`dependents` | 配偶者1人と配偶者以外の親族一覧。同じ人を重複登録しない |
| `widow_status` | 確認済みの `none`・`widow`・`single_parent_mother`・`single_parent_father`。ひとり親の人的控除差を区別する |
| `disability` | 本人の確認済み区分 `general`・`special`、又は `null` |
| `working_student` | 資格の確認結果。該当する場合は `working_student_nonwork_income` に給与所得等以外の所得も指定する |

親族には `name`、`birth_date`、`income`、`eligible` が必須。`eligible` は所得・年齢以外の生計、事業専従者、国外居住等の要件を確認した結果とする。年齢・所得要件は計算で再確認する。`other_taxpayer_dependent: true` の人は除外する。同居老親等には `cohabiting: true` と `is_lineal_ascendant: true` が必要。親族の障害は `general`・`special`・`special_cohabiting` で指定できる。

## 結果と接続

`deductions` に住民税控除額と人的控除差を別々に返す。特定親族特別控除・配偶者特別控除の人的控除差は0とし、現在の所得税との控除額の差を流用しない。1月1日生まれも法定の年齢境界で判定する。ひとり親控除は2027年所得（2028年度課税）から33万円を使う。

`resident_tax_income_levy` は標準税率10%による合算所得割の調整控除後・他の税額控除前の推定値。税目別の百円端数、超過税率、均等割・森林環境税は含まない。雑損控除、分離課税、自治体独自の減免等も自動組立ての対象外なので、該当する場合は確認済みの住民税資料を使う現行経路で対応する。

`furusato_input` をJSONとして保存し、既存の `tax calc-furusato-limit-detailed` 又は `tax calc-furusato-limit` の `--input` に渡せる。同じ計算結果は `furusato_limit` にも含まれる。率の途中切捨てをせず、2027年の193万円上限と基礎控除調整の0円下限を既存の計算で適用する。

住宅ローン控除、高所得特例、他の寄附、分離課税等を含めた実負担2,000円を保証するものではない。入力不足や対象外年分を、以前の年分や所得税控除の合計で代用しない。DBへの保存はこのCLIでは行わない。

## 根拠と検証

- [横浜市の所得控除表](https://www.city.yokohama.lg.jp/kurashi/koseki-zei-hoken/zeikin/y-shizei/kojin-shiminzei-kenminzei/kojin-shiminzei-shosai/shotokukoujoR8.html): 住民税の各控除・人的控除差・年齢範囲。
- [横浜市の令和8年度地方税制改正](https://www.city.yokohama.lg.jp/kurashi/koseki-zei-hoken/zeikin/zeisei/zeiseikaisei.files/0010_20260330.pdf): 2028年度からのひとり親控除。
- [財務省の地方税法改正解説931〜932頁](https://www.mof.go.jp/tax_policy/tax_reform/outline/fy2026/explanation/PDF/p0921-0989.pdf): 特例控除上限と税率判定の基礎控除調整。

`tests/unit/test_resident_tax_estimate.py` で上流の問題の再現例、控除・年齢・年分・所得制限・丸めを検証し、`tests/scripts/test_resident_and_housing.py` で自動組立てから既存CLIへの接続を検証する。
