# 開発時の契約

計算・CLI・DB・リリースを変更する場合に関係する節を参照してください。税法の表は既存実装の契約であり、別年度にそのまま適用しません。

## コーディング規約

### 金額は必ず int（円）

- **float 禁止** — 金額を扱う変数・フィールドは全て `int`（円単位の整数）
- 消費税の按分計算も整数演算（`//` 演算子）で行う
- `amount: int = Field(gt=0, description="円単位の整数")`

### 端数処理

#### 所得税

| 対象 | ルール | 法的根拠 |
|------|--------|---------|
| 課税所得 | 1,000円未満切捨て `(amount // 1_000) * 1_000` | 国税通則法118条 |
| 復興特別所得税 | 1円未満切捨て `tax * 21 // 1000` | 復興財源確保法13条 |
| 所得税及び復興特別所得税の額（㊺） | 端数処理なし | — |
| 申告納税額（納付の場合のみ） | 100円未満切捨て `(amount // 100) * 100` | 国税通則法119条 |
| 還付金 | 1円単位（切捨てなし） | 国税通則法120条 |

#### 消費税

| 対象 | ルール | 法的根拠 |
|------|--------|---------|
| 課税標準額 | 1,000円未満切捨て `(amount // 1_000) * 1_000` | 国税通則法118条 |
| 消費税額（国税） | 課税標準額 × 78/1000（標準）or 624/10000（軽減） | 消費税法29条 |
| 差引税額 | 100円未満切捨て `(amount // 100) * 100` | 国税通則法119条 |
| 地方消費税 | 差引税額または控除不足還付税額 × 22/78。納税額は100円未満切捨て、還付額は1円未満切捨て | 地方税法72条の89 |

#### 各種控除

| 対象 | ルール | 法的根拠 |
|------|--------|---------|
| 生命保険料控除 | 1円未満切り上げ `-(-amount // divisor)` | 所得税法76条 |
| 地震保険料控除 | 1円未満切り上げ `-(-amount // divisor)` | 所得税法77条 |
| 住宅ローン控除 | 100円未満切捨て | 租税特別措置法41条2項 |
| 減価償却費 | 普通償却費・必要経費算入額の各欄で1円未満切上げ | 確定申告書等作成コーナーFAQ「減価償却費の端数処理」 |

### 型ヒント

- 全関数に型ヒントを付与する
- ファイル先頭に `from __future__ import annotations` を記述
- `X | None` 記法を使う（`Optional[X]` は使わない）

### Pydantic モデル命名

- `*Input` — ツールへの入力（例: `IncomeTaxInput`）
- `*Result` — ツールからの出力（例: `IncomeTaxResult`）
- `*Params` — 検索条件（例: `JournalSearchParams`）
- `*Record` — DBレコード（例: `JournalRecord`）
- 定義は `src/shinkoku/models.py` に集約する

### CLI モジュール規約

- parser 構築: `src/shinkoku/cli/__init__.py` の `build_parser()` で全サブコマンドを登録
- エントリーポイント: 同ファイルの `main()` で引数解析・dispatch・エラー処理を行う
- 各モジュール（`src/shinkoku/cli/*.py`）は `register(subparsers)` 関数を公開し、サブコマンドを登録する
- 入力: 複雑なパラメータは `--input <json_file>` で JSON ファイル受け取り。単純パラメータは CLI 引数
- 出力: JSON を stdout に出力
- エラー: `{"status": "error", "message": "..."}` を stdout + exit code 1
- DB 系: `--db-path` 引数で SQLite パスを受け取り
- ビジネスロジックは `src/shinkoku/tools/` の純粋関数として分離する

### Ruff

- `line-length`: 100
- `target-version`: py311

### コメント

- ドメイン固有ロジック（税法の計算根拠、勘定科目の説明等）には日本語コメントを付ける
- 自明なコードにはコメントを付けない

### コミットとリリース

コミットする場合は日本語の件名・本文と Conventional Commits の型を使い、`Refs: fix-NN` trailerを保持します。件名は20〜25文字程度を目安にし、件名の直後と`Refs: fix-NN`行の直前の2か所に空行を置きます。実際の参照番号は対象作業から取得し、捏造しません。

コミット後は次の2コマンドで件名と`Refs:` trailerを検証し、実出力を報告書へ残します。引用符もこのまま使います。

```bash
git log -1 --format=%s <SHA>
git log -1 --format='%(trailers:key=Refs,valueonly)' <SHA>
```

`src/shinkoku/` または `skills/` を変更するコミット・PRでは、`pyproject.toml` と `.claude-plugin/plugin.json` を同じバージョンに更新します。互換性破壊はMAJOR、機能追加はMINOR、修正はPATCHです。CIのVersion Checkを満たしてください。ルートMarkdown・テスト等だけの変更では更新不要です。

## DB 規約

- SQLite WAL モード + `foreign_keys=ON`
- 接続は `db.get_connection()` / 初期化は `db.init_db()` を使う
- 勘定科目コード体系:
  - `1xxx`: 資産（asset）
  - `2xxx`: 負債（liability）
  - `3xxx`: 純資産（equity）
  - `4xxx`: 収益（revenue）
  - `5xxx`: 費用（expense）


## テスト規約

- 構成: `tests/unit/` / `tests/scripts/` / `tests/integration/`
- `tests/scripts/`: CLI の統合テスト（subprocess で `shinkoku` コマンドを呼び出し、JSON 出力を検証）
- `tests/unit/`: DB・config 等のコアモジュールのユニットテスト
- `tests/integration/`: 複数モジュールの結合テスト
- 共有フィクスチャ: `in_memory_db`, `in_memory_db_with_accounts`, `sample_journals`
- マーカー: `@pytest.mark.slow`
