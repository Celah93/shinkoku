# income-tax: 事業源泉徴収・税理士報酬・損失繰越を扱うとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ1.8: 事業所得の源泉徴収（支払調書）

取引先から受け取った支払調書の情報を登録する。

### 支払調書の取り込み

1. `shinkoku import payment-statement --file-path PATH` で支払調書PDF/画像からデータを抽出する

#### 画像ファイルの場合: OCR 読み取り

`extracted_text` が空の場合（画像ファイルまたはスキャン PDF）、画像の読み取りは `/reading-payment-statement` スキルを使用する。
   読み取り方・照合・不明箇所の扱いは該当する reading-* Skill に従います。実データへの登録前に確認する内容をまとめます。

2. `shinkoku ledger bw-add --db-path DB_PATH --fiscal-year YEAR --input withholding.json` で取引先別の源泉徴収情報を登録する:
   ```json
   {
     "client_name": "取引先名",
     "gross_amount": 1000000,
     "withholding_tax": 102100
   }
   ```
   年分は `--fiscal-year` で指定する。JSONには `fiscal_year` や `detail` のラッパーを付けない。
3. `shinkoku ledger bw-list --db-path DB_PATH --fiscal-year YEAR` で登録済み情報を確認する
4. 源泉徴収税額の合計を `business_withheld_tax` として所得税計算に使用する


## ステップ1.8.5: 税理士等報酬の登録

税理士・弁護士等に報酬を支払っている場合、報酬明細を登録する。

`pf-add` は決算書の「税理士・弁護士等の報酬・料金の内訳」用の明細である。
旧来のフィールド名 `payer_name`・`payer_address` には、本人が支払った相手である税理士・弁護士等の氏名・住所を入れる。
支払者である本人の氏名・住所を入れない。`fee_amount` は本年中の報酬等の金額、
`expense_deduction` はそのうち必要経費へ算入する金額であり、帳簿の経費計上額と照合する。

1. `shinkoku ledger pf-list --db-path DB_PATH --fiscal-year YEAR` で登録済みの税理士等報酬を確認する
2. 未登録の場合は `shinkoku ledger pf-add --db-path DB_PATH --fiscal-year YEAR --input fee.json` で登録する:
   ```json
   {
     "payer_address": "支払先である税理士等の住所",
     "payer_name": "支払先である税理士等の氏名",
     "fee_amount": 300000,
     "expense_deduction": 0,
     "withheld_tax": 30630
   }
   ```
   年分は `--fiscal-year` で指定する。JSONには `fiscal_year` や `detail` のラッパーを付けない。
3. `withheld_tax` は本人が報酬から預かって納付する**税理士・弁護士側の税額**であり、本人の事業源泉、給与源泉、その他の源泉徴収税額や還付計算には含めない。
   申告書作成では、決算書の報酬内訳表の源泉徴収税額欄にだけ転記する。預り金の記帳と納付の管理は別に行う。
4. 本人の `business_withheld_tax` はステップ1.8の `bw-list` の確認済み合計だけを使う。
   例えば本人の事業源泉134,772円、税理士への支払源泉20,420円なら、入力する本人分は134,772円のままである。
5. 本人分の明細をすべて登録して読戻し、所得税計算後に `shinkoku tax sanity-check --db-path DB_PATH --input sanity_input.json` で照合する。
   DBとの不一致や誤合算の疑いが出た場合は、登録漏れと税の帰属を確認し、入力を確定して再計算する。差額を機械的に差し引かない。

源泉の帰属と納付は[国税庁の税理士等報酬の説明](https://www.nta.go.jp/taxes/shiraberu/taxanswer/gensen/2798.htm)を参照する。


## ステップ1.9: 損失繰越の確認

前年以前に事業で損失が発生し、青色申告している場合、繰越控除を適用できる。

1. `shinkoku ledger lc-list --db-path DB_PATH --fiscal-year YEAR` で登録済みの繰越損失を確認する
2. 未登録の場合は `shinkoku ledger lc-add --db-path DB_PATH --fiscal-year YEAR --input loss.json` で登録する:
   ```json
   {
     "loss_year": 2023,
     "amount": 500000
   }
   ```
   申告対象の年分は `--fiscal-year` で指定し、損失が発生した年はJSONの `loss_year` に記載する。`fiscal_year` や `detail` のラッパーは付けない。
3. 繰越損失の合計を `loss_carryforward_amount` として所得税計算に使用する
