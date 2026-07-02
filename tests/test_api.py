"""API 엔드포인트 동작 테스트 (핸들러 직접 호출)."""

import pytest
from fastapi import HTTPException

from src.api import read_departments, read_employee, read_employees, read_root


def test_read_root():
    body = read_root()
    assert body["service"] == "khali"
    assert body["employees"] == 50
    assert body["departments"] == 10


def test_read_departments():
    departments = read_departments()
    assert len(departments) == 10


def test_read_employees_with_filter():
    employees = read_employees(department="billing")
    assert len(employees) == 5


def test_read_employee_found():
    employee = read_employee("fee-calculator")
    assert employee.name == "관리비 부과 담당"


def test_read_employee_not_found():
    with pytest.raises(HTTPException) as exc_info:
        read_employee("no-such-employee")
    assert exc_info.value.status_code == 404
