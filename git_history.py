from collections import defaultdict
from datetime import datetime
import statistics
from typing import Dict, List, Optional, Set, Any
from git import Repo


def normalize(file_stats: Dict[str, float]) -> None:
    """
    Normalize the numeric scores in-place to a [0,1] range.
    """
    scores = list(file_stats.values())
    min_score, max_score = min(scores), max(scores)

    for f in file_stats:
        file_stats[f] = (file_stats[f] - min_score) / (max_score - min_score + 1e-9)


def calculate_change_proneness_score(
    commit_count: Dict[str, float],
    commit_churn: Dict[str, float],
    commit_score: Dict[str, float],
) -> Dict[str, float]:
    """
    Compute a weighted change-proneness score per file.
    """
    change_proneness_score: Dict[str, float] = {}

    normalize(commit_count)
    normalize(commit_churn)
    normalize(commit_score)

    for file in commit_count:
        change_proneness_score[file] = (
            (2 / 5) * commit_count[file]
            + (1 / 5) * commit_churn[file]
            + (2 / 5) * commit_score[file]
        )

    return change_proneness_score


def get_git_stats(
    repo: Repo,
    file_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Extract raw Git evolution metrics for files in the repo.

    Args:
        repo: A GitPython Repo instance pointing to the project repository.
        file_filter: If provided, only metrics for files containing this substring
                     in the path will be returned.

    Returns:
        List[Dict[str, Any]]: A list of per-file Git metric records including
        commit history, churn, recency, contributor count, etc.
    """
    commits = list(repo.iter_commits(repo.active_branch.name))

    commit_count: Dict[str, int] = defaultdict(int)
    churn: Dict[str, int] = defaultdict(int)
    bug_fix_commits: Dict[str, int] = defaultdict(int)
    commit_dates: Dict[str, List[int]] = defaultdict(list)
    authors: Dict[str, Set[str]] = defaultdict(set)
    commit_types: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for commit in commits:
        is_bugfix = any(
            k in commit.message.lower()
            for k in ["fix", "bug", "issue", "error"]
        )
        for file, stats in commit.stats.files.items():
            if file_filter and file_filter not in file:
                continue

            change_type = stats.get("change_type", "M")
            commit_types[file][change_type] += 1

            commit_count[file] += 1
            commit_dates[file].append(commit.committed_date)
            churn[file] += stats["lines"]
            authors[file].add(commit.author.email)

            if is_bugfix:
                bug_fix_commits[file] += 1

    now = datetime.now().timestamp()
    results: List[Dict[str, Any]] = []

    for f in commit_count:
        dates = sorted(commit_dates[f])
        first, last = datetime.fromtimestamp(dates[0]), datetime.fromtimestamp(dates[-1])
        age_days = (now - dates[0]) / 86400
        recency_days = (now - dates[-1]) / 86400

        mean_gap = (
            statistics.mean(
                [(dates[i] - dates[i - 1]) / 86400 for i in range(1, len(dates))]
            ) if len(dates) > 1 else age_days
        )

        results.append(
            {
                "file": f,
                "commit_count": commit_count[f],
                "churn": churn[f],
                "bug_fix_commits": bug_fix_commits[f],
                "developer_count": len(authors[f]),
                "avg_commit_size": churn[f] / commit_count[f],
                "first_commit_date": first.isoformat(),
                "last_commit_date": last.isoformat(),
                "days_since_last_commit": recency_days,
                "mean_gap_days": mean_gap,
                "commit_type_counts": dict(commit_types[f]),
            }
        )

    return results


def create_git_stats_analysis_report(
    git_metrics: List[Dict[str, Any]]
) -> str:
    """
    Build a human-readable analytical summary of Git metrics for each file.
    Helps an LLM understand file stability/risk.
    """
    if not git_metrics:
        return "No Git history found for the analyzed files."

    report_lines: List[str] = []

    report_lines.append("------ GIT-BASED CODE STABILITY AND EVOLUTION REPORT ------\n")

    for m in sorted(git_metrics, key=lambda x: x.get("commit_count", 0), reverse=True):
        file_name = m.get("file", "unknown file")

        commit_count = m.get("commit_count", 0)
        churn = m.get("churn", 0)
        dev_count = m.get("developer_count", 0)
        last_mod_days = int(m.get("days_since_last_commit", 9999))

        activity_level = (
            "very active" if commit_count > 50
            else "moderately active" if commit_count > 10
            else "rarely changed"
        )

        recency_label = (
            "recently modified" if last_mod_days < 30
            else "inactive for a while" if last_mod_days < 365
            else "stagnant or legacy code"
        )

        summary = (
            f"File: {file_name}\n"
            f"- Commit frequency: {commit_count} ({activity_level})\n"
            f"- Total churn (lines changed): {churn}\n"
            f"- Developers involved: {dev_count}\n"
            f"- Last modified: {last_mod_days} days ago ({recency_label})\n"
        )

        report_lines.append(summary)
        report_lines.append("-" * 60 + "\n")

    return "\n".join(report_lines)


def build_report(
    repo: Repo,
    filepath: str,
) -> str:
    """
    Full pipeline: gather metrics for a given file, build a formatted analysis report.
    """
    git_metrics = get_git_stats(repo, filepath)
    return create_git_stats_analysis_report(git_metrics)

# For debugging purposes
if __name__ == "__main__":
    repo = Repo("projects/text_classification")
    c = build_report(repo, "app.py")

    print(c)
