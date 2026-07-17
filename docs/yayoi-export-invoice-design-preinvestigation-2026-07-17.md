# 弥生会計エクスポート・インボイス対応 設計前調査報告書

- 調査日: 2026-07-17
- 対象: `C:\Users\User\Documents\GPT_CODEX_Projects\shinkoku-main`
- 対象バージョン表記: `0.6.12`
- 調査種別: リポジトリ内の事前調査（実装、テスト追加、および外部一次資料の確認は対象外）
- 前提資料: `docs/yayoi23-import-investigation-2026-07-17.md`

## 1. 結論

現行の中核コードは、納税者自身の消費税上の立場を永続的には保持していない。
設定ファイルへ保持できる情報は、自身の適格請求書発行事業者登録番号だけである。
課税事業者・免税事業者の区分、選択した計算方法、および簡易課税の事業区分は、
`shinkoku.config.yaml`にもDBにも保存されない。

`/assess`は課税区分と利用可能な方法を判定し、引継書へ記載する。
`calc-consumption`は、計算時に`ConsumptionTaxInput`として方法、売上額、および仕入額を
都度受け取る。このため、引継書または入力JSONがない処理では、システムが納税者の
課税方式を参照できない。仕訳登録時および弥生エクスポート時にも、現行の中核コードだけでは
課税方式に応じた分岐ができない。

本則課税の計算には、帳簿から課税仕入れを自動集計するコード経路がない。
入力された`taxable_purchases_10`と`taxable_purchases_8`の全額を控除対象として計算し、
適格請求書、免税事業者からの仕入れ、および経過措置の控除割合を区別しない。
これは弥生エクスポートとは独立して、本則課税の計算精度に関わる欠落である。

仕訳モデルには、税率、取引先の登録番号、請求書区分、および仕入税額控除割合がない。
レシートの読取結果から仕訳JSONへの変換は、コードではなくスキルを実行するエージェントが
担当する。証憑パス用の`source_file`は存在するが、レシート処理で設定する指示はない。

70%および30%の出典は、リポジトリ内では令和8年度税制改正大綱を反映したとする
買い手側の5段階経過措置資料である。売り手側の3割特例とは、資料上で別の制度として
記載されている。ただし、外部一次資料との照合は本調査の対象外であり、リポジトリ内の
資料の法的な確定状況は本報告書では確定しない。

既存の帳簿CSV出力は、標準出力へ一般的な表形式を出す処理である。
CP932のファイル出力、BOM、ファイル拡張子、および最終バイト列としての改行形式は
明示されていない。共通の出力分岐は参考にできるが、弥生の25列形式を生成するライターは
独立した専用処理が必要になる構造である。

## 2. 調査条件と現物の状態

- `shinkoku.config.yaml`は、対象ツリーに存在しなかった。
- `.shinkoku/progress/02-assess.md`は、対象ツリーに存在しなかった。
- `.shinkoku/progress/08-consumption-tax.md`も、対象ツリーに存在しなかった。
- そのため、実データの値ではなく、設定モデル、設定例、スキルの出力仕様、およびDBスキーマを確認した。
- 対象ツリーには有効なGit管理情報がなく、`git status --short`は
  `fatal: not a git repository`で終了した。したがって、完了条件にあるGitによる
  クリーン状態の証明はできなかった。
- 実装ファイルおよびテストファイルは変更していない。本報告書だけを新規作成した。

## 3. A. 納税者属性の保持状況

### 3.1 属性別の保持状況

| 属性 | config | DB | `/setup` | `/assess`・引継書 | 計算時入力 | 永続化の結論 |
|---|---|---|---|---|---|---|
| 課税事業者・免税事業者 | なし | なし | 質問なし | 判定し、`02-assess.md`へ記載 | `ConsumptionTaxInput`には項目なし | config・DBには永続化されない |
| 2割特例・簡易課税・本則課税 | なし | なし | 質問なし | 利用可能な方法を`02-assess.md`へ記載し、適用方法を`08-consumption-tax.md`へ記載 | `method: str`を毎回渡す | config・DBには永続化されない |
| 自身のインボイス登録有無・番号 | `invoice_registration_number: str | None` | なし | 任意の番号を質問してconfigへ保存 | 登録有無を課税判定に使用 | 計算入力には項目なし | 番号だけがconfigへ永続化される。独立した登録有無フラグはない |
| 簡易課税の事業区分 | なし | なし | 質問なし | 消費税スキルが判定・使用 | `simplified_business_type: int | None`（1〜6） | config・DBには永続化されない |

