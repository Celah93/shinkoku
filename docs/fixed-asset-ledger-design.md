# 固定資産台帳と年度繰越の設計

作成日：2026-09-16。起点は `9a3aa44`（`codex/fix-setup-confirmation-roundtrip`）。初回案への承認と簡素化の指示を反映した。本書は段階1から順に実装する設計であり、将来のコマンドを実装済みとは扱わない。

実装状況：0.19.0で段階1のモデル・移行・CRUDを、0.20.0で段階2の共通詳細計算を、0.21.0で段階3の読取り専用CLI・転記項目・仕訳候補を提供する。段階4以後は未実装である。

このforkの独自機能として設計する。fork元への還流やスキーマ互換性は前提にしない。このforkの既存DBは移行し、追加列は初期値を `NULL=未確認` とする。

## 1. 承認された方針

- 初版の自動計算は、既存の定額法関数が対象とする取得時期の、100％事業用・直接法の有形資産に限定する。
- 台帳の保存、計算候補の取得、仕訳の確定を分ける。確定・取消は独立した`fa-post`・`fa-unpost`で行う。
- 訂正は逆仕訳と再確定によって行う。確定済みの年度行は直接上書きしない。
- 後続は、共用資産、少額特例の年度枠、一括償却、定率法・処分の順とする。
- 税率・端数処理・耐用年数の正本は既存の`tax_constants`と計算関数である。台帳やSkillに別の数値表を持たせない。

初版にはrevision、expected_revision、計算ID、入力のダイジェスト、再送を成功扱いする冪等判定、`BEGIN IMMEDIATE`、台帳監査テーブルを設けない。二重計上は資産UIDと年度に対する有効な確定記録の部分一意インデックスで防ぎ、確定済みの要求は常に`FA_ALREADY_POSTED`で止める。明示的な書込みトランザクションと、その失敗時のロールバックは維持する。

## 2. 現状と段階1の境界

起点の[schema.sql](../src/shinkoku/schema.sql)には`fixed_assets`があったが、固定資産のCRUD CLIはなかった。0.19.0でCRUDを追加する。[calc-depreciation](../src/shinkoku/cli/tax_calc.py)は引き続きDBへ保存しない。既存の償却関数は必要経費額を計算するが、前年の累計、残存簿価による制限、登録した仕訳との対応は管理しない。

段階1は、モデル、NULLを維持する旧DBの移行、資産UID、`fa-add`・`fa-list`・`fa-update`・`fa-delete`だけを提供する。計算、仕訳登録、確定、取消、翌期繰越、監査履歴は実装しない。既存の償却計算関数と、そのテストの期待値を変更しない。

段階1では`fixed_assets`とそのインデックスを整備する。初版の補助テーブルは最終的に`fixed_asset_postings`と`fixed_asset_posting_journals`の2本とし、確定処理を作る段階4で追加する。未使用の補助テーブルを段階1に先行追加しない。

## 3. 対象外と確認待ち

共用資産、年途中の割合変更、定率法、一括償却、少額特例の年度枠、除却・売却の自動処理は後続段階で扱う。既存の`method`や処理区分にこれらの値を保存できることと、自動計算に対応していることを区別する。対象外や情報不足を、計算済み0円として返さない。

法人、リース資産、資本的支出と修繕費の区分判定、資産の分割・統合、部分売却、買換え・圧縮記帳、割増・特別償却、相続・贈与、非業務用からの転用、中古資産の耐用年数の自動判定、製造原価への配賦、不動産所得用の決算書は初版の対象外とする。土地は償却しない。無形資産に有形資産の備忘価額を当てはめない。

## 4. データモデル

### 4.1 年度別の資産行

`fixed_assets.id`は年度行のID、`asset_uid`は現物を年をまたいで識別するIDである。名称・日付・金額の一致による名寄せはしない。新規登録にはUUIDを発行し、同名・同額の別資産を扱えるようにする。UIDは通常の更新JSONから変更できない。

既存の`name`、`acquisition_date`、`acquisition_cost`、`fiscal_year`、`memo`を維持する。日付は検証済みのISO文字列、金額は円整数とする。`method`、`useful_life`、`business_use_ratio`、`accumulated_depreciation`はNULLを許し、新規行へ定額法・割合100・累計0を暗黙に入れない。割合は確認済み0を保存可能にするが、0の資産を自動計算できるという意味にはしない。

