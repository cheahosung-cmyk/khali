"""khali CLI 진입점.

    khali list [--department DEPT] [--q KEYWORD]   직원 목록 출력
    khali show EMPLOYEE_ID                          직원 상세(시스템 프롬프트 포함) 출력
    khali export [--dir DIR]                        Claude Code 서브에이전트 파일로 내보내기
    khali serve [--host HOST] [--port PORT]         조회 API 서버 실행
"""

import argparse

from src.export import export_agents
from src.roster import DEPARTMENTS, get_department, get_employee, list_employees


def _cmd_list(args: argparse.Namespace) -> int:
    employees = list_employees(department=args.department, q=args.q)
    if not employees:
        print("조건에 맞는 직원이 없습니다.")
        return 1
    current_dept = None
    for e in employees:
        if e.department != current_dept:
            current_dept = e.department
            dept = get_department(current_dept)
            print(f"\n[{dept.name if dept else current_dept}]")
        print(f"  {e.id:28s} {e.name} - {e.description}")
    print(f"\n총 {len(employees)}명")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    employee = get_employee(args.employee_id)
    if employee is None:
        print(f"직원을 찾을 수 없습니다: {args.employee_id}")
        return 1
    dept = get_department(employee.department)
    print(f"이름: {employee.name} ({employee.id})")
    print(f"부서: {dept.name if dept else employee.department}")
    print(f"권장 모델: {employee.model}")
    print(f"담당: {employee.description}")
    print(f"\n시스템 프롬프트:\n{employee.system_prompt}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    written = export_agents(args.dir)
    print(f"{len(written)}개 에이전트 파일을 {args.dir} 에 내보냈습니다.")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("src.api:app", host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="khali",
        description=f"상가건물 관리소장을 위한 AI 직원 {len(list_employees())}명 "
        f"({len(DEPARTMENTS)}개 부서) 관리 도구",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_list = subparsers.add_parser("list", help="직원 목록 출력")
    p_list.add_argument("--department", help="부서 슬러그로 필터 (예: facilities)")
    p_list.add_argument("--q", help="키워드로 필터")
    p_list.set_defaults(func=_cmd_list)

    p_show = subparsers.add_parser("show", help="직원 상세 출력")
    p_show.add_argument("employee_id")
    p_show.set_defaults(func=_cmd_show)

    p_export = subparsers.add_parser("export", help="Claude Code 서브에이전트로 내보내기")
    p_export.add_argument("--dir", default=".claude/agents", help="내보낼 디렉터리")
    p_export.set_defaults(func=_cmd_export)

    p_serve = subparsers.add_parser("serve", help="조회 API 서버 실행")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
