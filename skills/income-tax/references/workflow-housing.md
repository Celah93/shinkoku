# income-tax: 住宅ローン控除の明細を登録するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ3.5: 住宅ローン控除明細の DB 登録（該当者のみ）

住宅ローン控除（初年度）を適用する場合、詳細情報を DB に登録する。

1. `shinkoku ledger hl-add --db-path DB_PATH --fiscal-year YEAR --input housing.json` で住宅ローン控除の明細を登録する:
   ```json
   {
     "housing_type": "new_custom",
     "housing_category": "certified",
     "move_in_date": "2026-03-15",
     "year_end_balance": 30000000,
     "is_special_target_individual": false,
     "has_pre_r6_building_permit": false,
     "purchase_date": "2026-01-20",
     "purchase_price": 40000000,
     "total_floor_area": 8000,
     "residential_floor_area": 8000,
     "property_number": null,
     "application_submitted": false
   }
   ```

`housing_type`は新築、買取再販`broker_renovated_resale`、通常中古`used`、増改築を
区別する。旧`resale`は使わない。本人・配偶者の生年月日と扶養親族はDBから計算JSONへ
渡し、計算結果の`housing_loan_credit_entries`と`warnings`を確認する。住宅区分別の
年末残高上限テーブルは `references/deduction-tables.md` を参照。