### 3.2 configとsetup

`ShinkokuConfig`の先頭の属性は、次の定義である。

> `tax_year: int = 2025`  
> `has_business_income: bool = False`  
> `db_path: str = "./shinkoku.db"`  
> `output_dir: str = "./output"`  
> `invoice_registration_number: str | None = None`

出典: `src/shinkoku/config.py:113-120`

`FilingConfig`の「申告方法」は、消費税の計算方法ではない。
ここで保持するものは、提出方法、青色・白色、青色申告特別控除、簡易帳簿、および
電子帳簿などである。

> `submission_method: str = "e-tax"`  
> `return_type: str = "blue"`  
> `simple_bookkeeping: bool = False`

出典: `src/shinkoku/config.py:77-86`

設定例にも、自身の登録番号だけがある。

> `# 適格請求書発行事業者の登録番号（T + 13桁）`  
> `invoice_registration_number:`

出典: `shinkoku.config.example.yaml:4-14`

`/setup`は、事業所得がある場合に任意の登録番号を質問し、YAMLへ書き出す。

> `invoice_registration_number: T + 13桁の番号（任意、スキップ可）`

出典: `skills/setup/SKILL.md:39-51`

> `invoice_registration_number: {invoice_registration_number}`

出典: `skills/setup/SKILL.md:227-239`

設定モデルの型は単なる`str | None`であり、`T + 13桁`を検証する`Field(pattern=...)`はない。
登録番号の存在を登録有無として利用することは可能であるが、登録日、取消日、および
対象年度時点の有効性は保持しない。

### 3.3 DB

年度テーブルは、年度、状態、および作成日時だけを保持する。

> `year INTEGER PRIMARY KEY`  
> `status TEXT NOT NULL DEFAULT 'open'`  
> `created_at TEXT NOT NULL DEFAULT (datetime('now'))`

出典: `src/shinkoku/schema.sql:4-9`

課税区分、計算方法、自身の登録番号、および簡易課税の事業区分に相当するカラムは、
DBスキーマにない。

### 3.4 assessと引継書

`/assess`は、インボイス登録の有無を課税事業者判定へ使用する。

> `Q4. 適格請求書発行事業者（インボイス登録）をしていますか？`  
> `Yes → 課税事業者（インボイス登録による）`  
> `No → 免税事業者`

出典: `skills/assess/SKILL.md:270-289`

課税事業者の場合には、2割特例、簡易課税、および本則課税を判定する。

> `Q1. 2割特例の適用要件を満たすか？`  
> `Q2. ...簡易課税の届出をしているか？`  
> `No → 本則課税で申告`

出典: `skills/assess/SKILL.md:292-304`

判定結果は画面上に表示され、`.shinkoku/progress/02-assess.md`へ書き出される。

> `課税事業者区分: [課税事業者 / 免税事業者]`  
> `申告方法: [2割特例 / 簡易課税 / 本則課税]`

出典: `skills/assess/SKILL.md:333-350`

> `.shinkoku/progress/02-assess.md`  
> `課税事業者区分: {課税事業者/免税事業者}`  
> `適用可能な方法: {2割特例/簡易課税/本則課税}`

出典: `skills/assess/SKILL.md:363-420`

このファイルはセッション間の引継書であり、configまたはDBではない。
また、`02-assess.md`の仕様は「適用可能な方法」を保存するため、最終的に選択した一つの方法を
必ず表すものではない。

### 3.5 consumption-taxと計算入力

消費税スキルは、引継書があれば読み、なければユーザーへ確認する。

> `.shinkoku/progress/02-assess.md`を読み込む  
> `ファイルが存在しない場合はスキップし、ユーザーに必要情報を直接確認する`

出典: `skills/consumption-tax/SKILL.md:31-40`