| 段階1で追加する列 | 型と意味 |
|---|---|
| `asset_uid` | `TEXT NULL`。新規登録時に生成する。旧行は最初の明示的な更新時に採番するが、税務上の確認済みとは扱わない |
| `previous_asset_id` | `INTEGER NULL`。前年行への自己外部キー。段階1では読取り専用で、段階5の繰越が設定する |
| `origin` | `TEXT NULL`。`acquired_this_year / verified_opening / rollover`。段階1の入力は前2種だけとする |
| `placed_in_service_date` | `TEXT NULL`。取得日と区別した供用開始日 |
| `asset_class` | `TEXT NULL`。`tangible / intangible / non_depreciable` |
| `asset_account_code` | `TEXT NULL`。`accounts.code`への外部キー。固定資産の資産科目を明示する |
| `quantity`、`quantity_unit` | `TEXT NULL`。数量・面積は正の10進文字列とし、金額に再乗算しない |
| `treatment` | `TEXT NULL`。既存の`SmallAssetTreatment`と同じ処理区分。通常償却の`method`とは別概念である |
| `opening_accumulated_depreciation` | `INTEGER NULL`。確認済みの期首累計。事業割合を掛ける前の額である |
| `basis_confirmed_at` | `TEXT NULL`。取得情報・期首額・計上方法の確認日時 |
| `book_basis` | `TEXT NULL`。`full_cost_direct / business_portion_direct / indirect` |
| `prior_private_use` | `INTEGER NULL`。未確認・私用なし・私用ありを区別する |
| `additional_depreciation_applicable` | `INTEGER NULL`。割増・特別償却について未確認・不適用・適用を区別する |
| `annual_facts_confirmed_at` | `TEXT NULL`。当年の割合・使用状況・処分がないこと等を確認した日時 |
| `evidence_ref` | `TEXT NULL`。証憑や前年明細へのローカル参照 |

追加列はすべて、旧DBの移行直後にはNULLにする。技術上の識別子も移行時には採番しない。`UNIQUE(asset_uid, fiscal_year)`をNULL以外のUIDに適用し、自己外部キーの削除はRESTRICTとする。

`basis_confirmed`と`annual_facts_confirmed`は入力用の任意の真偽値である。trueならサーバーが日時を保存し、falseまたは明示的なnullなら確認を取り消す。更新で省略すれば維持する。これは確認操作の指定であり、`prior_private_use`等の事実値とは異なる。後者のfalseとNULLは保存・読戻しでも区別する。

### 4.2 累計額の意味

- 新規の未確定行では`accumulated_depreciation`をNULLとし、確認済みの期首額は別列に保存する。
- 段階4以後は、有効な確定記録がある場合だけ当年末累計として扱う。「期首累計＋当年の割合適用前の償却額」で置き換え、現在値へ反復加算しない。
- 旧行の既存累計はDB内で変更せず保持する。ただし意味を推測しない。段階1の出力では`legacy_values.accumulated_depreciation`へ示し、計算用の`accumulated_depreciation`はNULLとする。
- 段階1の入力で当年末累計を任意に設定することはできない。旧値を期首額へ利用する場合は、ユーザーが前年資料と照合して`opening_accumulated_depreciation`へ明示する。
- 通常償却の全体額と必要経費額を混同しない。共用資産への拡張で、必要経費額だけを累計へ足す設計にはしない。

### 4.3 段階4の補助テーブルと制約

| テーブル | 役割 |
|---|---|
| `fixed_asset_postings` | 年度行ID、資産UID、年分、入力事実と計算結果のJSON、償却額・必要経費額・期末額、確定日時、状態を保持する。取消後も履歴を残す |
| `fixed_asset_posting_journals` | 確定記録ID、仕訳ID、役割（償却・取消）を保持する。仕訳内容のダイジェストは持たない |

`fixed_asset_postings`には、状態が有効な記録だけに`UNIQUE(asset_uid, fiscal_year)`を適用する部分一意インデックスを設ける。同じ要求の再送も成功扱いせず、`FA_ALREADY_POSTED`とする。関連仕訳のFKは履歴を消すCASCADEにしない。

