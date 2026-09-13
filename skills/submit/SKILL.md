---
name: submit
description: 作成済み申告書を最終点検し、提出方法・期限・納付と保存を案内する。
---

# submit

申告書の整合性と提出準備を点検します。ブラウザ入力が依頼された場合はe-tax Skillへ進みます。署名・送信はユーザー操作で、準備完了を提出完了と記録しません。

個別データを扱うときは [共通の設定・確認境界](../_shared/context.md) を参照します。一般説明だけで設定や全進捗を読みません。必要な工程を選び、他の資料は読み込まないでください。

## 必要な資料

- 納税者・対応範囲・申告内容を最終確認するとき: [review](references/workflow-review.md)
- 電子・郵送・窓口の提出方法を案内するとき: [methods](references/workflow-methods.md)
- 対象年度の期限と納付方法を確認するとき: [deadlines](references/workflow-deadlines.md)
- 提出後の保存や進捗を記録するとき: [result](references/workflow-result.md)

## 完了

依頼された出力を作り、根拠・入力・CLI結果を照合し、見つかった問題を修正して再確認します。承認待ち・資料不足・未送信を完了済みと区別して報告します。
