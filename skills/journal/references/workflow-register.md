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
  "description": "摘要テキスト",
  "lines": [
    {"side": "debit", "account_code": "5200", "amount": 1000},
    {"side": "credit", "account_code": "1100", "amount": 1000}
  ]
}
```

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

### 登録時の検証ルール

以下を検証し、不備があれば登録前に警告する:

1. **日付の妥当性**: 会計年度の範囲内であるか（例: 2025-01-01 〜 2025-12-31）
2. **勘定科目の存在**: 借方・貸方の科目コードがマスタに存在するか
3. **金額の正値**: 金額が正の整数であるか
4. **貸借の一致**: 複合仕訳の場合、借方合計 = 貸方合計であるか
5. **消費税区分の整合**: 科目の tax_category と税率の組み合わせが妥当か
