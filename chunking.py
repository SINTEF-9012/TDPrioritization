import os
import fitz
import re

from haystack import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

REFERENCE_HEADINGS = [
    r"^\s*references\s*$",
    r"^\s*bibliography\s*$",
    r"^\s*reference\s*$",
]

BOILERPLATE_PATTERNS = [
    r"creativecommons\.org",
    r"\bVOLUME\s+\d+\b",
    r"\bIEEE\b",
    r"\bThe Authors\b",
    r"\blicensed under\b",
    r"\bdoi\b",
    r"http[s]?://",
    r"^\s*\d{5,}\s*$",   # long numeric lines (page ids)
]

REF_SIGNAL = re.compile(
    r"(\bet al\.\b|\bvol\.\b|\bpp\.\b|\bproc\.\b|\btrans\.\b|\bdoi\b|http[s]?://|\(\d{4}\)|\[\d+\])",
    re.IGNORECASE
)

def convert_chunked_text_to_haystack_documents(chunk_size=1500, chunk_overlap=250):
    pdf_info = convert_pdf_files_to_text_pages()
    documents: list[Document] = []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    for file_name, file_info in pdf_info.items():
        base_meta = dict(file_info["metadata"]) or {}
        base_meta.pop("encryption", None)
        base_meta.update({"chunked": True, "type": "article", "file_name": file_name})

        for p in file_info["pages"]:
            page_meta = {**base_meta, "page": p["page"]}
            lc_docs = splitter.create_documents([p["text"]], metadatas=[page_meta])
            for d in lc_docs:
                if not is_good_chunk(d.page_content):
                    continue
                documents.append(Document(content=d.page_content, meta=d.metadata))

    return documents

def convert_pdf_files_to_text_pages(pdf_dir="articles") -> dict[str, dict]:
    out = {}
    for filename in os.listdir(pdf_dir):
        if not filename.endswith(".pdf"):
            continue

        path = os.path.join(pdf_dir, filename)
        doc = fitz.open(path)

        pages = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text and text.strip():
                clean_text = strip_references(text)
                clean_text = strip_boilerplate(clean_text)
                clean_text = strip_reference_blocks(clean_text)
                pages.append({"page": i, "text": clean_text})

        out[filename] = {"metadata": doc.metadata, "pages": pages}
    return out

def strip_references(text: str) -> str:
    lines = text.splitlines()
    cut_idx = None
    for i, line in enumerate(lines):
        if any(re.match(pat, line.strip().lower()) for pat in REFERENCE_HEADINGS):
            cut_idx = i
            break
    if cut_idx is not None:
        return "\n".join(lines[:cut_idx])
    return text

def strip_boilerplate(text: str) -> str:
    cleaned = []
    for line in text.splitlines():
        l = line.strip()
        if not l:
            cleaned.append(line)
            continue

        low = l.lower()
        if any(re.search(p, low, flags=re.IGNORECASE) for p in BOILERPLATE_PATTERNS):
            continue

        # Drop lines that are mostly punctuation / separators
        if len(l) >= 8 and sum(ch.isalnum() for ch in l) / len(l) < 0.35:
            continue

        cleaned.append(line)
    return "\n".join(cleaned)

def is_good_chunk(s: str) -> bool:
    s = s.strip()
    if len(s) < 500:  # too short to carry an argument
        return False

    # Reference/citation density
    bracket_cites = len(re.findall(r"\[\d+\]", s))
    year_cites = len(re.findall(r"\(\d{4}\)", s))
    urls = len(re.findall(r"http[s]?://", s, flags=re.IGNORECASE))
    dois = len(re.findall(r"\bdoi\b", s, flags=re.IGNORECASE))
    etal = len(re.findall(r"\bet al\.\b", s, flags=re.IGNORECASE))

    # If it looks like a bibliography chunk, discard
    if bracket_cites + year_cites + urls + dois + etal >= 12:
        return False

    # If too many lines look like citations (short, comma-heavy, year-heavy)
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if lines:
        refy = 0
        for ln in lines:
            if REF_SIGNAL.search(ln):
                refy += 1
        if refy / len(lines) > 0.45:
            return False

    return True

def strip_reference_blocks(text: str, window_lines: int = 20, min_hits: int = 10) -> str:
    """
    Remove long blocks that resemble bibliographies, even if there is no 'References' heading.
    Looks for a window of lines with high density of reference signals.
    """
    lines = text.splitlines()
    n = len(lines)

    # scan for first likely reference block
    for start in range(0, max(0, n - window_lines)):
        window = lines[start:start + window_lines]
        hits = sum(1 for line in window if REF_SIGNAL.search(line or ""))
        if hits >= min_hits:
            # drop from start of that block to end
            return "\n".join(lines[:start]).rstrip()

    return text

if __name__ == "__main__":
    docs = convert_chunked_text_to_haystack_documents()
    print(docs)
