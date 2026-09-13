# income-tax: 年金・雑所得・暗号資産・総合課税の配当等を扱うとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ1.10: その他の所得の確認（雑所得・配当所得・一時所得・年金所得・退職所得）

事業所得・給与所得以外の総合課税の所得を確認・登録する。

### 公的年金等の雑所得

公的年金の収入は `calc-income` の `pension_income` と `pension_is_over_65` に渡す。年金以外の雑所得だけを `misc_income` に入れ、年金所得を二重に加算しない。源泉徴収は `other_income_withheld_tax` に含める。

給与収入も渡せば、年金控除・給与と年金の所得金額調整・2027年の控除合計280万円上限を年間計算の中で処理する。給与850万円超の子ども・特別障害者等の要件は `salary_income_adjustment_eligible` 又は本人・扶養親族情報で確認する。詳しい順序と架空入力例は `docs/income-tax-2027.md` を参照する。

単体で年金控除だけを確かめる場合:

```bash
uv run shinkoku tax calc-pension --input pension_input.json
```

```json
{
  "fiscal_year": 2027,
  "pension_income": 2000000,
  "is_over_65": true,
  "other_income": 0,
  "salary_income_deduction": 0
}
```

給与がない上の例では `deduction_amount: 1100000`、`taxable_pension_income: 900000`。2027年の正の年金収入には給与所得控除額が必須で、給与なしも0と明示する。最低控除の基本額は65歳未満60万円・65歳以上110万円で、他所得による減額を別に適用する。

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
- `misc_income`: 年金以外の雑所得合計（仮想通貨含む）
- `pension_income` / `pension_is_over_65`: 公的年金の収入・年齢区分
- `dividend_income_comprehensive`: 配当所得（総合課税選択分）
- `one_time_income`: 一時所得の収入金額（1/2 計算は内部で実施）
- `other_income_withheld_tax`: その他所得の源泉徴収税額合計


## ステップ1.11: （対象外）分離課税

分離課税（株式・FX の第三表）は対象外。該当する場合は税理士への相談を案内する。
