# income-tax: ふるさと納税以外の寄附を扱うとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ1.14: ふるさと納税以外の寄附金の確認

政治活動寄附金、認定NPO法人、公益社団法人等への寄附金を確認する。

1. `shinkoku ledger don-list --db-path DB_PATH --fiscal-year YEAR` で登録済み寄附金を確認する
2. 未登録の場合は `shinkoku ledger don-add --db-path DB_PATH --fiscal-year YEAR --input donation.json` で登録する:
   ```json
   {
     "donation_type": "npo",
     "recipient_name": "寄附先名",
     "amount": 50000,
     "date": "2025-06-01",
     "receipt_number": null
   }
   ```
   年分は `--fiscal-year` で指定する。JSONには `fiscal_year` や `detail` のラッパーを付けない。
   donation_type: political / npo / public_interest / specified / other
3. 寄附金控除の計算:
   - 政治・認定NPO・公益社団法人等の3区分ごとに、年中の全額を所得控除か税額控除のどちらか一方へそろえる
   - 3区分の選択を最大8通り比較し、最終税額が最小の候補を `calc_income_tax` が選ぶ。同額なら所得控除を優先する
   - 総所得金額等40%枠と2,000円の足切りは、所得控除→公益→NPO→政治の順に共有する
   - 公益とNPOは所得税額25%枠を共有し、政治は別の25%枠を使う。算式額と25%上限額は100円未満を切り捨てる
4. 申告用の確定値は `calc-income` の結果を使う。`calc-deductions` の寄附金項目は方式選択前の中間候補である
