from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

from prioritizer.cli.args import parse_statistics_args

METRIC_LABELS = {
    "metrics.ranking.ndcg": "nDCG",
    "metrics.ranking.kendall_tau": "Kendall tau",
    "metrics.ranking.spearman_rho": "Spearman rho",
    "metrics.ranking.rbo": "RBO",
    "metrics.severity_labelling.accuracy": "Accuracy",
    "metrics.severity_labelling.ordinal_accuracy": "Ordinal accuracy",
    "metrics.severity_labelling.weighted_kappa": "Weighted kappa",
    "metrics.severity_labelling.cohen_kappa": "Cohen's kappa",
    "ndcg": "nDCG",
    "kendall_tau": "Kendall tau",
    "spearman_rho": "Spearman rho",
    "rbo": "RBO",
    "accuracy": "Accuracy",
    "ordinal_accuracy": "Ordinal accuracy",
    "weighted_kappa": "Weighted kappa",
    "cohen_kappa": "Cohen's kappa",
    "Runtime (in seconds)": "Runtime (s)",
}


def pretty_metric_name(metric: str) -> str:
    return METRIC_LABELS.get(metric, metric)


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    Flatten nested dictionaries.

    Example:
        {"metrics": {"ranking": {"ndcg": 0.5}}}
    becomes:
        {"metrics.ranking.ndcg": 0.5}
    """
    items: List[tuple[str, Any]] = []

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)

        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))

    return dict(items)


def safe_bool_str(value: Any) -> str:
    """Convert bool-like values into readable label text."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if value is None:
        return "none"
    return str(value)


def build_configuration_label(row: pd.Series) -> str:
    return " | ".join(
        [
            f"G={safe_bool_str(row.get('Git data included'))}",
            f"P={safe_bool_str(row.get('Pylint analysis included'))}",
            f"R={safe_bool_str(row.get('RAG included'))}",
            f"T={safe_bool_str(row.get('Test coverage report'))}",
            f"C={safe_bool_str(row.get('Code context'))}",
        ]
    )


def margin_of_error_95(std: float, n: int) -> float:
    """
    Approximate 95% confidence interval margin of error.
    """
    if n <= 1 or pd.isna(std):
        return float("nan")
    return 1.96 * std / math.sqrt(n)


def get_seed_numbers(df: pd.DataFrame, configuration: str | None = None) -> List[int]:
    """
    Extract seed numbers for the selected configuration.
    """
    working_df = df.copy()

    if configuration is not None:
        working_df = working_df[working_df["configuration"] == configuration].copy()
    else:
        configurations = working_df["configuration"].dropna().unique().tolist()
        if len(configurations) != 1:
            raise ValueError(
                "Multiple configurations found. Specify which configuration to export."
            )

    if "Seed number" not in working_df.columns:
        return []

    return sorted(
        set(
            int(seed)
            for seed in pd.to_numeric(working_df["Seed number"], errors="coerce").dropna().tolist()
        )
    )

def discover_json_files(input_dir: Path) -> List[Path]:
    """Recursively discover all JSON files in a directory."""
    return sorted(path for path in input_dir.rglob("*.json"))


def load_reports(json_files: Iterable[Path]) -> pd.DataFrame:
    """
    Load JSON reports into a flat DataFrame.
    """
    records: List[Dict[str, Any]] = []

    for json_file in json_files:
        try:
            with json_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            flat = flatten_dict(data)
            flat["source_file"] = str(json_file)
            records.append(flat)

        except Exception as exc:
            print(f"[WARN] Failed to read {json_file}: {exc}")

    if not records:
        raise ValueError("No valid JSON reports were loaded.")

    df = pd.DataFrame(records)
    df["configuration"] = df.apply(build_configuration_label, axis=1)
    return df


