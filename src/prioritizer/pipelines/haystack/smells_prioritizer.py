from prioritizer.analysis import build_project_structure
from prioritizer.ingestion.chunking import convert_chunked_text_to_haystack_documents
from prioritizer.llm.analyze_code_segment import analyze_code_segments_via_ai
from prioritizer.llm.prompt_template import PROMPT_TEMPLATE
from prioritizer.llm.ollama_client import OllamaGenerator
from prioritizer.llm.azure_component import AzureOpenAIGenerator
from prioritizer.ingestion.smells_ingestion import read_and_store_relevant_smells, add_further_context

from haystack import Pipeline, Document
from haystack.components.builders.prompt_builder import PromptBuilder
from haystack_integrations.document_stores.chroma import ChromaDocumentStore
from haystack.components.embedders import SentenceTransformersDocumentEmbedder, SentenceTransformersTextEmbedder
from haystack_integrations.components.retrievers.chroma import ChromaEmbeddingRetriever

from langchain_ollama import ChatOllama

import csv
from pathlib import Path
from typing import List, Any, Optional


def build_haystack_documents(smells: dict[str, Any], code_context_mode: str = "analysis") -> List[Document]:
    docs: List[Document] = []
    use_ai_analysis = code_context_mode == "analysis"
    include_raw_code = code_context_mode == "code"
    context_label = "AI SUMMARIZATION OF THE CODE" if use_ai_analysis else "CODE SEGMENT"

    for s in smells:
        code_context = None
        if use_ai_analysis:
            code_context = s.get("ai_code_segment_summary")
        if code_context is None and include_raw_code:
            code_context = s.get("code_segment")

        content = (
            f"SMELL\n"
            f"- id: {s.get('index')}\n"
            f"- type_of_smell: {s.get('type_of_smell')}\n"
            f"- name: {s.get('name')}\n"
            f"- file_path: {s.get('file_path')}\n"
            f"- module_or_class: {s.get('module_or_class')}\n"
            f"- line_number: {s.get('line_number')}\n\n"
            f"DESCRIPTION\n{s.get('description')}\n\n"
            f"GIT_ANALYSIS\n{s.get('git_analysis', 'N/A')}\n\n"
            f"PYLINT_REPORT\n{s.get('pylint_report', 'N/A')}\n\n"
            f"{context_label}\n{code_context or 'N/A'}\n"
        )

        docs.append(Document(
            content=content,
            meta={
                "type": "smell",
                "index": s.get("index"),
                "smell_name": s.get("name"),
                "file_path": s.get("file_path"),
                "description": s.get("description"),
            }
        ))
    return docs


