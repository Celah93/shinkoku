# income-tax: iDeCo・社会保険・保険会社別内訳を扱うとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ1.6: iDeCo・小規模企業共済の確認

掛金払込証明書がある場合は `shinkoku import deduction-certificate --file-path PATH` で取り込むことができる。

1. iDeCo（個人型確定拠出年金）の年間掛金を確認する
   - 小規模企業共済等掛金払込証明書から金額を確認
   - 全額が所得控除（上限: 自営業者は年額81.6万円）
2. 小規模企業共済の掛金がある場合も同様に確認する

#### 画像ファイルの場合: OCR 読み取り

`extracted_text` が空の場合（画像ファイルまたはスキャン PDF）、画像の読み取りは `/reading-deduction-cert` スキルを使用する。
   読み取り方・照合・不明箇所の扱いは該当する reading-* Skill に従います。実データへの登録前に確認する内容をまとめます。


## ステップ1.12: 社会保険料の種別別内訳の登録

所得控除の内訳書に種別ごとの記載が必要なため、社会保険料を種別別に登録する。

社会保険料の控除証明書がある場合は `shinkoku import deduction-certificate --file-path PATH` で取り込むことができる。

1. `shinkoku ledger si-list --db-path DB_PATH --fiscal-year YEAR` で登録済み項目を確認する
2. 未登録の場合は `shinkoku ledger si-add --db-path DB_PATH --fiscal-year YEAR --input insurance.json` で種別ごとに登録する:
   ```json
   {
     "fiscal_year": 2025,
     "detail": {
       "insurance_type": "national_health",
       "name": "保険者名",
       "amount": 300000
     }
   }
   ```
   insurance_type: national_health / national_pension / national_pension_fund / nursing_care / labor_insurance / other
3. 合計額を `social_insurance` として控除計算に使用する


## ステップ1.13: 保険契約の保険会社名の登録

所得控除の内訳書に保険会社名の記載が必要なため、保険契約を登録する。

控除証明書の画像・PDFがある場合は `shinkoku import deduction-certificate --file-path PATH` で取り込むことができる。
取り込み後、抽出データに基づいて `shinkoku ledger ip-add --db-path DB_PATH --fiscal-year YEAR --input policy.json` で登録する。

1. `shinkoku ledger ip-list --db-path DB_PATH --fiscal-year YEAR` で登録済み項目を確認する
2. 未登録の場合は `shinkoku ledger ip-add --db-path DB_PATH --fiscal-year YEAR --input policy.json` で登録する:
   ```json
   {
     "fiscal_year": 2026,
     "detail": {
       "policy_type": "life_general_new",
       "company_name": "保険会社名",
       "premium": 80000
     }
   }
   ```
   policy_type: life_general_new / life_general_old / life_medical_care / life_annuity_new / life_annuity_old / earthquake / old_long_term
3. 生命保険料は `life_insurance_detail` パラメータに、地震保険料は `earthquake_insurance_premium` に反映する
