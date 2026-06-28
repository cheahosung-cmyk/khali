"""Khali - LLM Council.

여러 AI(ChatGPT, Claude, Gemini)를 각자의 강점에 맞춰 순서대로 호출하고
하나의 통합된 답변을 만들어내는 시스템.

흐름 (LLM Council):
    1. Drafter   (ChatGPT) - 초안 작성
    2. Skeptic   (Claude)  - 비판 및 수정
    3. Verifier  (Gemini)  - 검증 및 선별
    4. Synthesizer (ChatGPT/Claude) - 최종본 종합
"""

__version__ = "0.1.0"

from .council import Council, CouncilResult, StageResult

__all__ = ["Council", "CouncilResult", "StageResult", "__version__"]