中核の計算入力は、方法と金額を毎回受け取る。

> `method: str = Field(pattern=r"^(standard|simplified|special_20pct)$")`  
> `taxable_purchases_10: int = 0`  
> `taxable_purchases_8: int = 0`  
> `simplified_business_type: int | None = Field(default=None, ge=1, le=6)`

出典: `src/shinkoku/models.py:498-516`

計算後の引継書には、選択した方法を記録する仕様がある。

> `適用方法: {2割特例/簡易課税/本則課税}`

出典: `skills/consumption-tax/SKILL.md:271-317`

したがって、スキル実行中には引継書またはユーザー入力から情報を利用できるが、
中核の仕訳処理および任意の後続処理が安定して参照できる永続属性ではない。

### 3.6 納税者属性を保持する層の選択肢

以下は選択肢と制約の列挙であり、推奨順位は付けない。

1. `shinkoku.config.yaml`へ消費税セクションを追加する。
   - 例: 課税区分、標準の計算方法、自身の登録番号、および簡易課税事業区分を保持する。
   - 制約: 課税区分および選択方法は年度ごとに変わり得るため、単一の現在値では履歴を表しにくい。
   - 制約: DBだけを受け取るCLIからは、configの場所または読み込み規約が別途必要になる。

2. `fiscal_years`テーブルを拡張する。
   - 年度別の課税区分、選択方法、および事業区分を直接参照できる。
   - 制約: 既存DBのマイグレーション、NULL・初期値の扱い、およびconfigとの同期方針が必要になる。
   - 制約: 登録番号の履歴や登録期間を年度属性だけで表す場合には、粒度が粗くなる。

3. 納税者または年度別の消費税プロファイル用テーブルを新設する。
   - 登録番号の有効期間、課税区分、届出状況、および年度ごとの選択方法を分離できる。
   - 制約: テーブル、モデル、CRUD、CLI、参照規約、およびマイグレーションの範囲が広くなる。

4. 現行どおりに、入力JSONと進捗引継書だけで保持する。
   - DBおよびconfigの変更は不要である。
   - 制約: 引継書がない処理、別セッション、直接CLI実行、およびエクスポート処理で参照できない。
   - 制約: 同一年度に異なる入力が渡されても、中核側が整合性を検証できない。

5. configを既定値、DBの年度属性を確定値とする併用方式にする。
   - 初期設定と年度別確定値を分離できる。
   - 制約: 優先順位、同期、更新責任、および不一致時の扱いを定義する必要がある。

## 4. B. 消費税計算の依存関係

### 4.1 calc-consumptionの入力元

CLIは、JSONを読み、`ConsumptionTaxInput`を作り、純粋関数へ渡すだけである。

> `params = _load_json(args.input)`  
> `input_data = ConsumptionTaxInput(**params)`  
> `result = calc_consumption_tax(input_data)`

出典: `src/shinkoku/cli/tax_calc.py:186-191`

この経路には、`db_path`、DB接続、仕訳検索、または`journal_lines`の集計がない。

スキルは、帳簿コマンドの結果から金額を算出するようにエージェントへ指示し、
その金額をJSONへ設定する。

> `ledger.py trial-balance や ledger.py search の結果から以下を算出する`  
> 入力JSONに`taxable_purchases_10`および`taxable_purchases_8`を記載する

出典: `skills/consumption-tax/SKILL.md:80-118`

したがって、現状はエージェントまたはユーザーが集計した値をJSONへ渡す前提であり、
中核コードによる帳簿からの自動集計ではない。

### 4.2 方法別の仕入額への依存

- 2割特例では、売上税額の80%を仕入控除税額として計算し、入力された仕入額を使用しない。
- 簡易課税では、売上税額へみなし仕入率を掛け、入力された仕入額を使用しない。
- 本則課税では、入力された税込仕入額へ税率を掛け、仕入控除税額を直接計算する。

> `special_20pct: ... national_tax_on_sales * (100 - SPECIAL_20PCT_RATE)`  
> `simplified: ... national_tax_on_sales * ratio`  
> `standard: input_data.taxable_purchases_10 ... + input_data.taxable_purchases_8 ...`

