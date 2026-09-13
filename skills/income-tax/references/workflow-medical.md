# income-tax: 医療費の明細を集計するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ1.7: 医療費明細の集計

医療費控除を適用する場合、明細を集計する。

### 医療費の登録・集計

1. `shinkoku ledger me-list --db-path DB_PATH --fiscal-year YEAR` で登録済み医療費明細を取得する
2. 未登録の医療費がある場合は `shinkoku ledger me-add --db-path DB_PATH --fiscal-year YEAR --input medical.json` で登録する:
   ```json
   {
     "fiscal_year": 2025,
     "detail": {
       "date": "2025-03-15",
       "patient_name": "山田太郎",
       "medical_institution": "ABC病院",
       "amount": 150000,
       "insurance_reimbursement": 0,
       "description": null
     }
   }
   ```
3. 集計結果（total_amount - total_reimbursement）を医療費控除の計算に使用する