割合履歴、少額資産の要件、一括単位、定率法の保証・改定、処分価額等の列・テーブルは、それぞれの後続機能で追加する。台帳専用の`audit_log`は必要性が生じた時点で設計する。既存の一般仕訳の訂正履歴は維持する。

## 5. CLIとJSON契約

年度とDBパスは既存のledgerと同じフラグに置く。入力は平坦なJSONとし、`{fiscal_year, detail: {...}}`のラッパーを使わない。未知キー、数値文字列、金額に対するbool、不正な日付や列挙値を拒否する。

| 段階1のコマンド | 契約 |
|---|---|
| `fa-add` | `--db-path DB --fiscal-year YEAR --input asset.json`。`FixedAssetInput`から新規UID付きの年度行を作る。仕訳は作らない |
| `fa-list` | `--db-path DB --fiscal-year YEAR [--input filter.json]`。`FixedAssetListInput`で`asset_id`または`asset_uid`を任意指定できる。省略時は対象年度の全件 |
| `fa-update` | `--db-path DB --fiscal-year YEAR --asset-id ID --input patch.json`。`FixedAssetUpdateInput`による部分更新。省略は維持、NULLは許容する欄だけを未確認へ戻す |
| `fa-delete` | `--db-path DB --fiscal-year YEAR --input delete.json`。`FixedAssetDeleteInput`で`asset_id`を指定する。別年度の同じIDを削除しない |

一覧のフィルターと削除対象も入力モデルを持たせ、4コマンドのJSON例を既存のSkill契約テストで自動検査できるようにする。確認用のダミーのboolや、不要なJSONラッパーは設けない。

成功は`status: "ok"`を返す。追加・更新は`asset`、一覧は`fiscal_year`・`assets`・`count`、削除は`deleted_id`を持つ。各資産には基本情報、追加した確認情報、`missing_fields`、段階1で年次計算が未提供であることを示す状態を含める。

段階3以後のCRUD出力の`calculation_available`はtrueで、計算コマンドの提供を示す能力フラグである。個々の資産の計算可能性は、このフラグではなく次の診断で確認する。

### 段階3の読取り専用CLI

`shinkoku ledger fa-depreciation --db-path DB --fiscal-year YEAR`は年度の全資産を診断する。任意の`--input selection.json`で対象の年度行IDを指定できる。

```json
{"asset_ids": [1]}
```

`FixedAssetCalculationInput`は省略または空のオブジェクトを全件として扱う。asset_idsの空配列・null・重複・正の整数以外の値・未知キーを拒否する。全件はID順、指定時は入力順に返す。指定IDが対象年度にない場合も行を省略せず、FA_NOT_FOUNDのblocked行にする。

出力は`status`、`fiscal_year`、`assets`、`count`、`complete`、`total_expense`、`calculable_subtotal`を持つ。各行の状態はready・no_depreciation・blockedの3つだけとし、already_postedは段階4で追加する。

- readyでは`calculation`に段階2の詳細、`statement_fields`に決算書用の項目、`journal_candidate`に年末の借方5200／貸方の資産科目を返す。sourceはadjustment、is_adjustmentはtrue、税区分はout_of_scopeである。
- no_depreciationでは確認済みの額0と転記項目を返し、仕訳候補はNULLにする。0円のJournalLineは作らない。
- blockedでは計算額・計算結果・転記項目・仕訳候補をNULLにし、`missing_fields`と`error_code`・`blocking_reason`を返す。不足情報はFA_INPUT_UNCONFIRMED、その他の段階2の拒否はFA_CALCULATION_BLOCKEDとする。

1行でもblockedならcomplete=false・total_expense=nullにし、計算できた行の合計だけをcalculable_subtotalへ返す。診断の取得自体は成功なのでexit 0である。入力不正、DB未存在・未移行、年度未作成、DBの操作エラーは従来のエラーJSONとexit 1とする。資産0件では空のassets・count=0・complete=true・合計0となり、未確認行がある場合とは区別する。

実装は`ledger_preview_fixed_asset_depreciation`から段階2の`ledger_calculate_fixed_asset_depreciation`を呼ぶ。後者へ共有の読み取り接続を渡し、同じスナップショットから入力事実と計算結果を取得する。query_onlyを有効にした通常の読取りトランザクションを使い、台帳・仕訳・確認状態・累計を保存しない。率・丸め・終端を再実装せず、転記項目は検証済みの結果を写す。

