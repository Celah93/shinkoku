---
name: gather
description: 申告種類に応じた必要書類と入手先・不足時の対応を整理する。
---

# gather

ユーザーに必要な書類と不足分の対応を示します。申告種類が既知ならassessのやり直しは不要です。書類が未収集でも入手案内まで進め、収集済みとは記録しません。

個別データを扱うときは [共通の設定・確認境界](../_shared/context.md) を参照します。一般説明だけで設定や全進捗を読みません。必要な工程を選び、他の資料は読み込まないでください。

## 必要な資料

- 申告種類ごとの書類を選ぶとき: [requirements](references/workflow-requirements.md)
- 取得時期、電子データ、不足書類の代替を調べるとき: [collection](references/workflow-collection.md)
- 収集状態と次に必要な作業を記録するとき: [result](references/workflow-result.md)

## 完了

依頼された出力を作り、根拠・入力・CLI結果を照合し、見つかった問題を修正して再確認します。承認待ち・資料不足・未送信を完了済みと区別して報告します。
