# shinkoku

確定申告を支援する AI コーディングエージェント向けプラグインです。Python CLI と SQLite が帳簿管理・税額計算・データ保存を担当し、Agent Skills が書類読取り、確認、確定申告書等作成コーナーへの入力を案内します。

**Claude Code Plugin** として動作するほか、**SKILL.md オープン標準** に準拠した Agent Skills パッケージとして、Claude Code / Cursor / Windsurf / GitHub Copilot / Gemini CLI / Codex / Cline / Roo Code / Antigravity など 40 以上の AI コーディングエージェントで利用できます。

## forkについて

このリポジトリ（[`Celah93/shinkoku`](https://github.com/Celah93/shinkoku)）は、[`kazukinagata/shinkoku`](https://github.com/kazukinagata/shinkoku) をfork元とする派生版です。

- このREADMEは、`Celah93/shinkoku` の現在の `main` ブランチにある実装を説明しています
- fork版で追加・変更された機能、CLI、スキル、税制対応は、fork元へ反映されているとは限りません
- fork元の更新は、このforkへ自動では反映されません。同期時には、双方の差分と互換性を確認する必要があります
- 原著作者の表示とMIT Licenseは維持しています。詳細は [LICENSE](./LICENSE) を確認してください
- `pyproject.toml` とプラグインマニフェストには、fork元のURLや作者表記が残っています。fork版の取得先と報告先は、このREADMEに記載した `Celah93/shinkoku` です
- fork版の不具合や追加機能は [`Celah93/shinkoku`](https://github.com/Celah93/shinkoku) へ、fork元に関する内容は [`kazukinagata/shinkoku`](https://github.com/kazukinagata/shinkoku) へ報告してください

## 想定ユーザー

| 対象 | 対応レベル | 備考 |
|------|-----------|------|
| 個人事業主（青色申告・一般用） | Full | メインターゲット。帳簿 → 決算書 → 税額計算 → 作成コーナー入力 |
| 会社員 + 副業（事業所得） | Full | 源泉徴収票 + 事業所得の税額計算 → 作成コーナー入力 |
| 給与所得のみ（会社員） | Full | 還付申告・医療費控除等 → 作成コーナー入力 |
| 消費税課税事業者 | Full | 2割特例・簡易課税・本則課税すべて対応 |
| ふるさと納税利用者 | Full | 寄附金 CRUD + 控除計算 + 限度額推定 |
| 住宅ローン控除（初年度） | Full | 控除額計算（添付書類は別途必要） |
| 医療費控除 | Full | 明細集計＋控除額計算 |
| 仮想通貨トレーダー | Full | 雑所得（総合課税）として申告書に自動反映 |

`Full` は、対象となる申告ワークフローの計算と作成コーナーへの入力支援がそろっていることを示します。申告内容の最終確認、本人認証、電子署名、送信は利用者が行います。

## 現在の実装状況

### 実装済み

| 領域 | できること |
|------|------------|
| 帳簿・決算 | SQLite の年度管理、開始残高、仕訳の追加・一括追加・検索・更新・削除、重複検出、試算表、損益計算書、貸借対照表、総勘定元帳、減価償却、棚卸し、決算整理 |
| 所得税 | 給与所得、事業所得、雑所得、総合課税の配当所得、一時所得、損失繰越、所得控除、税額控除、源泉徴収税額、予定納税額を反映した納付額・還付額の計算 |
| 所得税サニティチェック | 計算入力と計算結果を再計算し、青色申告特別控除、課税所得の丸め、復興特別所得税、税額控除、源泉徴収税額、還付額などを10項目で検査 |
| 消費税 | 2割特例、簡易課税、本則課税の計算・比較、税率区分、インボイス区分、経過措置、帳簿のみ保存の特例、申告書第二表用の集計、警告の出力 |
| ふるさと納税 | 寄附記録の追加・一覧・削除・集計、寄附金控除、控除限度額の推定 |
| 書類・データ取込 | 汎用 CSV の解析、PDF のテキスト抽出・画像変換、マルチモーダル LLM を使ったレシート・請求書・源泉徴収票・控除証明書・支払調書の構造化 |
| e-Tax 入力 | Claude in Chrome、Antigravity、Playwright CLI を使った確定申告書等作成コーナーへのブラウザ入力支援 |
| 初期設定・保護 | 設定ファイルと SQLite DB の初期化、個人データを対象とする `.gitignore` の設定 |

所得税計算 CLI が受け付ける年分別定数は、2025年分、2026年分、2027年分です。これら以外の年分はエラーになります。実際の申告では、対象年分の国税庁画面と最新の税制を必ず確認してください。

### 補助 CRUD・単体計算のみ

| 領域 | 実装済み | 未統合の部分 |
|------|----------|--------------|
| 株式 | 証券会社・口座別の譲渡損益、配当、源泉税、譲渡損失繰越の保存・一覧・削除 | 分離課税の税額計算、申告書計算、e-Tax 入力 |
| FX | 証券会社別の実現損益、スワップ収入、経費、損失繰越の保存・一覧・削除 | 先物取引に係る雑所得等の税額計算、申告書計算、e-Tax 入力 |
| 公的年金 | 公的年金等控除と課税年金所得の単体計算 | 通常の所得税計算、申告書計算、e-Tax 入力への自動統合 |
| 退職所得 | 退職所得控除と課税退職所得の単体計算 | 通常の所得税計算、申告書計算、e-Tax 入力への自動統合 |

### 未対応

以下のケースには対応していません。

| 対象 | 理由 |
|------|------|
| 不動産所得 | 不動産所得用の決算書・申告 |
| 譲渡所得（不動産売却） | 長期/短期税率、3,000万円特別控除 |
| 外国税額控除 | 外国税支払額の追跡・控除計算 |
| 農業所得・山林所得 | 専用所得区分 |
| 白色申告 | 帳簿機能の一部は利用できますが、収支内訳書と白色申告用の申告フローは未実装 |
| 非居住者 | 日本居住者専用 |
| 法人税・法人申告 | `/incorporation` は法人成りの相談機能であり、法人税申告には非対応 |
| マイナポータル連携 | 外部サービスとの API 連携は未実装 |

### 自動化の境界

```text
書類読取り・CSV解析 → 仕訳候補 → 利用者の確認 → SQLiteへ保存
SQLite・入力JSON    → 税額計算 → 作成コーナーへ入力 → 利用者が認証・署名・送信
```

- `import` コマンドは、CSV の解析結果または OCR 用の入力情報を返します。仕訳を自動では保存しません
- 画像の OCR は、CLI 自体ではなく、`/reading-*` スキルを実行するマルチモーダル LLM が行います
- 仕訳は、利用者が候補を確認した後に `ledger journal-add` または `ledger journal-batch-add` が SQLite へ保存します
- 税額計算 CLI は JSON 入力を受け取る計算層です。スキルが帳簿・書類・利用者への確認結果から入力を組み立てます
- e-Tax の本人認証、電子署名、最終送信は自動化しません

---

## ⚠️ 免責事項

**確定申告は自己責任で行ってください。**

- 本ツールが生成した申告書・計算結果は、提出前に**必ずご自身で内容を確認**してください
- 税法の解釈や申告内容に不安がある場合は、**税理士等の専門家に相談**することを強く推奨します
- 本ツールの利用によって生じた**いかなる損害についても、開発者は責任を負いません**
- 税制と国税庁の画面は毎年改正されます。対応年分であっても、最新情報との照合が必要です

---

## インストール

以下の手順では、このfork版である `Celah93/shinkoku` をインストールします。fork元を利用する場合は、[`kazukinagata/shinkoku` のREADME](https://github.com/kazukinagata/shinkoku#readme) に記載された手順を使用してください。両方を同じ名前でインストールすると、利用中のコードを判別しにくくなるため注意してください。

### 前提条件

- Python 3.11 以上
- [uv](https://docs.astral.sh/uv/) パッケージマネージャ

### CLI のインストール

スキルが内部で `shinkoku` コマンドを呼び出します。通常は `/setup` スキルが自動でインストールしますが、手動で行う場合は以下を実行してください。

```bash
# インストール
uv tool install git+https://github.com/Celah93/shinkoku

# 更新
uv tool upgrade shinkoku
```

> Cowork の場合は、チャットで Claude にインストールを依頼してください。

### 方法 1: Claude Code プラグイン（フル機能）

プラグイン機能を使い、OCR 画像読取を含む全機能を利用できます。

```bash
# マーケットプレイスを追加
/plugin marketplace add Celah93/shinkoku

# プラグインをインストール
/plugin install shinkoku@shinkoku
```

### 方法 2: スキルのみインストール（40+ エージェント対応）

[skills](https://github.com/vercel-labs/skills) CLI でスキルをインストールできます。

```bash
# スキルのインストール（インストール先エージェントを対話的に選択）
npx skills add Celah93/shinkoku

# 特定のエージェントにグローバルインストール
npx skills add Celah93/shinkoku -g -a claude-code -a cursor

# インストール可能なスキル一覧を確認
npx skills add Celah93/shinkoku --list

```

### 環境別の補足

| 環境 | 設定方法 |
|------|---------|
| Claude Code | `/plugin marketplace add Celah93/shinkoku` → `/plugin install shinkoku@shinkoku` |
| Cowork | プラグイン > 個人用 > GitHub からマーケットプレイスを追加 > `Celah93/shinkoku` を入力してマーケットプレイスを追加し、その後表示される shinkoku プラグインをインストール |
| その他 | `npx skills add Celah93/shinkoku` でインストール（方法 2 を参照） |

### ブラウザ自動化（e-Tax に必要）

`/e-tax` スキルでは、確定申告書等作成コーナーへの入力にブラウザ自動化が必要です。以下の3方式に対応しています。

| 方式 | 対象環境 | 備考 |
|------|---------|------|
| Claude in Chrome（推奨） | Windows / macOS のネイティブ Chrome | Claude in Chrome 拡張機能が必要 |
| Antigravity Browser Sub-Agent | Windows / macOS / Linux | Antigravity IDE のブラウザ操作機能を利用 |
| Playwright CLI（β版） | WSL / Linux 等 | `@playwright/cli` のインストールが必要 |

#### Claude in Chrome の有効化（Claude Code）

Claude in Chrome を利用するには、Claude Code 起動時にフラグを付けるか、セッション内でコマンドを実行します。

```bash
# 起動時に有効化
claude --chrome

# セッション内で有効化
/chrome
```

#### Playwright CLI のインストール

Claude in Chrome, Antigravity を利用する場合このステップは不要です。

```bash
# パッケージインストール
npm install -g @playwright/cli@latest

# スキルインストール（エージェントがコマンドを認識するために必要）
playwright-cli install --skills

# Chromium インストール
npx playwright install chromium
```

WSL の場合、GUI 表示が必要です（headed モードで Chrome を操作するため）。Windows 11 では WSLg が標準搭載されており追加設定は不要です。Windows 10 では X Server（VcXsrv 等）が必要です。

どのブラウザ方式を使う場合でも、QR コード等による本人認証、電子署名、申告データの最終送信は利用者が行います。

## 使い方

### 作業ディレクトリの準備

shinkoku はプラグイン（またはスキル）としてインストールして使います。**このリポジトリを clone する必要はありません。**

お好きなディレクトリを作業フォルダとして使ってください。確定申告に関するデータはすべてこのフォルダ内に保存されます。

```bash
# 例: 確定申告用のフォルダを作成
mkdir ~/kakuteishinkoku && cd ~/kakuteishinkoku

# git で管理する場合（推奨）
git init
```

### セットアップ

作業ディレクトリで `/setup` と入力すると、対話形式で初期設定が始まります。

```
/setup
```

セットアップでは以下が行われます:

1. 設定ファイル（`shinkoku.config.yaml`）の生成
2. `.gitignore` の自動設定（git リポジトリの場合）
3. データベース（`shinkoku.db`）の初期化

### 個人データの保護

shinkoku は作業ディレクトリに以下のファイルを生成します。これらにはマイナンバー・住所・財務データ等の**個人情報が含まれます**。

| ファイル | 内容 |
|---------|------|
| `shinkoku.config.yaml` | マイナンバー・電話番号・住所等の個人情報 |
| `shinkoku.db` / `shinkoku.db-wal` / `shinkoku.db-shm` | 帳簿・仕訳の財務データ |
| `.shinkoku/` | 進捗ファイル（納税者情報のサマリー） |
| `output/` | 生成レポート |

`/setup` を git リポジトリ内で実行すると、これらのファイルが `.gitignore` に自動追加されます。ユーザーが設定した書類ディレクトリ（請求書・レシート等）も同様に追加されます。

> **注意**: `.gitignore` に登録されていても、`git add -f` で強制追加するとコミットされてしまいます。個人情報を含むファイルを絶対にリモートリポジトリにプッシュしないよう注意してください。

## スキル一覧

スキルは、AIに「何を確認し、どの `shinkoku` コマンドを呼び、結果をどう案内するか」を教える作業手順書です。税額計算やデータ保存そのものは、Pythonで実装されたCLIが担当します。

利用者が直接呼び出すスキルのほか、画像読取り専用スキルと、AIが必要なときだけ裏で読み込む内部コンテキストがあります。

### 申告作業の全体像

```text
/setup → /assess → /gather → /journal → /settlement
                                      ├→ /income-tax ──────┐
                                      └→ /consumption-tax ─┤
                                                           ↓
                                                     /submit → /e-tax
```

- 所得税だけを申告する場合、`/consumption-tax` は不要です
- `/submit` は提出前の確認、`/e-tax` は確定申告書等作成コーナーへの実入力を担当します
- 途中で税務上の疑問が出た場合は、補助スキルを単独で呼び出せます

### メインワークフロー（利用者が直接使う）

| 段階 | スキル | 役割 |
|------|--------|------|
| 1. 初期設定 | `/setup` | 設定ファイル（`shinkoku.config.yaml`）とSQLite DBを作る |
| 2. 申告判定 | `/assess` | 所得税・消費税の申告要否を判定し、年度別の課税区分を保存する |
| 3. 書類準備 | `/gather` | 必要書類のチェックリストと取得先を案内する |
| 4. 日常記帳 | `/journal` | CSV・レシート・請求書を取り込み、仕訳の登録・検索・修正・削除を行う |
| 5. 決算 | `/settlement` | 減価償却・棚卸し・決算整理を行い、試算表・損益計算書・貸借対照表を作る |
| 6. 所得税計算 | `/income-tax` | 所得・所得控除・税額控除・源泉徴収税額から納付額または還付額を計算する |
| 6. 消費税計算 | `/consumption-tax` | 2割特例・簡易課税・本則課税を比較し、消費税額を計算する |
| 7. 提出前確認 | `/submit` | 申告内容の最終チェックと、e-Tax・郵送・持参の提出方法を案内する |
| 8. 電子申告 | `/e-tax` | 計算結果を確定申告書等作成コーナーへブラウザ入力する |

### 補助スキル（必要なときに単独で使う）

| スキル | 役割 | 計算・保存 |
|-------|------|------------|
| `/tax-advisor` | 控除、扶養、節税、税制改正などの税務相談に答える | 原則として相談・情報提供 |
| `/furusato` | 受領証を読み、寄附の登録・一覧・削除・集計と控除限度額推定を行う | DB保存・計算あり |
| `/invoice-system` | インボイス登録、仕入税額控除、経過措置、少額特例などを説明する | 制度説明が中心 |
| `/e-bookkeeping-compliance` | 優良な電子帳簿や電子帳簿保存法の要件を満たしているか診断する | 帳簿の診断 |
| `/capabilities` | 対応できる申告、対象者、既知の制限事項を一覧する | 状況表示のみ |
| `/incorporation` | 法人成りの税額比較、法人形態、設立手続き、役員報酬を案内する | 法人税申告には非対応 |

### 書類読取りスキル

通常は `/journal`、`/income-tax`、`/furusato` などから呼び出されます。画像やPDFを構造化データへ変換するところまでを担当し、仕訳登録や税額計算は呼出元のスキルが行います。

| スキル | 読取対象 |
|-------|---------|
| `/reading-receipt` | レシート・領収書・ふるさと納税受領証明書 |
| `/reading-withholding` | 源泉徴収票 |
| `/reading-invoice` | 請求書 |
| `/reading-deduction-cert` | 控除証明書（生命保険料・地震保険料等） |
| `/reading-payment-statement` | 支払調書 |

### 内部コンテキスト（利用者は直接呼び出さない）

`user-invocable: false` のスキルです。税務相談や判定を行う際に、AIが必要なものだけを自動で読み込みます。

| スキル | AIへ提供する情報 |
|-------|------------------|
| `tax-legal-context` | 税理士法との境界、回答範囲、免責事項 |
| `tax-housing-loan-context` | 住宅ローン控除の要件・限度額・計算根拠 |
| `tax-invoice-credit-context` | 仕入税額控除、帳簿のみ保存の特例、インボイス経過措置 |
| `tax-ebookkeeping-context` | 電子帳簿保存法の保存要件とshinkokuの対応状況 |

### 名前が似ているスキルの違い

- `/invoice-system` は制度説明、`/consumption-tax` は実際の税額計算
- `/submit` は提出前確認、`/e-tax` はブラウザへの実入力
- `/reading-*` は書類の読取り、`/journal` は仕訳としての保存
- `/tax-advisor` は相談窓口、`/income-tax` は申告用の所得税計算
- `/e-bookkeeping-compliance` は利用者向け診断、`tax-ebookkeeping-context` は診断に使う内部資料

## 対応エージェント

### OCR 画像読取

レシート・源泉徴収票等の画像読取（`/reading-*` スキル）は、利用する LLM がマルチモーダル（画像認識）に対応している必要があります。これはエージェントプラットフォームではなく、接続先の LLM の能力に依存します。CLI の `import` コマンドだけでは画像を OCR しません。

#### 2026年7月23日時点の画像入力対応モデル例

| プロバイダー | 現行モデルの例 | 公式情報 |
|-------------|----------------|----------|
| Anthropic | Claude Fable 5、Claude Opus 4.8、Claude Sonnet 5、Claude Haiku 4.5 | [Claudeモデル一覧](https://platform.claude.com/docs/en/about-claude/models/overview) |
| OpenAI | GPT-5.6 Sol（`gpt-5.6-sol`）、GPT-5.6 Terra、GPT-5.6 Luna | [OpenAIモデル一覧](https://developers.openai.com/api/docs/models) |
| Google | Gemini 3.6 Flash、Gemini 3.5 Flash | [Geminiモデル一覧](https://ai.google.dev/gemini-api/docs/models) |

- 上記は対応モデルの固定リストではなく、2026年7月23日時点の例です
- Claude Opus 4.6、Claude Sonnet 4.6、GPT-5.2等の旧世代でも、利用環境で画像入力が有効であれば読取りに使用できます
- 実際に選択できるモデルは、Claude Code、Codex、Cursor等の利用環境、契約プラン、モデルの提供状況によって異なります
- **画像入力に対応するマルチモーダル LLM**ではOCR読取りが可能ですが、**テキスト専用 LLM**では手動入力が必要です

### OCR デュアル検証（サブエージェント利用）

2つのサブエージェントが独立に画像を読み取り、結果をクロスチェックする機能です。サブエージェントの並列実行に対応したプラットフォームで利用できます。非対応のプラットフォームでは、単一読取 + ユーザー確認にフォールバックします。

| エージェント | デュアル検証 |
|-------------|:---:|
| Claude Code | ✓ |
| Cowork | ✓ |
| Cursor 2.5+ | ✓ |
| GitHub Copilot | ✓ |
| Cline | ✓ |
| Antigravity | ✓ |
| Windsurf | — |
| Gemini CLI | △ |
| Roo Code | △ |

- **△**: サブエージェント機能はあるが並列実行が制限的

## 開発者向け情報

### テスト

```bash
make test                              # 全テスト実行
uv run pytest tests/unit/ -v           # ユニットテスト
uv run pytest tests/scripts/ -v        # CLI テスト
uv run pytest tests/integration/ -v    # 統合テスト
```

### Lint / 型チェック

```bash
make lint                                            # Ruff lint + format + mypy
uv run ruff format --check src/ tests/               # フォーマットチェック
uv run mypy src/shinkoku/ --ignore-missing-imports   # 型チェック
```

### プロジェクト構成

```
shinkoku/
├── .claude-plugin/
│   ├── plugin.json              # Claude Code プラグインマニフェスト
│   └── marketplace.json         # マーケットプレイス定義
├── .github/
│   └── workflows/
│       └── test.yml             # CI パイプライン
├── skills/                      # Agent Skills（SKILL.md オープン標準）
│   ├── setup/SKILL.md           #   初回セットアップ
│   ├── assess/SKILL.md          #   申告要否判定
│   ├── gather/SKILL.md          #   書類収集
│   ├── journal/SKILL.md         #   仕訳入力・帳簿管理
│   ├── settlement/SKILL.md      #   決算整理・決算書作成
│   ├── income-tax/SKILL.md      #   所得税計算
│   ├── consumption-tax/SKILL.md #   消費税計算
│   ├── submit/SKILL.md          #   提出準備
│   ├── tax-advisor/SKILL.md     #   税務アドバイザー
│   ├── furusato/SKILL.md        #   ふるさと納税
│   ├── invoice-system/SKILL.md  #   インボイス制度の案内
│   ├── e-bookkeeping-compliance/SKILL.md # 電子帳簿保存法の診断
│   ├── e-tax/SKILL.md           #   e-Tax 電子申告（Claude in Chrome）
│   ├── capabilities/SKILL.md    #   機能確認
│   ├── incorporation/SKILL.md   #   法人成り相談
│   ├── reading-receipt/SKILL.md          # OCR: レシート
│   ├── reading-withholding/SKILL.md      # OCR: 源泉徴収票
│   ├── reading-invoice/SKILL.md          # OCR: 請求書
│   ├── reading-deduction-cert/SKILL.md   # OCR: 控除証明書
│   └── reading-payment-statement/SKILL.md # OCR: 支払調書
├── src/shinkoku/
│   ├── cli/                     # CLI エントリーポイント（shinkoku コマンド）
│   │   ├── __init__.py          #   main() + サブコマンド登録
│   │   ├── ledger.py            #   帳簿管理 CLI
│   │   ├── tax_calc.py          #   税額計算 CLI
│   │   ├── import_data.py       #   データ取込 CLI
│   │   ├── pdf.py               #   PDF ユーティリティ CLI
│   │   ├── furusato.py          #   ふるさと納税 CLI
│   │   └── profile.py           #   プロファイル CLI
│   ├── tools/                   # ビジネスロジック（純粋関数）
│   │   ├── ledger.py            #   帳簿管理
│   │   ├── tax_calc.py          #   税額計算
│   │   ├── import_data.py       #   データ取り込み
│   │   ├── pdf.py               #   PDF ユーティリティ
│   │   ├── furusato.py          #   ふるさと納税
│   │   └── profile.py           #   プロファイル取得
│   ├── models.py                # Pydantic モデル定義
│   ├── db.py                    # SQLite DB 管理
│   ├── schema.sql               # SQLite スキーマ
│   ├── master_accounts.py       # 勘定科目マスタ
│   ├── tax_constants.py         # 税制定数
│   ├── config.py                # 設定ファイル読み込み
│   ├── hashing.py               # ハッシュユーティリティ
│   └── duplicate_detection.py   # 重複検出ロジック
├── tests/
│   ├── unit/                    # ユニットテスト
│   ├── scripts/                 # CLI テスト
│   ├── integration/             # 統合テスト
│   ├── fixtures/                # テストフィクスチャ
│   └── helpers/                 # テストヘルパー
├── shinkoku.config.example.yaml # 設定ファイルテンプレート
├── pyproject.toml
├── Makefile
└── uv.lock
```

### 技術スタック

- Python 3.11+
- SQLite（WAL モード）
- Pydantic（モデル定義・バリデーション）
- pdfplumber（PDF 読取）
- Playwright（ブラウザ自動化フォールバック — Python `playwright` + npm `@playwright/cli`）
- PyYAML（設定ファイル読み込み）
- Ruff（lint / format）
- mypy（型チェック）
- pytest（テスト）

## ライセンス

fork元の `kazukinagata/shinkoku` と同じMIT Licenseです。原著作者の著作権表示を含む詳細は [LICENSE](./LICENSE) を参照してください。

## コントリビュート

このforkへのIssueやPull Requestを歓迎します。日本語での報告・提案で構いません。

- fork版のバグ報告: [`Celah93/shinkoku` のIssue](https://github.com/Celah93/shinkoku/issues)を作成してください。再現手順があると助かります
- fork版の機能提案: [`Celah93/shinkoku` のIssue](https://github.com/Celah93/shinkoku/issues)で議論した上でPRを作成してください
- fork元のバグや提案: [`kazukinagata/shinkoku` のIssue](https://github.com/kazukinagata/shinkoku/issues)へ報告してください
- PR: `main` ブランチに対して作成してください。CI（lint + テスト）が通ることを確認してください
