"""AI 직원(에이전트)의 데이터 모델."""

from pydantic import BaseModel, Field


class Employee(BaseModel):
    """AI 직원 한 명의 정의.

    id는 영문 슬러그로 고유해야 하며, Claude Code 서브에이전트로 내보낼 때
    파일명과 에이전트 이름으로 그대로 사용된다.
    """

    id: str = Field(..., pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str = Field(..., description="직함 (한국어)")
    department: str = Field(..., description="소속 부서 슬러그")
    description: str = Field(..., description="언제 이 직원에게 일을 맡기는지 한 줄 설명")
    system_prompt: str = Field(..., description="이 직원의 역할·작업 방식을 정의하는 시스템 프롬프트")
    model: str = Field("sonnet", description="권장 모델 (haiku/sonnet/opus)")


class Department(BaseModel):
    """부서 정의."""

    id: str
    name: str
    headcount: int
