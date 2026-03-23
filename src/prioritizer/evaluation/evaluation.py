import pandas as pd
from io import StringIO
from scipy.stats import kendalltau, spearmanr
import numpy as np
from sklearn.metrics import accuracy_score, cohen_kappa_score
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

def gain(r):
    return 2**r - 1 

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

def _keep_only_table_block(text: str) -> str:
    lines = text.splitlines()
    kept = []
    started = False

    for line in lines:
        stripped = line.strip()
        normalized = stripped.lower().replace(" ", "")

        if not started and normalized.startswith("rank|id|nameofsmell|"):
            started = True
            kept.append(stripped)
            continue

        if started:
            if "|" in stripped:
                kept.append(stripped)
            else:
                break

    return "\n".join(kept).strip() if kept else text.strip()

def _normalize_eval_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = [str(c).strip() for c in df.columns]

    df["Id"] = pd.to_numeric(df["Id"], errors="raise").astype(int)

    if "Severity" in df.columns:
        df["Severity"] = df["Severity"].astype(str).str.strip().str.upper()

    return df

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

def severity_label_accuracy(gt_df: pd.DataFrame, llm_df: pd.DataFrame) -> dict:
    """
    Measures how accurately the LLM assigned severity labels compared to ground truth.
    Matches smells by Id.
    """
    merged = gt_df.merge(llm_df[["Id", "Severity"]], on="Id", suffixes=("_gt", "_llm"))
    
    gt_labels  = merged["Severity_gt"].str.strip().str.upper().tolist()
    llm_labels = merged["Severity_llm"].str.strip().str.upper().tolist()

    return {
        "accuracy": accuracy_score(gt_labels, llm_labels),
        "cohen_kappa": cohen_kappa_score(gt_labels, llm_labels),
        "n_matched": len(merged),
        "n_unmatched": len(gt_df) - len(merged),
    }

def severity_label_accuracy_ordinal(gt_df: pd.DataFrame, llm_df: pd.DataFrame) -> dict:
    """
    Measures severity label accuracy with ordinal penalties.
    A label that is 2 steps away (HIGH vs LOW) penalises more than 1 step away (HIGH vs MEDIUM).
    
    Ordinal scale: LOW=1, MEDIUM=2, HIGH=3
    Penalty per smell = |gt_rank - llm_rank| / max_possible_distance (2)
    Score per smell   = 1 - penalty  (1.0 = exact, 0.5 = one step off, 0.0 = two steps off)
    """
    MAX_DISTANCE = 2

    merged = gt_df.merge(llm_df[["Id", "Severity"]], on="Id", suffixes=("_gt", "_llm"))

    gt_labels  = merged["Severity_gt"].str.strip().str.upper().tolist()
    llm_labels = merged["Severity_llm"].str.strip().str.upper().tolist()

    scores = []
    details = []
    for id_, gt, llm in zip(merged["Id"].tolist(), gt_labels, llm_labels):
        gt_rank  = SEVERITY_MAP.get(gt,  None)
        llm_rank = SEVERITY_MAP.get(llm, None)

        if gt_rank is None or llm_rank is None:
            continue

        distance = abs(gt_rank - llm_rank)
        score    = 1.0 - (distance / MAX_DISTANCE)
        scores.append(score)
        details.append({"id": id_, "gt": gt, "llm": llm, "distance": distance, "score": score})

    ordinal_accuracy = float(np.mean(scores)) if scores else 0.0

    gt_numeric  = [SEVERITY_MAP[l] for l in gt_labels  if l in SEVERITY_MAP]
    llm_numeric = [SEVERITY_MAP[l] for l in llm_labels if l in SEVERITY_MAP]
    try:
        weighted_kappa = float(cohen_kappa_score(gt_numeric, llm_numeric, weights="linear"))
    except Exception:
        weighted_kappa = float("nan")

    exact     = sum(1 for d in details if d["distance"] == 0)
    one_off   = sum(1 for d in details if d["distance"] == 1)
    two_off   = sum(1 for d in details if d["distance"] == 2)

    return {
        "ordinal_accuracy": ordinal_accuracy,
        "weighted_kappa": weighted_kappa,
        "exact_matches": exact,
        "one_step_off": one_off,
        "two_steps_off": two_off,
        "n_matched": len(scores),
        "n_unmatched": len(gt_df) - len(scores),
        "details": details,
    }

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
    df = df.copy()
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    for col in df.columns:
        if df[col].dtype == "object":
            df.loc[:, col] = df[col].map(
                lambda x: x.strip().strip("'").strip('"') if isinstance(x, str) else x
            )

    return df

