"""로스터를 Claude Code 서브에이전트 파일(.claude/agents/*.md)로 내보내기."""

from pathlib import Path

from src.models import Employee
from src.roster import EMPLOYEES, get_department


def render_agent_markdown(employee: Employee) -> str:
    """직원 한 명을 Claude Code 서브에이전트 마크다운으로 변환한다."""
    dept = get_department(employee.department)
    dept_name = dept.name if dept else employee.department
    description = f"[{dept_name}] {employee.name}. {employee.description}."
    return (
        "---\n"
        f"name: {employee.id}\n"
        f"description: {description}\n"
        f"model: {employee.model}\n"
        "---\n\n"
        f"{employee.system_prompt}\n"
    )


def export_agents(target_dir: str | Path, employees: list[Employee] | None = None) -> list[Path]:
    """직원들을 target_dir 아래 .md 파일로 내보내고 생성된 경로 목록을 반환한다.

    기본값은 로스터 전체(50명)이며, employees로 일부만 내보낼 수 있다.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for employee in employees if employees is not None else EMPLOYEES:
        path = target / f"{employee.id}.md"
        path.write_text(render_agent_markdown(employee), encoding="utf-8")
        written.append(path)
    return written
