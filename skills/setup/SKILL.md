---
name: setup
description: shinkokuの初期設定を作成するか、指定された既存設定を更新する。
---

# setup

必要な設定と保存先を揃え、内容を確認して保存・読戻しまで行います。設定更新では該当項目だけを扱い、初回ヒアリングを繰り返しません。既存DBの再初期化や原本の上書きをせず、個人データのGit除外を保ちます。

個別データを扱うときは [共通の設定・確認境界](../_shared/context.md) を参照します。一般説明だけで設定や全進捗を読みません。必要な工程を選び、他の資料は読み込まないでください。

## 必要な資料

- CLI・既存設定・保存先を確認するとき: [environment](references/workflow-environment.md)
- 初回設定、または納税者・住所・事業情報を更新するとき: [profile](references/workflow-profile.md)
- 申告方法・控除に影響する事項を設定するとき: [filing](references/workflow-filing.md)
- 具体的な設定内容を確認して保存し、新規DBを初期化するとき: [save](references/workflow-save.md)
- 設定結果と進捗を記録するとき: [result](references/workflow-result.md)

## 完了

依頼された出力を作り、根拠・入力・CLI結果を照合し、見つかった問題を修正して再確認します。承認待ち・資料不足・未送信を完了済みと区別して報告します。
