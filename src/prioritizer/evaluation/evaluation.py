import pandas as pd
from io import StringIO
from scipy.stats import kendalltau, spearmanr
import numpy as np
from sklearn.metrics import ndcg_score
import rbo
import re
from pathlib import Path
from datetime import datetime
import json
import argparse

from typing import Dict, List, Optional, Sequence

EXPECTED_COLS: List[str] = [
    "Rank",
    "Id",
    "Name of Smell",
    "Name",
    "File",
    "Severity",
    "Reason for Prioritization",
]

SEVERITY_MAP: Dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

def gain(r): # (2**r - 1)
    return (2**r - 1) #np.log2(1 + r)

def _ranks_with_missing_penalty(
    gt_ids: Sequence[str],
    llm_ids: Sequence[str],
) -> tuple[list[int], list[int], list[str]]:
    """
    Build ranks for Kendall/Spearman/RBO where missing GT items in LLM are assigned
    the worst rank (len(llm_ids)), i.e., placed after all predicted items.

    Returns:
      ranks_llm: positions of GT items in LLM (missing -> worst)
      ranks_gt:  0..len(gt_ids)-1
      missing:   list of missing GT ids
    """
    pos = {id_: idx for idx, id_ in enumerate(llm_ids)}
    worst = len(llm_ids)  # missing items are treated as bottom

    ranks_llm = [pos.get(id_, worst) for id_ in gt_ids]
    ranks_gt = list(range(len(gt_ids)))
    missing = [id_ for id_ in gt_ids if id_ not in pos]
    return ranks_llm, ranks_gt, missing


def ndcg_ranking_using_only_id(gt_ids: Sequence[str], llm_ids: Sequence[str]) -> float:
    """
    NDCG where relevance is derived from GT rank (top GT item most relevant).
    Missing GT items contribute 0 because they never appear in llm_ids.
    """
    rel = {id_: len(gt_ids) - i for i, id_ in enumerate(gt_ids)} 

    def dcg(ids: Sequence[str]) -> float:
        score = 0.0
        for i, id_ in enumerate(ids):
            r = rel.get(id_, 0)
            score += gain(r) / np.log2(i + 2)
        return score

    dcg_pred = dcg(llm_ids[: len(gt_ids)])

    idcg = dcg(gt_ids)

    return float(dcg_pred / idcg) if idcg > 0 else 0.0


def ndcg_based_on_severity_of_smells(llm_ids: Sequence[str], relevance_by_id: Dict[str, int], k: int | None = None) -> float:
    """
    Standard severity-based NDCG. Missing items implicitly get 0 relevance.
    """
    if k is None:
        k = len(llm_ids)

    def dcg(ids: Sequence[str]) -> float:
        score = 0.0
        for i, id_ in enumerate(ids[:k]):
            r = relevance_by_id.get(id_, 0)
            score += gain(r) / np.log2(i + 2)
        return score
    
    ideal_ids = sorted(relevance_by_id.keys(), key=lambda x: relevance_by_id.get(x, 0), reverse=True)

    dcg_pred = dcg(llm_ids)
    idcg = dcg(ideal_ids)

    return float(dcg_pred / idcg) if idcg > 0 else 0.0


_NORMALIZE_CHARS = str.maketrans({
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
})

_CODE_FENCE_START = re.compile(r"(?s)^.*?```[a-zA-Z]*\s*")
_CODE_FENCE_END = re.compile(r"\s*```.*$")


def _strip_code_fences(text: str) -> str:
    text = _CODE_FENCE_START.sub("", text)
    text = _CODE_FENCE_END.sub("", text)
    return text.strip()


def _strip_wrapping_quotes(text: str) -> str:
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def _clean_lines(text: str) -> str:
    """
    Removes empty lines, markdown separators, and duplicate headers.
    """
    lines = text.splitlines()
    cleaned: List[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^-+\|(-+\|?)+$", line):  # markdown table separators
            continue
        if line.lower().startswith("rank|") and cleaned and "rank|" in cleaned[0].lower():
            continue  # skip duplicate header
        cleaned.append(line)

    return "\n".join(cleaned)


def _finalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].map(
                lambda x: x.strip().strip("'").strip('"') if isinstance(x, str) else x
            )
    return df


