# consumption-tax: 方法を比較し、選択済みの方法で最終計算・保存するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ3: 申告方法の比較（任意）

比較は `estimate` で行う。方式を確認して申告用の最終計算をするときは `calculation_mode: "filing"` を指定し、2割・3割特例には確認済みの `invoice_special_eligibility` を渡す。入力例と除外条件は `docs/tax-eligibility.md` を参照する。未確認の試算をそのまま申告用の確定値へ昇格させない。

3割特例は `method: "special_30pct"` とし、年度プロファイルも同じ値を保存する。2027・2028年分だけに使い、以前の簡易課税事業区分があれば確認済みの変更時に `simplified_business_type: null` で消去する。

複数の方法が選択可能な場合、それぞれの税額を試算して比較表を提示する。

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
消費税の申告方法比較
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| 方法 | 納付税額 | 備考 |
|------|---------|------|
| 2割特例 | ○○,○○○円 | 届出不要 |
| 簡易課税 | ○○,○○○円 | 届出が必要 |
| 本則課税 | ○○,○○○円 | インボイス保存要 |

→ 最も有利な方法: [方法名]（差額: ○○,○○○円）
```

比較試算の各呼び出しには `--db-path` を付けない。


## ステップ3.5: 申告方法の確定・保存・最終計算

1. 比較結果と適用要件を示し、最終的に使う申告方法をユーザーへ確認する
2. 確定した方法を `fiscal-year-update` で年度DBへ保存する
3. 保存後、同じDBを指定して最終計算し、`method_verified: true` を確認する

本則課税または2割特例を確定する場合は、以前の簡易課税事業区分が残らないよう
`simplified_business_type` を明示NULLにする。

```json
{
  "consumption_tax_method": "standard",
  "simplified_business_type": null
}
```

2割特例では `consumption_tax_method` を `special_20pct` とする。簡易課税では事業区分を
同じパッチに含める。

```json
{
  "consumption_tax_method": "simplified",
  "simplified_business_type": 5
}
```

```bash
shinkoku ledger fiscal-year-update --db-path DB --fiscal-year YEAR --input profile_patch.json
shinkoku tax calc-consumption --db-path DB --input consumption_input.json
```

書込み前に最終計算しない。保存値と入力値の照合を通した結果を申告用の確定結果とする。
