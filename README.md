# khali

**LLM Council** — ChatGPT, Claude, Gemini 등 여러 AI를 각자의 강점에 맞춰
순서대로 호출하고 **하나의 통합된 답변**으로 만들어 주는 도구입니다.

AI 하나의 답변만 믿으면 틀린 정보에 당할 수 있습니다. 한 AI가 낸 답을 다른
AI에게 던져 검토·검증시키면, 놓쳤던 오류·과장을 잡아내 더 완벽한 답이 나옵니다.

> 아이디어 출처: 안드레이 카파시(Andrej Karpathy)가 제안한 "LLM Council"
> (여러 LLM을 협업시켜 고품질 답변을 만드는 멀티 에이전트 방식).

## 4단계 워크플로우

| 단계 | 역할 | 담당 AI | 하는 일 |
|------|------|---------|---------|
| 1 | **Drafter** (초안 작성) | ChatGPT | 목표·자료로 초안 작성, 확인 필요한 부분은 `[확인 필요]` 표시 |
| 2 | **Skeptic** (비판·수정) | Claude | 칭찬 없이 오류·과장·누락·모호한 표현만 지적 |
| 3 | **Verifier** (검증·선별) | Gemini | 초안+비판을 보고 최종에 남길 내용만 선별 |
| 4 | **Synthesizer** (종합) | ChatGPT | 위 결과를 종합해 실무용 최종 답변 작성 |

각 AI의 강점에 맞춰 일을 분배합니다: ChatGPT(범용성), Claude(긴 글 분석·비판),
Gemini(정보 탐색·문맥 이해).

## 설치

```bash
pip install -e .
```

## 사용법

### 1) mock(모의) 모드 — API 키 없이 바로 실행

키가 없어도 전체 4단계 흐름을 테스트할 수 있습니다.

```bash
python -m src.main "우리 인스타 채널을 50만 팔로워로 키우려면?" --mock
```

`pip install -e .` 를 했다면 `khali` 명령으로도 실행됩니다:

```bash
khali "우리 인스타 채널을 50만 팔로워로 키우려면?" --mock
```

옵션:

| 옵션 | 설명 |
|------|------|
| `-m, --materials` | 참고 자료 전달 |
| `--final-only` | 중간 단계 숨기고 최종 답변만 출력 |
| `--mock` | 실제 키가 있어도 모의 응답으로 강제 실행 |

### 2) 실제 API 연결

`.env.example` 을 복사해 `.env` 를 만들고 키를 채우면 실제 모델이 동작합니다.
(키가 비어 있는 모델은 자동으로 mock 으로 대체됩니다.)

```bash
cp .env.example .env
# .env 에서 OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY 입력

# 실제 SDK 설치 (사용하는 것만 설치해도 됩니다)
pip install openai anthropic google-generativeai
```

### 3) 파이썬에서 직접 사용

```python
from src.council import Council
from src.config import load_settings

settings = load_settings()
settings.force_mock = True  # 키 없이 테스트

council = Council(settings=settings)
result = council.run("우리 채널을 50만 팔로워로 키우려면?")

print(result.final)          # 최종 통합 답변
for stage in result.stages:  # 단계별 산출물
    print(stage.title, stage.provider, stage.output)
```

## 동작 방식

- 단계별 역할 프롬프트는 [`src/prompts.py`](src/prompts.py) 에 있습니다.
- 각 단계의 산출물은 다음 단계 입력으로 전달됩니다
  (초안 → 비판 → 검증 → 종합).
- provider 는 [`src/providers/`](src/providers/) 에 있으며, API 키가 없으면
  자동으로 `MockProvider` 로 대체됩니다.
- 단계별 모델은 `.env`(`DRAFTER_MODEL` 등)로 바꿀 수 있습니다.

## 테스트

```bash
pip install pytest
pytest
```

## 구조

```
src/
  main.py            # CLI 진입점 (khali 명령)
  council.py         # 4단계 오케스트레이터
  prompts.py         # 단계별 역할 프롬프트
  config.py          # 설정/키 로딩 (.env)
  providers/
    base.py          # Provider 인터페이스
    mock.py          # 모의 응답 (키 불필요)
    openai.py        # ChatGPT
    anthropic.py     # Claude
    gemini.py        # Gemini
tests/
  test_council.py
```
