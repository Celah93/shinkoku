# journal: 帳簿を検索するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ4: 仕訳の検索

登録済みの仕訳を検索する。

### `search` コマンド

```bash
# search_params.json に JournalSearchParams を記述
shinkoku ledger search \
  --db-path DB --input search_params.json
```

`search_params.json` の形式:
```json
{
  "fiscal_year": 2025,
  "date_from": "2025-01-01",
  "date_to": "2025-03-31",
  "account_code": "5200",
  "description_contains": "Amazon"
}
```

**検索結果の表示:**

- 検索結果を日付順の一覧表で表示する
- 各仕訳には journal_id を表示する（修正・削除で使用）
- 合計金額を末尾に表示する