blockedの条件は、段階2が必要とする事実や確認日時の不足、通常償却以外、対応外の資産科目・資産区分・計上方式、定率法、100％以外の割合、私用からの転用、追加償却の適用、旧定額法の取得時期、日付・年分・期首累計の不整合、指定IDの年度不一致・不存在である。readyは未計上の保証ではない。手動で償却済みでも同じ候補を返し得るので、登録前に既存仕訳と照合する。

失敗は既存と同じstdoutのJSONとexit 1で返す。`status`と`message`を維持し、必要に応じて`code`・`asset_id`を付加する。列挙値のエラーには許容値を含める。存在しないDB・未移行のDBは勝手に作成・移行せず、初期化の操作を案内する。

### 入力例

`fa-add`に渡す、太郎の架空PCの登録例：

```json
{
  "name": "検証用PC",
  "acquisition_date": "2026-04-01",
  "placed_in_service_date": "2026-04-01",
  "acquisition_cost": 250000,
  "quantity": "1",
  "quantity_unit": "台",
  "asset_class": "tangible",
  "asset_account_code": "1130",
  "treatment": "normal_depreciation",
  "method": "straight_line",
  "useful_life": 4,
  "business_use_ratio": 100,
  "opening_accumulated_depreciation": 0,
  "origin": "acquired_this_year",
  "book_basis": "full_cost_direct",
  "prior_private_use": false,
  "additional_depreciation_applicable": false,
  "basis_confirmed": true,
  "annual_facts_confirmed": true,
  "evidence_ref": "tests/fixtures/scenarios/taro/evidence.json#pc",
  "memo": "凍結済みの架空PC"
}
```

`fa-list`のフィルターと`fa-delete`の対象はそれぞれ次の形である。

```json
{"asset_id": 1}
```

`fa-update`の例：

```json
{"memo": "証憑と照合済み", "annual_facts_confirmed": null}
```

税務上の確認が未完了でも基本情報だけで登録できる。確認日時は条件不足を無視する許可にはせず、後段階の計算は必要な事実も検証する。取得日と供用日、取得価額と期首累計の矛盾は登録・更新時に拒否する。

### 後続コマンド

`fa-depreciation`は読取り専用で、対象年の入力事実・詳細計算結果・転記項目・仕訳候補を返す。`fa-post`はその結果を入力として受け取り、DBから再計算した結果と構造化された値を比較する。計算IDやダイジェストは作らない。更新後に一致しない候補は`FA_CALCULATION_MISMATCH`で拒否する。

`fa-unpost`は確定記録IDと取消理由を受け取り、確認後に逆仕訳を作る。`fa-rollover`は前年と翌年を指定し、通常は候補、明示的な適用で翌年行を生成する。これらは段階1ではCLIに登録しない。

## 6. 計算の共通化

### 段階2で追加する終端処理の根拠（2026-09-16確認）

実装に先立ち、以下を年次計算の根拠として確定する。従来の単発計算の率・丸め・金額は変えない。

