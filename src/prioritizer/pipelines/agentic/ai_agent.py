from prioritizer.analysis import build_project_structure, get_code_segment_from_file_based_on_line_number
from prioritizer.ingestion.chunking import convert_chunked_text_to_haystack_documents
from prioritizer.llm.analyze_code_segment import analyze_code_segments_via_ai
from prioritizer.llm.prompt_template import PROMPT_TEMPLATE
from prioritizer.ingestion.smells_ingestion import read_and_store_relevant_smells, add_further_context

from prioritizer.pipelines.agentic.agent_state import State
from prioritizer.pipelines.agentic.system_prompt import SYSTEM_PROMPT

from pathlib import Path
import csv

from git import Repo

import os
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END

from langchain_openai import AzureChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage


def load_smells(state: State) -> State:
    smells_to_search_for = state.get("smell_types")

    smells = read_and_store_relevant_smells(smells_to_search_for)

    return {
        **state,
        "smells": smells
    }

def create_more_context(state: State) -> State:
    smells = state.get("smells") or []

    git_stats = state.get("use_git")
    pylint = state.get("use_pylint")
    repo = state.get("repo")

    smells = add_further_context(repo, smells, git_stats, pylint)

    return {
        **state,
        "smells": smells
    }

def analyze_code_segments_with_agent(state: State) -> State:
    smells = state.get("smells") or []
    use_analysis = state.get("use_code") == False
    smells = analyze_code_segments_via_ai(smells, state.get("llm"), use_analysis)
    prompt_tokens = state.get("prompt_tokens")


    return {
        **state,
        "smells": smells
    }

def _format_smell_for_prompt(s: Dict[str, Any], idx: int, state: State) -> str:
    code_block = "\n"

    if state.get("use_code"): code_block = f"""\
    \nCode segment:
    {s.get("code_segment")}\n
    """.strip()


    return f"""\
[{idx}], id={s.get("index")}, smell={s.get("name")}, category={s.get("type_of_smell")},
file={s.get("file_path")} line={s.get("line_number")}

analyzer_description:
{s.get("description")}

git_analysis:
{s.get("git_analysis")}

pylint_report:
{s.get("pylint_report")}
{code_block}
ai_code_segment_summary:
{s.get("ai_code_segment_summary")}
""".strip()

def prioritize_smells_node(state: State) -> State:
    smells = state.get("smells") or []
    llm = state.get("llm")

    if not smells:
        return {**state, "output_text": "No smells to prioritize."}

    smells_block = "\n\n---\n\n".join(
        _format_smell_for_prompt(s, idx=i+1, state=state) for i, s in enumerate(smells)
    )

    out_dir = state.get("out_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = out_dir / "prompt.txt"

    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(smells_block)

    user_prompt = f"""\
Rank the following smell instances by refactoring priority (highest priority first).

Smell instances:
{smells_block}

"""

    resp = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    text = (resp.content or "").strip()

    return {
        **state, 
        "output_text": text if text else None
    }

def write_prioritization_report(state: State) -> State:
    out_dir = state.get("out_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    llm_output_file = out_dir / "agent_output.csv"

    with open(llm_output_file, "w", encoding="utf-8") as f:
        csv.writer(f).writerow([state.get("output_text")])

    return state

def run_agent_pipeline(args, smells):

    safe_model = args.ollama_model.replace(":", "_").replace("/", "_") if args.llm_provider == "ollama" else "azure"
    folder_name = f"{args.output_dir}_agent_model_{safe_model}"
    experiments_dir = Path("experiments") / folder_name
 
    api_key = os.environ.get("UIO_SE_GROUP_GPT_API_KEY")
    resource_name = os.environ.get("UIO_SE_GROUP_GPT_RESOURCE_NAME")
    deployment_name = os.environ.get("UIO_SE_GROUP_GPT_DEPLOYMENT_NAME")
    api_version = os.environ.get("UIO_SE_GROUP_API_VERSION")

    endpoint_url = (
        f"https://{resource_name}.openai.azure.com/"
    )

    code_context_mode = getattr(args, "code_context_mode", "analysis")
    use_code = code_context_mode == "code"

    if args.llm_provider == "azure":
        llm = AzureChatOpenAI(
            azure_endpoint=endpoint_url,
            api_key=api_key,
            azure_deployment=deployment_name,
            api_version=api_version,
            temperature=1,
            max_tokens=40000,
            timeout=None,
            max_retries=2,
        )
    else:
        llm = ChatOllama(
            model=args.ollama_model,
            validate_model_on_init=True,
            temperature=0,
        )

    smells_graph = StateGraph(State)

    smells_graph.add_node("load_smells", load_smells)
    smells_graph.add_node("create_more_context", create_more_context)
    smells_graph.add_node("analyze_code_segments_with_agent", analyze_code_segments_with_agent)
    smells_graph.add_node("prioritize_smells_node", prioritize_smells_node)
    smells_graph.add_node("write_prioritization_report", write_prioritization_report)

    smells_graph.add_edge(START, "load_smells")
    smells_graph.add_edge("load_smells","create_more_context")
    smells_graph.add_edge("create_more_context","analyze_code_segments_with_agent")
    smells_graph.add_edge("analyze_code_segments_with_agent", "prioritize_smells_node")
    smells_graph.add_edge("prioritize_smells_node", "write_prioritization_report")
    smells_graph.add_edge("write_prioritization_report", END)

    compiled_graph = smells_graph.compile()

    compiled_graph.invoke({
        "smell_types": smells,
        "smells": None,
        "use_git": args.include_git_stats,
        "use_pylint": args.run_pylint_astroid,
        "use_code": use_code,
        "repo": Repo(f"test_projects/{args.project_name}"),
        "llm": llm,
        "out_dir": experiments_dir,
        "output_text": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
          })

    (experiments_dir / "agent_graph.png").write_bytes(
        compiled_graph.get_graph().draw_mermaid_png()
    )


"""
What “agentic advantage” should mean in your context

An agent is useful when it can:

decompose the ranking task into smaller reasoning tasks,

iterate with checks and corrections,

adaptively fetch missing evidence, and

produce structured intermediate outputs you can evaluate.

Your baseline RAG cannot do these cleanly because it is one-shot.

Step 1: Add structure + validation (fast and immediately “agentic”)

Node A: build smell evidence cards (deterministic)

Node B: per-smell scoring (LLM produces strict JSON)

Node C: global ranking (LLM uses the JSON)

Node D: validate output; repair if needed

This is the highest ROI and easiest to justify.

Step 2: Add adaptive RAG per smell

Node: retrieve_research(smell_type) for each smell

compress retrieved chunks into “evidence highlights”

use those highlights in scoring and ranking

This will differentiate agentic pipeline from Haystack baseline clearly.

Implement per-smell structured scoring (map) + global rank synthesis (reduce).

Add an output validator + repair loop to guarantee completeness and rule compliance.

If you still want “external knowledge,” do local RAG over curated references, not live web browsing.



bash run_analyzer.sh gitmetrics --llm-provider ollama --add-project-structure --pipeline agent --ollama-model gemini-3-flash-preview:cloud

bash run_analyzer.sh gitmetrics --llm-provider azure --add-project-structure --pipeline agent


Switch from rank to High, medium and low. MAybe do both and compare the result to each other.

"""