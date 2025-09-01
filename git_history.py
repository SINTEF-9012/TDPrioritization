import git
from collections import defaultdict
import os
from datetime import datetime
import statistics

def normalize(file_stats: defaultdict): 
    scores = list(file_stats.values())
    min_score, max_score = min(scores), max(scores)

    for f in file_stats:
        file_stats[f] = (file_stats[f] - min_score) / (max_score - min_score + 1e-9)

def generate_score_for_commit_dates(commit_dates_for_files: defaultdict):
    if len(commit_dates_for_files) < 2: return 0

    file_stats = defaultdict()

    for file in commit_dates_for_files:
        commit_dates = commit_dates_for_files[file]
        commit_dates.sort()

        gaps = []
        for i in range(1, len(commit_dates)):
            # Time between the last two commits
            delta_days = (datetime.fromtimestamp(commit_dates[i]) - datetime.fromtimestamp(commit_dates[i-1])).days
            gaps.append(delta_days)

        if len(gaps) < 2: 
            file_stats[file] = 0 # Is there any use in doing anything differently when there are only two commits?
            continue

        mean_gap = statistics.mean(gaps)
        recency = (datetime.now() - datetime.fromtimestamp(commit_dates[-1])).days
        std_dev_gap = statistics.stdev(gaps)

        commit_history_score_for_file = 1/(mean_gap+1) + 1/(std_dev_gap+1) + 1/(recency+1) # TODO score value should be calculated in a better way?
        file_stats[file] = commit_history_score_for_file

    return file_stats

def calculate_change_proneness_score(commit_count, commit_churn, commit_score):
    change_proneness_score = defaultdict()

    normalize(commit_count)
    normalize(commit_churn)
    normalize(commit_score)

    for file in commit_count:
        change_proneness_score[file] = (2/5)*commit_count[file] + (1/5)*commit_churn[file] + (2/5)*commit_score[file]

    return change_proneness_score

def calculate_fault_proneness_score():
    ...

def analyze_repo(repo_path):
    """
    Analyze change-proneness and fault-proneness metrics for each file in a Git repo.
    
    Metrics extracted:
      - commit_count (change-proneness)
      - churn (lines added + deleted)
      - bug_fix_commits (fault-proneness proxy)
    """

    repo = git.Repo(repo_path)

    branch = repo.active_branch.name    
    print(f"[INFO] Using branch: {branch}")

    commits = list(repo.iter_commits(branch))

    # Data structures to hold metrics
    commit_count = defaultdict(int)      # how often file changes
    commit_dates = defaultdict(list)     # The dates for each commit for a file
    churn = defaultdict(int)             # added + deleted lines
    bug_fix_commits = defaultdict(int)   # how often file is in a bugfix commit

    for commit in commits:
        # Check if commit looks like a bugfix (simple heuristic)
        is_bugfix = any(word in commit.message.lower() for word in ["fix", "bug", "issue", "error"]) # TODO Can we change it so that we ignore the keyword if it is part of the file name?
        date = commit.committed_date

        for file in commit.stats.files:
            commit_count[file] += 1
            commit_dates[file].append(date)
            stats = commit.stats.files[file]
            churn[file] += stats["lines"]

            if is_bugfix:
                bug_fix_commits[file] += 1

    commits_score = generate_score_for_commit_dates(commit_dates)

    change_proneness_score = calculate_change_proneness_score(commit_count=commit_count, commit_churn=churn, commit_score=commits_score)

    print(change_proneness_score)

    # Collect results
    results = []
    for file_path in commit_count:
        results.append({
            "file": file_path,
            "commit_count": commit_count[file_path],
            "commit_score": commits_score[file_path],
            "churn": churn[file_path],
            "bug_fix_commits": bug_fix_commits[file_path],
        })

    return results


# For debugging purposes
if __name__ == "__main__":
    repo_path = "projects/system-design-primer" 
    metrics = analyze_repo(repo_path)

    # Pretty print results
    for m in metrics:
        print(
            f"{m['file']}: commits={m['commit_count']}, churn={m['churn']}, bugfix_commits={m['bug_fix_commits']}, commit_date_score={m['commit_score']}"
        )


# See if the LLM can create a scoring value itself and compare it to the way I have done it. 
# We have to give the LLM the actual metrics, scoring values should not be given to the llm. 
# Comparison - give it just the history (my current metrics), then the score, then the message. THen we can try to introduce agents. 

# Ground truth - How to meassure the correctness of the output. We choose two-three files, and anylyze the code smells and devide which are the most important. 
# We decide beforehand which file has the most important smell. 

# Ask Karthik which file/code smells are the most important. Use this as the ground truth for the correctness. 
# Soft test - Plausibility of the LLM when testing. 
# We need to find different ways of testing the plausibility of the LLMs. 
# Baseline - Asking the LLM to prioritize the code smells the provided in the documents. Which metrics should be part 
# the baseline. 
# Plasubility score - defined by myself - should be justified. 

# Make the use of LLMs scalable
# Alter the prompt template
# Add articles/documents to the RAG about code smells to help the LLM better prioritize.
# Structurize the output 
# Use remote API for LLMS
# Give code smells to an agent
# Use of agents in later iterations?
# Should I use sonarQube?

