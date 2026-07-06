"""대화 백엔드 구현 — Claude API(유료)·Gemini API(무료 티어)·Ollama(로컬, 완전 무료).

모든 프로바이더는 두 메서드를 제공한다.
- chat(system, messages) -> (답변 텍스트, 거절 여부). 답변은 출력까지 담당한다.
- extract_json(system, prompt, schema) -> JSON 문자열 또는 None. 프로필 추출용.
"""
import json
import os

import requests

from . import config


def _strip_fence(text: str) -> str:
    """모델이 ```json ... ``` 로 감싸 반환한 경우 코드 펜스를 벗긴다."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rstrip()
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class AnthropicProvider:
    """Claude API. ANTHROPIC_API_KEY 필요(유료). 대화 품질이 가장 좋다."""

    name = "Claude API"

    def __init__(self):
        import anthropic

        self.client = anthropic.Anthropic()

    def chat(self, system: str, messages: list) -> tuple[str, bool]:
        with self.client.messages.stream(
            model=config.CLAUDE_MODEL,
            max_tokens=config.CHAT_MAX_TOKENS,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": config.CHAT_EFFORT},
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
            final = stream.get_final_message()
        print()
        reply = "".join(b.text for b in final.content if b.type == "text")
        return reply, final.stop_reason == "refusal"

    def extract_json(self, system: str, prompt: str, schema: dict) -> str | None:
        resp = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.EXTRACT_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {"type": "json_schema", "schema": schema},
                "effort": "low",
            },
        )
        if resp.stop_reason != "end_turn":
            return None
        return next((b.text for b in resp.content if b.type == "text"), None)


class GeminiProvider:
    """Google Gemini API. GEMINI_API_KEY 필요 — https://aistudio.google.com 에서 무료 발급."""

    name = "Gemini API(무료 티어)"

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise SystemExit("GEMINI_API_KEY가 없습니다. https://aistudio.google.com 에서 무료 발급하세요.")

    def _call(self, system: str, contents: list, generation_config: dict) -> dict:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{config.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": contents,
                "generationConfig": generation_config,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _contents(messages: list) -> list:
        return [
            {"role": "user" if m["role"] == "user" else "model",
             "parts": [{"text": m["content"]}]}
            for m in messages
        ]

    @staticmethod
    def _text(data: dict) -> str:
        cand = (data.get("candidates") or [{}])[0]
        parts = cand.get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)

    @staticmethod
    def _blocked(data: dict) -> bool:
        if data.get("promptFeedback", {}).get("blockReason"):
            return True
        cand = (data.get("candidates") or [{}])[0]
        return cand.get("finishReason") == "SAFETY"

    def chat(self, system: str, messages: list) -> tuple[str, bool]:
        data = self._call(system, self._contents(messages), {
            "maxOutputTokens": config.CHAT_MAX_TOKENS,
            "thinkingConfig": {"thinkingBudget": 0},  # 대화는 속도 우선
        })
        if self._blocked(data):
            print()
            return "", True
        text = self._text(data)
        print(text)
        return text, not text.strip()

    def extract_json(self, system: str, prompt: str, schema: dict) -> str | None:
        data = self._call(system, [{"role": "user", "parts": [{"text": prompt}]}], {
            "maxOutputTokens": config.EXTRACT_MAX_TOKENS,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        })
        if self._blocked(data):
            return None
        return _strip_fence(self._text(data)) or None


