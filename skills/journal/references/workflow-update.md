# journal: 確認済み仕訳を修正・削除するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ5: 仕訳の修正・削除

### 5-1. 仕訳の修正（`journal-update`）

```bash
shinkoku ledger journal-update \
  --db-path DB --fiscal-year 2025 --journal-id 42 --input updated.json
```

- 修正前後の差分を表示してから確認する
- 修正理由を摘要に追記することを推奨する

### 5-2. 仕訳の削除（`journal-delete`）

```bash
shinkoku ledger journal-delete \
  --db-path DB --journal-id 42
```

- 削除対象の仕訳内容を表示して確認する
- 「この仕訳を削除します。よろしいですか？」と最終確認する
- 削除は取り消しできない旨を注意喚起する