def load_embedder_pair(
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> tuple[SentenceTransformersDocumentEmbedder, SentenceTransformersTextEmbedder]:
    doc_embedder = SentenceTransformersDocumentEmbedder(model=model_name)
    query_embedder = SentenceTransformersTextEmbedder(model=model_name)
    doc_embedder.warm_up()
    query_embedder.warm_up()
    return doc_embedder, query_embedder


def ensure_articles_indexed(
    document_store: ChromaDocumentStore,
    doc_embedder: SentenceTransformersDocumentEmbedder,
    include_articles: bool,
    persistent_storage: bool,
) -> None:
    if not include_articles:
        print("Articles disabled; proceeding without embedded literature.")
        return

    if document_store.count_documents() > 0 and persistent_storage:
        print(f"Reusing existing article embeddings ({document_store.count_documents()} docs).")
        return

    chunked_docs = convert_chunked_text_to_haystack_documents()
    embedded_docs = doc_embedder.run(documents=chunked_docs)["documents"]
    document_store.write_documents(embedded_docs)
    print(f"Embedded {len(embedded_docs)} article chunks and wrote them to Chroma.")


def retrieve_documents(
    query_embedder: SentenceTransformersTextEmbedder,
    document_store: ChromaDocumentStore,
    question: str,
) -> List[Document]:
    """Embeds the question and retrieves relevant documents from the store."""
    query_embedding = query_embedder.run(question)["embedding"]
    retriever = ChromaEmbeddingRetriever(document_store=document_store)
    return retriever.run(query_embedding=query_embedding)["documents"]


def build_llm(provider: str, model_name: str, prompt_file: Path):
    if provider == "ollama":
        return OllamaGenerator(model=model_name, full_prompt_file=prompt_file)
    return AzureOpenAIGenerator(full_prompt_file=prompt_file)


def build_pipeline(prompt_template: str, model_name: str, prompt_file: Path, provider: str) -> Pipeline:
    prompt_builder = PromptBuilder(
        template=prompt_template,
        required_variables=["question", "smells"],
    )
    llm = build_llm(provider, model_name, prompt_file)

    pipeline = Pipeline()
    pipeline.add_component("prompt_builder", prompt_builder)
    pipeline.add_component("llm", llm)
    pipeline.connect("prompt_builder.prompt", "llm.prompt")

    return pipeline


def prepare_smells(args, smells: List[str], project_path: str, llm) -> List[Document]:
    """Loads, enriches, and builds Haystack documents from raw smell data."""
    code_context_mode = getattr(args, "code_context_mode", "analysis")
    send_code_segment  = code_context_mode in ("analysis", "code")
    send_code_analysis = code_context_mode == "analysis"

    code_smells_dic = read_and_store_relevant_smells(smells)
    code_smells_dic = add_further_context(
        project_path,
        code_smells_dic,
        args.include_git_stats,
        args.run_pylint_astroid,
        send_code_segment,
    )
    code_smells_dic = analyze_code_segments_via_ai(code_smells_dic, llm, send_code_analysis)
    return build_haystack_documents(code_smells_dic, code_context_mode)


def build_question() -> str:
    return (
        "Use evidence from the embedded research (INFO ON CODE SMELLS AND TECHNICAL DEBT) to rank ALL code smells "
        "by refactoring priority in this project. The smells to consider are: Long Method, Large Class, Long File, "
        "High Cyclomatic Complexity, and Feature Envy. "
        "For each smell instance, justify its rank using research-backed signals such as change-proneness "
        "(e.g., churn and recency), fault/defect-proneness (bug association), severity metrics "
        "(e.g., size, cyclomatic or cognitive complexity), propagation risk, and expected refactoring ROI "
        "(cost versus long-term maintainability benefit). "
        "When the research discusses any of these smells—or closely related concepts such as God Class, "
        "Large/God Method, complexity, coupling, or cohesion—explicitly apply those principles to the "
        "available project-specific evidence (git statistics, churn, recency, static analysis, and lint results)."
    )


def run_rag_pipeline(args, smells: List[str], document_store: ChromaDocumentStore, project_path: str) -> Path:
    safe_model     = args.ollama_model.replace(":", "_").replace("/", "_")
    experiments_dir = Path("experiments") / f"{args.output_dir}_rag_model_{safe_model}"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    full_prompt_file = experiments_dir / "full_prompt.txt"

    pipeline   = build_pipeline(PROMPT_TEMPLATE, args.ollama_model, full_prompt_file, args.llm_provider)
    llm_client = ChatOllama(model=args.ollama_model, temperature=0, seed=42)

    documents = prepare_smells(args, smells, project_path, llm_client)
    if not documents:
        print("The project does not contain any of the code smells you inquired about.")
        return experiments_dir

    question = build_question()

    retrieved_documents: List[Document] = []
    if args.use_rag:
        doc_embedder, query_embedder = load_embedder_pair()
        ensure_articles_indexed(document_store, doc_embedder, args.use_rag, args.persistent_storage)
        retrieved_documents = retrieve_documents(query_embedder, document_store, question)

    prompt_inputs = {
        "question":          question,
        "smells":            documents,
        "documents":         retrieved_documents,
        "project_structure": build_project_structure(
            f"src/prioritizer/data/projects/{args.project_name}"
        ) if args.include_project_structure else "Not included.",
    }

    print("Running model:", args.ollama_model)
    results = pipeline.run({"prompt_builder": prompt_inputs})["llm"]

    llm_output_file = experiments_dir / "llm_output.csv"
    with open(llm_output_file, "w", encoding="utf-8") as f:
        csv.writer(f).writerow([results["response"]])

    if args.llm_provider == "azure":
        print(results["prompt_tokens"])

    return experiments_dir