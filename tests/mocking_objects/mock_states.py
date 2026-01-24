from pathlib import Path
from typing import List, Dict, Any


CORRECT_OUTPUT = """\
"Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization
1|14|Feature Envy|calculate_semantic_coupling|../test_projects/gitmetrics/gitmetrics/metrics/coupling.py|HIGH|Core metric method heavily relies on OS utilities, creating strong propagation risk across the codebase
2|20|Feature Envy|calculate_change_proneness|../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py|HIGH|Extremely long method with intensive diff API usage, high coupling and maintenance cost
3|21|Feature Envy|calculate_error_proneness|../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py|HIGH|Large method mixing bug-related logic, tightly coupled to external file-bug data, high defect risk
4|13|Feature Envy|calculate_structural_coupling|../test_projects/gitmetrics/gitmetrics/metrics/coupling.py|HIGH|Relies heavily on commit objects, propagating changes throughout core metric calculations
5|19|Feature Envy|calculate_change_frequency|../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py|HIGH|Long method with multiple responsibilities, core metric impact and high change risk
6|15|Feature Envy|calculate_cohesion|../test_projects/gitmetrics/gitmetrics/metrics/coupling.py|HIGH|Repeated OS calls within core metric, moderate propagation risk
7|9|Feature Envy|calculate_co_change_metrics|../test_projects/gitmetrics/gitmetrics/metrics/co_change.py|HIGH|Matrix-centric logic tightly bound to external structures, affecting core co-change analysis
8|5|Feature Envy|main|../test_projects/gitmetrics/gitmetrics/cli.py|HIGH|CLI entry point tightly coupled to argument namespace, broad application impact
9|23|Feature Envy|get_logger|../test_projects/gitmetrics/gitmetrics/utils/logger.py|HIGH|Logger factory depends on global logging module, affecting logging throughout the project
10|22|Feature Envy|setup_logging|../test_projects/gitmetrics/gitmetrics/utils/logger.py|HIGH|Logging configuration manipulates root_logger directly, influencing global logger behavior"\
"""

FAULTY_NO_HEADER = """\
"1|14|Feature Envy|calculate_semantic_coupling|../test_projects/gitmetrics/gitmetrics/metrics/coupling.py|HIGH|Core metric method heavily relies on OS utilities
2|20|Feature Envy|calculate_change_proneness|../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py|HIGH|Extremely long method with intensive diff API usage"\
"""

FAULTY_DUPLICATE_ID = """\
"Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization
1|14|Feature Envy|calculate_semantic_coupling|../test_projects/gitmetrics/gitmetrics/metrics/coupling.py|HIGH|Core metric method heavily relies on OS utilities
2|14|Feature Envy|calculate_change_proneness|../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py|HIGH|Duplicate Id reused incorrectly
3|21|Feature Envy|calculate_error_proneness|../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py|HIGH|Large method mixing bug logic"\
"""

FAULTY_SEVERITY_ORDER = """\
"Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization
1|14|Feature Envy|calculate_semantic_coupling|../test_projects/gitmetrics/gitmetrics/metrics/coupling.py|LOW|Minor concern
2|20|Feature Envy|calculate_change_proneness|../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py|HIGH|Critical core logic with high propagation risk"\
"""

FAULTY_RANKS = """\
"Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization
1|14|Feature Envy|calculate_semantic_coupling|../test_projects/gitmetrics/gitmetrics/metrics/coupling.py|HIGH|Core metric method
3|20|Feature Envy|calculate_change_proneness|../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py|HIGH|Skipped rank 2"\
"""

FAULTY_EXTRA_TEXT = """\
"Here is the prioritization you requested:
Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization
1|14|Feature Envy|calculate_semantic_coupling|../test_projects/gitmetrics/gitmetrics/metrics/coupling.py|HIGH|Core metric method"\
"""

MOCK_SMELLS = [
    {
        "index": "14",
        "type_of_smell": "Feature Envy",
        "name": "calculate_semantic_coupling",
        "file_path": "../test_projects/gitmetrics/gitmetrics/metrics/coupling.py",
        "description": "Core metric method heavily relies on OS utilities, creating strong propagation risk across the codebase",
    },
    {
        "index": "20",
        "type_of_smell": "Feature Envy",
        "name": "calculate_change_proneness",
        "file_path": "../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py",
        "description": "Extremely long method with intensive diff API usage, high coupling and maintenance cost",
    },
    {
        "index": "21",
        "type_of_smell": "Feature Envy",
        "name": "calculate_error_proneness",
        "file_path": "../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py",
        "description": "Large method mixing bug-related logic, tightly coupled to external file-bug data, high defect risk",
    },
    {
        "index": "13",
        "type_of_smell": "Feature Envy",
        "name": "calculate_structural_coupling",
        "file_path": "../test_projects/gitmetrics/gitmetrics/metrics/coupling.py",
        "description": "Relies heavily on commit objects, propagating changes throughout core metric calculations",
    },
    {
        "index": "19",
        "type_of_smell": "Feature Envy",
        "name": "calculate_change_frequency",
        "file_path": "../test_projects/gitmetrics/gitmetrics/metrics/change_proneness.py",
        "description": "Long method with multiple responsibilities, core metric impact and high change risk",
    },
    {
        "index": "15",
        "type_of_smell": "Feature Envy",
        "name": "calculate_cohesion",
        "file_path": "../test_projects/gitmetrics/gitmetrics/metrics/coupling.py",
        "description": "Repeated OS calls within core metric, moderate propagation risk",
    },
    {
        "index": "9",
        "type_of_smell": "Feature Envy",
        "name": "calculate_co_change_metrics",
        "file_path": "../test_projects/gitmetrics/gitmetrics/metrics/co_change.py",
        "description": "Matrix-centric logic tightly bound to external structures, affecting core co-change analysis",
    },
    {
        "index": "5",
        "type_of_smell": "Feature Envy",
        "name": "main",
        "file_path": "../test_projects/gitmetrics/gitmetrics/cli.py",
        "description": "CLI entry point tightly coupled to argument namespace, broad application impact",
    },
    {
        "index": "23",
        "type_of_smell": "Feature Envy",
        "name": "get_logger",
        "file_path": "../test_projects/gitmetrics/gitmetrics/utils/logger.py",
        "description": "Logger factory depends on global logging module, affecting logging throughout the project",
    },
    {
        "index": "22",
        "type_of_smell": "Feature Envy",
        "name": "setup_logging",
        "file_path": "../test_projects/gitmetrics/gitmetrics/utils/logger.py",
        "description": "Logging configuration manipulates root_logger directly, influencing global logger behavior",
    },
]


def make_mock_state(output_text: str, smells: List[Dict[str, Any]], max_repairs: int = 2) -> Dict[str, Any]:
    return {
        "smell_types": ["Long Method", "Large Class", "Long File", "High Cyclomatic Complexity", "Feature Envy"],
        "smells": smells,

        "repo": None,
        "use_git": False,
        "use_pylint": False,
        "use_code": False,
        "llm": None,

        "output_text": output_text,
        "out_dir": Path("experiments/mock"),

        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,

        "validation_errors": {},
        "is_valid": None,
        "repair_attempts": 0,
        "max_repair_attempts": max_repairs,
    }

