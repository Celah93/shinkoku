# 住宅ローンの単体計算と2028〜2030年入居

`tax calc-housing-loan` は、2022〜2030年入居のルールから、所得税額による上限を適用する前の控除可能額を計算する。年間所得税の `tax calc-income`・`tax calc-deductions` は2025〜2027年分の対応を維持する。2030年までの住宅ルールの存在は、その年の申告全体への対応を意味しない。

## 入力例

```bash
shinkoku tax calc-housing-loan --input housing_calculation.json
```

```json
{
  "claim_fiscal_year": 2028,
  "aggregate_income": 5000000,
  "other_requirements_confirmed": true,
  "housing_loan_details": [{
    "housing_type": "new_custom",
    "housing_category": "energy_efficient",
    "move_in_date": "2028-09-01",
    "year_end_balance": 30000000,
    "is_special_target_individual": false,
    "building_confirmation_date": "2027-12-31",
    "building_completion_date": "2028-07-01",
    "is_disaster_red_zone": false,
    "total_floor_area": 8000,
    "residential_floor_area": 8000,
    "loan_term_years": 30
  }]
}
```

これは架空の省エネ基準適合の新築住宅で、建築確認の経過措置を満たす。結果の `housing_loan_credit` は140,000円、`credit_period` は10年となる。

`claim_fiscal_year` は控除を計算する年で、入居年と別に指定する。対応する入居年と10年・13年の控除期間に従い、期間終了は `expired` として返す。`aggregate_income` はその控除年の繰越控除前の合計所得金額。

`year_end_balance` は、取得対価・持分・居住用部分・補助金等を確認した控除対象の残高を渡す。`other_requirements_confirmed` は、自己居住、取得・入居の期限、対象金融機関、取得区分・住宅性能の証明、併用不可の特例等を確認した結果である。このCLIがこれらの事実や証明書を自動で認定するものではない。未確認・対象外なら計算を進めない。

## 2028年からの条件

| 対象 | 処理 |
|---|---|
| 省エネ基準適合の新築 | 建築確認日が2027-12-31以前又は登記簿上の建築日が2028-06-30以前なら2,000万円・10年。両方とも期限後なら対象外 |
| 省エネ基準適合の買取再販・通常の既存住宅 | 一般2,000万円、特例対象個人3,000万円・13年。新築の経過措置を適用しない |
| 認定住宅・ZEHの新築や買取再販、既存住宅 | 取得区分別の限度額と13年間の期間を保持する |
| 新築の立地 | `is_disaster_red_zone` の確認が必須。規制対象の区域に該当する場合は `is_rebuilding` で建替えの例外も確認する |
| 床面積 | 単位は㎡×100。40㎡以上50㎡未満は合計所得1,000万円以下とし、子育て世帯等の限度額上乗せを使わない。50㎡以上の所得上限は2,000万円 |
| 居住割合・借入期間 | 居住用部分が床面積の半分以上、償還期間が10年以上であることを検証する |

経過措置は片方の日付で対象と確認できれば計算できる。非該当とするには両方の確認が必要であり、欠けた日付を期限後とみなさない。立地のフラグは、勧告・公表等の条件を含めて住宅に適用される規制の該当性を確認して設定する。区域情報の自動照会は行わない。

特例対象個人は入居年末の本人・配偶者・親族情報から判定するか、確認済みの `is_special_target_individual` を渡す。両方ある場合は矛盾を拒否する。世帯情報は `taxpayer_birth_date`・`spouse_birth_date`・`spouse_income`・`dependents` をトップレベルへ渡す。

2025年以前入居の40㎡以上50㎡未満の経過措置、被災者の特別な率などはこの単体計算で新たに対応しない。年間所得税の既存経路と、この単体CLIの床面積・所得・借入期間の検証は別であり、後者の検査結果を未確認の申告全体へ流用しない。

## 保存と複数明細

`ledger hl-add`・`ledger hl-list` で、建築確認日・建築日、災害レッドゾーン、建替え、借入期間を保存・読取りできる。旧DBにはNULLの列を追加し、元の明細を保持する。旧明細のNULLは未確認であり、自動的にfalseや適格に変えない。実帳簿への保存には対象内容のユーザー確認が必要である。

同じ借入れの重複適用には、全明細で同じ `dual_application_group` と `year_end_balance`、正の `cost_for_proration` を指定する。按分後の残高合計を維持し、控除期間が混在する場合は有効な明細だけでグループの上限を適用する。グループが異なる明細は別の借入れとして計算する。

結果の `entries` には入居年・控除年・適用年数・期間・限度額・状態を返す。実際の所得税と住民税へ配分した控除額、納付額、公式申告画面への転記は計算していない。

## 根拠と検証

- [財務省の所得税関係改正解説225〜226頁](https://www.mof.go.jp/tax_policy/tax_reform/outline/fy2026/explanation/PDF/p0210-0436.pdf): 借入限度額・期間・買取再販の区別。
- [国土交通省の住宅税制](https://www.mlit.go.jp/jutakukentiku/house/zeisei_index2.html): 入居期限、建築日の経過措置、床面積と立地制限。

`tests/unit/test_housing_loan_2028.py` と `tests/scripts/test_resident_and_housing.py` で日付・年齢・面積・所得・期間の境界、情報不足、DB往復、旧年間計算の対応年分を検証する。