出典: `src/shinkoku/tools/tax_calc.py:1403-1418, 1441-1467`

### 4.3 非適格仕入れおよび経過措置の区別

`ConsumptionTaxInput`には、適格・非適格の区分、取引先登録番号、請求書区分、および
仕入税額控除割合のフィールドがない。本則課税ルートにも、80%、70%、50%、30%、または0%を
掛ける分岐がない。入力された`taxable_purchases_10`と`taxable_purchases_8`は、
全額が控除可能な課税仕入れとして計算される。

このため、免税事業者からの仕入れを他の課税仕入れと合算して入力した場合には、
本則課税の計算が過大な仕入税額控除になる可能性がある。弥生向け出力の有無とは無関係に、
消費税計算側で区別できない状態である。

## 5. C. 仕訳データモデルと税区分の値域

### 5.1 journal_linesの値域

DBが許可する`journal_lines.tax_category`は、次の6種類またはNULLである。

> `taxable_10`  
> `taxable_8`  
> `taxable_8_reduced`  
> `non_taxable`  
> `exempt`  
> `out_of_scope`

出典: `src/shinkoku/schema.sql:56-68`

`tax_rate`カラムはない。税率は`tax_category`の文字列へ埋め込まれている。
明細には、別に`tax_amount INTEGER DEFAULT 0`がある。

Pydanticモデル側は、`tax_category`を単なる任意文字列として受け取る。

> `tax_category: str | None = None`  
> `tax_amount: int = 0`

出典: `src/shinkoku/models.py:11-18`

仕訳登録処理は、入力された値を変換せず、そのままDBへ挿入する。

> `line.tax_category`  
> `line.tax_amount`

出典: `src/shinkoku/tools/ledger.py:158-197`

したがって、実際に永続化できる値域はDBのCHECK制約の6種類またはNULLである。
モデル段階では任意文字列が通るため、範囲外の値はDB挿入時に初めて失敗する。

### 5.2 account masterとの関係

`accounts.tax_category`の値域は、`taxable`、`non_taxable`、`exempt`、
`out_of_scope`、またはNULLであり、仕訳明細より粗い。

出典: `src/shinkoku/schema.sql:11-19`

現行の`MASTER_ACCOUNTS`で実際に使用されている値は、`taxable`、`non_taxable`、
`out_of_scope`、およびNULLである（例: `src/shinkoku/master_accounts.py:294-342`）。
`exempt`はスキーマ上は許可されるが、現行マスターには設定例がない。

仕訳検証は、年度、貸借一致、および勘定科目の存在だけを確認する。
勘定科目マスターの`tax_category`を`journal_lines.tax_category`へ変換または補完しない。

出典: `src/shinkoku/tools/ledger.py:75-99`

### 5.3 請求書関連項目の不存在

`journals`には、日付、摘要、取引先、content hash、source、source_fileなどがある。
`journal_lines`には、貸借、科目、金額、税区分、および税額がある。

出典: `src/shinkoku/schema.sql:22-35, 56-68`

取引先のインボイス登録番号、請求書区分、番号照合結果、取引日時点の有効性、
仕入税額控除割合、および判定根拠に相当するカラムはない。
`JournalEntry`および`JournalLine`にも、同じ項目はない。

出典: `src/shinkoku/models.py:11-30`

### 5.4 既存DBのマイグレーション

DB初期化は、スキーマを適用した後に`_migrate`を呼ぶ。

> `conn.executescript(schema_sql)`  
> `_migrate(conn)`

出典: `src/shinkoku/db.py:20-28`

`_migrate`は、`PRAGMA table_info`でカラムを確認し、必要な場合に`ALTER TABLE ... ADD COLUMN`を
実行する方式である。マイグレーション番号または`PRAGMA user_version`による版管理はない。

出典: `src/shinkoku/db.py:31-46`

新しいNULL許容カラムの追加は現行方式でも可能である。一方で、NOT NULL、CHECK制約、
既存行の初期値、既存監査ログの表現、および複数カラム間の整合を必要とする場合には、
単純なカラム追加だけでは足りない。

### 5.5 content_hashへの影響

現在の`content_hash`は、日付と、並べ替えた`side`・`account_code`・`amount`だけから計算する。