def find_metric_columns(df: pd.DataFrame) -> List[str]:
    """
    Identify numeric metric columns to summarize.
    """
    excluded = {
        "timestamp",
        "project name",
        "pipeline",
        "llm_provider",
        "Seed number",
        "model",
        "temperature",
        "max_tokens",
        "Git data included",
        "Pylint analysis included",
        "RAG included",
        "Test coverage report",
        "Code context",
        "source_file",
        "configuration",
        "metrics.coverage.n_gt",
        "metrics.coverage.n_llm",
        "metrics.coverage.n_missing",
        "metrics.coverage.n_matched",
        "metrics.coverage.n_unmatched",
        "metrics.coverage.missing_ids",
        "metrics.severity_labelling.one_step_off",
        "metrics.severity_labelling.two_steps_off",
        "metrics.severity_labelling.exact_matches",
    }

    metric_cols: List[str] = []

    for col in df.columns:
        if col in excluded:
            continue
        if col.startswith("metrics.") or col == "Runtime (in seconds)":
            metric_cols.append(col)

    return metric_cols


def coerce_numeric_metrics(df: pd.DataFrame, metric_cols: List[str]) -> pd.DataFrame:
    """
    Convert metric columns to numeric where possible.
    """
    result = df.copy()

    for col in metric_cols:
        result[col] = pd.to_numeric(result[col], errors="coerce")

    return result


def summarize_metrics(df: pd.DataFrame, metric_cols: List[str]) -> pd.DataFrame:
    """
    Compute summary statistics by configuration for each metric.
    """
    rows: List[Dict[str, Any]] = []

    grouped = df.groupby("configuration", dropna=False)

    for configuration, group in grouped:
        for metric in metric_cols:
            series = pd.to_numeric(group[metric], errors="coerce").dropna()

            if series.empty:
                continue

            n = int(series.count())
            mean = float(series.mean())
            std = float(series.std(ddof=1)) if n > 1 else float("nan")
            median = float(series.median())
            min_val = float(series.min())
            max_val = float(series.max())

            moe = margin_of_error_95(std, n) if n > 1 else float("nan")
            ci_low = mean - moe if n > 1 else float("nan")
            ci_high = mean + moe if n > 1 else float("nan")

            rows.append(
                {
                    "configuration": configuration,
                    "metric": pretty_metric_name(metric),
                    "count": n,
                    "mean": mean,
                    "std": std,
                    "median": median,
                    "min": min_val,
                    "max": max_val,
                    "ci95_low": ci_low,
                    "ci95_high": ci_high,
                }
            )

    summary_df = pd.DataFrame(rows)

    if not summary_df.empty:
        summary_df = summary_df.sort_values(["configuration", "metric"]).reset_index(drop=True)

    return summary_df

def build_metrics_payload(
    df: pd.DataFrame,
    summary_df: pd.DataFrame,
    reports_dir: Path,
    configuration: str | None = None,
) -> dict:
    """
    Build a compact machine-readable payload with summary statistics
    for later cross-experiment comparison plots.
    """
    table_df = summary_df.copy()

    if configuration is not None:
        raw_config_df = df[df["configuration"] == configuration].copy()
    else:
        configurations = summary_df["configuration"].dropna().unique().tolist()
        if len(configurations) != 1:
            raise ValueError(
                "Multiple configurations found. Specify which configuration to export."
            )
        configuration = configurations[0]
        raw_config_df = df[df["configuration"] == configuration].copy()

    seed_numbers = []

    if "Seed number" in raw_config_df.columns:
        seed_numbers = [
            int(seed)
            for seed in pd.to_numeric(raw_config_df["Seed number"], errors="coerce").dropna().tolist()
        ]
    
    metric_order = [
        "nDCG",
        "Kendall tau",
        "Spearman rho",
        "RBO",
        "Accuracy",
        "Cohen's kappa",
        "Ordinal accuracy",
        "Weighted kappa",
        "Runtime (s)",
    ]

    metrics_payload = {}

    for _, row in table_df.iterrows():
        metric = row["metric"]
        metrics_payload[metric] = {
            "count": int(row["count"]),
            "mean": round(float(row["mean"]), 3) if pd.notna(row["mean"]) else None,
            "std": round(float(row["std"]), 3) if pd.notna(row["std"]) else None,
            "median": round(float(row["median"]), 3) if pd.notna(row["median"]) else None,
            "min": round(float(row["min"]), 3) if pd.notna(row["min"]) else None,
            "max": round(float(row["max"]), 3) if pd.notna(row["max"]) else None,
            "ci95_low": round(float(row["ci95_low"]), 3) if pd.notna(row["ci95_low"]) else None,
            "ci95_high": round(float(row["ci95_high"]), 3) if pd.notna(row["ci95_high"]) else None,
        }

    ordered_metrics_payload = {
        metric: metrics_payload[metric]
        for metric in metric_order
        if metric in metrics_payload
    }

    return {
        "experiment": reports_dir.name,
        "configuration": configuration,
        "seed_numbers": seed_numbers,
        "metrics": ordered_metrics_payload,
    }

