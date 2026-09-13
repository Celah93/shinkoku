---
name: settlement
description: 年度末の決算整理と減価償却を行い、試算表・損益計算書・貸借対照表を検証する。
---

# settlement

日常仕訳と期首残高を確認し、必要な決算整理だけを行います。登録前のユーザー確認、減価償却の端数処理、貸借一致を維持します。既存の決算結果を再利用できる場合は工程をやり直しません。

個別データを扱うときは [共通の設定・確認境界](../_shared/context.md) を参照します。一般説明だけで設定や全進捗を読みません。必要な工程を選び、他の資料は読み込まないでください。

## 必要な資料

- 対象年度、記帳状態、期首残高を確かめるとき: [checks](references/workflow-checks.md)
- 減価償却・棚卸・未払等の決算整理候補を作るとき: [adjustments](references/workflow-adjustments.md)
- 決算書の生成と貸借一致を検証するとき: [statements](references/workflow-statements.md)
- 決算結果と進捗を保存するとき: [result](references/workflow-result.md)

## 完了

依頼された出力を作り、根拠・入力・CLI結果を照合し、見つかった問題を修正して再確認します。承認待ち・資料不足・未送信を完了済みと区別して報告します。
