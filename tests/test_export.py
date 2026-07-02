"""Claude Code 서브에이전트 내보내기 테스트."""

from src.export import export_agents, render_agent_markdown
from src.roster import EMPLOYEES, get_employee


def test_render_agent_markdown_frontmatter():
    employee = get_employee("condo-law-advisor")
    md = render_agent_markdown(employee)
    assert md.startswith("---\n")
    assert "name: condo-law-advisor\n" in md
    assert "model: opus\n" in md
    assert employee.system_prompt in md


def test_export_agents_writes_all_files(tmp_path):
    written = export_agents(tmp_path)
    assert len(written) == len(EMPLOYEES) == 50
    for path in written:
        assert path.exists()
        assert path.suffix == ".md"
        assert path.read_text(encoding="utf-8").startswith("---\n")


def test_export_agents_subset(tmp_path):
    subset = [get_employee("chief-assistant")]
    written = export_agents(tmp_path, employees=subset)
    assert [p.name for p in written] == ["chief-assistant.md"]