def build_metric_statistics_table(summary_df: pd.DataFrame, configuration: str | None = None) -> pd.DataFrame:
    """
    Build a table where metrics are rows and summary statistics are columns.
    """
    table_df = summary_df.copy()

    if configuration is not None:
        table_df = table_df[table_df["configuration"] == configuration].copy()
        if table_df.empty:
            raise ValueError(f"No summary statistics found for configuration: {configuration}")
    else:
        configurations = table_df["configuration"].dropna().unique().tolist()
        if len(configurations) != 1:
            raise ValueError(
                "Multiple configurations found. Specify which configuration to export."
            )

    table_df["ci95"] = table_df.apply(
        lambda row: "-"
        if pd.isna(row["ci95_low"]) or pd.isna(row["ci95_high"])
        else f"[{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]",
        axis=1,
    )

    result = table_df[
        ["metric", "mean", "std", "median", "min", "max", "ci95"]
    ].copy()

    metric_order = [
        "nDCG",
        "Kendall tau",
        "Spearman rho",
        "RBO",
        "Accuracy",
        "Cohen's kappa",
        "Ordinal accuracy",
        "Weighted kappa",
        "Runtime (s)",
    ]

    result["metric"] = pd.Categorical(result["metric"], categories=metric_order, ordered=True)
    result = result.sort_values("metric").reset_index(drop=True)

    return result


def escape_latex(text: str) -> str:
    """
    Escape special LaTeX characters in plain text.
    """
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }

    result = str(text)
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def dataframe_to_latex_tabular(df: pd.DataFrame, seed_numbers: List[int] | None = None) -> str:
    """
    Convert a dataframe into a LaTeX tabular string using booktabs.
    """
    headers = [
        r"\textbf{Metric}",
        r"\textbf{Mean}",
        r"\textbf{Std}",
        r"\textbf{Median}",
        r"\textbf{Min}",
        r"\textbf{Max}",
        r"\textbf{95\% CI}",
    ]    
    
    col_spec = "XrrrrrX"


    lines = [
        r"\begin{table}[H]",
        r"\caption{}",
        r"\renewcommand{\arraystretch}{1.75}",
        rf"\begin{{tabularx}}{{\textwidth}}{{{col_spec}}}",
        r"\hline",
        " & ".join(headers) + r" \\",
        r"\hline",
    ]

    for _, row in df.iterrows():
        metric = r"\textit{" + escape_latex(str(row["metric"])) + r"}"
        mean = f"{row['mean']:.3f}" if pd.notna(row["mean"]) else "-"
        std = f"{row['std']:.3f}" if pd.notna(row["std"]) else "-"
        median = f"{row['median']:.3f}" if pd.notna(row["median"]) else "-"
        min_val = f"{row['min']:.3f}" if pd.notna(row["min"]) else "-"
        max_val = f"{row['max']:.3f}" if pd.notna(row["max"]) else "-"
        ci95 = escape_latex(str(row["ci95"]))

        lines.append(
            f"{metric} & {mean} & {std} & {median} & {min_val} & {max_val} & {ci95} \\\\"
        )

    if seed_numbers:
        seed_text = ", ".join(str(seed) for seed in seed_numbers)
        wrapped_spec = r"p{\dimexpr\textwidth-2\tabcolsep-2\arrayrulewidth\relax}"
        
        lines.append(r"\hline")
        lines.append(rf"\multicolumn{{7}}{{l}}{{\textbf{{Seed numbers}}}} \\")
        lines.append(r"\hline")
        lines.append(
            rf"\multicolumn{{7}}{{{wrapped_spec}}}{{\raggedright\arraybackslash {escape_latex(seed_text)}}} \\"
        )

    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabularx}",
            r"\end{table}",
        ]
    )

    return "\n".join(lines)


