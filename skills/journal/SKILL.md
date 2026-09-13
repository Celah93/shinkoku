---
name: journal
description: 取引を仕訳候補に変換し、承認済みの登録・修正・削除や帳簿検索を行う。
---

# journal

CSV・領収書・請求書から仕訳候補を作ります。原本、対象年度、日付・金額・勘定科目・税区分を照合し、重複を検出します。実帳簿への登録・修正・削除は対象の一覧をユーザーが確認してから行います。検索や候補作成だけで承認待ちにしません。

個別データを扱うときは [共通の設定・確認境界](../_shared/context.md) を参照します。一般説明だけで設定や全進捗を読みません。必要な工程を選び、他の資料は読み込まないでください。

CLIの形式は `shinkoku ledger <subcommand> [args]` と `shinkoku import <subcommand> [args]`。JSON入出力・勘定科目マスタ・税区分の契約は既存CLIと [勘定科目](references/account-master.md) を必要時に確認します。

## 必要な資料

- 新年度・新規帳簿の初期化が必要なとき: [initialization](references/workflow-initialization.md)
- CSV・領収書・請求書から候補を作り重複を確認するとき: [import](references/workflow-import.md)
- 確認済み候補を登録するとき: [register](references/workflow-register.md)
- 帳簿を検索するとき: [search](references/workflow-search.md)
- 確認済み仕訳を修正・削除するとき: [update](references/workflow-update.md)
- 勘定科目や按分の例を必要とするとき: [patterns](references/workflow-patterns.md)
- 帳簿処理の結果と進捗を記録するとき: [result](references/workflow-result.md)

## 完了

依頼された出力を作り、根拠・入力・CLI結果を照合し、見つかった問題を修正して再確認します。承認待ち・資料不足・未送信を完了済みと区別して報告します。
