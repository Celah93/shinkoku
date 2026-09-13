---
name: e-tax
description: 計算済み申告データを国税庁の作成コーナーに入力・照合する。署名と送信は本人が行う。
---

# e-tax

計算済みの申告内容をブラウザに入力し、計算結果と画面の値を照合します。対象年度・所得に必要なデータだけを使い、事業所得のない申告に決算書を要求しません。

本人認証・マイナンバー入力・電子署名・最終送信は本人操作です。その間はブラウザを操作しません。申告内容の目視確認と、所得税・消費税それぞれの送信フェーズへ進む意思確認を維持します。ユーザーの完了報告だけでなく、再開後に受付結果を確認して提出状態を記録します。

操作前に現在の画面・対象年度・セッションを確認します。参照のセレクタ・画面順・例示データを未確認のまま入力しません。既に送信済みなら再提出の意図が明示されるまで再実行しません。

個別データを扱うときは [共通の設定・確認境界](../_shared/context.md) を参照します。一般説明だけで設定や全進捗を読みません。必要な工程を選び、他の資料は読み込まないでください。

## 必要な資料

- 利用可能なブラウザ方式を選ぶとき: [browser](references/workflow-browser.md)
- 中断・再開・送信済み状態を扱うとき: [resume](references/workflow-resume.md)
- 入力前に税額・プロファイル・必要な決算を検証するとき: [checks](references/workflow-checks.md)
- 画面の全体構造を調べる必要があるとき: [navigation](references/workflow-navigation.md)
- 申告種類を選んで本人認証へ進むとき: [start](references/workflow-start.md)
- 事業所得があり決算書を入力するとき: [business](references/workflow-business.md)
- 所得税の申告内容を入力するとき: [income](references/workflow-income.md)
- 消費税申告が必要で該当方式を入力するとき: [consumption](references/workflow-consumption.md)
- 入力内容と計算結果を照合するとき: [review](references/workflow-review.md)
- 入力確認後、本人の意思確認・署名・手動送信へ進むとき: [submission](references/workflow-submission.md)
- 保存・受信結果・進捗を記録するとき: [result](references/workflow-result.md)
- 画面不応答、ダイアログ、環境依存の問題があるとき: [troubleshooting](references/workflow-troubleshooting.md)

## 完了

依頼された出力を作り、根拠・入力・CLI結果を照合し、見つかった問題を修正して再確認します。承認待ち・資料不足・未送信を完了済みと区別して報告します。