def write_latex_table(
    df: pd.DataFrame,
    summary_df: pd.DataFrame,
    output_dir: Path,
    configuration: str | None = None,
    filename: str = "metric_statistics_table.tex",
) -> None:
    """
    Build and write a LaTeX table for one configuration.
    """
    table_df = build_metric_statistics_table(summary_df, configuration=configuration)
    seed_numbers = get_seed_numbers(df, configuration)
    latex_str = dataframe_to_latex_tabular(table_df, seed_numbers)

    out_path = output_dir / filename
    with out_path.open("w", encoding="utf-8") as f:
        f.write(latex_str)

    print(f"[INFO] Saved LaTeX table: {out_path}")


def write_metrics_payload(
    df: pd.DataFrame,
    summary_df: pd.DataFrame,
    reports_dir: Path,
    output_dir: Path,
    configuration: str | None = None,
    filename: str = "metrics_summary.json",
) -> None:
    """
    Write compact summary statistics for later comparison across experiments.
    """
    payload = build_metrics_payload(
        df=df,
        summary_df=summary_df,
        reports_dir=reports_dir,
        configuration=configuration,
    )

    out_path = output_dir / filename
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Saved metrics summary: {out_path}")


def run(
    reports_dir: Path,
    output_dir: Path,
    configuration: str | None = None,
) -> None:
    """
    Main entry point for collecting statistics and exporting a LaTeX table.
    """
    if not reports_dir.exists():
        raise FileNotFoundError(f"Reports directory does not exist: {reports_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    json_files = discover_json_files(reports_dir)

    if not json_files:
        raise FileNotFoundError(f"No JSON files found in {reports_dir}")

    print(f"[INFO] Found {len(json_files)} JSON files in {reports_dir}")

    raw_df = load_reports(json_files)
    metric_cols = find_metric_columns(raw_df)
    df = coerce_numeric_metrics(raw_df, metric_cols)
    summary_df = summarize_metrics(df, metric_cols)

    write_latex_table(df, summary_df, output_dir, configuration=configuration)

    write_metrics_payload(
        df=df,
        summary_df=summary_df,
        reports_dir=reports_dir,
        output_dir=output_dir,
        configuration=configuration,
    )

    print(f"[INFO] Wrote outputs to {output_dir}")
    print("[DONE] Process complete.\n")

def generate_statistics_for_experiments_folder(report_dir: Path | None = None) -> None:
    experiments_dir = Path("experiments")
    stats_dir = Path("statistics")

    if report_dir is not None:
        report_dir = Path(report_dir)

        if not report_dir.exists():
            raise FileNotFoundError(
                f"Evaluation report directory does not exist: {report_dir}"
            )

        if not report_dir.is_dir():
            raise NotADirectoryError(
                f"Expected a directory containing evaluation reports, got: {report_dir}"
            )

        output_dir = stats_dir / f"statistics_summary_{report_dir.name}"

        print(f"[INFO] Processing {report_dir} -> {output_dir}")
        run(reports_dir=report_dir, output_dir=output_dir)
        return

    if not experiments_dir.exists():
        raise FileNotFoundError(f"Experiments directory does not exist: {experiments_dir}")

    stats_dir.mkdir(parents=True, exist_ok=True)

    if report_dir is None:
        subfolders = sorted(p for p in experiments_dir.iterdir() if p.is_dir())

        for report_dir in subfolders:
            output_dir = stats_dir / f"statistics_summary_{report_dir.name}"
            print(f"[INFO] Processing {report_dir} -> {output_dir}")
            
            run(reports_dir=report_dir, output_dir=output_dir)

if __name__ == "__main__":
    args = parse_statistics_args()
    generate_statistics_for_experiments_folder(report_dir=args.report_dir)
