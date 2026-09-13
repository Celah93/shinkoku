# e-tax: 所得税の申告内容を入力するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ3: 所得税の申告書入力

> ⚠️ **ネイティブダイアログ注意**: 「次へ」クリック後に画面が遷移しない場合、ネイティブダイアログ（alert/confirm）が表示されている可能性がある。技術的な知見の「ネイティブダイアログの検知と対処」を参照。

### SS-AA-010a: 申告する所得の選択等

URL: `https://www.keisan.nta.go.jp/r7/syotoku/taM010a40_doInitialDisplay#bbctrl`

#### 生年月日

| フィールド | name |
|-----------|------|
| 年 | `inOutDto.shnkkBirthymdYy` |
| 月 | `inOutDto.shnkkBirthymdMm` |
| 日 | `inOutDto.shnkkBirthymdDd` |

#### 所得種類の選択（チェックボックス）

| 所得 | name | 典型的な選択 |
|------|------|-------------|
| 給与 | `inOutDto.kyuy` | 会社員: checked |
| 事業（営業等） | `inOutDto.jgyoEgyoTo` | 個人事業主: checked |
| 事業（農業） | `inOutDto.jgyoNogyo` | |
| 不動産 | `inOutDto.fdosn` | |
| 雑（業務・その他） | `inOutDto.ztsGyomSnt` | 暗号資産等: checked |
| 公的年金等 | `inOutDto.kotkNnknKgyoNnknEtc` | |
| 退職金 | `inOutDto.tasyku` | |
| 株式等 | `inOutDto.hatoKbshkJyotRsh` | |
| 先物取引 | `inOutDto.skmnTrhk` | |
| 一時 | `inOutDto.ichj` | |

**shinkoku 対象の典型パターン**:
- 会社員＋副業（事業所得）: `kyuy` + `jgyoEgyoTo` + `ztsGyomSnt`（暗号資産あれば）
- 給与所得のみ: `kyuy`

### SS-AA-050: 収入・所得の入力ハブ

選択した所得種類ごとに入力リンクが表示される。各リンクをクリックして個別入力画面へ遷移。

### SS-CA-010: 給与所得の源泉徴収票の入力

> **物理的な源泉徴収票との対応**: 年末調整済みと年末調整未済で**別フォーム・別ラベル体系**。
> 年末調整済み = A〜L（12項目）、年末調整未済 = A〜E（5項目）。
> 物理的な源泉徴収票の「給与所得控除後の金額」「所得控除の額の合計額」欄は、
> 年末調整済みフォームでは入力不要だが、年末調整未済フォームでは B(自動)・C(入力) として存在する。

#### 年末調整済みフォーム

URL: `https://www.keisan.nta.go.jp/r7/syotoku/taS510a10_doAdd_nncyzm#bbctrl`

##### 主要入力フィールド

| ラベル | name | 備考 |
|--------|------|------|
| A: 支払金額 | `inOutDto.shhraKngk` | 必須 |
| B: 源泉徴収税額 | `inOutDto.gnsnTyosyuZegk` | 2段記載時は下段 |
| E: 社会保険料等の金額 | `inOutDto.sykaHknryoToKngk` | |
| K: 支払者の住所 | `inOutDto.shhrasyJysyKysyOrSyzach` | 28文字以内 |
| L: 支払者の氏名又は名称 | `inOutDto.shhrasyNameOrMesyo` | 28文字以内 |

##### ラジオボタン（記載有無の選択）

| フィールド | ラベル | name | 値 |
|-----------|--------|------|-----|
| 控除対象配偶者の記載 | C | `inOutDto.kojyTashoHagsyKsaUm` | 1(あり)/2(なし) |
| 控除対象扶養親族の記載 | D | `inOutDto.kojyTashoFyoShnzkKsaUm` | 1(あり)/2(なし) |
| 生命保険料控除額の記載 | F※ | `inOutDto.semeHknryoKojygkKsaUm` | 1(あり)/2(なし) |
| 地震保険料控除額の記載 | G※ | `inOutDto.jshnHknryoKojygkKsaUm` | 1(あり)/2(なし) |
| 住宅借入金等特別控除額の記載 | H※ | `inOutDto.jyutkKrirknToTkbtsKojyGkKsaUm` | 1(あり)/0(なし) |
| 所得金額調整控除額の記載 | I※ | `inOutDto.sytkKngkTyoseKojygkKsaUm` | 1(あり)/0(なし) |
| 本人が障害者・寡婦等 | J※ | `inOutDto.hnninSygsyKfHtriyKnroGkseKsaUm` | 1(あり)/2(なし) |

