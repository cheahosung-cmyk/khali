"""로스터 무결성 테스트."""

from src.roster import DEPARTMENTS, EMPLOYEES, get_employee, list_employees


def test_roster_has_50_employees():
    assert len(EMPLOYEES) == 50


def test_employee_ids_are_unique():
    ids = [e.id for e in EMPLOYEES]
    assert len(ids) == len(set(ids))


def test_departments_headcount_matches_roster():
    for dept in DEPARTMENTS:
        members = [e for e in EMPLOYEES if e.department == dept.id]
        assert len(members) == dept.headcount, dept.id


def test_every_employee_belongs_to_known_department():
    dept_ids = {d.id for d in DEPARTMENTS}
    for e in EMPLOYEES:
        assert e.department in dept_ids, e.id


def test_every_employee_has_substantial_prompt():
    for e in EMPLOYEES:
        assert len(e.system_prompt) >= 100, e.id
        assert e.description, e.id


def test_models_are_valid():
    for e in EMPLOYEES:
        assert e.model in {"haiku", "sonnet", "opus"}, e.id


def test_get_employee():
    assert get_employee("chief-assistant") is not None
    assert get_employee("no-such-employee") is None


def test_list_employees_filters():
    facilities = list_employees(department="facilities")
    assert len(facilities) == 5
    assert all(e.department == "facilities" for e in facilities)

    by_keyword = list_employees(q="승강기")
    assert any(e.id == "elevator-manager" for e in by_keyword)

    combined = list_employees(department="legal", q="집합건물")
    assert [e.id for e in combined] == ["condo-law-advisor"]
