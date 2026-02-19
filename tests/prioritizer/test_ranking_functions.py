from pathlib import Path
import pytest

from prioritizer.evaluation.evaluation import (
    format_output_from_llm_to_csv_format,
    ndcg_ranking_using_only_id,
    ndcg_based_on_severity_of_smells,
    EXPECTED_COLS,
    ranking_computation
)

def test_format_output_with_header(tmp_path: Path):
    llm_text = """\
Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization
1|10|Long Method|foo|foo.py|High|Too long
2|11|Feature Envy|bar|bar.py|Medium|Envious
"""
    llm_file = tmp_path / "llm_output.txt"
    llm_file.write_text(llm_text)

    df = format_output_from_llm_to_csv_format(llm_file)

    assert list(df.columns) == EXPECTED_COLS
    assert df.shape == (2, len(EXPECTED_COLS))
    assert df.loc[0, "Rank"] == 1
    assert df.loc[1, "Name"] == "bar"


def test_format_output_without_header(tmp_path: Path):
    # LLM sometimes omits header; function should assign EXPECTED_COLS when column count matches.
    llm_text = """\
1|7|Long File|alpha|alpha.py|Low|Large file
2|8|Cyclic Dependency|beta|beta.py|High|Dependency cycle
"""
    llm_file = tmp_path / "llm_output_no_header.txt"
    llm_file.write_text(llm_text)

    df = format_output_from_llm_to_csv_format(llm_file)

    assert list(df.columns) == EXPECTED_COLS
    assert df.loc[0, "Name of Smell"] == "Long File"
    assert df.loc[1, "File"] == "beta.py"


def test_format_output_strips_markdown_fences(tmp_path: Path):
    llm_text = """\
Some intro text
```markdown
Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization
1|1|Long Method|foo|foo.py|High|Because
```
"""
    llm_file = tmp_path / "llm_with_fence.txt"
    llm_file.write_text(llm_text)

    df = format_output_from_llm_to_csv_format(llm_file)

    assert df.loc[0, "Rank"] == 1
    assert df.loc[0, "Name"] == "foo"


def test_ndcg_perfect_match():
    gt = ["a", "b", "c"]
    llm = ["a", "b", "c"]
    assert ndcg_ranking_using_only_id(gt, llm) == 1.0

def test_ndcg_standard_perfect_ranking():
    gt_ids = {
        "1": 3,
        "2": 2,
        "3": 1
    }

    llm_ids = ["1", "2", "3"] 

    score = ndcg_based_on_severity_of_smells(llm_ids, gt_ids)

    assert score == pytest.approx(1.0)

def test_ranking_function():
    metrics = ranking_computation(
        "tests/prioritizer/example_data/example_ground_truth.csv",
        "tests/prioritizer/example_data/example_llm_output.csv"
    )

    assert metrics["n_gt"] == 15
    assert metrics["n_llm"] == 15
    assert metrics["n_missing"] == 0
    assert metrics["missing_ids"] == []

    assert metrics["tau"] == pytest.approx(0.2, abs=1e-12)
    assert metrics["rho"] == pytest.approx(0.30357142857142855, abs=1e-12)
    assert metrics["rbo"] == pytest.approx(0.5939691789691789, rel=1e-12)
    