def format_output_from_llm_to_csv_format(llm_output: str | Path) -> pd.DataFrame:
    """
    Parses the LLM output file into a DataFrame with EXPECTED_COLS, using '|'
    as delimiter and supporting both header-present and headerless outputs.
    """
    llm_output = Path(llm_output)
    raw_text = llm_output.read_text(encoding="utf-8")

    text = _strip_code_fences(raw_text)
    text = text.translate(_NORMALIZE_CHARS).replace('""', '"').strip()
    text = _strip_wrapping_quotes(text)
    text = _clean_lines(text)

    parse_errors: List[Exception] = []

    for header_setting in (0, None):
        try:
            df = pd.read_csv(StringIO(text), sep=r"\|", engine="python", header=header_setting)
            df = _finalize_df(df)

            # Case 1: header is present and matches (or includes) expected cols
            if set(EXPECTED_COLS).issubset(set(df.columns)):
                return df[EXPECTED_COLS]

            # Case 2: no header, but column count matches expected
            if header_setting is None and df.shape[1] == len(EXPECTED_COLS):
                df.columns = EXPECTED_COLS
                return df

        except Exception as e:
            parse_errors.append(e)

    print("CSV parsing failed. Cleaned text was:\n")
    print(text)

    if parse_errors:
        raise parse_errors[-1]
    raise ValueError("Could not parse LLM output.")


def _load_ground_truth_df(ground_truth: str | Path) -> pd.DataFrame:
    gt_path = Path(ground_truth)
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth not found: {gt_path}")

    return pd.read_csv(gt_path, sep="|", engine="python")


def ranking_computation(ground_truth: str | Path, llm_output: str | Path) -> Optional[dict]:
    llm_df = format_output_from_llm_to_csv_format(llm_output)
    gt_df = _load_ground_truth_df(ground_truth)

    llm_ids = [str(x) for x in llm_df["Id"].tolist()]
    gt_ids = [str(x) for x in gt_df["Id"].tolist()]

    relevance_by_id = {
        str(row["Id"]): SEVERITY_MAP[str(row["Severity"]).strip()]
        for _, row in gt_df.iterrows()
    }

    ranks_llm, ranks_gt, missing = _ranks_with_missing_penalty(gt_ids, llm_ids)

    tau, _ = kendalltau(ranks_llm, ranks_gt)
    rho, _ = spearmanr(ranks_llm, ranks_gt)

    metrics = {
        "tau": float(tau) if tau is not None else float("nan"),
        "rho": float(rho) if rho is not None else float("nan"),
        "ndcg": float(ndcg_ranking_using_only_id(gt_ids, llm_ids)),
        "ndcg based on smell severity": float(ndcg_based_on_severity_of_smells(llm_ids, relevance_by_id)),
        "rbo": float(rbo.RankingSimilarity(llm_ids, gt_ids).rbo()),
        "n_gt": int(len(gt_ids)),
        "n_llm": int(len(llm_ids)),
        "n_missing": int(len(missing)),
        "missing_ids": missing,
    }

    return metrics


def order_prioritized_smells_by_rank_asc(file: str | Path) -> None:
    """
    Sorts an existing ground-truth file in-place by Rank ascending.
    """
    file = Path(file)
    df = pd.read_csv(file, sep="|", engine="python")
    df["Rank"] = pd.to_numeric(df["Rank"], errors="coerce")
    df = df.sort_values(by="Rank", ascending=True).reset_index(drop=True)
    df.to_csv(file, sep="|", index=False)


def write_evaluation_report(ground_truth: str, out_dir: str | Path, args: argparse.Namespace) -> Path:
    """
    Writes a minimal JSON evaluation report into out_dir, using the pipeline-specific
    default LLM output filename.
    """
    out_dir = Path(out_dir)
    llm_filename = "agent_output.csv" if args.pipeline == "agent" else "llm_output.csv"
    llm_file = out_dir / llm_filename

    metrics = ranking_computation(ground_truth, llm_file)
    if metrics is None:
        raise ValueError("ranking_computation returned None (likely missing/hallucinated IDs)")

    report = {
        "timestamp": datetime.now().isoformat(),
        "project name": args.project_name,

        "pipeline": args.pipeline,
        "llm_provider": args.llm_provider,
        "temperature": getattr(args, "temperature", None),
        "max_tokens": getattr(args, "max_tokens", None),

        "use_git": args.include_git_stats,
        "use_pylint": args.run_pylint_astroid,
        "use_code": (getattr(args, "code_context_mode", "analysis") == "code"),

        "metrics": metrics,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"evaluation__{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report_path

if __name__ == "__main__":
    args = argparse.Namespace(
        pipeline="rag",
        project_name="simapy",
        llm_provider="azure",
        include_git_stats=True,
        run_pylint_astroid=False,
        code_context_mode="analysis",
        temperature=1.0,
        max_tokens=40000,
    )

    write_evaluation_report(
        "src/prioritizer/data/ground_truth/prioritized_smells_simapy.csv", 
        "experiments/baseline_rag_model_gpt-oss_120b-cloud", 
        args
    )
