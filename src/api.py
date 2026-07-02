"""AI 직원 로스터 조회 API."""

from fastapi import FastAPI, HTTPException

from src import __version__
from src.models import Department, Employee
from src.roster import DEPARTMENTS, get_employee, list_employees

app = FastAPI(
    title="Khali - AI Agent Management System",
    description="상가건물 관리소장을 위한 AI 직원 50명 로스터 API",
    version=__version__,
)


@app.get("/")
def read_root() -> dict:
    """서비스 정보와 직원 수를 반환한다."""
    return {
        "service": "khali",
        "version": __version__,
        "employees": len(list_employees()),
        "departments": len(DEPARTMENTS),
    }


@app.get("/departments", response_model=list[Department])
def read_departments() -> list[Department]:
    """부서 목록을 반환한다."""
    return DEPARTMENTS


@app.get("/employees", response_model=list[Employee])
def read_employees(department: str | None = None, q: str | None = None) -> list[Employee]:
    """직원 목록을 반환한다. department·q로 필터링할 수 있다."""
    return list_employees(department=department, q=q)


@app.get("/employees/{employee_id}", response_model=Employee)
def read_employee(employee_id: str) -> Employee:
    """직원 한 명의 상세 정보를 반환한다."""
    employee = get_employee(employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail=f"employee not found: {employee_id}")
    return employee