> `sorted(lines, key=lambda ln: (ln.side, ln.account_code, ln.amount))`  
> `parts.append(f"{line.side}:{line.account_code}:{line.amount}")`

出典: `src/shinkoku/hashing.py:10-23`

税区分、税額、摘要、source_file、および将来の請求書関連項目は、ハッシュへ入らない。
登録処理は、このハッシュを完全一致の重複判定に使用する。

出典: `src/shinkoku/tools/ledger.py:108-143`

DBには、年度とNULLではないcontent hashの組み合わせに部分UNIQUEインデックスがある。

出典: `src/shinkoku/schema.sql:395-400`

請求書関連項目をハッシュへ入れない場合には、日付、科目、および金額が同じで、
請求書区分だけが異なる仕訳も完全一致として扱われる。ハッシュへ入れる場合には、
既存行のハッシュ再計算、旧ハッシュとの互換、UNIQUE衝突、およびFix #06で定めた
`force`時のNULL化との整合を設計する必要がある。

## 6. D. レシート読取から仕訳登録までの変換パス

### 6.1 読取結果

`/reading-receipt`の`RECEIPT_DATA`は、次の項目だけを返す。

> `date`  
> `vendor`  
> `total_amount`  
> `tax_included`  
> `items[].name / amount / quantity`

出典: `skills/reading-receipt/SKILL.md:57-74`

税率別金額、税額、登録番号、請求書区分、および控除割合はない。

`shinkoku import receipt`のコードは、OCRを行わない。ファイルの存在を確認し、
空のテンプレートを返すだけである。

> `OCR is performed by Claude Vision`  
> `this tool only verifies the file exists and returns an empty template`

出典: `src/shinkoku/tools/import_data.py:235-253`

CLIのヘルプも「レシート画像の存在チェック＋テンプレート返却」と記載している。

出典: `src/shinkoku/cli/import_data.py:87-95`

### 6.2 仕訳JSONへの変換主体

`/journal`は、読取結果を確認し、勘定科目を推定し、確認後に仕訳へ変換するように
エージェントへ指示する。

> `RECEIPT_DATAブロックの内容を解析する`  
> `品目から勘定科目を推定する`  
> `確認後、仕訳データに変換する`

出典: `skills/journal/SKILL.md:129-147`

この変換を実装した関数または中間モデルはない。変換規則はスキル指示だけに存在する。

### 6.3 デュアル検証へ項目を追加する場合の変更箇所

現行の読取スキルは、主要フィールドを比較するように一般的に指示する。

出典: `skills/reading-receipt/SKILL.md:20-36`

`/journal`は、単一・複数の両方で、比較対象を`total_amount`、`date`、`vendor`と明記する。

出典: `skills/journal/SKILL.md:129-156`

比較項目を追加する場合に影響する箇所は、少なくとも次のとおりである。

1. `skills/reading-receipt/SKILL.md`の読取ルール、`RECEIPT_DATA`形式、および結果照合ルール。
2. `skills/journal/SKILL.md`の単一レシート用比較項目。
3. 同ファイルの複数レシート用比較項目。
4. `import_receipt`のテンプレートにも項目を返す設計にする場合には、
   `src/shinkoku/tools/import_data.py`の戻り値。
5. 比較結果を仕訳へ保存する場合には、`JournalEntry`、`JournalLine`、DBスキーマ、
   登録・検索・更新・監査ログ、およびcontent hash方針。

### 6.4 source_file

`JournalEntry`には`source_file: str | None`があり、仕訳登録処理は指定された値を
`journals.source_file`へ保存する。

出典: `src/shinkoku/models.py:21-30`、`src/shinkoku/tools/ledger.py:158-178`

検索処理も値を返す（`src/shinkoku/tools/ledger.py:383-416`）。
一方で、`skills/reading-receipt/`および`skills/journal/`には`source_file`を設定する指示がない。
したがって、カラムは利用可能であるが、現行のレシート変換で証憑パスが必ず記録される
保証はない。

## 7. E. 経過措置資料とFix #09の重なり

### 7.1 70%および30%のリポジトリ内出典

