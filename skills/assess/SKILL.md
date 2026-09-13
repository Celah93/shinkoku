---
name: assess
description: 所得税・消費税・住民税の申告要否と必要な申告種類を判定する。
---

# assess

必要な申告種類と根拠を示します。収入と所得を区別し、不明な課税区分を推測で確定しません。所得税・消費税・住民税の該当範囲を判定し、実データを更新する場合の確認を維持します。

個別データを扱うときは [共通の設定・確認境界](../_shared/context.md) を参照します。一般説明だけで設定や全進捗を読みません。必要な工程を選び、他の資料は読み込まないでください。

## 必要な資料

- 個別の判定に必要な収入・家族・事業情報を確認するとき: [intake](references/workflow-intake.md)
- 所得税の要否・対象外の分離課税を判断するとき: [income](references/workflow-income.md)
- 消費税の要否と課税状態を確定・保存するとき: [consumption](references/workflow-consumption.md)
- 住民税の要否を判断するとき: [resident](references/workflow-resident.md)
- 判定結果をまとめ、進捗を保存するとき: [result](references/workflow-result.md)
- 特殊ケース、追加の法令資料、免責の確認が必要なとき: [exceptions](references/workflow-exceptions.md)

## 完了

依頼された出力を作り、根拠・入力・CLI結果を照合し、見つかった問題を修正して再確認します。承認待ち・資料不足・未送信を完了済みと区別して報告します。