class OpenAICompatProvider:
    """OpenAI 호환 API. 기본은 OpenRouter의 무료·무검열 Venice 모델.

    키는 OPENROUTER_API_KEY 또는 OPENAI_COMPAT_API_KEY에서 읽는다.
    OPENAI_COMPAT_URL/MODEL을 바꾸면 Groq·Mistral·LM Studio 등도 쓸 수 있다.
    """

    def __init__(self):
        self.api_key = (os.environ.get("OPENROUTER_API_KEY")
                        or os.environ.get("OPENAI_COMPAT_API_KEY"))
        if not self.api_key:
            raise SystemExit(
                "OPENROUTER_API_KEY가 없습니다. https://openrouter.ai/keys 에서 무료 발급하세요."
            )
        self.url = config.OPENAI_COMPAT_URL.rstrip("/")
        self.model = config.OPENAI_COMPAT_MODEL
        self.name = f"OpenAI 호환({self.model})"

    def _messages(self, system: str, messages: list) -> list:
        return [{"role": "system", "content": system}, *messages]

    def chat(self, system: str, messages: list) -> tuple[str, bool]:
        resp = requests.post(f"{self.url}/chat/completions", json={
            "model": self.model,
            "messages": self._messages(system, messages),
            "max_tokens": config.CHAT_MAX_TOKENS,
            "stream": True,
        }, headers={"Authorization": f"Bearer {self.api_key}"},
            stream=True, timeout=300)
        resp.raise_for_status()
        parts, refused = [], False
        for line in resp.iter_lines():
            if not line or not line.startswith(b"data: "):
                continue
            payload = line[len(b"data: "):]
            if payload == b"[DONE]":
                break
            chunk = json.loads(payload)
            choice = (chunk.get("choices") or [{}])[0]
            if choice.get("finish_reason") == "content_filter":
                refused = True
            piece = choice.get("delta", {}).get("content") or ""
            if piece:
                print(piece, end="", flush=True)
                parts.append(piece)
        print()
        text = "".join(parts)
        return text, refused or not text.strip()

    def extract_json(self, system: str, prompt: str, schema: dict) -> str | None:
        resp = requests.post(f"{self.url}/chat/completions", json={
            "model": self.model,
            "messages": self._messages(system, [{"role": "user", "content": prompt}]),
            "max_tokens": config.EXTRACT_MAX_TOKENS,
        }, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=300)
        resp.raise_for_status()
        choice = (resp.json().get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        return _strip_fence(text) or None


class OllamaProvider:
    """로컬 Ollama. 완전 무료·오프라인이지만 대화 품질은 API 모델보다 떨어진다."""

    name = "Ollama(로컬)"

    def __init__(self):
        self.url = config.OLLAMA_URL.rstrip("/")
        self.model = config.OLLAMA_MODEL
        self.name = f"Ollama(로컬, {self.model})"

    def available(self) -> bool:
        try:
            requests.get(f"{self.url}/api/tags", timeout=2)
            return True
        except requests.RequestException:
            return False

    def chat(self, system: str, messages: list) -> tuple[str, bool]:
        resp = requests.post(f"{self.url}/api/chat", json={
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": True,
        }, stream=True, timeout=300)
        resp.raise_for_status()
        parts = []
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                print(piece, end="", flush=True)
                parts.append(piece)
            if chunk.get("done"):
                break
        print()
        return "".join(parts), False

    def extract_json(self, system: str, prompt: str, schema: dict) -> str | None:
        resp = requests.post(f"{self.url}/api/chat", json={
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
        }, timeout=300)
        resp.raise_for_status()
        return _strip_fence(resp.json().get("message", {}).get("content", "")) or None


def make_provider():
    """환경변수로 백엔드 선택. COMPANION_PROVIDER 우선, 없으면 가용한 것 자동 선택."""
    choice = os.environ.get("COMPANION_PROVIDER", "").lower()
    if choice == "anthropic":
        return AnthropicProvider()
    if choice == "gemini":
        return GeminiProvider()
    if choice in ("openrouter", "openai"):
        return OpenAICompatProvider()
    if choice == "ollama":
        return OllamaProvider()
    if choice:
        raise SystemExit(
            f"알 수 없는 COMPANION_PROVIDER: {choice} (anthropic | gemini | openrouter | ollama)"
        )
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if os.environ.get("GEMINI_API_KEY"):
        return GeminiProvider()
    if os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_COMPAT_API_KEY"):
        return OpenAICompatProvider()
    ollama = OllamaProvider()
    if ollama.available():
        return ollama
    raise SystemExit(
        "사용할 수 있는 대화 백엔드가 없습니다. 무료로 쓰려면 하나를 준비하세요.\n"
        "  1) OpenRouter 무료 키(무검열 모델 포함): https://openrouter.ai/keys 발급 후\n"
        "     export OPENROUTER_API_KEY=...\n"
        "  2) Gemini 무료 API 키: https://aistudio.google.com 에서 발급 후\n"
        "     export GEMINI_API_KEY=...\n"
        f"  3) 로컬 Ollama: https://ollama.com 설치 후  ollama pull {config.OLLAMA_MODEL}\n"
        "Claude API(유료)를 쓰려면 export ANTHROPIC_API_KEY=..."
    )