`transitional-measures-timeline.md`は、自身を経過措置のSingle Source of Truthとし、
令和8年度税制改正大綱の変更を反映したと記載する。

> `このファイルは...唯一の正（Single Source of Truth）です`  
> `令和8年度税制改正大綱...の変更を反映済み`

出典: `skills/invoice-system/references/transitional-measures-timeline.md:1-6`

同資料は、売り手側の2割特例・3割特例と、買い手側の仕入控除経過措置を別節で扱う。
売り手側の3割特例は、個人事業主の売上税額に対する納付率30%として記載される。

出典: `skills/invoice-system/references/transitional-measures-timeline.md:10-34`

買い手側には、次の5段階が記載される。

> R5.10.1〜R8.9.30: 80%  
> R8.10.1〜R9.9.30: 70%  
> R9.10.1〜R10.9.30: 50%  
> R10.10.1〜R11.9.30: 30%  
> R11.10.1〜: 0%

出典: `skills/invoice-system/references/transitional-measures-timeline.md:43-55`

同資料は、旧3段階から新5段階への変更として明記する。

> `80%→50%→0%`から`80%→70%→50%→30%→0%`に細分化された

出典: `skills/invoice-system/references/transitional-measures-timeline.md:110-120`

したがって、リポジトリ内資料における70%と30%は、売り手側の3割特例との混同ではなく、
令和8年度税制改正大綱による変更として記載された買い手側の仕入控除割合である。

同じスケジュールは、次の資料にも重複して記載される。

- `skills/tax-advisor/reference/tax-reform/transition.md:46-70, 133-157`
- `skills/tax-advisor/reference/tax-reform/2026.md:176-205`
- `skills/consumption-tax/references/tax-classification.md:161-168`
- `skills/tax-invoice-credit-context/references/input-tax-credit-rules.md:92-94`

ただし、`2026.md`は、大綱に基づく法案成立前の情報であるという免責を記載する。

> `法案成立前の情報として参考利用のこと`

出典: `skills/tax-advisor/reference/tax-reform/2026.md:1-7`

外部一次資料の確認は指示書で対象外とされているため、本調査では、5段階の内容が
現在の成立法および最新の公表資料と一致するかを検証していない。

### 7.2 Fix #09の成果物

ファイル名および本文について、`Fix #09`、`Fix#09`、`fix09`、`Fix_09`、
`2026年税制改正`、`令和8年度税制改正`、`中間報告`、および`調査報告`を検索した。
明示的にFix #09と名付けられた成果物または中間報告は、現行ツリーでは確認できなかった。

Fix #09の明示名はないが、内容上の候補となる資料は、次のとおりである。

- `skills/tax-advisor/reference/tax-reform/2026.md`
- `skills/tax-advisor/reference/tax-reform/transition.md`
- `skills/invoice-system/references/transitional-measures-timeline.md`

これらは70%および30%へ触れているが、コミット履歴がないため、Fix #09との関係は
ファイル内容だけでは確定できない。

## 8. F. 出力層の現状

### 8.1 帳簿CSV出力

`ledger`の`--format`は、`json`または`csv`を受け取る。

> `p.add_argument("--format", choices=["json", "csv"], default="json")`

出典: `src/shinkoku/cli/ledger.py:862-867`

この引数は、`search`、`audit-log`、`trial-balance`、`pl`、`bs`、および
`general-ledger`に付与される。

出典: `src/shinkoku/cli/ledger.py:900-950`

CSV出力は、CLIモジュール内の単一関数`_output_csv`へ集約されている。
`io.StringIO()`と`csv.writer()`を使用し、resultのキーに応じて、仕訳帳、総勘定元帳、
残高試算表、損益計算書、貸借対照表、および監査ログを表形式へ変換する。

出典: `src/shinkoku/cli/ledger.py:122-273`

仕訳帳CSVの列は9列である。

> `journal_id, date, description, counterparty, side, account_code, amount, tax_category, tax_amount`

出典: `src/shinkoku/cli/ledger.py:137-166`

出力先はファイルではなく標準出力である。

> `print(out.getvalue(), end="")`

出典: `src/shinkoku/cli/ledger.py:268-273`

