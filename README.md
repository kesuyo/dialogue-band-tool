# 帯テキスト一括合成ツール v1.3

セリフなし画像フォルダ + 台本CSV から、セリフあり版を一括生成します。
元の画像は変更しません。セリフのない画像はそのままコピーされる（または `--uniform-height` で空帯を付けて縦横比を揃える）ため、出力フォルダがそのまま「セリフあり版」の完成品になります。
セリフなし版（元のフォルダ）と合わせて、DLsite / FANZA へ「セリフあり本編 + セリフなし差分」として同梱できます。

## 必要なもの
- Python 3 と Pillow（`pip install pillow`）
- 日本語フォント（Windows / macOS / Linux の標準日本語フォントを自動検出します。見つからない場合や好みのフォントを使いたい場合は `--font` などでパスを指定してください）
  - **Linux**: Noto Sans CJK / Noto Serif CJK / IPAゴシック・明朝
  - **Windows**: BIZ UDゴシック・明朝 / 游ゴシック・游明朝 / メイリオ / MSゴシック・明朝
  - **macOS**: ヒラギノ角ゴシック・明朝 / Noto Sans・Serif CJK
- （任意）`budoux`（`pip install budoux`）：入っていれば日本語の文節分割精度をさらに高めます

## 使い方

### GUI で使う（おすすめ）
Windows では [launch_gui.bat](launch_gui.bat) をダブルクリックするだけで起動します（コンソール画面は出ません）。
コマンドラインから直接起動する場合：
```bash
python gui.py
```
左側の4つのタブで設定を調整しながら、右側のライブプレビューで仕上がりを確認できます：
- **基本**: 画像フォルダ・台本CSV・設定JSON・`extend`/`overlay` 切替・全ページ文字サイズ統一・出力形式
- **話者・色**: 話者名デザイン（プレート/左バー/【括弧】/なし）・話者名サイズ・本文との間隔・カラーピッカー（帯色/文字色/話者色）
- **位置・透過**: 帯の上下配置・文字揃え・上下位置・左右余白・行間・透過の濃さ・グラデ幅・端マージン・文字縁取り
- **フォント・詳細**: フォント個別指定・対象キー絞り込み・見た目・話者設定のリセット

### コマンドライン（CLI）で使う
```bash
python add_dialogue_band.py <画像フォルダ> <台本.csv> <出力フォルダ> [オプション]
```
※ Windows 環境で `python` コマンドがストア版スタブを指す場合は、インストール済み Python のフルパス（例: `C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe`）または `py -3` で実行してください。

### 主なオプション
#### 基本
- `--mode extend|overlay` : `extend`=下に帯を継ぎ足す（既定・推奨、絵が隠れない）／`overlay`=半透明帯を重ねる（絵の縦が伸びない）
- `--band 0.24` : 帯の高さ（画像の横幅に対する比率）
- `--max-lines 2` : セリフの最大行数（既定 2）
- `--font-scale 1.0` : フォントサイズ全体の倍率（画像幅に自動比例した基準サイズに掛かります）
- `--uniform-font` : 事前に全画像をスキャンし、全ページが収まる共通の最大文字サイズに自動統一
- `--uniform-height` : `extend` モード時に、セリフなし画像にも同じ高さの空帯を付けて全ページの高さを統一
- `--speaker-colors` : 話者ごとに名前の色を自動で割り当てる
- `--config PATH` : 設定JSON（[sample_config.json](sample_config.json) 参照）を読み込む（CLI引数が設定ファイルより優先）

#### 話者名・位置・透過・配色（v1.2〜v1.3）
- `--speaker-style plate|bar|bracket|plain` : 話者名の装飾スタイル（`plate`=ネームプレート風・既定 / `bar`=左バー / `bracket`=【話者名】 / `plain`=文字のみ）
- `--speaker-scale 1.0` : 話者名サイズの独立倍率（`0.5`〜`2.5`、本文 `--font-scale` を下げても連動して縮みません）
- `--speaker-gap 0.50` : 話者名と本文の間隔（話者名サイズに対する比率、`0.15`〜`1.50`）
- `--position bottom|top` : 帯の位置（`bottom`=下端・既定 / `top`=上端）
- `--align left|center|right` : 文字と話者名の水平揃え（既定 `left`）
- `--text-offset-y 0.0` : 帯内での文字ブロック上下微調整（`-0.35`〜`+0.35`、帯高さに対する比率）
- `--pad-x 0.045` : 左右の余白（画像幅に対する比率、既定 `0.045`）
- `--line-height 1.45` : 行間倍率（既定 `1.45`）
- `--overlay-opacity 0.76` : `overlay` 時の帯の不透明度（`0.0`〜`1.0`、既定 `0.76`）
- `--overlay-fade 0.30` : `overlay` 時のグラデーション幅（`0.0`〜`0.60`、帯高さに対する比率、既定 `0.30`）
- `--overlay-margin 0.0` : `overlay` 時の上下端からの余白（`0.0`〜`0.25`、画像高さに対する比率）
- `--text-outline 0` : 文字の縁取り太さ（`0`〜`4`、既定 `0`）
- `--band-color #0C0C0E` / `--text-color #FFFFFF` / `--narration-color #EAEDF5` : 帯色・本文色・地の文色

