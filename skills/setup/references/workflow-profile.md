# setup: 初回設定、または納税者・住所・事業情報を更新するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ2: 基本設定のヒアリング

以下の項目を 利用可能な質問手段 で確認する:

### 2-1. 対象年度

- `tax_year`: 確定申告の対象年度（デフォルト: 2025）

### 2-1b. 事業所得の有無

- `has_business_income`: 事業所得（副業含む）の有無（true / false）

事業所得がない場合、以下のステップをスキップする:
- 2-2（インボイス登録番号）
- 2.6-3（事業所住所）
- 2.7（事業情報）
- 2.8 の申告の種類（blue/white）・記帳方法の質問（給与所得のみなら不要）

### 2-2. 適格請求書発行事業者の登録番号（事業所得がある場合のみ）

- `invoice_registration_number`: T + 13桁の番号（任意、スキップ可）


## ステップ2.5: 納税者情報のヒアリング

以下の項目を 利用可能な質問手段 で段階的に確認する。すべて任意（スキップ可能）だが、確定申告書等作成コーナーへの入力や人的控除の判定に使用される。

### 2.5-1. 氏名

- `taxpayer.last_name`: 姓
- `taxpayer.first_name`: 名
- `taxpayer.last_name_kana`: 姓（カタカナ）
- `taxpayer.first_name_kana`: 名（カタカナ）

### 2.5-2. 基本情報

- `taxpayer.gender`: 性別（male / female）
- `taxpayer.date_of_birth`: 生年月日（YYYY-MM-DD）
- `taxpayer.phone`: 電話番号
- `taxpayer.relationship_to_head`: 世帯主との続柄（本人/妻/夫/子等）

### 2.5-3. マイナンバー

- `taxpayer.my_number`: マイナンバー12桁（取扱注意 — config に保存するが、ツール出力やログには一切表示しない）

### 2.5-4. 人的控除に関する状態（任意）

- `taxpayer.widow_status`: 寡婦/ひとり親の区分（none / widow / single_parent）
- `taxpayer.disability_status`: 障害者の区分（none / general / special）
- `taxpayer.working_student`: 勤労学生に該当するか（true / false）


## ステップ2.6: 住所情報のヒアリング

### 2.6-1. 自宅住所

- `address.postal_code`: 郵便番号
- `address.prefecture`: 都道府県
- `address.city`: 市区町村
- `address.street`: 番地
- `address.building`: 建物名・部屋番号（任意）

### 2.6-2. 1月1日時点の住所（異なる場合のみ）

- `address.jan1_address`: 1/1 時点の住所（住民税の課税自治体判定に使用）

### 2.6-3. 事業所住所（事業所得がある場合のみ。自宅と異なる場合のみ）

- `business_address.postal_code` 〜 `business_address.building`


## ステップ2.7: 事業情報のヒアリング

事業所得がある場合に確認する。

- `business.trade_name`: 屋号
- `business.industry_type`: 業種
- `business.business_description`: 事業内容
- `business.establishment_year`: 開業年
