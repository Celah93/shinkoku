# income-tax: 年金・雑所得・暗号資産・総合課税の配当等を扱うとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ1.10: その他の所得の確認（雑所得・配当所得・一時所得・年金所得・退職所得）

事業所得・給与所得以外の総合課税の所得を確認・登録する。

### 公的年金等の雑所得

公的年金等の収入がある場合、年金控除を計算して雑所得を求める。

1. 年金収入の有無を確認する
2. `uv run shinkoku tax calc-pension --input pension_input.json` で公的年金等控除を計算する:
   ```bash
   uv run shinkoku tax calc-pension --input pension_input.json
   ```
   入力 JSON:
   ```json
   {
     "pension_income": 2000000,
     "is_over_65": true,
     "other_income": 0
   }
   ```
   出力:
   ```json
   {
     "pension_income": 2000000,
     "deduction_amount": 1100000,
     "taxable_pension_income": 900000,
     "other_income_adjustment": 0
   }
   ```
3. `taxable_pension_income` を雑所得として `misc_income` に加算する
4. 令和7年改正: 65歳未満の最低保障額60万→70万、65歳以上の最低保障額110万→130万

### 退職所得

退職所得の申告支援は対象外です。以下は既存の計算コマンドの例で、申告への対応を意味しません。計算だけを依頼された場合に限り検証し、申告処理は専門家へ案内します。

1. 退職金の有無を確認する
2. `uv run shinkoku tax calc-retirement --input retirement_input.json` で退職所得を計算する:
   ```bash
   uv run shinkoku tax calc-retirement --input retirement_input.json
   ```
   入力 JSON:
   ```json
   {
     "severance_pay": 10000000,
     "years_of_service": 20,
     "is_officer": false,
     "is_disability_retirement": false
   }
   ```
   出力:
   ```json
   {
     "severance_pay": 10000000,
     "retirement_income_deduction": 8000000,
     "taxable_retirement_income": 1000000,
     "half_taxation_applied": true
   }
   ```
3. 退職所得は原則分離課税（退職時に源泉徴収済み）だが、確定申告で精算する場合もある
4. 役員等の短期退職（勤続5年以下）は1/2課税が適用されない

### 雑所得（miscellaneous）

副業の原稿料、暗号資産の売却益、その他の雑収入。

1. `shinkoku ledger oi-list --db-path DB_PATH --fiscal-year YEAR` で登録済み雑所得を確認する
2. 未登録の収入がある場合は `shinkoku ledger oi-add --db-path DB_PATH --fiscal-year YEAR --input other_income.json` で登録する:
   ```json
   {
     "fiscal_year": 2025,
     "detail": {
       "income_type": "miscellaneous",
       "description": "収入の内容",
       "revenue": 500000,
       "expenses": 50000,
       "withheld_tax": 51050,
       "payer_name": "支払者名"
     }
   }
   ```
3. 雑所得 = 収入 - 経費（特別控除なし）

### 仮想通貨（暗号資産）

暗号資産の売却益は雑所得（総合課税）として申告する。

1. `shinkoku ledger ci-list --db-path DB_PATH --fiscal-year YEAR` で登録済み仮想通貨所得を確認する
2. 未登録の場合は `shinkoku ledger ci-add --db-path DB_PATH --fiscal-year YEAR --input crypto.json` で取引所別に登録する:
   ```json
   {
     "fiscal_year": 2025,
     "detail": {
       "exchange_name": "取引所名",
       "gains": 300000,
       "expenses": 10000
     }
   }
   ```
3. 合計を雑所得として total_income に加算する

### 配当所得（総合課税選択分）

総合課税を選択した配当は配当控除（税額控除）の対象となる。

1. `shinkoku ledger oi-list --db-path DB_PATH --fiscal-year YEAR` で `income_type: "dividend_comprehensive"` を確認する
2. 未登録の場合は `shinkoku ledger oi-add --db-path DB_PATH --fiscal-year YEAR --input dividend.json` で登録する
3. 配当控除: 課税所得1,000万以下の部分 → 配当の10%、超える部分 → 5%

### 一時所得

保険満期金、懸賞金等の一時的な所得。

1. `shinkoku ledger oi-list --db-path DB_PATH --fiscal-year YEAR` で `income_type: "one_time"` を確認する
2. 未登録の場合は `shinkoku ledger oi-add --db-path DB_PATH --fiscal-year YEAR --input one_time.json` で登録する
3. 一時所得 = max(0, (収入 - 経費 - 特別控除50万円)) × 1/2

### `calc_income_tax` への反映

上記のその他所得は以下のパラメータで `calc_income_tax` に渡す:
- `misc_income`: 雑所得合計（仮想通貨含む）
- `dividend_income_comprehensive`: 配当所得（総合課税選択分）
- `one_time_income`: 一時所得の収入金額（1/2 計算は内部で実施）
- `other_income_withheld_tax`: その他所得の源泉徴収税額合計


## ステップ1.11: （対象外）分離課税

分離課税（株式・FX の第三表）は対象外。該当する場合は税理士への相談を案内する。
