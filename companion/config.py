"""컴패니언 설정값."""
import os
from pathlib import Path

CLAUDE_MODEL = os.environ.get("COMPANION_MODEL", "claude-opus-4-8")
CHAT_MAX_TOKENS = 1024        # 대화 답변은 짧게
EXTRACT_MAX_TOKENS = 2048     # 취향 추출용
CHAT_EFFORT = "low"           # 대화는 응답 속도가 중요

HISTORY_KEEP = 40             # 세션 간 이어갈 최근 메시지 수
HISTORY_SEND = 60             # 한 요청에 보낼 최대 메시지 수
LIST_CAP = 40                 # 프로필 항목별 최대 개수

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "companion"
PERSONA_PATH = DATA_DIR / "persona.json"
PROFILE_PATH = DATA_DIR / "profile.json"
HISTORY_PATH = DATA_DIR / "history.json"
