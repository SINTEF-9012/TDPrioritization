from prioritizer.analysis import build_project_structure, get_code_segment_from_file_based_on_line_number
from prioritizer.llm.analyze_code_segment import analyze_code_segments_via_ai
from prioritizer.llm.prompt_template import PROMPT_TEMPLATE
from prioritizer.ingestion.smells_ingestion import read_and_store_relevant_smells, add_further_context
from prioritizer.ingestion.chunking import convert_chunked_text_to_langchain_documents

from prioritizer.pipelines.agentic.agent_state import State
from prioritizer.pipelines.agentic.system_prompt import SYSTEM_PROMPT
from prioritizer.pipelines.agentic.reviewing_output import review_output_node
from prioritizer.pipelines.agentic.repair_node import repair_output_node
from prioritizer.pipelines.agentic.embedding_retrieval import index_documents_into_chroma

from pathlib import Path
import csv
import argparse
import os
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, START, END

from langchain_openai import AzureChatOpenAI
from langchain_ollama import ChatOllama
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
    test_coverage = state.get("use_test_coverage")

    smells = add_further_context(repo, smells, git_stats, pylint, True, test_coverage)

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

def _format_rag_results(s: Dict[str, Any], max_chars: int = 700) -> str:
    """
    Formats RAG results as numbered document blocks with clear source attribution
    and snippet boundaries, making it easier for the LLM to reference and reason
    about individual pieces of evidence.
    """
    ev = s.get("rag_results") or []
    if not ev:
        return "## BACKGROUND KNOWLEDGE\n<No documents retrieved>"

    blocks = ["## BACKGROUND KNOWLEDGE (GENERAL GUIDANCE ONLY)",
              "The following documents provide general insights about technical debt and code smells.",
              "Treat these as reference material ONLY — do NOT use them as smell-specific evidence.",
              ""]

    for i, e in enumerate(ev, 1):
        meta     = e.get("metadata") or {}
        src      = meta.get("file_name") or meta.get("source") or "unknown"
        page     = meta.get("page_number") or meta.get("page")
        score    = meta.get("score") or meta.get("similarity")

        snippet  = (e.get("text") or "").strip()

        header_parts = [f"source={src}"]
        if page:
            header_parts.append(f"page={page}")
        if score:
            header_parts.append(f"relevance={score:.2f}")

        blocks.append(f"[DOC {i} | {' | '.join(header_parts)}]")
        blocks.append(snippet[:max_chars])
        if len(snippet) > max_chars:
            blocks.append(f"... [truncated, {len(snippet) - max_chars} chars omitted]")
        blocks.append("")  

    return "\n".join(blocks)

def _format_smell_for_prompt(s: Dict[str, Any], idx: int, state: State) -> str:
    code_block = "\n"

    if state.get("use_code"): code_block = f"""\
    Code segment:
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

test_coverage
{s.get("test_coverage_report")}

{code_block}

ai_code_segment_summary:
{s.get("ai_code_segment_summary")}

Retrieved RAG info:
{_format_rag_results(s)}
""".strip()


def build_article_query(smell: Dict[str, Any], include_code: bool) -> str:
    parts = [
        f"code smell: {smell.get('name','')}",
        f"category: {smell.get('type_of_smell','')}",
        f"file: {smell.get('file_path','')} line: {smell.get('line_number','')}",
        smell.get("description", ""),
        smell.get("ai_code_segment_summary", ""),
    ]

    if smell.get("git_analysis"):
        parts.append(smell["git_analysis"])
    if smell.get("pylint_report"):
        parts.append(smell["pylint_report"])
    if include_code and smell.get("code_segment"):
        parts.append(smell["code_segment"])

    return "\n".join([p.strip() for p in parts if p and str(p).strip()])