### 8.2 文字コード、BOM、および改行

本番コードは、標準出力の文字コードを明示していない。
`sys.stdout.reconfigure`、`PYTHONIOENCODING`の設定、およびファイルの`encoding=`指定はない。
したがって、実際の文字コードは実行環境から継承される。

CLIテストの共通ヘルパーだけは、子プロセスと親の復号をUTF-8へ固定する。

> `encoding="utf-8"`  
> `PYTHONUTF8: 1`  
> `PYTHONIOENCODING: utf-8`

出典: `tests/scripts/conftest.py:42-56`

`csv.writer`の既定dialectが作る文字列の行終端はCRLFである。
調査環境の標準ライブラリで1行を書き出した結果は、`'a,b\r\n'`であった。
ただし、その文字列を標準出力へ渡した後の最終バイト列は、標準出力の文字コードと
改行変換に依存する。BOMも付与されない。

既存のCSVテストは、終了コード、ヘッダー、およびデータ行の存在を確認するが、
文字コード、BOM、CRLFの最終バイト列、およびファイル拡張子は検証しない。

出典: `tests/scripts/test_ledger.py:1747-1856`

### 8.3 CP932の出力前例

CP932対応は、CSV入力側にだけ存在する。

> UTF-8、UTF-8 BOM、またはCP932を判定する  
> CP932でデコードしてCSVを読み込む

出典: `src/shinkoku/tools/import_data.py:16-37, 136-153`

`src/`および`tests/`にある`cp932`・`shift_jis`の該当箇所は、入力の検出、読込、
および入力テストだけである。CP932でファイルを書き出す処理は確認できなかった。

### 8.4 弥生ライターへの再利用可能性

再利用可能なものは、`--format`の引数追加パターン、結果を出力形式へ振り分ける構造、
および仕訳と明細を平坦化する考え方である。

一方で、現在の`_output_csv`は、弥生形式のレコード種別、25列配置、識別フラグ、
税区分サフィックス、ヘッダー有無、CP932、ファイル出力、および拡張子を扱わない。
また、resultのキーを見て分岐するCLIローカル関数であり、汎用のライター抽象化ではない。
そのため、弥生の行生成およびエンコード処理は、既存の表形式CSVとは独立した
専用ライターになる構造である。

## 9. 「存在しない」とした項目の検索条件

対象範囲は、特記がない限り`src/`、`skills/`、`tests/`、`shinkoku.config.example.yaml`、
および`docs/`である。`rg --files`で確認できたファイルは、`src/`・`skills/`・`tests/`が
184件、現行ツリー全体が202件であった。

| 結論 | 主な検索パターン | 対象範囲・補足 |
|---|---|---|
| config・DBに課税区分と計算方法がない | `taxable_business`, `tax_exempt`, `consumption_tax_method`, `special_20pct`, `simplified_business_type`, `invoice_registration_number`, `課税事業者`, `免税事業者`, `2割特例`, `簡易課税`, `本則課税` | `src/shinkoku/config.py`, `src/shinkoku/schema.sql`, `shinkoku.config.example.yaml`, `skills/setup/`, `skills/assess/`, `skills/consumption-tax/`。該当した計算時入力・スキル文書を個別に追跡した |
| 帳簿から消費税計算への自動集計がない | `taxable_purchases_10`, `taxable_purchases_8`, `ConsumptionTaxInput`, `calc_consumption_tax`, `journal_lines`, `ledger_search`, `trial_balance` | `src/`, `skills/`, `tests/`。該当箇所は入力モデル、計算関数、CLI、テスト、およびスキル文書であり、DB集計関数からの呼出しはなかった |
| 仕訳に請求書関連項目がない | `tax_rate`, `invoice_category`, `input_tax_credit_rate`, `invoice_valid`, `invoice_verified`, `registration_number`, `qualified_invoice`, `credit_rate` | `src/shinkoku/schema.sql`, `src/shinkoku/models.py`, `src/shinkoku/tools/`, `src/shinkoku/cli/`。寄付金等の無関係な`credit_rate`は除外した。登録番号はconfigにだけ該当した |
| レシートから仕訳への変換コードがない | `RECEIPT_DATA`, `import_receipt`, `receipt_ocr`, `JournalEntry`, `journal-batch-add`, `total_amount`, `vendor` | `src/`, `skills/reading-receipt/`, `skills/journal/`, `tests/`。存在確認テンプレートとスキル指示だけが該当した |
| レシート経路でsource_file設定の保証がない | `source_file` | `src/`, `skills/`, `tests/`。モデル、DB、帳簿処理には該当したが、`skills/reading-receipt/`と`skills/journal/`には該当しなかった |
| 明示的なFix #09成果物がない | `Fix #09`, `Fix#09`, `fix09`, `Fix_09`およびファイル名の`fix.?09` | 現行ツリー全202ファイル。明示名の該当なし |
| 弥生出力コードがない | `yayoi`, `弥生`, `仕訳日記帳`, `借方税区分`, `貸方税区分`, `インポート形式` | `src/`, `skills/`, `tests/`。該当なし。前提の調査報告書は検索対象から除外した |
| CP932ファイル出力がない | `cp932`, `shift.?jis`, `encoding=`, `write_text`, `write_bytes`, `csv.writer`, `csv.DictWriter`, `newline=` | `src/`, `tests/`。CP932の該当は入力側だけであり、CSV出力は標準出力だけであった |

