from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Set, Optional
from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError, GitCommandError


def fetch_all_from_remote(repo: Repo, remote: str = "origin") -> None:
    """Best-effort fetch. Never raises (by design)."""
    try:
        is_shallow = repo.git.rev_parse("--is-shallow-repository").strip() == "true"
    except Exception:
        is_shallow = False

    if is_shallow:
        try:
            repo.git.fetch("--unshallow")
        except Exception:
            try:
                repo.git.fetch(remote, "--unshallow")
            except Exception:
                pass

    try:
        repo.git.fetch("--all", "--tags", "--prune")
    except Exception:
        pass


def fetch_and_basic_stats(
    repo_path: str,
    rev: str = "--all",
    *,
    do_fetch: bool = True,
) -> Dict[str, Any]:
    """
    Compute repo-level Git stats in a single pass over commits reachable from `rev`.

    Returns a dict with:
      - ok: bool
      - error: str (if ok=False)
      - repository_name, repo_path, rev_scope
      - total_commits, commits_last_30_days, commits_last_90_days
      - contributors
      - repo_age_days (since oldest commit in rev)
      - last_commit_days (since newest commit in rev)
    """
    repo_name = repo_path.rstrip("/").split("/")[-1]

    try:
        repo = Repo(repo_path)
    except (InvalidGitRepositoryError, NoSuchPathError) as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "repository_name": repo_name,
            "repo_path": repo_path,
            "rev_scope": rev,
        }

    if do_fetch:
        fetch_all_from_remote(repo)

    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    cutoff_90 = now - timedelta(days=90)

    total_commits = 0
    commits_last_30 = 0
    commits_last_90 = 0
    contributors: Set[str] = set()

    latest_dt: Optional[datetime] = None
    oldest_dt: Optional[datetime] = None

    try:
        for c in repo.iter_commits(rev):
            total_commits += 1

            dt = c.committed_datetime
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            if latest_dt is None:
                latest_dt = dt
            oldest_dt = dt 

            if dt >= cutoff_30:
                commits_last_30 += 1
            if dt >= cutoff_90:
                commits_last_90 += 1

            email = getattr(c.author, "email", None)
            name = getattr(c.author, "name", None)
            key = (email or "").strip().lower() or (name or "").strip().lower()
            if key:
                contributors.add(key)

    except GitCommandError as e:
        return {
            "ok": False,
            "error": f"GitCommandError while iterating commits for rev='{rev}': {e}",
            "repository_name": repo_name,
            "repo_path": repo_path,
            "rev_scope": rev,
        }

    if total_commits == 0 or latest_dt is None or oldest_dt is None:
        return {
            "ok": True,
            "repository_name": repo_name,
            "repo_path": repo_path,
            "rev_scope": rev,
            "total_commits": 0,
            "commits_last_30_days": 0,
            "commits_last_90_days": 0,
            "contributors": 0,
            "repo_age_days": 0,
            "last_commit_days": 0,
        }

    return {
        "ok": True,
        "repository_name": repo_name,
        "repo_path": repo_path,
        "rev_scope": rev,
        "total_commits": total_commits,
        "commits_last_30_days": commits_last_30,
        "commits_last_90_days": commits_last_90,
        "contributors": len(contributors),
        "repo_age_days": (now - oldest_dt).days,
        "last_commit_days": (now - latest_dt).days,
    }


def build_git_repo_input_for_llm(repo_path: str, rev: str = "--all") -> str:
    repo_info = fetch_and_basic_stats(repo_path, rev=rev)

    if not repo_info.get("ok", False):
        name = repo_info.get("repository_name", repo_path.split("/")[-1])
        scope = repo_info.get("rev_scope", rev)
        err = repo_info.get("error", "unknown error")
        return (
            "<git_repo_context>\n"
            f"repo: {name}\n"
            f"scope: {scope}\n"
            f"status: error\n"
            f"error: {err}\n"
            "</git_repo_context>\n"
        )

    name = repo_info["repository_name"]
    scope = repo_info["rev_scope"]

    return (
        "<git_repo_context>\n"
        f"repo: {name}\n"
        f"scope: {scope}\n"
        f"age_days: {repo_info['repo_age_days']}\n"
        f"days_since_last_commit: {repo_info['last_commit_days']}\n"
        f"commits_total: {repo_info['total_commits']}\n"
        f"commits_last_30d: {repo_info['commits_last_30_days']}\n"
        f"commits_last_90d: {repo_info['commits_last_90_days']}\n"
        f"contributors: {repo_info['contributors']}\n"
        "</git_repo_context>\n"
    )

if __name__ == "__main__":
    stats = build_git_repo_input_for_llm("test_projects/simapy")
    print(stats)


"""
import statements between files too see which files are central to the repo"""