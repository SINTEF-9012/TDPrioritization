from functools import lru_cache
import hashlib
from pathlib import Path
from typing import List, Sequence, Tuple

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

from prioritizer.ingestion.chunking import convert_chunked_text_to_langchain_documents


def _stable_doc_id(doc: Document) -> str:
    meta = doc.metadata or {}
    source = str(meta.get("file_name") or meta.get("source") or "unknown")
    page = str(meta.get("page") or "")
    chunk_index = str(meta.get("chunk_index") or "")

    h = hashlib.sha256()
    h.update(source.encode("utf-8"))
    h.update(b"|")
    h.update(page.encode("utf-8"))
    h.update(b"|")
    h.update(chunk_index.encode("utf-8"))
    h.update(b"|")
    h.update(doc.page_content.encode("utf-8"))
    return h.hexdigest()


@lru_cache(maxsize=2)
def _get_embeddings(model_name: str) -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=model_name)


def load_chroma_store(
    persist_dir: str = "src/prioritizer/data/embeddings_db",
    *,
    collection_name: str = "articles",
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2",
) -> Chroma:
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    embeddings = _get_embeddings(embedding_model)

    return Chroma(
        collection_name=collection_name,
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
    )


def _existing_ids(store: Chroma, ids: Sequence[str]) -> set[str]:
    if not ids:
        return set()

    try:
        col = store._collection 
    except Exception:
        return set()

    existing: set[str] = set()
    step = 1000

    for i in range(0, len(ids), step):
        batch = ids[i : i + step]
        try:
            res = col.get(ids=batch) 
            for ex_id in (res.get("ids") or []):
                existing.add(ex_id)
        except Exception:
            return set()

    return existing


def index_documents_into_chroma(
    docs: List[Document],
    *,
    persist_dir: str = "src/prioritizer/data/embeddings_db",
    collection_name: str = "articles",
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2",
    batch_size: int = 128,
) -> Tuple[Chroma, int]:
    store = load_chroma_store(
        persist_dir=persist_dir,
        collection_name=collection_name,
        embedding_model=embedding_model,
    )

    ids = [_stable_doc_id(d) for d in docs]
    existing = _existing_ids(store, ids)

    new_docs: List[Document] = []
    new_ids: List[str] = []
    for d, i in zip(docs, ids):
        if i in existing:
            continue
        new_docs.append(d)
        new_ids.append(i)

    for start in range(0, len(new_docs), batch_size):
        store.add_documents(
            new_docs[start : start + batch_size],
            ids=new_ids[start : start + batch_size],
        )

    if hasattr(store, "persist"):
        store.persist()

    return store, len(new_docs)

if __name__ == "__main__":
    docs = convert_chunked_text_to_langchain_documents()

    store, added = index_documents_into_chroma(
        docs,
        collection_name="articles",
        embedding_model="sentence-transformers/all-mpnet-base-v2",
        batch_size=128,
    )

    print(f"Indexed {added} new chunks. Store ready.")