def _drop_embedded_header_rows(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for col_name in ("Rank", "Id", "Severity"):
        if col_name in df.columns:
            df = df[df[col_name].astype(str).str.strip().str.upper() != col_name.upper()].copy()

    return df

def format_output_from_llm_to_csv_format(llm_output: str | Path) -> pd.DataFrame:
    llm_output = Path(llm_output)
    raw_text = llm_output.read_text(encoding="utf-8")

    text = _strip_code_fences(raw_text)
    text = text.translate(_NORMALIZE_CHARS).replace('""', '"').strip()
    text = _strip_wrapping_quotes(text)
    text = _clean_lines(text)
    text = _keep_only_table_block(text)

    parse_errors: List[Exception] = []

    for header_setting in (0, None):
        try:
            df = pd.read_csv(StringIO(text), sep=r"\|", engine="python", header=header_setting)
            df = _finalize_df(df)

            if set(EXPECTED_COLS).issubset(set(df.columns)):
                df = df[EXPECTED_COLS].copy()
                df = _drop_embedded_header_rows(df)
                return df

            if header_setting is None and df.shape[1] == len(EXPECTED_COLS):
                df = df.copy()
                df.columns = EXPECTED_COLS
                df = _drop_embedded_header_rows(df)
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


def ranking_computation(ground_truth: str | Path,llm_output: str | Path) -> Optional[dict]:
    llm_df = format_output_from_llm_to_csv_format(llm_output)
    gt_df = _load_ground_truth_df(ground_truth)

    llm_df = _normalize_eval_df(llm_df)
    gt_df = _normalize_eval_df(gt_df)

    llm_ids = [str(x) for x in llm_df["Id"].tolist()]
    gt_ids  = [str(x) for x in gt_df["Id"].tolist()]

    ranks_llm, ranks_gt, missing = _ranks_with_missing_penalty(gt_ids, llm_ids)
    tau, _ = kendalltau(ranks_llm, ranks_gt)
    rho, _ = spearmanr(ranks_llm, ranks_gt)

    severity_acc         = severity_label_accuracy(gt_df, llm_df)
    severity_acc_ordinal = severity_label_accuracy_ordinal(gt_df, llm_df)

    metrics = {
        "ranking": {
            "ndcg": float(ndcg_ranking_using_only_id(gt_ids, llm_ids)),
            "kendall_tau": float(tau) if tau is not None else float("nan"),
            "spearman_rho": float(rho) if rho is not None else float("nan"),
            "rbo": float(rbo.RankingSimilarity(llm_ids, gt_ids).rbo()),
        },
        "severity_labelling": {
            "accuracy": severity_acc["accuracy"],
            "cohen_kappa": severity_acc["cohen_kappa"],
            "ordinal_accuracy": severity_acc_ordinal["ordinal_accuracy"],
            "weighted_kappa": severity_acc_ordinal["weighted_kappa"],
            "exact_matches": severity_acc_ordinal["exact_matches"],
            "one_step_off": severity_acc_ordinal["one_step_off"],
            "two_steps_off": severity_acc_ordinal["two_steps_off"],
        },
        "coverage": {
            "n_gt": int(len(gt_ids)),
            "n_llm": int(len(llm_ids)),
            "n_matched": severity_acc["n_matched"],
            "n_unmatched": severity_acc["n_unmatched"],
            "n_missing": int(len(missing)),
            "missing_ids": missing,
        },
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
    llm_filename = "output.csv" if args.pipeline == "agent" else "output.csv"
    llm_file = out_dir / llm_filename

    metrics = ranking_computation(ground_truth, llm_file)
    if metrics is None:
        raise ValueError("ranking_computation returned None (likely missing/hallucinated IDs)")

    llm_df = format_output_from_llm_to_csv_format(llm_file)
    llm_output_records = llm_df.to_dict(orient="records")

    report = {
        "timestamp": datetime.now().isoformat(),
        "project name": args.project_name,

        "pipeline": args.pipeline,
        "llm_provider": args.llm_provider,
        "model": args.ollama_model if args.llm_provider == "ollama" else args.deployment,
        "temperature": getattr(args, "temperature", None),
        "max_tokens": getattr(args, "max_tokens", None),

        "Git data included": args.include_git_stats,
        "Pylint analysis included": args.run_pylint_astroid,
        "RAG included": args.use_rag,
        "Test coverage report": args.use_test_coverage,

        "Code context": args.code_context_mode,

        "metrics": metrics,
        "output": llm_output_records,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"evaluation__{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report_path

def mrr_for_high_severity(llm_ids, relevance_by_id):
    """Rank of first HIGH severity item in LLM output."""
    for i, id_ in enumerate(llm_ids):
        if relevance_by_id.get(id_, 0) == 3:
            return 1.0 / (i + 1)
    return 0.0

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
        deployment = "o4-mini",
        use_rag = False,
        use_test_coverage = False,
    )

    write_evaluation_report(
        "src/prioritizer/data/ground_truth/prioritized_smells_simapy.csv", 
        "experiments/agent_pipeline_azure_o4-mini", 
        args
    )
