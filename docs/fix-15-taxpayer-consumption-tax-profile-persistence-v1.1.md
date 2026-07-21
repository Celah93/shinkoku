# fix-15: 納税者消費税属性の年度別永続化

- 作成日: 2026-07-17
- 版: v1.1
- Fix番号: #15（#10〜#14 は fix-09 第6節の申し送りで予約済みのため）
- 前提資料: `docs/yayoi-export-invoice-design-preinvestigation-2026-07-17.md`（項目A・独立発見1・独立発見3）
- 種別: スキーマ拡張＋CLI追加＋検証強化（弥生エクスポート・インボイス判定の前提整備）

## 1. 目的

納税者の消費税上の属性（課税事業者区分・申告方法・簡易課税事業区分）を
年度別に永続化し、仕訳登録・エクスポート等の任意の処理から参照可能にする。

現状、これらは `/assess` の引継書と計算時入力JSONにしか存在せず、
引継書のないセッションや直接CLI実行では、システムが納税者の課税方式を参照できない
（設計前調査報告書 3.1〜3.5）。

## 2. 決定事項と Why-not

以下は決定済みであり、実装中に変更しない。変更が必要と判明した場合は
実装を中断して報告する。

### 決定1: 保持層は `fiscal_years` テーブルの拡張とする

- **Why not 専用プロファイルテーブル（調査報告書の選択肢3）**:
  登録番号の有効期間など細粒度の表現が可能だが、現時点でその粒度を要求する
  処理が存在しない。必要になった時点で移行する。
- **Why not config併用（選択肢5）**: 既定値と確定値の優先順位・同期・不一致時の
  扱いという新しい問題領域を持ち込む。単一の保持先の方が整合検証が単純になる。
- **Why not config単独（選択肢1）**: 課税区分・申告方法は年度ごとに変わる属性であり、
  単一の現在値では複数年度のDBに対して整合しない。

### 決定2: 申告方法カラムは「確定値のみ」を保持し、期中は NULL とする

- カラムに値が存在すること＝その年度の申告方法がユーザー確認のうえ確定したこと、
  という一義的なセマンティクスとする。
- **Why not 予定値運用**: 予定値を書くと「値がある＝確定」が成り立たなくなり、
  参照側が確定・仮を区別する仕組みが別途必要になる。
- **帰結（重要）**: 仕訳登録時・レシート取込時のインボイス属性の記録要否は、
  申告方法カラムに依存させてはならない。2割特例は申告時の事後選択であり、
  期中は本則課税へ切り替える可能性が常に残るためである。
  期中の判定に使ってよいのは課税事業者区分までとする。
  （本指示書の範囲ではインボイス属性の記録自体は実装しない。将来Fixの前提として明記する）

### 決定3: 値の検証は Pydantic モデル層で厳格に行い、DBには CHECK 制約を付けない

- **Why not DB CHECK**: 令和9年分から3割特例（`special_30pct` 等）の追加が
  確実視されており、SQLiteのCHECK制約変更はテーブル再構築を要する。
  モデル層検証なら列挙の拡張がコード変更だけで済む。
- 独立発見1（`JournalLine.tax_category` はモデル素通し・DBで遅く失敗）の
  逆の構造とし、エラーは入力に最も近い層で早く出す。
- 本指示書では `journal_lines.tax_category` 側の修正は行わない（別Fix）。

### 決定4: 自身の登録番号は config 据え置きとする

- 登録番号は年度属性ではなく納税者属性であり、現行の
  `ShinkokuConfig.invoice_registration_number` を継続使用する。
- **Why not fiscal_years へ移動**: 年度別に持つと同一番号の重複記録になる。
  有効期間の表現が必要になった場合は決定1のWhy-notと同時に再検討する。
- 形式検証（`T` + 13桁）の追加は本指示書の範囲外とする（issue化する）。

## 3. 仕様

### 3.1 スキーマ変更

`fiscal_years` に以下の3カラムを追加する。すべてNULL許容、CHECK制約なし、
DEFAULTなし（NULL）。

| カラム | 型 | 意味 |
|---|---|---|
| `taxpayer_status` | TEXT | `taxable` / `exempt`。NULL = 未判定 |
| `consumption_tax_method` | TEXT | `standard` / `simplified` / `special_20pct`。NULL = 未確定 |
| `simplified_business_type` | INTEGER | 1〜6。NULL = 未設定 |

- `schema.sql` の `fiscal_years` 定義に追加する。
- 既存DB向けに `src/shinkoku/db.py` の `_migrate` へ、`PRAGMA table_info` による
  存在確認と `ALTER TABLE fiscal_years ADD COLUMN ...` を追加する（現行方式踏襲）。

### 3.2 Pydantic モデル

新モデル `FiscalYearTaxProfile` を `models.py` に追加する。

- `taxpayer_status: Literal["taxable", "exempt"] | None = None`
- `consumption_tax_method: Literal["standard", "simplified", "special_20pct"] | None = None`
- `simplified_business_type: int | None = Field(default=None, ge=1, le=6)`
- モデルバリデータ: `consumption_tax_method == "simplified"` のとき
  `simplified_business_type` が NULL ならエラー（確定値として書けない）。
- モデルバリデータ: `taxpayer_status == "exempt"` のとき
  `consumption_tax_method` が非NULLならエラー（免税事業者に申告方法はない）。

### 3.3 CLI

`shinkoku ledger` に2サブコマンドを追加する。

1. `fiscal-year-show --db-path DB --fiscal-year YEAR`
   - 該当年度の3属性を含むJSONを返す。年度が存在しなければ `status: error`。
