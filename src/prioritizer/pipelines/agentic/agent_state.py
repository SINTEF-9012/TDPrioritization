from typing import TypedDict, List, Dict, Any, Optional
from git import Repo
from langchain_core.language_models.chat_models import BaseChatModel
from pathlib import Path

class State(TypedDict):
    smell_types: List[str]                      
    smells: Optional[List[Dict[str, Any]]]

    repo: Repo
    use_git: bool
    use_pylint: bool
    use_code: bool

    llm: BaseChatModel

    output_text: Optional[str]
    out_dir: Path

    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]

    validation_errors: Optional[dict[str, Any]]
    is_valid: Optional[bool]
    repair_attempts: int
    max_repair_attempts: int