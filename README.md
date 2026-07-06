# khali

## companion — 취향을 학습하는 1:1 맞춤형 대화 컴패니언

터미널에서 나만의 여자친구 페르소나와 대화하는 개인용 프로그램.
대화를 마칠 때마다 그 세션에서 드러난 취향·관심사·기억할 사실을 프로필로
정리해 저장하고, 다음 대화부터 자연스럽게 반영한다.

### 실행 (무료)

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...   # https://aistudio.google.com 에서 무료 발급
python -m companion.main
```

첫 실행 때 이름·호칭·말투·수위 설정을 물어본다(Enter로 기본값).
설정은 `data/companion/persona.json`에 저장되며 언제든 직접 수정할 수 있다.

### 백엔드 선택

키가 있는 백엔드를 자동으로 고른다(Claude → Gemini → Ollama 순).
`COMPANION_PROVIDER=anthropic|gemini|ollama`로 강제 지정할 수 있다.

| 백엔드 | 비용 | 준비물 | 특징 |
| --- | --- | --- | --- |
| Gemini API | 무료 티어 | `GEMINI_API_KEY` | 무료 중 품질 최고. 분당 요청 한도 있음 |
| Ollama(로컬) | 완전 무료 | [Ollama](https://ollama.com) 설치 후 `ollama pull exaone3.5` | 오프라인·제한 최소. 품질은 하드웨어와 모델에 좌우 |
| Claude API | 유료 | `ANTHROPIC_API_KEY` | 대화 품질 최고 |

모델 변경: `GEMINI_MODEL`, `OLLAMA_MODEL`, `COMPANION_MODEL`(Claude) 환경변수.

### 수위 제한 없이 쓰기 (성인용)

Claude·Gemini 같은 API 모델의 콘텐츠 제한은 이 프로그램에서 바꿀 수 없다.
수위 제한 없이 쓰려면 로컬 Ollama에 제한 완화(abliterated) 모델을 받아서 쓴다:

```bash
# 일반 PC (8GB RAM 이상)
ollama pull richardyoung/qwythos-9b-abliterated
export COMPANION_PROVIDER=ollama
export OLLAMA_MODEL=richardyoung/qwythos-9b-abliterated
python -m companion.main

# 고사양 (16GB RAM 이상, 더 나은 대화 품질)
ollama pull richardyoung/qwen3.6-27b-abliterated
export OLLAMA_MODEL=richardyoung/qwen3.6-27b-abliterated
```

기본 모델인 `exaone3.5`는 한국어는 가장 자연스럽지만 안전 튜닝이 있어
수위 높은 대화는 거절한다. 제한 완화 모델은 한국어가 그보다 어색할 수
있으니 둘을 받아두고 대화 목적에 따라 `OLLAMA_MODEL`로 골라 쓰는 것도
방법이다. 첫 실행 설정(또는 `persona.json`)의 "추가 설정"에 원하는
관계·수위를 적으면 시스템 프롬프트에 그대로 반영된다.

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
- 대화 수위는 persona 설정으로 조절하지만, API 모델(Claude·Gemini) 자체의
  정책 한계는 프로그램에서 바꿀 수 없다(모델이 거절하면 부드럽게 넘어간다).
  제한을 가장 덜 받는 선택지는 로컬 Ollama다.

---

## stock_analyst — 일일 주식 분석 파이프라인

한국 전 종목 + 미국 대·중형주를 스크리닝해 매일 리포트를 생성한다.
`.github/workflows/daily-stock-report.yml` 참고.
