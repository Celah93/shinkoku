# journal: 確認済み候補を登録するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ3: 仕訳の登録

ユーザーが確認したデータを帳簿に登録する。

### 3-1. 単一仕訳の登録（`journal-add`）

```bash
# journal.json に JournalEntry を JSON で記述
shinkoku ledger journal-add \
  --db-path DB --fiscal-year 2025 --input journal.json
```

`journal.json` の形式:
```json
{
  "date": "2025-01-15",
  "description": "事業で使う消耗品を購入した",
  "source": "manual",
  "lines": [
    {"side": "debit", "account_code": "5190", "amount": 1100, "tax_category": "taxable_10", "tax_amount": 100},
    {"side": "credit", "account_code": "1002", "amount": 1100, "tax_category": "out_of_scope", "tax_amount": 0}
  ]
}
```

この例では、消費税10％を含む購入額1,100円を消耗品費とし、事業用の普通預金から支払う。
`lines[].tax_category` には仕訳行の税区分を指定する。勘定科目マスタの `taxable` は指定しない。
税区分と `source` の許容値は[下の対応表](#仕訳行の税区分と勘定科目分類)を参照する。

### 3-2. 一括仕訳登録（`journal-batch-add`）

CSV取り込み等で複数の仕訳を一度に登録する場合に使用する。

```bash
# entries.json に JournalEntry の配列を記述
shinkoku ledger journal-batch-add \
  --db-path DB --fiscal-year 2025 --input entries.json
```

**登録前の確認事項:**

- 登録件数と合計金額をサマリーとして提示する
- 「以下の N 件の仕訳を登録します。よろしいですか？」と確認する
- ユーザーの明示的な承認を得てから `journal-batch-add` を実行する

### 重複で登録が止まった場合

完全重複の判定は、日付と借貸・勘定科目・金額の組合せを使い、取引先や摘要を含めない。
そのため、別の取引先への同日・同額・同じ科目の仕訳も、完全重複として登録が止まる。

1. エラーや警告に示された既存の仕訳、または一括入力内の該当行を原簿と照合する。
2. 取引先、請求書・領収書番号、発生日、入出金を確認し、同じ取引の二重計上なら追加しない。
3. **原簿で別取引と確認でき、登録内容が承認済みの場合だけ**、同じ入力に `--force` を付けて登録する。
   一括登録では、警告対象の全件が別取引であることを確認する。未確認の候補を含めて一律に強制登録しない。
4. 登録後に帳簿を読戻し、確認した件数・取引先・金額を照合する。一括登録が失敗した場合も、再実行前に登録状態を確認する。

```bash
shinkoku ledger journal-add --db-path DB --fiscal-year YEAR --input journal.json --force
shinkoku ledger journal-batch-add --db-path DB --fiscal-year YEAR --input entries.json --force
```

`--force` は確認済みの別取引を登録するための指定である。日付や摘要を変えて重複判定を回避しない。

### 仕訳行の税区分と勘定科目分類

勘定科目マスタの `accounts.tax_category` は科目の一般的な分類であり、
仕訳行の `lines[].tax_category` はその取引の税率・課税関係を表す。科目の分類をそのまま転記せず、
証憑と取引内容から仕訳行の値を決める。例えば、地代家賃の科目が `taxable` でも、住宅の貸付けは `non_taxable` とする。

| 取引の課税関係 | 勘定科目マスタの分類 | 仕訳行に指定する値 |
|---|---|---|
| 標準税率10％の課税取引 | `taxable` | `taxable_10` |
| 既存データの8％区分 | `taxable` | `taxable_8`（既存DBの許容値として保持。新しい軽減8％の行には下記の区分を使う） |
| 軽減税率8％の課税取引 | `taxable` | `taxable_8_reduced` |
| 非課税取引 | `non_taxable` | `non_taxable` |
| 輸出免税等の取引 | `exempt` | `exempt` |
| 消費税の対象外の取引 | `out_of_scope`、または資産等の未分類 | `out_of_scope` |
| 区分の未設定 | `null` | `null` または省略（保存可能だが、申告用の税区分の確認を済ませた意味ではない） |

`tax_amount` にはその行に記載する消費税額を円単位の整数で指定する。上の購入例では消耗品費の行に100円を記載し、
決済だけを表す普通預金の行には0円を記載する。借方と貸方へ同じ税額を重複計上しない。

`source` は仕訳全体に指定し、`csv_import`（CSV取込）、`receipt_ocr`（領収書読取）、
`invoice_ocr`（請求書読取）、`manual`（手動入力）、`adjustment`（決算整理）のいずれかとする。
`null` と省略も既存契約として保存できる。独自の値は追加しない。
許容値以外はDBを開く前に入力モデルで拒否され、エラーJSONの `message` に許容値が表示される。

### 登録時の検証ルール

以下を検証し、不備があれば登録前に警告する:

1. **日付の妥当性**: 会計年度の範囲内であるか（例: 2025-01-01 〜 2025-12-31）
2. **勘定科目の存在**: 借方・貸方の科目コードがマスタに存在するか
3. **金額の正値**: 金額が正の整数であるか
4. **貸借の一致**: 複合仕訳の場合、借方合計 = 貸方合計であるか
5. **消費税区分の整合**: 上の対応表に従い、取引の課税関係と仕訳行の `tax_category` を確認したか
