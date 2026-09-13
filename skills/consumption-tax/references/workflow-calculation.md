# consumption-tax: 課税売上集計と方法別計算をするとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ1: 課税売上の集計

帳簿から課税売上高を税率区分別に集計する。`shinkoku ledger trial-balance --db-path DB --fiscal-year YEAR` や `shinkoku ledger search --db-path DB --input search.json` の結果から以下を算出する:

### 集計項目

| 項目 | 説明 |
|------|------|
| 課税売上高（税込） | 税率10%と軽減税率8%を区分して集計 |
| 課税売上高（税抜） | 課税標準額（1,000円未満切り捨て） |
| 非課税売上高 | 受取利息等の非課税取引 |
| 免税売上高 | 輸出取引等（該当する場合） |

### 勘定科目との対応

- 売上（4001）: 通常は課税売上（tax_category = taxable）
- 受取利息（4100）: 非課税売上（tax_category = non_taxable）
- 雑収入（4110）: 内容に応じて課税/非課税を判定


## ステップ2: 消費税額の計算

### 比較・検討用の `calc-consumption` 呼び出し

申告方法を最終確定する前の試算では、DBと異なる方法を比較できるように
`--db-path` を付けない。

```bash
shinkoku tax calc-consumption --input consumption_input.json
```
入力 JSON (ConsumptionTaxInput):
```json
{
  "fiscal_year": 2025,
  "method": "special_20pct",
  "taxable_sales_10": 5500000,
  "taxable_sales_8": 0,
  "taxable_purchases_10": 0,
  "taxable_purchases_8": 0,
  "simplified_business_type": null,
  "interim_payment": 0
}
```

本則課税（`method: "standard"`）では、仕入れを `purchase_details` に明細で渡す。各明細には課税仕入れの認識日、税込金額、税率区分、控除区分を指定する。

```json
{
  "fiscal_year": 2026,
  "method": "standard",
  "taxable_sales_10": 5500000,
  "purchase_details": [
    {
      "tax_recognition_date": "2026-09-30",
      "amount_inclusive": 550000,
      "tax_rate": "standard_10",
      "credit_category": "nonqualified_transitional",
      "supplier_key": "supplier-001"
    }
  ]
}
```

`credit_category` は `qualified_invoice`、`nonqualified_transitional`、`book_only_full_credit`、`small_amount_full_credit`、`noncreditable`、`unknown` のいずれか。認識日と区分は入力側で確定し、計算層はその値を使う。旧形式の `taxable_purchases_10/8` を使う場合は、全件を適格請求書ありとして扱うことを明示する `legacy_purchase_assumption: "all_qualified"` が必要で、結果に警告が付く。

出力 (ConsumptionTaxResult):
- `method`: 適用した申告方法
- `taxable_sales_total`: 課税売上高合計（税込、表示用）
- `taxable_base_10`: 課税標準額（10%分、税抜、1,000円切捨て）
- `taxable_base_8`: 課税標準額（8%分、税抜、1,000円切捨て）
- `national_tax_on_sales`: 消費税額（国税: 7.8%分 + 6.24%分）
- `tax_on_sales`: = national_tax_on_sales（後方互換エイリアス）
- `tax_on_purchases`: 控除対象仕入税額（国税部分）
- `full_credit_purchase_amount` / `full_credit_tax_amount`: 100%控除区分の税率別内訳
- `transitional_credit_breakdown`: 経過措置の控除率・税率別内訳
- `noncreditable_amount`: 控除不可区分の税率別税込額
- `unclassified_amount` / `unclassified_count`: 未分類明細の税込額と件数
- `form_2_3`: 付表2-3の⑨・⑩・⑪・⑫・⑰に対応する税率別集計
- `warnings`: 未分類、旧形式入力、仕入先上限を確認するための警告
- `calculation_method`: `tax_inclusive_total`（割戻し計算）
- `net_tax`: 差引税額（100円切捨て、正の場合のみ）
- `refund_shortfall`: 控除不足還付税額（仕入 > 売上の場合）
- `interim_payment`: 国税の中間納付税額
- `local_interim_payment`: 地方消費税の中間納付税額。国税の中間納付が正なら申告用では必須。実額が0円なら0を明示する
- `tax_due`: 後方互換の符号付き集計値 = net_tax - interim_payment（正 = 納付、負 = 中間納付分の還付）
- `local_tax_due`: 中間納付前の地方消費税額（納付時は100円未満切捨て、還付時は1円未満切捨て）
- `local_tax_due_after_interim_payment`: 地方消費税の精算後の符号付き額
- `local_interim_refund`: 地方消費税の中間納付に対する還付額
- `total_due`: 合計納付または還付額 = tax_due - refund_shortfall + local_tax_due_after_interim_payment（負 = 還付）

