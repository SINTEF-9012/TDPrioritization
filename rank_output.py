import pandas as pd
from io import StringIO
from scipy.stats import kendalltau, spearmanr
import numpy as np
from sklearn.metrics import ndcg_score
import rbo
import re

def ndcg(gt, llm):
    relevance_map = {item: len(gt) - i for i, item in enumerate(gt)}

    # Build relevance arrays for each position
    y_true = np.array([[relevance_map[item] for item in gt]])
    y_pred = np.array([[relevance_map.get(item, 0) for item in llm]])

    return ndcg_score(y_true, y_pred)


def format_output_from_llm_to_csv_format(llm_output):
    with open(llm_output, "r") as f: 
        raw_text = f.read()

    # --- Step 1: Remove Markdown-style fences (e.g., ```csv or ```text) ---
    text = re.sub(r"(?s)^.*?```[a-zA-Z]*\s*", "", raw_text)  # remove everything up to and including ```csv
    text = re.sub(r"\s*```.*$", "", text)                    # remove trailing ```
    text = text.strip()

    text = (
        text
        .replace("“", '"')
        .replace("”", '"')
        .replace("-", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace('""', '"')
        .strip()
    )

    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]

    lines = text.splitlines()

    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^-+\|(-+\|?)+$", line):  # matches ---|---|--- patterns
            continue
        if line.lower().startswith("rank|") and cleaned_lines and "rank|" in cleaned_lines[0].lower():
            continue  # skip duplicate headers
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    try:
        df = pd.read_csv(StringIO(text), sep="|", engine="python")
        for col in df.select_dtypes(include="object"):
            df[col] = df[col].map(lambda x: x.strip().replace("'", "").replace('"', "") if isinstance(x, str) else x)

    except Exception as e:
        print("CSV parsing failed, showing cleaned text for debugging:")
        print(text)
        raise e
            
    return df

def ranking_function(ground_truth, llm_output):
    formatted_llm_output_df = format_output_from_llm_to_csv_format(llm_output)
    ground_truth_df = pd.read_csv(ground_truth, sep=",", engine="python")

    order1 = list(formatted_llm_output_df["Name"] + ";" + formatted_llm_output_df["File"])
    order2 = list(ground_truth_df["Name"] + ";" + ground_truth_df["File"])
    
    ranks1 = ranks2 = None
    try:
        ranks1 = [order1.index(x) for x in order2]
        ranks2 = list(range(len(order2)))
    except Exception as e:
        print("Error occured likely due to hallucinations during llm processing.", e)
        return None
    else:
        # Kendall’s Tau (−1 = opposite order, 1 = identical)
        tau, _ = kendalltau(ranks1, ranks2)
        print("Kendall's Tau:", tau)

        rho, _ = spearmanr(ranks1, ranks2)
        print("Spearman's Rho:", rho)

        ndcg_score = ndcg(order1, order2)

        print("nDCG: ", ndcg_score)

        rbo_score = rbo.RankingSimilarity(ranks1, ranks2).rbo()

        print("RBO: ", rbo_score)


if __name__ == "__main__":
    ranking_function("ground_truth.csv", "baseline_gpt-oss:20b-cloud/llm_output.csv")