#### フォント・出力・チェック
- `--font PATH` / `--font-serif PATH` / `--font-bold PATH` : 本文・地の文（明朝）・話者名（太字）フォントパス
- `--format keep|png|jpg|webp` : 出力画像形式の指定（既定 `keep` は元ファイル形式を維持）
- `--quality 92` : JPEG / WebP 出力時の画質（既定 92、JPEG はサブサンプリングなし `subsampling=0`）
- `--dry-run` : 画像を書き出さず、台本照合・統一フォントサイズ・溢れチェックのみ実行
- `--strict` : CSV警告・画像未対応の台本キー・文字溢れ（切り捨て）が発生した場合にエラー終了コード 1 を返す
- `--only 001,003` : 指定した番号キーの画像だけを処理する（部分再生成用）

## 設定ファイル（`sample_config.json`）
GUI の「保存」ボタンから書き出せるほか、テキストエディタで編集して CLI からも `--config sample_config.json` でそのまま使えます。
```json
{
  "mode": "extend",
  "position": "bottom",
  "band": 0.24,
  "max_lines": 2,
  "font_scale": 1.0,
  "uniform_font": false,
  "uniform_height": false,
  "align": "left",
  "text_offset_y": 0.0,
  "pad_x": 0.045,
  "line_height": 1.45,
  "speaker_style": "plate",
  "speaker_scale": 1.0,
  "speaker_gap": 0.5,
  "format": "keep",
  "quality": 92,
  "band_color": "#0C0C0E",
  "overlay_opacity": 0.76,
  "overlay_fade": 0.30,
  "overlay_margin": 0.0,
  "text_outline": 0,
  "text_color": "#FFFFFF",
  "narration_color": "#EAEDF5",
  "speaker_colors": {
    "彼女": "#FF9EC7",
    "彼": "#96C8FF"
  }
}
```

## 台本CSV（ヘッダなし可、UTF-8 / BOM付きUTF-8対応）
```csv
001,彼女,……ねえ、今日はもう少しだけ、そばにいて？
002,,（地の文・ナレーションは話者を空に。本文が明朝体になります）
003,彼,"「分かった。今日は帰らないで、\n朝までずっとそばにいるよ」"
```
- 番号は画像ファイル名の先頭セパレータ（`_` / `-` / 半角スペース のうち最も手前）以前と照合します（例: `001_xxx.png` / `001-a_xxx.png` → `001`）
- セリフにカンマや複数行を含めたい場合は `"..."` のようにダブルクォートで囲んでください。セル内の `\n`（または実際の改行）は手動改行としてそのまま尊重されます
- 空行と `#` で始まる行、および先頭列が `id` / `no` / `番号` のヘッダ行は無視します
- 重複キー・列不足・台本に対応する画像がない場合・画像に対応する台本がない場合は警告を出します
- 最小フォントサイズでも最大行数に収まらず末尾が切り捨てられた場合は `WARNING [OVERFLOW]` を出力します

## 組版・デザインの仕様
- **解像度自動比例**: 文字サイズ・余白・境界線・アクセントバー・縁取り・ドロップシャドウが画像幅に比例するため、低解像度〜4K画像まで崩れません
- **禁則処理**: 行頭禁則（句読点、ひらがな/カタカナ小書き `っゃゅょぁぃぅぇぉッャュョァィゥェォ`、長音・波ダッシュ・全角ダッシュ `ー〜～—―`、閉じ括弧）、行末禁則（開き括弧）、`……`/`——`/`！？` の分割禁止、英数字単語・`v1.0`/`100%` の分割禁止に対応
- **自然な折り返し**: 句読点（`。？！、，・`）や文節の区切りを優先しつつ行長バランスを最適化する動的計画法（DP）折り返しを採用。手動改行 `\n` を入れた箇所は強制維持します（任意で `budoux` も利用可）
- **視認性向上**: 帯内の垂直中央揃え（および上下微調整）、話者名の独立サイズ＆スタイル選択（プレート/左バー/括弧/なし）、`extend` 時の上端区切り線、`overlay` 時の上端グラデーションフェード＋文字ドロップシャドウ＋任意縁取りを実装
- **EXIF / 透過PNG対応**: スマホ等で撮影した画像の EXIF 回転を自動補正し、透過PNGは帯色背景に合成して破綻を防ぎます

## 同梱ファイル
- `add_dialogue_band.py` : 本体（CLI / 合成エンジン）
- `gui.py` : デスクトップGUI（タブ構成・ライブプレビュー・一括生成・設定保存）
- `launch_gui.bat` : Windows 用ダブルクリック起動ランチャー
- `sample_config.json` : 設定ファイル見本
- `sample_input/` : 見本の入力画像3枚
- `sample_script.csv` : 見本の台本（3行）
- `sample_output_extend/` : 継ぎ足し方式の出力見本
- `sample_output_overlay/` : 重ね方式の出力見本
- `tests/test_add_dialogue_band.py` : 自動テストスイート

## 自動テストの実行
```bash
python -m unittest discover -s tests -v
```
（禁則・折り返し・CSV読込・フォントフォールバック・`extend`/`overlay`/`--uniform-height`/`--uniform-font`/話者デザイン＆サイズ/上配置・文字揃え・透過＆縁取り・解像度スケーリング/JPEG変換/`--dry-run`/`--strict`/GUI設定ラウンドトリップの 17 テストを収録）