def retrieve_processed_data_from_articles(state: State) -> State:
    store = state.get("store")
    smells = state.get("smells") or []
    top_k = 4
    include_code = bool(state.get("use_code"))

    if store is None or not smells:
        return { **state }

    new_smells: List[Dict[str, Any]] = []
    for s in smells:
        query = build_article_query(s, include_code=include_code)

        if not query.strip():
            new_smells.append({**s, "rag_results": []})
            continue

        retrieved_results = store.similarity_search_with_score(query, k=top_k)

        evidence = []
        for doc, score in retrieved_results:
            evidence.append({
                "text": doc.page_content,
                "metadata": doc.metadata or {},
                "score": float(score),
            })

        new_smells.append({**s, "rag_results": evidence, "rag_query": query})

    return {**state, "smells": new_smells}


def retrieve_git_repo_data():
    ...

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

def route_execution_after_review(state: State) -> str: 
    if state.get("is_valid"):
        return "write_prioritization_report"
    
    if state.get("repair_attempts", 0) > state.get("max_repair_attempts", 2):
        return "write_prioritization_report"
    
    return "repair_output_node"

def route_execution_to_rag_node(state: State) -> str: 
    if state.get("use_rag"):
        return "retrieve_processed_data_from_articles"
    else:
        return "prioritize_smells_node"
    

def write_prioritization_report(state: State) -> State:
    out_dir = state.get("out_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    llm_output_file = out_dir / "agent_output.csv"

    with open(llm_output_file, "w", encoding="utf-8") as f:
        csv.writer(f).writerow([state.get("output_text")])

    return state




def run_agent_pipeline(args: argparse.Namespace, smells: List, project_path: str) -> Path:

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

    docs = convert_chunked_text_to_langchain_documents()

    store, _ = index_documents_into_chroma(
        docs,
        collection_name="articles",
        embedding_model="sentence-transformers/all-mpnet-base-v2",
        batch_size=128,
    )

    smells_graph = StateGraph(State)

    smells_graph.add_node("load_smells", load_smells)
    smells_graph.add_node("create_more_context", create_more_context)
    smells_graph.add_node("analyze_code_segments_with_agent", analyze_code_segments_with_agent)
    smells_graph.add_node("retrieve_processed_data_from_articles", retrieve_processed_data_from_articles)
    smells_graph.add_node("prioritize_smells_node", prioritize_smells_node)
    smells_graph.add_node("review_output_node", review_output_node)
    smells_graph.add_node("repair_output_node", repair_output_node)
    smells_graph.add_node("write_prioritization_report", write_prioritization_report)

    smells_graph.add_edge(START, "load_smells")
    smells_graph.add_edge("load_smells","create_more_context")
    smells_graph.add_edge("create_more_context","analyze_code_segments_with_agent")

    smells_graph.add_conditional_edges(
        "analyze_code_segments_with_agent",
        route_execution_to_rag_node,
        {
            "retrieve_processed_data_from_articles": "retrieve_processed_data_from_articles",
            "prioritize_smells_node": "prioritize_smells_node",
        },
    )

    smells_graph.add_edge("retrieve_processed_data_from_articles", "prioritize_smells_node")
    smells_graph.add_edge("prioritize_smells_node", "review_output_node")

    smells_graph.add_conditional_edges(
        "review_output_node",
        route_execution_after_review,
        {
            "repair_output_node": "repair_output_node",
            "write_prioritization_report": "write_prioritization_report",
        },
    )

    smells_graph.add_edge("repair_output_node", "review_output_node")
    smells_graph.add_edge("write_prioritization_report", END)

    compiled_graph = smells_graph.compile()

    compiled_graph.invoke({
        "smell_types": smells,
        "smells": None,
        "use_git": args.include_git_stats,
        "use_pylint": args.run_pylint_astroid,
        "use_code": use_code,
        "use_rag": args.use_rag,
        "use_test_coverage": args.use_test_coverage,
        "repo": project_path,
        "llm": llm,
        "store": store,
        "out_dir": experiments_dir,
        "output_text": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })

    (experiments_dir / "agent_graph.png").write_bytes(
        compiled_graph.get_graph().draw_mermaid_png()
    )

    return experiments_dir


"""
bash run_analyzer.sh simapy  --llm-provider ollama --add-project-structure --pipeline agent --test-coverage --rag

"""