## 10. 本件とは独立して確認した不整合・リスク

修正は行っていない。

1. **仕訳税区分の検証層が一致しない。**  
   `JournalLine.tax_category`は任意文字列を受け取る一方で、DBは6種類に制限する。
   そのため、利用者向けの入力エラーではなく、DBのCHECK制約エラーとして遅く表面化する。

2. **勘定科目と仕訳明細で税区分の語彙が異なる。**  
   勘定科目は`taxable`という粗い区分を使用し、仕訳明細は`taxable_10`などを使用する。
   両者を変換または補完するコードがないため、マスターの既定税区分は明細へ自動反映されない。

3. **簡易課税の事業区分が未指定の場合に、第5種へ黙って補完される。**  
   入力モデルでは`None`を許可するが、計算関数は`input_data.simplified_business_type or 5`を
   使用する（`src/shinkoku/tools/tax_calc.py:1447-1452`）。未指定と第5種の意図的指定を
   結果から区別できない。

4. **Single Source of Truthの宣言と資料の重複が一致しない。**  
   `transitional-measures-timeline.md`は唯一の正と宣言するが、同じ5段階表が
   `transition.md`、`2026.md`、`tax-classification.md`などにも複製されている。
   改正時に資料間で差異が生じる可能性がある。

5. **制度資料の確定状態が資料間で明確に統一されていない。**  
   一方の資料は「変更を反映済み」と記載し、`2026.md`は「法案成立前」と免責する。
   リポジトリ内だけでは、現在どの状態を確定値として扱うかを判断できない。

## 11. 検証状況と制約

- A〜Fについて、実装、スキーマ変更、およびテスト追加は行っていない。
- `csv.writer`の既定行終端は、調査環境の標準ライブラリで`\r\n`になることを確認した。
- 既存のCSV出力テストとCP932入力テストを対象にしたpytestは、開発依存関係
  `types-pyyaml`をネットワーク制限下で取得できなかったため、実行できなかった。
- テスト実行の準備で生成された未完成の`.venv/`は、`.gitignore`の対象である。
  削除の許可が得られなかったため、調査終了時点で残っている。実装コードではない。
- 対象ツリーは有効なGitリポジトリではないため、`git status`によるクリーン状態の確認は
  実施不能である。実装ファイルを変更していないことは、本調査の操作範囲に基づく確認である。

## 12. 設計前に未確定のまま残る事項

以下は、指示書により本調査の対象外である。

1. 弥生会計が受け付ける税区分サフィックスの正確な文字列と対応バージョン。
2. 国税庁公表サイトのWeb-APIまたは全件データの利用条件、申請要件、および照合方式。
3. 令和8年度改正後の仕入控除割合について、成立法および最新の国税庁資料との一致。
4. 少額特例などを含めた法的な適用優先順位。
5. 納税者属性を保持する層、およびcontent hashへ請求書属性を含めるかという設計判断。

