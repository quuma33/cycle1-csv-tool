# CSV分析ツール

CSVファイルを読み込み、列ごとの基本統計量・数値列間の相関係数をコンソールに出力し、
日別の折れ線グラフ（PNG）とMarkdownレポートを生成するコマンドラインツールです。

詳しい仕様は [SPEC.md](./SPEC.md) を参照してください。

## セットアップ　A

Python 3の仮想環境を作成し、依存ライブラリ（pandas, matplotlib）をインストールします。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使い方

仮想環境を有効化した状態で実行してください。

```bash
source .venv/bin/activate
python3 csv_stats.py sample_data.csv
```

基本統計量・相関係数がコンソールに出力され、`./output/` に折れ線グラフ（PNG）が保存されます。

### オプション

| オプション | 説明 | デフォルト |
|---|---|---|
| `input`（位置引数） | 入力CSVファイルパス | 必須 |
| `--output-dir` | グラフ画像の出力先ディレクトリ | `./output` |
| `--stats-out` | 統計量を書き出すCSVパス | 書き出さない |
| `--report-out` | 統計量・相関・グラフをまとめたMarkdownレポートの出力パス | 書き出さない |
| `--no-plot` | グラフを生成しない | false |
| `--columns` | 対象列をカンマ区切りで指定 | 全列 |

### 実行例

```bash
# 統計量CSV + Markdownレポート + グラフを一度に出力
python3 csv_stats.py sample_data.csv --stats-out summary.csv --report-out report.md

# グラフ不要で統計量だけ確認
python3 csv_stats.py sample_data.csv --no-plot

# 特定の列だけに絞って確認
python3 csv_stats.py sample_data.csv --columns sales,temperature --no-plot
```

## 入力CSVの想定

- カンマ区切り、UTF-8（Shift-JISなど他の文字コードも自動フォールバックで対応）
- 1行目はヘッダー行
- 数値に変換できない列は「件数・欠損値数」のみ算出（統計量は `-` 表示）
- 列名に `date`/`time` を含み日付として解釈できる列があれば、折れ線グラフのX軸に使用

サンプルとして [sample_data.csv](./sample_data.csv)（店舗の日次データ）を同梱しています。

## エラーハンドリング

以下のような壊れやすい入力にも、わかりやすいメッセージを出して安全に終了します。

- 空のCSV / 存在しないファイルパス
- 数値列に文字列が混ざっている場合（変換できない値は欠損値として扱う）
- ヘッダーのみでデータ行が0件のCSV
- `--columns` に存在しない列名を指定した場合
- Shift-JISなどUTF-8以外の文字コードで保存されたCSV
- セミコロン区切りなど、想定と異なる区切り文字のCSV
- 仮想環境を有効化せずに実行した場合（`pandas`未インストール）

## 開発時のディレクトリ構成

```
.
├── SPEC.md            # 仕様書
├── README.md          # このファイル
├── csv_stats.py        # 本体スクリプト
├── requirements.txt    # 依存ライブラリ
├── sample_data.csv     # 動作確認用サンプルCSV
└── output/              # グラフ画像の出力先（gitignore対象）
```

`output/`, `report.md`, `summary.csv` はツール実行で再生成できる成果物のため、
`.gitignore` で追跡対象から除外しています。
