# setup: 具体的な設定内容を確認して保存し、新規DBを初期化するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ5: 設定のプレビューと保存

1. 収集した設定内容を YAML 形式でプレビュー表示する
2. ユーザーの確認を得る
3. ファイル書込ツールで CWD に `shinkoku.config.yaml` を保存する

YAML の形式は以下のテンプレートに従う:

```yaml
# shinkoku ユーザー設定ファイル
# /setup スキルで対話的に生成できます。

# 対象年度
tax_year: {tax_year}

# 事業所得の有無（副業含む）
has_business_income: {has_business_income}

# データベースファイルのパス
db_path: {db_path}

# 進捗ファイル等の出力先ディレクトリ
output_dir: {output_dir}

# 適格請求書発行事業者の登録番号（T + 13桁）
invoice_registration_number: {invoice_registration_number}

# --- 納税者情報 ---
taxpayer:
  last_name: {last_name}
  first_name: {first_name}
  last_name_kana: {last_name_kana}
  first_name_kana: {first_name_kana}
  gender: {gender}
  date_of_birth: {date_of_birth}
  phone: {phone}
  my_number: {my_number}
  widow_status: {widow_status}
  disability_status: {disability_status}
  working_student: {working_student}
  relationship_to_head: {relationship_to_head}

# --- 住所 ---
address:
  postal_code: {postal_code}
  prefecture: {prefecture}
  city: {city}
  street: {street}
  building: {building}
  jan1_address: {jan1_address}

# --- 事業所住所（自宅と異なる場合のみ） ---
business_address:
  postal_code:
  prefecture:
  city:
  street:
  building:

# --- 事業情報 ---
business:
  trade_name: {trade_name}
  industry_type: {industry_type}
  business_description: {business_description}
  establishment_year: {establishment_year}

# --- 申告方法 ---
filing:
  submission_method: {submission_method}
  return_type: {return_type}
  blue_return_deduction: {blue_return_deduction}
  simple_bookkeeping: {simple_bookkeeping}
  electronic_bookkeeping: {electronic_bookkeeping}
  tax_office_name: {tax_office_name}

# --- 家族構成 ---
family:
  has_spouse: {has_spouse}
  has_dependents: {has_dependents}
  dependent_count: {dependent_count}

# --- 住宅ローン控除 ---
housing_loan:
  applicable: {applicable}
  first_year: {first_year}

# --- 予定納税 ---
estimated_tax:
  applicable: {applicable}
  amount: {amount}

# --- 書類ディレクトリ（任意） ---
invoices_dir: {invoices_dir}
withholding_slips_dir: {withholding_slips_dir}
past_returns_dir: {past_returns_dir}
deductions_dir: {deductions_dir}
receipts_dir: {receipts_dir}
bank_statements_dir: {bank_statements_dir}
credit_card_statements_dir: {credit_card_statements_dir}
```

未設定の項目は値を空にする（`key:` のみ）。

**`my_number` の取扱い**: マイナンバーは config YAML に保存するが、`profile.py` の出力では `has_my_number: true/false` のみ返す。ログ・会話には出力しない。確定申告書等作成コーナーへの入力時のみ config から直接読み取る。

```bash
shinkoku profile --config PATH
```


## ステップ5.5: Git セーフティ設定

ユーザーの個人情報・財務データが誤って git にコミットされないよう、`.gitignore` を設定する。

### 手順

1. `git rev-parse --is-inside-work-tree` を実行し、CWD が git リポジトリかどうか確認する

2. **git リポジトリでない場合** → 以下のメッセージを表示してスキップする:
   > 現在のディレクトリは git リポジトリではありません。今後 git リポジトリ化する場合は、`.gitignore` に shinkoku 関連ファイルを追加して個人情報の漏洩を防いでください。

3. **git リポジトリの場合**:
   a. CWD の `.gitignore` を ファイル読取ツールで読み込む（存在しなければ新規作成前提で進める）
   b. 以下の必須エントリが `.gitignore` に含まれているか確認する:
      ```
      # shinkoku 確定申告データ（個人情報を含む — 削除しないこと）
      shinkoku.config.yaml
      shinkoku.db
      shinkoku.db-wal
      shinkoku.db-shm
      .shinkoku/
      output/
      ```
   c. ステップ4で設定された書類ディレクトリ（`invoices_dir`, `receipts_dir` 等）があれば、それも追加対象にする
   d. 不足しているエントリがある場合:
      - 追加するエントリの一覧をユーザーに提示する
      - セットアップに必要な `.gitignore` の不足分を追記する（既存の内容は保持する）。既に追跡済みの個人ファイルがあれば報告し、履歴削除を勝手に行わない
   e. 既に全エントリが含まれている場合 → 「`.gitignore` は設定済みです」と表示してスキップする


## ステップ6: データベースの初期化

1. `db_path` の値を確認し、相対パスの場合は CWD を基準に絶対パスに変換する
2. `shinkoku ledger init --db-path DB --fiscal-year YEAR` コマンドでデータベースを初期化する:
   ```bash
   shinkoku ledger init --db-path DB --fiscal-year YEAR
   ```
   - `--fiscal-year`: ステップ2 で設定した `tax_year`
   - `--db-path`: 絶対パスに変換した値
