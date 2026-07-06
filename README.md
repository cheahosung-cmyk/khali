# khali

## companion — 취향을 학습하는 1:1 맞춤형 대화 컴패니언

터미널에서 나만의 여자친구 페르소나와 대화하는 개인용 프로그램.
대화를 마칠 때마다 그 세션에서 드러난 취향·관심사·기억할 사실을 프로필로
정리해 저장하고, 다음 대화부터 자연스럽게 반영한다.

### 실행

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...   # https://console.anthropic.com 에서 발급
python -m companion.main
```

첫 실행 때 이름·호칭·말투·수위 설정을 물어본다(Enter로 기본값).
설정은 `data/companion/persona.json`에 저장되며 언제든 직접 수정할 수 있다.

### 명령어

| 명령 | 동작 |
| --- | --- |
| `/프로필` | 지금까지 학습한 취향·기억 보기 |
| `/기억 <내용>` | API 호출 없이 즉시 기억시키기 |
| `/초기화` | 프로필·대화 기록 전부 삭제 |
| `/잘자`, `/bye` | 오늘 대화를 학습하고 종료 |

### 동작 방식

- 대화 기록은 `data/companion/history.json`에 최근 40개까지 유지되어
  세션이 바뀌어도 이어서 대화할 수 있다.
- 종료 시 세션 대화 전체를 한 번 분석해 `data/companion/profile.json`을
  갱신한다(구조화 출력으로 JSON 스키마 강제).
- `data/` 디렉토리는 개인 데이터라 git에 커밋되지 않는다.
- 모델은 기본 `claude-opus-4-8`, `COMPANION_MODEL` 환경변수로 변경 가능.
- 대화 수위는 persona 설정으로 조절하지만, Anthropic API 모델 자체의
  정책 한계는 프로그램에서 바꿀 수 없다(모델이 거절하면 부드럽게 넘어간다).

---

## stock_analyst — 일일 주식 분석 파이프라인

한국 전 종목 + 미국 대·중형주를 스크리닝해 매일 리포트를 생성한다.
`.github/workflows/daily-stock-report.yml` 참고.
