---
name: income-tax
description: 所得・控除・源泉徴収から所得税と納付・還付額を計算する。
---

# income-tax

対象年度の所得・控除・予定納税を確認し、既存CLIで計算・検算します。事業所得がある場合だけ決算結果を使います。申告額を確定する前に家族構成、住宅ローン控除、予定納税の有無・金額を確かめ、不明を0にしません。計算途中の承認待ちは不要です。

所得税計算・控除集計・検算は2025〜2027年分に対応します。2027年の追加税・年金・給与調整・対象外の所得域は `docs/income-tax-2027.md` を確認します。高所得特例は `docs/furusato-and-minimum-tax-2027.md` に従い、申告不要所得も含めた全所得を確認します。新年度の画面・様式との照合は未検証です。未対応エラーを避けるために対象年を変えたり、入力から年分を削除したりしません。

申告用計算には `calculation_mode: "filing"` を指定し、青色控除を使うときは確認済みの `blue_return_eligibility` を渡します。`estimate` は試算です。必要な入力は [適用判定](../../docs/tax-eligibility.md) を参照します。

個別データを扱うときは [共通の設定・確認境界](../_shared/context.md) を参照します。一般説明だけで設定や全進捗を読みません。必要な工程を選び、他の資料は読み込まないでください。

## 必要な資料

- 個別の所得税計算を始め、入力の十分性と端数処理を確認するとき: [checks](references/workflow-checks.md)
- 源泉徴収票を読み取り、控除内訳を検算するとき: [withholding](references/workflow-withholding.md)
- 配偶者・扶養親族の適用を判断・登録するとき: [family](references/workflow-family.md)
- iDeCo・社会保険・保険会社別内訳を扱うとき: [insurance](references/workflow-insurance.md)
- 医療費の明細を集計するとき: [medical](references/workflow-medical.md)
- 事業源泉徴収・税理士報酬・損失繰越を扱うとき: [business](references/workflow-business.md)
- 年金・雑所得・暗号資産・総合課税の配当等を扱うとき: [other-income](references/workflow-other-income.md)
- ふるさと納税以外の寄附を扱うとき: [donations](references/workflow-donations.md)
- 所得控除を集計するとき: [deductions](references/workflow-deductions.md)
- 税額を計算しサニティチェックで検算するとき: [calculation](references/workflow-calculation.md)
- 住宅ローン控除の明細を登録するとき: [housing](references/workflow-housing.md)
- 最終計算を説明し次工程へ記録するとき: [result](references/workflow-result.md)

## 完了

依頼された出力を作り、根拠・入力・CLI結果を照合し、見つかった問題を修正して再確認します。承認待ち・資料不足・未送信を完了済みと区別して報告します。
