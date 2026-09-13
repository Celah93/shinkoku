# setup: 設定結果と進捗を記録するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ7: 次のステップの案内

セットアップ完了後、以下を案内する:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
セットアップ完了
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ 生成されたファイル:
  → shinkoku.config.yaml（設定ファイル）
  → {db_path}（データベース）

■ 次のステップ:
  1. /assess — 申告要否・種類の判定
  2. /gather — 必要書類の確認・収集
  3. /journal — 仕訳入力・帳簿管理
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```


## 引継書の出力

サマリー提示後、以下のファイルを ファイル書込ツールで出力する。
これにより、セッションの中断や Compact が発生しても次のステップで結果を引き継げる。

### ステップ別ファイルの出力

`.shinkoku/progress/01-setup.md` に以下の形式で出力する:

```
---
step: 1
skill: setup
status: completed
completed_at: "{当日日付 YYYY-MM-DD}"
fiscal_year: {tax_year}
---

# セットアップ結果

## 設定内容

- 対象年度: {tax_year}
- データベースパス: {db_path}
- 出力ディレクトリ: {output_dir}
- インボイス登録番号: {invoice_registration_number}

## 納税者情報

- 氏名: {last_name} {first_name}
- 生年月日: {date_of_birth}
- マイナンバー: {登録済み/未登録}
- 寡婦/ひとり親: {widow_status}
- 障害者区分: {disability_status}
- 勤労学生: {working_student}
- 世帯主との続柄: {relationship_to_head}

## 住所

- 自宅: {postal_code} {prefecture}{city}{street}{building}
- 1/1時点の住所: {jan1_address}（同上/異なる住所）
- 事業所住所: {設定あり/自宅と同じ}

## 事業情報

- 屋号: {trade_name}
- 業種: {industry_type}
- 事業内容: {business_description}

## 申告方法

- 提出方法: {submission_method}
- 申告の種類: {return_type}
- 青色申告特別控除: {blue_return_deduction}円
- 所轄税務署: {tax_office_name}

## 控除・申告に影響する重要事項

- 配偶者: {あり（概算所得: ○万円）/ なし}
- 扶養親族: {あり（○人、うち16歳未満○人）/ なし}
- 住宅ローン控除: {適用あり（初年度/2年目以降）/ 適用なし}
- 予定納税: {あり（合計○円）/ なし}
- 世帯主: {本人 / ○○（氏名）}

## 書類ディレクトリ

- 請求書: {invoices_dir}
- 源泉徴収票: {withholding_slips_dir}
- レシート: {receipts_dir}
- 銀行明細: {bank_statements_dir}
- クレカ明細: {credit_card_statements_dir}
- 控除関連: {deductions_dir}
- 過去の申告: {past_returns_dir}

## DB初期化

- 初期化結果: 成功
- 勘定科目マスタ: 登録済み

## 次のステップ

/assess で申告要否・種類を判定する
```

未設定の項目は「未設定」と記載する。

### 進捗サマリーの更新

`.shinkoku/progress/progress-summary.md` を新規作成する:

- YAML frontmatter: fiscal_year、last_updated（当日日付）、current_step: setup
- テーブル: 全ステップの状態を記載（setup を completed に、他は pending に）
- 次のステップの案内を記載

### 出力後の案内

ファイルを出力したらユーザーに以下を伝える:
- 「引継書を `.shinkoku/progress/` に保存しました。セッションが中断しても次のスキルで結果を引き継げます。」
- 次のステップの案内
