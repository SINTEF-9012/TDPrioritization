from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_chroma import Chroma

from pathlib import Path

class State(TypedDict):
    smell_types: List[str]                      
    smells: Optional[List[Dict[str, Any]]]

    repo: str

    use_git: bool
    use_pylint: bool
    code_context: str
    use_rag: bool
    use_test_coverage: bool

    llm: BaseChatModel
    store: Chroma

    output_text: Optional[str]
    out_dir: Path

    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]

    validation_errors: Optional[dict[str, Any]]
    is_valid: Optional[bool]
    repair_attempts: int
    max_repair_attempts: int