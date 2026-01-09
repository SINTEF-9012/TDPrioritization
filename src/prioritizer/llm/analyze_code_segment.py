from typing import Any, Dict, List, Optional, Tuple
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models.chat_models import BaseChatModel


_SUMMARY_CACHE: dict[Tuple[str, str, str, str], str] = {}

SUMMARY_SYSTEM_PROMPT = """\
You are a senior Python engineer specialized in code smells and technical debt.

Task:
- Given a smell type, smell description, and a code snippet, write a concise summary (2-4 sentences)
  describing how the snippet relates to that smell and the likely impact (maintainability, testability, defect risk).
- Do not propose refactorings.
- Do not output JSON, markdown, or bullet points.
Return ONLY the summary text.
"""

def _cache_key(smell: Dict[str, Any]) -> Tuple[str, str, str, str]:
    # Keyed by smell type + file + line + snippet hash
    snippet = smell.get("code_segment") or ""
    return (
        str(smell.get("type_of_smell", "")),
        str(smell.get("file_path", "")),
        str(smell.get("line_number", "")),
        str(hash(snippet)),
    )

def analyze_code_segments_via_ai(smells: List[Dict[str, Any]], llm: BaseChatModel, enabled: bool = True) -> List[Dict[str, Any]]:
    if not enabled:
        for s in smells:
            s["ai_code_segment_summary"] = None
        return smells

    for smell in smells:
        code_segment = (smell.get("code_segment") or "").strip()
        if not code_segment:
            smell["ai_code_segment_summary"] = None
            continue

        key = _cache_key(smell)
        if key in _SUMMARY_CACHE:
            smell["ai_code_segment_summary"] = _SUMMARY_CACHE[key]
            continue

        user_prompt = f"""\
Smell type: {smell.get("name")}
Smell category: {smell.get("type_of_smell")}

Analyzer description:
{smell.get("description")}

Code snippet:
{code_segment}
"""

        resp = llm.invoke([
            SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])

        summary = (resp.content or "").strip()
        smell["ai_code_segment_summary"] = summary if summary else None
        _SUMMARY_CACHE[key] = smell["ai_code_segment_summary"] or ""

    return smells