2. `fiscal-year-update --db-path DB --fiscal-year YEAR --input profile.json`
   - `FiscalYearTaxProfile` 形式のJSONを受け取り、検証後に更新する。
   - 部分更新とする: JSONに含まれないキーは変更しない。
     値を明示的にNULLへ戻す場合は `null` を指定する。
   - 更新前後の値をJSONで返す。

### 3.4 calc-consumption の整合検証

`shinkoku tax calc-consumption` にオプショナル引数 `--db-path` を追加する。

- 指定された場合: DBの `consumption_tax_method` と入力JSONの `method` を照合する。
  - DB側がNULL: 検証をスキップし、結果JSONに
    `method_verified: false`（理由: 未確定）を含める。
  - 一致: `method_verified: true` を含める。
  - 不一致: `status: error` とし、両方の値をメッセージに含めて計算を行わない。
  - `method == "simplified"` の場合、`simplified_business_type` も同様に照合する。
- 指定されない場合: 従来どおり計算し、`method_verified` キーは出力しない
  （後方互換。既存テストを壊さない）。
- **Why not 必須引数化**: 純粋計算としての現行利用（試算・複数方法の比較）を
  維持する。方法比較の試算では意図的にDBと異なる method を渡すため、
  検証は opt-in とする。

### 3.5 簡易課税事業区分の黙示補完の廃止（独立発見3の修正）

`src/shinkoku/tools/tax_calc.py` の `input_data.simplified_business_type or 5` を廃止する。

- `ConsumptionTaxInput` にモデルバリデータを追加:
  `method == "simplified"` かつ `simplified_business_type is None` は検証エラー。
- 計算関数側の `or 5` を削除し、simplified 経路では非NULLを前提とする。
- **Why not 本修正の別Fix化**: 3.4の照合仕様が「simplifiedなら事業区分も照合」を
  含むため、黙示補完が残ると照合結果と計算実態が食い違う。同時に閉じる必要がある。
- **互換性への注意**: これまで事業区分未指定のsimplified入力は第5種として
  計算されていた。この入力は今後エラーになる（意図した非互換）。
  既存テストに未指定simplifiedのケースがあれば、事業区分を明示する形へ修正し、
  その旨を報告書に記載する。

### 3.6 スキルの更新

1. `skills/assess/SKILL.md`:
   - 課税事業者判定の確定後、ユーザー確認のうえ `fiscal-year-update` で
     `taxpayer_status` を書き込む手順を追加する。
   - 申告方法はこの時点では書き込まない（適用可能な方法の提示まで。決定2）。
2. `skills/consumption-tax/SKILL.md`:
   - 冒頭の前提確認で `fiscal-year-show` を実行し、DB値があれば引継書より優先する。
   - ユーザーが申告方法を最終決定した時点で `fiscal-year-update` により
     `consumption_tax_method`（simplifiedの場合は事業区分も）を書き込む。
   - `calc-consumption` は `--db-path` 付きで呼ぶ手順に変更する。
   - 書き込み→計算の順とし、照合が必ず通る流れにする。

## 4. 実装前調査（実装着手前に報告すること）

1. `fiscal_years` への書き込み経路が `ledger init` 以外に存在するか
   （存在する場合、新カラムとの干渉有無）。
2. `_migrate` の現行実装が、追加済みカラムの再実行時に冪等であること。
3. 既存テストのうち、`calc-consumption` のCLI呼び出しと simplified 未指定入力に
   依存するものの一覧。
4. 上記で本指示書の仕様と矛盾が見つかった場合は、実装せず報告する。

## 5. テスト仕様

1. **マイグレーション**: 旧スキーマ（3カラムなし）のDBファイルに対して接続後、
   3カラムが追加され既存データが保持されること。再接続しても冪等であること。
2. **fiscal-year-update / show**: 正常系の書込・読出。部分更新でその他キーが
   不変であること。明示NULLで値が消えること。
3. **モデル検証**: 不正値（`taxpayer_status: "unknown"`、`method: "special_30pct"`、
   `simplified_business_type: 0` / `7`）がPydantic層で拒否されること。
   DBに直接INSERTした不正値はエラーにならないこと（決定3の確認。
   読出し時のモデル検証でエラーになる場合はその挙動を報告する）。
4. **exempt整合**: `taxpayer_status: "exempt"` と `consumption_tax_method` 非NULLの
   同時指定が拒否されること。
5. **照合**: `--db-path` あり×（DB NULL / 一致 / 不一致）×（standard / simplified）の
   組み合わせ。simplified一致時の事業区分不一致がエラーになること。
6. **後方互換**: `--db-path` なしの `calc-consumption` が従来と同一の結果JSONを
   返すこと（`method_verified` キーが存在しないこと）。
7. **黙示補完の廃止**: simplified＋事業区分未指定の入力が検証エラーになること。
   事業区分明示時の計算結果が従来と一致すること。

## 6. 完了条件

1. 3.1〜3.6 のすべてが実装され、5. のテストがすべて通ること。
2. 既存テストが全件通ること（3.5の意図した非互換による修正は報告書に列挙）。
3. `git status` がクリーンであること（コミット対象の変更のみが差分であること）。
4. 実装報告書に、変更ファイル一覧・テスト結果・3.5の互換性影響を記載すること。

## 7. 本指示書の範囲外（別Fix・別issue）

- インボイス属性（取引先登録番号・請求書区分・控除割合）の仕訳への追加
- 本則課税の経過措置控除率（日付駆動テーブル・1億円上限）= fix-12（fix-09 第6節の申し送り3）として指示書化予定
- 弥生会計向けエクスポート
- `journal_lines.tax_category` の検証層整理（独立発見1）
- 科目マスタと仕訳明細の税区分語彙の統一（独立発見2）
- `invoice_registration_number` の形式検証（`T` + 13桁）