> ※ F〜J のラベルはフォーム上の並び順からの推定（スクリーンショット未確認）

##### 条件付きフィールド（ラジオ/チェックで「記載あり」選択時に表示）

| ラベル | name | 表示条件 |
|--------|------|----------|
| B': 源泉徴収税額（内書き） | `inOutDto.gnsnTyosyuZegkUchgk` | チェック時 |
| 社会保険料等（内書き） | `inOutDto.sykaHknryoToUchgk` | チェック時 |
| 生命保険料控除額 | `inOutDto.semeHknryoKojygk` | F「記載あり」時 |
| 新生命保険料金額 | `inOutDto.shnSemeHknryoKngk` | F「記載あり」時 |
| 旧生命保険料金額 | `inOutDto.kyuSemeHknryoKngk` | F「記載あり」時 |
| 介護医療保険料金額 | `inOutDto.kagIryoHknryoKngk` | F「記載あり」時 |
| 新個人年金保険料金額 | `inOutDto.shnKjnNnknHknryoKngk` | F「記載あり」時 |
| 旧個人年金保険料金額 | `inOutDto.kyuKjnNnknHknryoKngk` | F「記載あり」時 |
| 地震保険料控除額 | `inOutDto.jshnHknryoKojygk` | G「記載あり」時 |
| 旧長期損害保険料金額 | `inOutDto.kyuCyokSngaHknryoKngk` | G「記載あり」時 |
| H: 住宅借入金等特別控除額 | `inOutDto.jyutkKrirknToTkbtsKojyGk` | H「記載あり」時 |
| H': 住宅借入金等特別控除可能額 | `inOutDto.jyutkKrirknToTkbtsKojyknoGk` | H「記載あり」時 |
| H'': 住宅借入金年末残高1回目 | `inOutDto.jyutkKrirknToNnmtszndkIkkam` | H「記載あり」時 |
| H''': 住宅借入金年末残高2回目 | `inOutDto.jyutkKrirknToNnmtszndkNkam` | チェック時 |
| 寡婦チェック | `inOutDto.ksaArKforkf` | J「記載あり」時 |
| 勤労学生チェック | `inOutDto.ksaArKnroGkse` | J「記載あり」時 |

#### 年末調整未済フォーム

URL: 要確認

##### 入力フィールド

| ラベル | name | 備考 |
|--------|------|------|
| A: 支払金額 | `inOutDto.shhraKngk` | 必須 |
| B: 給与所得控除後の金額 | （自動計算） | 入力不可。A から自動算出 |
| C: 所得控除の額の合計額 | 要確認 | **入力欄あり。源泉徴収票に記載があれば入力** |
| D: 源泉徴収税額 | `inOutDto.gnsnTyosyuZegk` | |
| E: 住宅借入金等特別控除額 | `inOutDto.jyutkKrirknToTkbtsKojyGk` | |

### SS-AA-070a: 控除の入力（1/2）— 支出系控除

入力リンクのハブ画面。各控除をクリックして個別入力画面に遷移。

対応控除:
- 社会保険料控除（源泉徴収票入力済みの場合「入力あり」表示）
- 小規模企業共済等掛金控除（iDeCo等）
- 生命保険料控除
- 地震保険料控除
- 雑損控除・災害減免
- 医療費控除
- 寄附金控除（ふるさと納税含む — ワンストップ特例分も要入力）

#### 寄附金控除・寄附金特別控除の入力確認

寄附金は `calc-income` の確定結果を使う。`calc-deductions` の寄附金項目は方式選択前の中間候補なので転記しない。

- `donation_selection` で公益・NPO・政治の選択方式を確認する
- 所得控除を選んだ寄附は第一表㉙と第二表「寄附金控除に関する事項」へ反映する
- `public_interest_donation_credit`、`npo_donation_credit`、`political_donation_credit` の合計を第一表「政党等寄附金等特別控除（㊱〜㊳欄）」と照合する
- 公益・NPO・政治はそれぞれの計算明細書へ分け、第二表「特例適用条文等」へ順に `措法41の18の3`、`措法41の18の2`、`措法41の18` と記載する
- 明細書の各中間値は `donation_adjustment` から転記し、最終額は公益⑫・NPO⑬・政治⑫と照合する

### SS-AA-080: 控除の入力（2/2）— 人的控除・住宅控除等

対応控除:
- 配偶者（特別）控除
- 扶養控除・特定親族特別控除
- 寡婦・ひとり親控除
- 勤労学生控除
- 障害者控除
- 基礎控除（自動計算表示）
- 住宅借入金等特別控除
- 住宅耐震改修特別控除等
- 予定納税額
- 繰越損失額

### SS-AA-090: 計算結果の確認

入力内容から計算された所得税額の確認画面。

表示項目:
- 収入金額・所得金額（所得種類別）
- 所得控除合計
- 課税される所得金額（1,000円未満切捨て）
- 上記に対する税額（速算表適用）
- 差引所得税額
- 復興特別所得税額（基準所得税額の2.1%）
- 所得税及び復興特別所得税の額
- 源泉徴収税額
- 申告納税額（100円未満切捨て）/ 還付される税金

**ここで shinkoku の計算結果と照合する**（後述「ステップ5: 申告内容の確認」参照）。

各セクションに「訂正する」ボタンがあり、前画面に戻れる。

### SS-AC-010a: 納付方法等の入力

納付金額が発生した場合に表示。還付の場合は還付口座入力画面（SS-AB-010a）が表示される。

| フィールド | type | name | 備考 |
|-----------|------|------|------|
| 延納を届け出る | checkbox | — | 利子税がかかる旨の注意あり |
| 納付方法 | select | `inOutDto.nofHoho` | 必須 |

納付方法の選択肢:

| value | 方法 |
|-------|------|
| 1 | 振替納税（期限内申告の場合に利用可） |
| 2 | 電子納税（ダイレクト納付/インターネットバンキング） |
| 3 | クレジットカード納付 |
| 5 | コンビニ納付 |
| 6 | 金融機関等での窓口納付 |

還付の場合は還付口座情報の入力:
- 金融機関名、支店名、口座番号、口座名義

### SS-AC-020a: 財産債務・住民税等

住民税に関する設定（給与からの特別徴収 or 自分で納付 等）。

### SS-AC-030: 基本情報の入力

| ラベル | name | 備考 |
|--------|------|------|
| 氏名フリガナ（姓） | `inOutDto.nameKnSe` | 11文字以内 |
| 氏名フリガナ（名） | `inOutDto.nameKnMe` | |
| 氏名漢字（姓） | `inOutDto.nameKnjSe` | 10文字以内 |
| 氏名漢字（名） | `inOutDto.nameKnjMe` | |
| 電話番号（種別） | `inOutDto.rnrkSkKbn` | 自宅/勤務先/携帯 |
| 電話番号（市外） | `inOutDto.shgaKykbn` | |
| 電話番号（市内） | `inOutDto.shnaKykbn` | |
| 電話番号（番号） | `inOutDto.knyusyBngo` | |
| 納税地区分 | `inOutDto.nozeCh` | 1=住所地, 2=事業所等 |
| 郵便番号 | `inOutDto.yubnBngoGnzaAddress` | 7桁 |
| 都道府県 | `inOutDto.tdofknGnzaAddress` | select |
| 市区町村 | `inOutDto.shkcyosnGnzaAddress` | 都道府県連動 select |
| 丁目番地等 | `inOutDto.cyomBnchToGnzaAddress` | 28文字以内 |
| 建物名 | `inOutDto.ttmnMeGoshtsGnzaAddress` | 28文字以内 |
| 提出先税務署（県） | `inOutDto.tesytSkZemsyTdofkn` | select |
| 提出先税務署 | `inOutDto.tesytSkZemsyZemsy` | 県連動 select |
| 職業 | `inOutDto.job` | 11文字以内 |
| 屋号・雅号 | `inOutDto.ygoGgo` | 30文字以内 |
| 世帯主の氏名 | `inOutDto.stanshNameKnj` | |
| 続柄 | `inOutDto.stanshKrTsdkgr` | select |
| 提出年月日 | `inOutDto.tesytYmdYy`/`Mm`/`Dd` | |

### SS-AC-040: マイナンバーの入力

マイナンバー（12桁）を入力する画面。チェックディジットアルゴリズムによる検証あり。

---
