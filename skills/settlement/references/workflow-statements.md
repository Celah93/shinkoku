# settlement: 決算書の生成と貸借一致を検証するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ3: 決算書の生成

決算整理仕訳がすべて登録された後、決算書を生成する。

### 3-1. 損益計算書の確認（`shinkoku ledger pl --db-path DB_PATH --fiscal-year YEAR`）

```bash
shinkoku ledger pl --db-path DB_PATH --fiscal-year YEAR
```
入力 JSON:
```json
{
  "fiscal_year": 2025
}
```
出力:
- `revenue`: 収益の内訳と合計
- `expenses`: 費用の内訳と合計
- `net_income`: 当期純利益（収益合計 - 費用合計）

**確認項目:**
- 売上金額が実績と一致するか
- 各経費科目が妥当か（異常に大きい・小さい科目がないか）
- 青色申告特別控除前の所得金額を確認する

### 3-2. 貸借対照表の確認（`shinkoku ledger bs --db-path DB_PATH --fiscal-year YEAR`）

```bash
shinkoku ledger bs --db-path DB_PATH --fiscal-year YEAR
```
入力 JSON:
```json
{
  "fiscal_year": 2025
}
```
出力:
- `assets` / `liabilities` / `equity`: 科目別の期末残高（期首残高 + 当期増減）のリスト
- `total_assets` / `total_liabilities`: 各カテゴリの期末残高合計
- `net_income`: 当期の収益 − 当期の費用
- `total_equity`: `equity` の合計 + `net_income`
  （`equity` リストの合計と `total_equity` は `net_income` の分だけ一致しない）
- `opening_assets` / `opening_liabilities` / `opening_equity`: 決算書の期首列に使う科目別残高
- `opening_total_*`: 期首残高のカテゴリ別合計

**確認項目:**
- 資産合計 = 負債合計 + 純資産合計 であるか（貸借一致）
- 現金・預金残高が実際の残高と一致するか
- 固定資産の帳簿価額が減価償却後の金額であるか
