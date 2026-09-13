# e-tax: 利用可能なブラウザ方式を選ぶとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ブラウザ自動化方式の選択

確定申告書等作成コーナーへの入力には、以下の3つの方式がある。

### 方式 A: Claude in Chrome（推奨）

| 項目 | 内容 |
|-----|------|
| 対象環境 | Windows / macOS のネイティブ Chrome |
| 前提 | Claude in Chrome 拡張機能がインストール済み |
| 利点 | OS 検出の問題なし。追加設定不要 |

### 方式 B: Antigravity Browser Sub-Agent

| 項目 | 内容 |
|-----|------|
| 対象環境 | Windows / macOS / Linux（Antigravity IDE） |
| 前提 | Antigravity IDE がインストール済みで `browser_subagent` ツールが利用可能 |
| 利点 | ネイティブ Chrome を使用するため OS 偽装不要。Linux でも動作 |

### 方式 C: Playwright CLI（フォールバック）

| 項目 | 内容 |
|-----|------|
| 対象環境 | WSL / Linux、または Claude in Chrome・Antigravity が利用できない環境 |
| 前提 | `@playwright/cli` + Playwright CLI スキル + `etax-stealth.js`（OS 偽装スクリプト） |
| 制限 | headed モード必須（QR コード認証に物理操作が必要） |

### 選び方

ユーザー指定を優先し、現在利用できるブラウザ操作ツールを選びます。Codexのブラウザツールでも同じ入力契約を使えます。方式Bはこの会話でサブエージェント利用が明示的に依頼された場合だけです。方式Cはその環境を使う場合に限り、現在のツール仕様と動作を確認して参照します。ツールがない場合でも入力値の整理と照合は続けます。

### 方式 B 使用時の操作方法

Antigravity の `browser_subagent` は高レベルなタスク記述で操作する。
各ステップの入力操作を自然言語で記述し、`browser_subagent` に委任する。

例:
- 「https://www.keisan.nta.go.jp/kyoutu/ky/sm/top_web#bsctrl を開く」
- 「『マイナンバーカードをお持ちですか』で『はい』のラジオボタンをクリック」
- 「name='sonekiKeisansyoFromMonth' の入力欄に '1' を入力」

※ Antigravity はネイティブ Chrome を使用するため、`etax-stealth.js` による OS 偽装は不要。

### 方式 C 使用時のセッション開始手順

Playwright CLI でブラウザを開く際の手順:

1. 環境変数を設定: `PLAYWRIGHT_MCP_INIT_SCRIPT=skills/e-tax/scripts/etax-stealth.js`
2. ブラウザ起動: `playwright-cli -s=etax open <url> --headed --browser=chrome`
3. 以降のコマンドは `-s=etax` セッション指定で実行
