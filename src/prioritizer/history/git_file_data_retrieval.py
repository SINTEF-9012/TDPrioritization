from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, List
from git import Repo

from pydriller import Repository

ERROR_KEYWORDS = ["fix", "bug", "issue", "error"]


def count_file_commits_last_n_days(
    repo: Repo,
    days: int,
    rev: str = "--all"
) -> Dict[str, int]:
    """
    Count how many commits touched each file in the last N days.

    Returns:
        Dict[file_path, commit_count]
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    file_commit_counts: Dict[str, int] = defaultdict(int)

    for c in repo.iter_commits(rev):
        dt = c.committed_datetime
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        if dt < cutoff:
            break

        for file_path in c.stats.files.keys():
            file_commit_counts[file_path] += 1

    return dict(file_commit_counts)


def count_file_commits_last_n_days_pydriller(
    repo_path: str,
    days: int,
    *,
    file_filter: Optional[str] = None,
) -> Dict[str, int]:
    """
    Count how many commits touched each file in the last N days (PyDriller).

    Args:
        repo_path: Path to local repo
        days: Window size in days
        file_filter: Optional substring filter (e.g., "src/")

    Returns:
        Dict[path, commit_count] for files modified within the window.
    """
    counts: Dict[str, int] = defaultdict(int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    current_files = {
        item.path
        for item in repo.tree().traverse()
        if item.type == "blob"
    }

    for c in Repository(repo_path, only_no_merge=True).traverse_commits():
        dt = c.committer_date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        if dt < cutoff: continue

        for mf in c.modified_files:
            path = mf.new_path or mf.old_path
            if not path or path not in current_files: continue

            if file_filter and file_filter not in path: continue
            counts[path] += 1

    return dict(counts)

def mine_file_lifetime_metrics(repo_path: str, file: str = None) -> Dict[str, Dict[str, Any]]:
    """
    For each current file in the repo, compute:

        - commit_count
        - churn_total (added + deleted lines)
        - first_modified
        - last_modified
        - days_since_last_change

    Returns:
        Dict[file_path, metrics_dict]
    """

    commit_count = defaultdict(int)
    churn_total = defaultdict(int)
    churn_last_30_days = defaultdict(int)
    added_lines = defaultdict(int)
    deleted_lines = defaultdict(int)
    bug_fix_commits = defaultdict(int)
    first_seen = {}
    last_seen = {}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)

    for c in Repository(repo_path, only_no_merge=True).traverse_commits():

        dt = c.committer_date
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)

        msg = (c.msg or "").lower()
        is_error_commit = any(
            k in msg
            for k in ERROR_KEYWORDS
        )

        for mf in c.modified_files:
            path = mf.new_path or mf.old_path

            if not path: continue
            if file and path != file: continue
            if is_error_commit: bug_fix_commits[path] += 1

            a = mf.added_lines or 0
            d = mf.deleted_lines or 0

            commit_count[path] += 1
            added_lines[path] += a
            deleted_lines[path] += d
            churn_total[path] += (a + d)

            if dt >= cutoff: churn_last_30_days[path] += (a + d)

            if path not in first_seen: first_seen[path] = dt

            last_seen[path] = dt 

    result: Dict[str, Dict[str, Any]] = {}

    for path in commit_count.keys():
        last_dt = last_seen[path]
        first_dt = first_seen[path]

        result[path] = {
            "commit_count": commit_count[path],
            "churn_total": churn_total[path],
            "churn_last_30_days": churn_last_30_days[path],
            "total_added_lines": added_lines[path],
            "total_deleted_lines": deleted_lines[path],
            "first_modified": first_dt.date().isoformat(),
            "last_modified": last_dt.date().isoformat(),
            "error_fixing_commits": bug_fix_commits[path],
            "days_since_last_change": (now - last_dt).days,
        }

    return result


def build_git_input_for_llm(project_name: str, file: str) -> str:
    """
    Build a compact, LLM-friendly context string for a single file's Git metrics.

    Expects (if available) these keys in metrics[file]:
      - commit_count
      - churn_total
      - total_added_lines
      - total_deleted_lines
      - churn_last_30_days (optional)
      - first_modified
      - last_modified
      - days_since_last_change
      - error_fixing_commits
    """
    metrics = mine_file_lifetime_metrics(project_name, file)

    if not metrics:
        return "GIT CONTEXT (per-file)\n(no git metrics provided)\n"

    m = metrics.get(file)
    if not m:
        return (
            "GIT CONTEXT (per-file)\n"
            f"File: {file}\n"
            "No git metrics found for this file.\n"
        )

    commit_count = m.get("commit_count", 0)
    churn_total = m.get("churn_total", 0)
    added = m.get("total_added_lines", 0)
    deleted = m.get("total_deleted_lines", 0)
    churn_30d = m.get("churn_last_30_days", 0)
    fixes = m.get("error_fixing_commits", 0)

    first_mod = m.get("first_modified", "unknown")
    last_mod = m.get("last_modified", "unknown")
    days_since = m.get("days_since_last_change", "unknown")

    return (
        f"<git_file_data>\n"
        f"File: {file}\n"
        f"Units:\n"
        f"- churn = lines_added + lines_deleted\n"
        f"\n"
        f"Metrics:\n"
        f"- commits_total: {commit_count}\n"
        f"- churn_total: {churn_total} (added={added}, deleted={deleted})\n"
        f"- churn_last_30_days: {churn_30d}\n"
        f"- error_fixing_commits: {fixes}  # heuristic from commit messages\n"
        f"- first_modified: {first_mod}\n"
        f"- last_modified: {last_mod}\n"
        f"- days_since_last_change: {days_since}\n"
        f"</git_file_data>\n"
    )

if __name__ == "__main__":
    repo = Repo("test_projects/simapy")
    dic = count_file_commits_last_n_days_pydriller("test_projects/simapy", 500)
    dic2 = count_file_commits_last_n_days(repo, 500)

    output = build_git_input_for_llm("test_projects/simapy", "src/simapy/sima/hydro/qtfinput.py")

    print(output)
