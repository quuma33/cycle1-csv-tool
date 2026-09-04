import argparse
import os
import sys
from pathlib import Path

try:
    import pandas as pd
    import matplotlib
except ModuleNotFoundError as e:
    print(
        f"エラー: 必要なライブラリが見つかりません（{e.name}）。\n"
        "仮想環境を有効化してから実行してください。例:\n"
        "  source .venv/bin/activate\n"
        "  python3 csv_stats.py <CSVファイル>\n"
        "または直接指定: .venv/bin/python csv_stats.py <CSVファイル>\n"
        "未インストールの場合は: .venv/bin/pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ENCODING_FALLBACKS = ["utf-8-sig", "cp932", "shift_jis", "euc_jp"]


def parse_args():
    parser = argparse.ArgumentParser(description="CSVの基本統計・相関・折れ線グラフを出力するツール")
    parser.add_argument("input", help="入力CSVファイルパス")
    parser.add_argument("--output-dir", default="./output", help="グラフ画像の出力先ディレクトリ（デフォルト: ./output）")
    parser.add_argument("--stats-out", default=None, help="統計量を書き出すCSVパス（省略時は書き出さない）")
    parser.add_argument("--report-out", default=None, help="統計量・相関・グラフをまとめたMarkdownレポートの出力パス（省略時は書き出さない）")
    parser.add_argument("--no-plot", action="store_true", help="グラフを生成しない")
    parser.add_argument("--columns", default=None, help="対象列をカンマ区切りで指定（省略時は全列）")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 読み込み
# ---------------------------------------------------------------------------

def load_csv(path: str) -> pd.DataFrame:
    """CSVを読み込む。よくある失敗はここでメッセージ化して終了する。"""
    df = None
    last_encoding_error = None
    for encoding in ENCODING_FALLBACKS:
        try:
            df = pd.read_csv(path, encoding=encoding)
            if encoding != "utf-8-sig":
                print(f"注意: UTF-8として読み込めなかったため、{encoding} として読み込みました。\n", file=sys.stderr)
            break
        except FileNotFoundError:
            print(f"エラー: ファイルが見つかりません: {path}", file=sys.stderr)
            sys.exit(1)
        except pd.errors.EmptyDataError:
            print(f"エラー: CSVが空、またはヘッダー行が読み取れません: {path}", file=sys.stderr)
            sys.exit(1)
        except pd.errors.ParserError as e:
            print(f"エラー: CSVの解析に失敗しました: {path}\n詳細: {e}", file=sys.stderr)
            sys.exit(1)
        except UnicodeDecodeError as e:
            last_encoding_error = e
            continue

    if df is None:
        print(
            f"エラー: 文字コードの読み込みに失敗しました: {path}\n"
            f"試した文字コード: {', '.join(ENCODING_FALLBACKS)}\n"
            f"詳細: {last_encoding_error}\n"
            "Excelから保存した場合は「CSV UTF-8」形式で保存し直すことを検討してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    if df.shape[1] == 0:
        print(f"エラー: 列が1つも見つかりませんでした: {path}", file=sys.stderr)
        sys.exit(1)

    if df.shape[1] == 1:
        col_name = str(df.columns[0])
        suspicious_delims = [d for d in [";", "\t", "|"] if d in col_name]
        if suspicious_delims:
            print(
                f"警告: 列が1つしか検出されませんでした。区切り文字が原因の可能性があります"
                f"（ヘッダーに '{suspicious_delims[0]}' が含まれています）。\n"
                "このCSVはカンマ区切り以外（セミコロン区切りなど）で保存されている可能性があります。\n",
                file=sys.stderr,
            )

    return df


def select_columns(df: pd.DataFrame, columns_arg: str) -> pd.DataFrame:
    target_cols = [c.strip() for c in columns_arg.split(",")]
    missing_cols = [c for c in target_cols if c not in df.columns]
    if missing_cols:
        print(
            f"エラー: 指定された列が見つかりません: {', '.join(missing_cols)}\n"
            f"利用可能な列: {', '.join(df.columns)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return df[target_cols]


# ---------------------------------------------------------------------------
# 列の数値判定（統計量・相関・グラフで共通利用）
# ---------------------------------------------------------------------------

def classify_columns(df: pd.DataFrame) -> dict:
    """各列を1回だけ数値変換し、結果を列名 -> 変換後Seriesの辞書として返す。
    数値として解釈できる値が1件もない列（純粋な文字列列）は辞書に含めない。
    """
    numeric_by_col = {}
    for col in df.columns:
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().sum() > 0:
            numeric_by_col[col] = numeric
    return numeric_by_col


# ---------------------------------------------------------------------------
# 統計量
# ---------------------------------------------------------------------------

def compute_stats(df: pd.DataFrame, numeric_by_col: dict) -> pd.DataFrame:
    rows = []
    for col in df.columns:
        total = len(df[col])
        numeric = numeric_by_col.get(col)

        if numeric is not None:
            count = numeric.notna().sum()
            rows.append({
                "列名": col,
                "件数": count,
                "欠損値数": total - count,
                "平均": round(numeric.mean(), 2) if count > 0 else "-",
                "中央値": round(numeric.median(), 2) if count > 0 else "-",
                "標準偏差": round(numeric.std(), 3) if count > 1 else "-",
            })
        else:
            count = df[col].count()
            rows.append({
                "列名": col,
                "件数": count,
                "欠損値数": total - count,
                "平均": "-",
                "中央値": "-",
                "標準偏差": "-",
            })
    return pd.DataFrame(rows)


def print_stats_table(stats_df: pd.DataFrame):
    print("列ごとの基本統計量:")
    print(stats_df.to_string(index=False) if not stats_df.empty else "(対象データがありません)")
    print()


# ---------------------------------------------------------------------------
# 相関
# ---------------------------------------------------------------------------

def compute_correlation(numeric_df: pd.DataFrame) -> pd.DataFrame | None:
    """数値列が2つ未満の場合はNoneを返す。"""
    if numeric_df.shape[1] < 2:
        return None
    return numeric_df.corr().round(3)


def print_correlation(corr_df: pd.DataFrame | None):
    if corr_df is None:
        print("相関係数: 数値列が2つ未満のため計算をスキップしました。\n")
        return
    print("相関係数:")
    print(corr_df.to_string())
    print()


# ---------------------------------------------------------------------------
# グラフ
# ---------------------------------------------------------------------------

def find_date_column(df: pd.DataFrame):
    for col in df.columns:
        if "date" in col.lower() or "time" in col.lower():
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().sum() > 0:
                return col, parsed
    return None, None


def make_line_plots(df: pd.DataFrame, numeric_df: pd.DataFrame, output_dir: Path) -> list[Path]:
    """折れ線グラフをPNGとして保存し、実際に保存したファイルパスの一覧を返す。"""
    if numeric_df.shape[1] == 0:
        print("グラフ: 数値列が見つからないためスキップしました。")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    date_col, date_series = find_date_column(df)
    x = date_series if date_series is not None else df.index

    saved_paths = []
    for col in numeric_df.columns:
        series = numeric_df[col]
        if series.notna().sum() == 0:
            print(f"グラフ: {col} は有効な数値がないためスキップしました。")
            continue

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(x, series, marker="o")
        ax.set_title(f"{col} over time")
        ax.set_xlabel(date_col if date_col else "index")
        ax.set_ylabel(col)
        fig.autofmt_xdate()
        fig.tight_layout()
        out_path = output_dir / f"line_{col}.png"
        fig.savefig(out_path)
        plt.close(fig)
        print(f"グラフを保存しました: {out_path}")
        saved_paths.append(out_path)

    return saved_paths


# ---------------------------------------------------------------------------
# Markdownレポート
# ---------------------------------------------------------------------------

def dataframe_to_markdown_table(df: pd.DataFrame, index_label: str = "") -> str:
    """外部依存（tabulate等）なしでMarkdownテーブル文字列を作る。"""
    if df.empty:
        return "(データなし)"

    if df.index.name is not None or not isinstance(df.index, pd.RangeIndex):
        df = df.reset_index().rename(columns={"index": index_label})

    headers = [str(c) for c in df.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def build_markdown_report(
    input_path: str,
    stats_df: pd.DataFrame,
    corr_df: pd.DataFrame | None,
    plot_paths: list[Path],
    report_out: Path,
) -> str:
    lines = [f"# CSV分析レポート: {Path(input_path).name}", ""]

    lines.append("## 基本統計量")
    lines.append("")
    lines.append(dataframe_to_markdown_table(stats_df))
    lines.append("")

    lines.append("## 相関係数")
    lines.append("")
    if corr_df is None:
        lines.append("数値列が2つ未満のため計算をスキップしました。")
    else:
        lines.append(dataframe_to_markdown_table(corr_df, index_label="列名"))
    lines.append("")

    lines.append("## グラフ")
    lines.append("")
    if not plot_paths:
        lines.append("グラフはありません。")
    else:
        for plot_path in plot_paths:
            rel_path = os.path.relpath(plot_path, start=report_out.parent)
            lines.append(f"![{plot_path.stem}]({rel_path})")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    df = load_csv(args.input)

    if args.columns:
        df = select_columns(df, args.columns)

    if df.shape[0] == 0:
        print("警告: データ行が0件です（ヘッダーのみ）。統計量・相関・グラフは出力できる範囲で表示します。\n")

    numeric_by_col = classify_columns(df)
    numeric_df = pd.DataFrame(numeric_by_col)

    stats_df = compute_stats(df, numeric_by_col)
    print_stats_table(stats_df)

    if args.stats_out:
        stats_df.to_csv(args.stats_out, index=False, encoding="utf-8-sig")
        print(f"統計量を保存しました: {args.stats_out}\n")

    corr_df = compute_correlation(numeric_df)
    print_correlation(corr_df)

    plot_paths = []
    if not args.no_plot:
        plot_paths = make_line_plots(df, numeric_df, Path(args.output_dir))

    if args.report_out:
        report_out = Path(args.report_out)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_text = build_markdown_report(args.input, stats_df, corr_df, plot_paths, report_out)
        report_out.write_text(report_text, encoding="utf-8")
        print(f"レポートを保存しました: {report_out}")


if __name__ == "__main__":
    main()