| 根拠URL | 段階2で適用する内容 |
|---|---|
| [国税庁 No.2106・概要と限度額](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm) | 平成19年4月1日以後取得の有形減価償却資産（坑道を除く）は取得価額から1円を除いた額まで償却する。坑道・無形資産の扱いを流用しない |
| [一般用決算書の書き方・4頁](https://www.nta.go.jp/taxes/shiraberu/shinkoku/tebiki/2025/pdf/037.pdf) | 月の途中でもその月を償却期間へ含める。普通償却費と事業割合適用後の額を分け、前年末残高から当年の償却額を引いて期末残高を求める |
| [作成コーナー・前年末未償却残高](https://www.keisan.nta.go.jp/r7yokuaru_sp/aoiroshinkoku/hitsuyokeihi/genkashokyakuhi/scid1731.html) | 期首の基礎は取得価額から前年末までの累計を引いた額である。前年の決算書の未償却残高を引き継ぐ |

2025年分の手引きは継続する算式・欄の意味の根拠であり、2026年分の最終画面を確認したものではない。年次計算の初版は、定額法・100％事業用・直接法の通常の有形資産（坑道を除く）に限る。処分、私用からの転用、割増・特別償却は適用しないことが確認済みでなければ計算しない。

取得時期の下限と備忘価額を`tax_constants`へ置く。期首簿価から備忘価額を除いた残額を当年の上限とし、上限に達した年だけ償却額を制限する。期首簿価がすでに備忘価額なら当年額は0、期末簿価はそのままとする。取得価額以上の期首累計や、当年に初めて供用した資産に正の期首累計がある場合は補正せず拒否する。

`annual_context`は年分、取得日、供用日、期首累計、資産区分、計上方式、私用・追加償却の不適用、確認済みの事実を明示する。供用が翌年なら当年の月数と償却額は0であり、明示された月数と異なれば拒否する。年次文脈がない従来入力では備忘価額の制約を新たに掛けず、詳細の期末簿価はNULLにする。

詳細には通常計算の額と制限後の普通償却費を分けて残す。制約を評価したことと、実際に額が減ったことも別の真偽値で返す。定率法の単発詳細は従来の一段階の切捨てを保持し、表示用の普通額に改めて割合を掛けて従来額を変えない。年次の定率法は保証・改定が未実装なので拒否する。

段階2の台帳経由の計算は、読取り専用の内部関数として提供し、段階3の`fa-depreciation`も同じ関数を使用する。少額資産の詳細は各候補の適格性と計算内訳を返すが、年次文脈による一括償却等の継続計算は行わない。

実装は`tools/depreciation.py`の`calculate_depreciation_details`と`depreciation_months`を正本とする。台帳の入口は`ledger_calculate_fixed_asset_depreciation`で、通常の有形資産科目（1100・1101・1110・1120・1130）の確認済み記録を読む。段階3の計算コマンド提供に合わせ、`calculation_available`はtrueとなる。

通常の詳細出力は`ordinary_amount`、`expense_amount`、`depreciation_basis`、`rate_numerator`・`rate_denominator`、`months`、`unconstrained_ordinary_amount`、`memo_value_constraint_applied`、`capped_to_book_value`、`opening_book_value`・`closing_book_value`を含む。少額資産の`--details`は従来の結果を`selection`、計算可能な候補の内訳を`calculations`へ分ける。既存の`remaining_balance`は従来の候補値として維持し、確認済みの年次簿価へ昇格させない。

### 共通層の構成

[既存の計算関数](../src/shinkoku/tools/tax_calc.py)から、DBアクセスを持たない詳細計算層を整理する。単発CLIと台帳は同じ関数を使い、普通償却費、必要経費額、基礎額、率、月数、残高の制限を返す。既存の金額を返す関数は、その詳細から必要な額を返すラッパーにする。

供用期間から月数を求める処理も共通層へ置く。月数の明示入力と日付に矛盾があれば拒否する。供用前などの確認済み0期間は、`months=0`を既存モデルへ無理に渡さず、計算不要という状態として扱う。

`calc-depreciation`の従来入力・出力・金額は維持し、詳細出力と年次の文脈は明示的なオプションで提供する。年次の文脈なしで期末簿価や償却完了まで確認済みとは表示しない。

有形の通常償却では備忘価額1円を残す終端処理が必要である。現行関数は残存簿価による制限を実装していないため、単に台帳側で別計算を足さず、根拠と独立したテストを用意して共通層へ追加する。備忘価額の扱いを一括償却や即時必要経費へ流用しない。[一般用決算書の書き方・4頁](https://www.nta.go.jp/taxes/shiraberu/shinkoku/tebiki/2025/pdf/037.pdf)

一括償却では個別の適格性と、一括した単位での計算・端数配賦・最終年の残額を分ける。処分後の配分継続は通常資産の停止処理から分離する。[所得税基本通達49－40の2](https://www.nta.go.jp/law/tsutatsu/kihon/shotoku/08/12.htm) 定率法の保証・改定への移行、割合変更の按分、少額特例の共有枠も、各後続段階で共通層の契約を確定してから解禁する。

## 7. 確定・取消と帳簿の境界

`台帳の登録 → 読取り専用の計算 → ユーザー確認 → 仕訳と台帳の確定 → 翌年行の生成`

段階4の`fa-post`は、通常のトランザクション内で次を行う。

1. 資産UIDと年分の有効な確定記録を調べ、存在すれば`FA_ALREADY_POSTED`で止める。同じ要求の再送も例外にしない。
2. DBに保存された事実から再計算し、提示済みの入力事実・結果・仕訳候補と一致することを確認する。
3. 既存の仕訳検証と重複検出を通して登録する。または`link_existing`で指定された手動仕訳の年度・日付・科目・全明細を照合して関連付ける。
4. 確定記録、仕訳参照、当年末累計を同時に保存する。途中失敗は全体をロールバックする。一意制約違反も`FA_ALREADY_POSTED`へ変換する。

既存の接続を開いてcommitする関数を順に呼ぶだけでは原子性を満たさない。接続を受け取る内部処理を整理し、既存の仕訳検証を再利用する。初版では`BEGIN IMMEDIATE`や独自のロック再試行を加えず、SQLiteの競合はエラーとして返す。

100％事業用・直接法の候補は、借方`5200`／貸方の資産科目、`source=adjustment`、`is_adjustment=true`、税区分`out_of_scope`とする。取得時の消費税を再計上しない。0円の仕訳行は作らない。

同日同額の別資産は原簿で別取引と確認した場合だけforce登録できる。取消済みの元仕訳と逆仕訳を確認した再確定も同様である。forceでも有効な確定記録の一意制約を迂回できない。既存の重複ハッシュは変更しない。

台帳に関連付いた仕訳への`journal-update`・`journal-delete`は、「先にfa-unpostが必要」というエラーで止める。ダイジェストによる失効検出は行わない。直接SQLによる改変や、未関連の一般仕訳の帰属を完全に検出する保証は初版に含めない。Skillでは台帳・PL・BS・関連仕訳の照合を継続する。

`fa-unpost`は確認済みの逆仕訳を登録し、有効な確定を取り消す。元の仕訳と確定記録は残す。以後の再確定は新しい確定記録を作る。後続年度に行がある場合は、まず新しい年度から未確定の繰越行を削除するか、確定を取り消して整理する必要がある。初版では後続行の自動失効・再マージを設けない。

段階4で、確定履歴のある年度行の直接更新・削除を拒否する保護をCRUDへ追加する。取消後も確定履歴を消す削除は許可しない。段階1には確定処理がないため、この保護は将来のテーブル追加と一緒に実装する。

## 8. 翌期繰越

段階5の`fa-rollover`は、前年の有効な確定結果から翌年の未確定行を生成する。年は連続する場合だけを受け付ける。UIDと取得情報・選択済み処理を引き継ぎ、前年末累計を翌年の期首累計へ入れる。当年末累計や償却仕訳はコピーしない。

当年の割合・使用状況等の確認日時はNULLへ戻す。前年値は参考として示せるが、翌年も確認済みとは扱わない。前年の訂正は後続行を先に整理してから行うので、版照合や失効状態の連鎖は設けない。

同じUID・同じ翌年の行が存在する場合は、内容の自動マージや成功扱いをせず、`FA_ROLLOVER_CONFLICT`で止める。年度行の一意制約で二重生成を防ぐ。複数資産の適用は全件成功か全件ロールバックとする。

台帳の繰越と、BSの期首残高・元入金の繰越は別操作とする。科目別残高を照合し、期首残高候補を示すことはできるが、自動で`ob-set-batch`を実行しない。保有している償却済み資産は台帳に残す。処分等を含む繰越は後続機能で扱う。

## 9. 旧DBの移行

移行は既存の`init_db()`／`_migrate()`の経路を使う。FAの読取りやCRUDが勝手に移行しない。接続は`get_connection()`を使い、WALと外部キーを保つ。

1. 旧テーブルの形を検出する。既存のID、全既存列、AUTOINCREMENTの採番上限を保持する。
2. SAVEPOINT内で新しい定義の作業テーブルを作り、列を明示して旧値をコピーする。新規列は指定せずNULLのままにする。
3. コピー件数・値を確認し、旧テーブルを置き換え、インデックスを作る。外部キーを無効化しない。失敗したらDDLとデータをSAVEPOINTの前へ戻す。
4. UIDと年度の一意性、外部キー、採番、元の値を確認する。再移行では何も増やさない。移行中断後も旧テーブルから安全に再実行できることをテストする。
5. 取得日を供用日へ、旧累計を期首累計へコピーしない。旧デフォルト値を確認済みの事実へ昇格させない。

`init_db()`は通常のBEGINで移行全体を囲み、FAのSAVEPOINTを内側に置く。後続の移行で中断した場合も固定資産の置換をロールバックし、接続を閉じる。これは一連の移行を原子的にするための処理であり、BEGIN IMMEDIATEによる競合制御ではない。

許容できない旧値がある場合は、黙って補正せず移行をロールバックする。旧データを捨てて先へ進まない。段階1では旧行の一覧と明示的な補完更新を提供し、前年との自動名寄せや繰越は行わない。

## 10. Skillと決算書への反映

段階1のsettlementにはCRUDのJSON例と、「台帳保存だけでは償却・仕訳・繰越は行われない」という境界を追加する。4例ともハンドラーから導出した入力モデルでstrict検証する。

段階6では、台帳と前年資料の照合、事実の補完、候補の取得、ユーザー確認、fa-post、PL・BSとの照合という順序へ変更する。承認済みの同じ内容について再承認は求めない。手動で償却済みなら追加記帳せず、照合して関連付ける。

e-taxには次の一覧を加える。欄の構成は[国税庁・一般用決算書の書き方](https://www.nta.go.jp/taxes/shiraberu/shinkoku/tebiki/2025/pdf/037.pdf)を参照するが、当年の画面・セレクタは別に確認する。

| 転記情報 | 入力・結果の対応 |
|---|---|
| 名称、数量・面積、単位 | 台帳のname・quantity・quantity_unit |
| 取得年月、供用日、取得価額 | acquisition_date・placed_in_service_date・acquisition_cost |
| 償却の基礎額、方式、耐用年数、率 | 共通計算の詳細結果。新たな率表を作らない |
| 償却期間、普通償却費、割増等、合計 | 共通計算の途中欄。割増等の未確認を0で埋めない |
| 事業割合、必要経費額 | 通常の償却額と区別したexpense_amount |
| 期末の未償却残高、摘要 | 確定残高、確認済みの制度・状態 |
| 画面外の照合情報 | UID、年度行ID、確定記録、仕訳ID。税務署向けの欄へ入力しない |

定率法の保証額・改定取得価額や処分情報は、その機能を実装する段階で追加する。転記の必要経費合計をPL、残高を計上方法に応じたBSと照合する。台帳の実装だけでPDF生成に対応したとは案内しない。

## 11. テスト計画

### 既存テストとの分担

- [test_depreciation.py](../tests/unit/test_depreciation.py)は率との対応、月数按分、丸め位置を保証する。段階1では変更しない。
- [test_small_asset_treatment.py](../tests/unit/test_small_asset_treatment.py)は選択・適格性・金額と年度枠の境界を保証する。段階1では変更しない。
- 新しい固定資産の単体テストは、CRUD、型、NULL、年度の分離、更新での省略とNULL、UIDの一意性を担当する。
- 移行テストは、非空の旧DB、複数年度、旧デフォルト値、再移行、移行中断、全旧値とID・採番上限の保持、WAL・FKを必須にする。
- CLIテストは実際のJSON・exit code、対象外のキー、数値文字列、日付、別年度ID、DBを作らないエラーを検証する。
- [Skill契約テスト](../tests/unit/test_skill_cli_contract.py)はFAの4入力モデルを自動導出し、4例の存在とstrict検証を確認する。CLIスナップショットと件数を意図した契約変更として更新する。

### 後続段階の必須境界

取得年と供用年の違い、年末・年始・月末・うるう日、供用前の期間、NULLと0、累計が取得価額を超える場合、最終償却年、備忘価額だけの翌年を検証する。確定済みの再要求、候補取得後の更新、同日同額の別資産、forceでも同一資産の二重確定を拒否すること、途中失敗のロールバック、手動仕訳との関連付け、汎用APIによる更新・削除の拒否、逆仕訳と再確定も検証する。

繰越は年度飛ばし、前年未確定、翌年行の重複、既存行との衝突、後続年度がある場合の取消拒否、台帳繰越だけで期首残高を変えないことを確認する。revisionやダイジェスト、再送成功のテストは初版に追加しない。

### 太郎の結合テスト

段階3では、PCのfa-addとfa-depreciationによる照合だけを既存の経路へ追加する。候補の日付・借貸・科目・金額・税区分を凍結済みの決算仕訳と比較し、46,875円で一致すること、候補取得でDBの論理内容が変わらないことを確認する。既存49項目と凍結済みの仕訳をjournal-batch-addで登録する経路は維持する。

段階6で、[既存の結合テスト](../tests/integration/test_frozen_filing_scenarios.py)へ台帳を組み込む。日常仕訳160件を保持し、PCを台帳へ登録する。台帳保存だけではPL・BS・仕訳件数が変わらないことを確認する。

凍結済みの決算仕訳を先に登録する代わりに、台帳から候補を作って凍結値と照合し、fa-postで登録する。償却額46,875円、期末簿価203,125円、全161仕訳、既存49項目を維持する。二郎の45項目とR6・R7も保持する。[太郎の独立期待値](../tests/fixtures/scenarios/taro/expected.md)

同じ確定要求がFA_ALREADY_POSTEDとなり、件数・累計・PLが変わらないことを確認する。翌年行の生成、当年事実の確認、期首残高の別登録、翌年の計算をつなぐ。新しい年の期待値は出典付きの手計算で凍結し、関数の出力から作らない。元のplaygroundは変更しない。

## 12. 実装順序

| 段階 | 範囲 | 必須の検査 |
|---|---|---|
| 1 | モデル、NULL移行、UID、CRUD、settlementの4例 | 非空旧DBと中断・再移行、全旧値・IDの保持、型・NULL・年度の単体/CLI、契約、既存償却テスト |
| 2 | 共通詳細計算、単発計算との共有、年次文脈・終端 | 既存2計算テスト、従来CLI契約、期間・残存簿価・丸めの独立期待値 |
| 3 | fa-depreciation、不足情報、転記と候補 | DB無変更、NULL・0、部分計算と全体額、太郎の候補一致 |
| 4 | 2補助テーブル、fa-post/unpost、関連仕訳の保護 | 有効確定の一意性、再要求拒否、再計算一致、原子性、force、取消・再確定、一般仕訳の回帰 |
| 5 | 翌期繰越、後続行がある場合の訂正制限 | 年度境界、重複拒否、後続年度の整理、期首残高を勝手に変更しないこと |
| 6 | settlement/e-taxの連結、太郎の結合テスト | 太郎49・二郎45項目、R6/R7、年度連結、全体test/lint、実行時間 |
| 7以後 | 共用資産→少額特例の年度枠→一括償却→定率法・処分 | 各機能の一次資料・独立期待値・境界が揃ってから自動化する |

段階1では監査履歴と確定用テーブルを作らない。段階1〜3だけで年次申告が完了すると案内しない。各段階は[開発規約](development-contracts.md)に従い、実装・Skill変更時の両バージョンファイル更新、CLI契約と所要時間の確認、全体検査を行う。Windowsでは--basetempを作業用ディレクトリへ向け、実DBをテストに使わない。

## 13. 初回案から変更した節

- 第1・3節：承認された初版と後続の順序を確定した。
- 第4節：revision・前年revisionを削除し、補助テーブルを2本へ絞った。割合履歴・制度要件・監査履歴を後続へ移した。初版の不適用確認はNULL許容列へ保存する。
- 第5節：expected_revisionと計算IDを入力から削除した。4つのCRUDに入力モデルと検査可能なJSON例を設け、候補の再計算比較を契約にした。
- 第7節：再送成功、ダイジェスト照合、BEGIN IMMEDIATEを削除した。一意制約とFA_ALREADY_POSTED、関連仕訳の直接変更拒否に置き換えた。
- 第8節：版・失効状態を使う繰越の再マージを削除した。既存行は衝突として止め、訂正は後続年度から整理する。
- 第9節：段階1のSAVEPOINTによる移行とNULL・全旧値の保持を具体化した。
- 第10〜12節：Skillの4例を段階1へ入れ、監査・版・ダイジェストの実装とテストを初版から外した。
- 第13節：判断待ちの論点を、承認済みの変更履歴へ置き換えた。
