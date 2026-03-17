import subprocess
import json
from pathlib import Path
import venv
import sys

COVERAGE_REPORTS_DIR = Path("src/prioritizer/data/test_coverage_reports")


def get_coverage_report_path(project_path: str | Path) -> Path:
    """Returns the expected coverage report path for a given project."""
    project_name = Path(project_path).name
    return COVERAGE_REPORTS_DIR / f"{project_name}_coverage.json"


def is_coverage_report_valid(report_path: Path, project_path: Path) -> bool:
    """
    Returns True if a cached coverage report exists and is still valid for the project.
    Invalid if:
    - Report does not exist
    - Report is empty
    - Report was generated for a different project (no file paths match the project)
    - Any source file in the project is newer than the report (project has changed)
    """
    if not report_path.exists() or report_path.stat().st_size == 0:
        return False

    try:
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return False

    expected_project_name = Path(project_path).name
    report_project_name   = report_path.stem.replace("_coverage", "")
    if expected_project_name != report_project_name:
        print(f"Coverage report is for '{report_project_name}', not '{expected_project_name}' — regenerating.")
        return False

    report_mtime = report_path.stat().st_mtime
    source_files = list(project_path.rglob("*.py"))
    if any(f.stat().st_mtime > report_mtime for f in source_files):
        print("Project files have changed since last coverage report — regenerating.")
        return False

    return True


def install_project_dependencies(project_path: Path, venv_dir: Path) -> bool:
    """
    Creates a temporary virtual environment and installs the project's dependencies into it.
    Returns True if successful, False otherwise.
    """
    print(f"Creating temporary virtual environment at: {venv_dir}")
    try:
        venv.create(venv_dir, with_pip=True, clear=True)
    except Exception as e:
        print(f"Failed to create virtual environment: {e}")
        return False

    # Determine pip and python executables inside the venv
    if sys.platform == "win32":
        pip    = venv_dir / "Scripts" / "pip"
    else:
        pip    = venv_dir / "bin" / "pip"

    subprocess.run([str(pip), "install", "pytest", "pytest-cov"], 
                   capture_output=True, cwd=project_path)

    for config_file, command in [
        ("pyproject.toml",   [str(pip), "install", "-e", "."]),
        ("setup.py",         [str(pip), "install", "-e", "."]),
        ("requirements.txt", [str(pip), "install", "-r", "requirements.txt"]),
    ]:
        if (project_path / config_file).exists():
            print(f"Installing dependencies from {config_file}...")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=project_path,
            )
            if result.returncode != 0:
                print(f"Dependency installation failed:\n{result.stderr}")
                return False
            print("Dependencies installed successfully.")
            return True

    print("No dependency config found — only pytest and pytest-cov installed.")
    return True


def run_coverage_analysis(project_path: str | Path, force_rerun: bool = False) -> dict:
    project_path = Path(project_path).resolve()
    COVERAGE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = get_coverage_report_path(project_path)

    if not force_rerun and is_coverage_report_valid(report_path, project_path):
        print(f"Reusing existing coverage report: {report_path}")
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
        return {
            Path(file).as_posix(): info["summary"]["percent_covered"]
            for file, info in data.get("files", {}).items()
        }

    test_files = list(project_path.rglob("test_*.py")) + list(project_path.rglob("*_test.py"))
    if not test_files:
        print("No test files found — skipping coverage analysis.")
        return {}

    venv_dir = project_path / ".coverage_venv"

    try:
        install_project_dependencies(project_path, venv_dir)

        # Use the pytest inside the venv, not the system one
        if sys.platform == "win32":
            pytest_executable = venv_dir / "Scripts" / "pytest"
        else:
            pytest_executable = venv_dir / "bin" / "pytest"

        print(f"Running coverage analysis for: {project_path.name}")
        result = subprocess.run(
            [
                str(pytest_executable),
                str(project_path),
                f"--cov={project_path}",
                "--cov-report", f"json:{report_path.resolve()}",
                "--quiet",
                "--no-header",
                "--tb=no",
            ],
            capture_output=True,
            text=True,
            cwd=project_path,
        )

        if not report_path.exists():
            print(f"Coverage report not generated. pytest exit code: {result.returncode}")
            print("--- pytest stdout ---")
            print(result.stdout)
            print("--- pytest stderr ---")
            print(result.stderr)
            return {}

        print(f"Coverage report saved to: {report_path}")
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return {
            Path(file).as_posix(): info["summary"]["percent_covered"]
            for file, info in data.get("files", {}).items()
        }

    except Exception as e:
        print(f"Coverage analysis failed: {e}")
        return {}

    finally:
        if venv_dir.exists():
            import shutil
            shutil.rmtree(venv_dir, ignore_errors=True)
            print(f"Temporary virtual environment removed.")

def return_test_coverage_analysis_for_file(project_path: str | Path, file: str) -> str:
    report_path = get_coverage_report_path(project_path)

    if not report_path.exists():
        return f"No coverage report found for {Path(project_path).name}."

    with open(report_path, encoding="utf-8") as f:
        data = json.load(f)

    files = data.get("files", {})

    file_path = Path(file).as_posix()
    matched_key = None
    for key in files:
        if Path(key).as_posix().endswith(file_path) or file_path.endswith(Path(key).as_posix()):
            matched_key = key
            break

    if matched_key is None:
        return (
            f"TEST COVERAGE",
            f"No coverage data found for: {file}"
        )

    file_data = files[matched_key]
    summary   = file_data.get("summary", {})

    lines = [
        f"TEST COVERAGE",
        f"File: {matched_key}",
        f"Covered lines:   {summary.get('covered_lines', 'N/A')}",
        f"Total statements:{summary.get('num_statements', 'N/A')}",
        f"Coverage:        {summary.get('percent_covered_display', 'N/A')}%",
        f"Missing lines:   {file_data.get('missing_lines', [])}",
    ]

    return "\n".join(lines)

if __name__ == "__main__":
    run_coverage_analysis("test_projects/simapy")
    file_report = return_test_coverage_analysis_for_file("test_projects/simapy", "src/simapy/sima/simo/simobody.py")

    print(file_report)