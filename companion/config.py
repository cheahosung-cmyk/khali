"""컴패니언 설정값."""
import os
from pathlib import Path

# 백엔드: COMPANION_PROVIDER(anthropic|gemini|ollama)로 선택, 미지정 시 자동
CLAUDE_MODEL = os.environ.get("COMPANION_MODEL", "claude-opus-4-8")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")   # 무료 티어
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "exaone3.5")          # 한국어 로컬 모델
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# OpenAI 호환 API (OpenRouter·Groq·Mistral·LM Studio 등)
# 기본값: OpenRouter의 무료·무검열 Venice 모델
OPENAI_COMPAT_URL = os.environ.get("OPENAI_COMPAT_URL", "https://openrouter.ai/api/v1")
OPENAI_COMPAT_MODEL = os.environ.get(
    "OPENAI_COMPAT_MODEL",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
)

CHAT_MAX_TOKENS = 1024        # 대화 답변은 짧게
EXTRACT_MAX_TOKENS = 2048     # 취향 추출용
CHAT_EFFORT = "low"           # 대화는 응답 속도가 중요(Claude 전용)

HISTORY_KEEP = 40             # 세션 간 이어갈 최근 메시지 수
HISTORY_SEND = 60             # 한 요청에 보낼 최대 메시지 수
LIST_CAP = 40                 # 프로필 항목별 최대 개수

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "companion"
PERSONA_PATH = DATA_DIR / "persona.json"
PROFILE_PATH = DATA_DIR / "profile.json"
HISTORY_PATH = DATA_DIR / "history.json"