### 2割特例の計算ロジック

```
1. 課税標準額 = 税込売上 × 100/110（10%分）or × 100/108（8%分）
   → 1,000円未満切捨て（国税通則法118条）

2. 消費税額（国税）= 課税標準額 × 7.8%（10%分）+ 課税標準額 × 6.24%（8%分）

3. 差引税額 = 消費税額 × 20%
   → 100円未満切捨て（国税通則法119条）

4. 地方消費税 = 差引税額 × 22/78
   → 100円未満切捨て
```

- インボイス登録により課税事業者になった者が対象
- 基準期間の課税売上が1,000万円以下であること
- 適用期限: 令和8年9月30日を含む課税期間まで
- 届出不要（申告書に適用する旨を記載するのみ）

### 簡易課税の計算ロジック

```
1. 課税標準額 = 税込売上 × 100/110（10%分）or × 100/108（8%分）
   → 1,000円未満切捨て（国税通則法118条）

2. 消費税額（国税）= 課税標準額 × 7.8%（10%分）+ 課税標準額 × 6.24%（8%分）

3. 控除対象仕入税額 = 消費税額 × みなし仕入率

4. 差引税額 = 消費税額 − 控除対象仕入税額
   → 100円未満切捨て（国税通則法119条）

5. 地方消費税 = 差引税額 × 22/78
   → 100円未満切捨て
```

**みなし仕入率（事業区分別）:**

| 事業区分 | 該当する事業 | みなし仕入率 |
|----------|-------------|-------------|
| 第1種 | 卸売業 | 90% |
| 第2種 | 小売業、農林水産業（飲食料品） | 80% |
| 第3種 | 製造業、農林水産業（その他）、建設業、電気ガス業 | 70% |
| 第4種 | その他（飲食店業等） | 60% |
| 第5種 | サービス業（運輸・通信・金融保険） | 50% |
| 第6種 | 不動産業 | 40% |

- フリーランス（IT、デザイン、コンサル等）は通常**第5種**（みなし仕入率50%）
- 2以上の事業を営む場合は、原則として事業区分ごとに計算する

### 本則課税の計算ロジック

```
1. 課税標準額 = 税込売上 × 100/110（10%分）or × 100/108（8%分）
   → 1,000円未満切捨て（国税通則法118条）

2. 課税売上に係る消費税額（国税）:
    標準税率分: 課税標準額 × 78/1000（= 7.8%）
    軽減税率分: 課税標準額 × 624/10000（= 6.24%）

3. 課税仕入に係る消費税額（国税）:
    標準税率分: 税込仕入額 × 78/1100（= 7.8/110）
    軽減税率分: 税込仕入額 × 624/10800（= 6.24/108）

4. 差引税額 = 売上消費税額 − 仕入消費税額
   正の場合 → 100円未満切捨て（国税通則法119条）
   負の場合 → 控除不足還付税額（端数処理なし）

5. 地方消費税 = 差引税額 × 22/78
   納付の場合 → 100円未満切捨て
   還付の場合 → 1円未満切捨て（100円未満切捨てはしない）
```

- 課税仕入の集計には適格請求書（インボイス）の保存が必要
- 帳簿の消費税区分（references/tax-classification.md）に基づいて集計する
- 課税売上割合が95%以上かつ課税売上高が5億円以下の場合、全額控除可能
- インボイス制度における仕入税額控除の詳細要件は /tax-invoice-credit-context を実行する
